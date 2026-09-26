"""启动器脚本的结构约束。

这里盯的是一个**真的漏过去过**的 bug：`build-app.sh` 生成的启动脚本里，
把 `export MCMTOOLS_HOME=...` 那一组烤在了读取这些变量的逻辑**后面**。

配着脚本开头的 `set -u`，第一行读 `$MCMTOOLS_HOME` 就以
`unbound variable` 退出了 —— 也就是**拷贝走的 app 双击完全没反应**。

它之所以能躲过所有测试：构建是在仓库原地做的，启动器优先用仓库那份
代码，本机跑起来一切正常；只有真正把 app 单独拷到别处才会踩到，
而 Finder 双击又会把 stderr 吞掉，连报错都看不见。

所以这里不测"能不能启动"（那要一个完整的 GUI 环境），
只测生成出来的脚本**自己站得住**：顺序对、能过 `bash -n`、
并且真的能在不给任何 MCMTOOLS_* 变量的情况下跑到 exec。

需要 `bash` 和已构建的 `MCMtools.app`；两者缺一就跳过。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "MCMtools.app" / "Contents" / "MacOS" / "MCMtools"
BUILD_SCRIPT = REPO / "build-app.sh"


def _launcher_text() -> str:
    if not LAUNCHER.is_file():
        pytest.skip("还没有构建 MCMtools.app（先跑 ./build-app.sh）")
    return LAUNCHER.read_text(encoding="utf-8")


class TestLauncherScript:
    def test_uses_strict_mode(self) -> None:
        """set -u 正是让顺序错误变成致命错误的原因 —— 它必须在。"""
        text = _launcher_text()
        assert "set -uo pipefail" in text

    def test_exports_come_before_they_are_read(self) -> None:
        """烘进去的 export 必须排在读取它们的逻辑之前。

        这条就是那个 bug 的直接回归：`set -u` 下，先读后写 = 立即退出。
        """
        text = _launcher_text()
        first_read = text.find("$MCMTOOLS_HOME")
        first_export = text.find("export MCMTOOLS_HOME=")
        assert first_export != -1, "启动器没有烘入 MCMTOOLS_HOME"
        assert first_read != -1, "启动器没有用 MCMTOOLS_HOME"
        assert first_export < first_read, (
            f"export MCMTOOLS_HOME（第 {text[:first_export].count(chr(10))+1} 行）"
            f" 排在第一次读取（第 {text[:first_read].count(chr(10))+1} 行）之后；"
            "set -u 下会在读到时立刻 unbound variable 退出"
        )

    def test_every_variable_it_reads_is_defined_first(self) -> None:
        """凡是读到的 MCMTOOLS_* 都得先有定义。

        比上一条更严：不只 MCMTOOLS_HOME，任何一个都可能成为那个
        "拷走就崩"的变量。
        """
        text = _launcher_text()
        # 只看烤进去的那一段（exec 之前），避免把引号里的字符串算进来
        head = text.split('exec "$PY3"', 1)[0]
        read = set(re.findall(r"\$\{?(MCMTOOLS_[A-Z_]+)", head))
        defined = set(re.findall(r"^export (MCMTOOLS_[A-Z_]+)=", head, re.M))
        # 赋值给本地变量的也算已定义
        defined |= set(re.findall(r"^(MCMTOOLS_[A-Z_]+)=", head, re.M))
        missing = sorted(read - defined)
        assert not missing, f"这些变量读之前没有定义：{missing}"

    def test_parses(self) -> None:
        text = _launcher_text()
        r = subprocess.run(["bash", "-n"], input=text, text=True,
                           capture_output=True)
        assert r.returncode == 0, r.stderr

    def test_survives_a_clean_environment(self) -> None:
        """不给任何 MCMTOOLS_* 变量也能跑过路径解析那一段。

        做法：把 exec 那一行换成打印 MCM_CORE，然后 `env -u` 掉所有
        相关变量跑一遍。这能在没有 GUI 的情况下复现"双击"的变量环境。
        """
        text = _launcher_text()
        # 把最后的 exec 换成回显，这样脚本不会真的去起服务
        stub = text.split('exec "$PY3"', 1)[0] + 'printf "MCM_CORE=%s\\n" "$MCM_CORE"\n'
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()),
        }
        r = subprocess.run(["bash", "-c", stub], text=True, capture_output=True,
                           env=env, timeout=60)
        assert r.returncode == 0, (
            f"干净环境下启动器失败了：\nstderr={r.stderr.strip()}\n"
            "（'unbound variable' 就是 export 顺序错了）"
        )
        assert "MCM_CORE=" in r.stdout
        core = r.stdout.strip().split("MCM_CORE=", 1)[1]
        # MCM_CORE 必须是一个真实存在的 core 目录（仓库的或包内的）
        assert (Path(core) / "mcmcore").is_dir(), f"MCM_CORE 指向了不存在的目录：{core}"

    def test_core_choice_has_a_fallback(self) -> None:
        """仓库不在时必须退回包内副本 —— 这正是"拷走能用"的那一半。"""
        text = _launcher_text()
        assert "MCMTOOLS_BUNDLE_CORE" in text
        # if 仓库在 / else 用包内，这个 else 分支是自包含的关键
        m = re.search(r'if \[ -d "\$MCMTOOLS_HOME/core/mcmcore" \]; then(.*?)fi',
                      text, re.S)
        assert m, "没有找到仓库/包内的二选一逻辑"
        assert "MCMTOOLS_BUNDLE_CORE" in m.group(1), \
            "仓库不在时没有回退到包内 core"


class TestBuildScriptEmitsInOrder:
    """直接查 build-app.sh 里那两段的先后，不必等构建。"""

    def test_build_script_emits_exports_before_reads(self) -> None:
        text = BUILD_SCRIPT.read_text(encoding="utf-8")
        emit = text.find("printf 'export MCMTOOLS_HOME=")
        # 读取逻辑现在放在 LAUNCHER_BODY heredoc 里
        read = text.find("LAUNCHER_BODY")
        assert emit != -1 and read != -1
        assert emit < read, (
            "build-app.sh 里烤 export 的那段排在 LAUNCHER_BODY 之后 —— "
            "生成的脚本会先读后写，set -u 下直接退出"
        )

    def test_build_script_declares_bundle_dirs(self) -> None:
        text = BUILD_SCRIPT.read_text(encoding="utf-8")
        for var in ("MCMTOOLS_BUNDLE_CORE", "MCMTOOLS_BUNDLE_TEMPLATES",
                    "MCMTOOLS_BUNDLE_WEB"):
            assert var in text, f"build-app.sh 没有烤入 {var}"
