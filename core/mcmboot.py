#!/usr/bin/env python3
"""启动引导：挑一个能跑的 Python，然后用它启动 MCMtools。

这个模块存在的唯一理由，是绕开两个具体的坑：

1. **macOS TCC**。当 MCMtools 位于 ~/Desktop、~/Documents、~/Downloads 时，
   系统沙箱会拒绝 `python3 /该目录/下的脚本`，报
   "Operation not permitted" —— 即使 .app 本身已经获准运行。
   但 `python3 -c "<源码>"` 是允许的：被拦的是"打开受保护目录里的文件"这个
   动作，而不是读它的内容。

   所以 .app 的启动器会把 **本文件的源码** 内联进 `-c` 参数
   （build-app.sh 在构建时把它嵌进去）。这样脚本永远不需要被当作文件打开。

2. **版本 ≠ 可用性**。曾经按版本号挑解释器，选中了较新的 Homebrew Python
   3.13 —— 它恰好缺 matplotlib；而系统自带的 3.9 依赖齐全。自动安装又因为
   TLS 证书错误失败，于是整个启动挂在一个本来正常的解释器旁边。
   所以现在**逐个探测候选解释器能不能真的 import 依赖**。

本模块只用标准库，因此任何 Python 3 都能执行它。
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

MIN_VERSION = (3, 9)

# 必须能 import 的核心依赖（import 名；pip 名可能不同）。
REQUIRED = ("pydantic", "yaml", "numpy", "matplotlib")


def _probe(exe: str) -> Optional[Tuple[int, int, bool]]:
    """返回 (主版本, 次版本, 依赖是否齐全)；探测不了返回 None。"""
    code = (
        "import sys, importlib.util\n"
        f"names = {REQUIRED!r}\n"
        "ok = all(importlib.util.find_spec(n) is not None for n in names)\n"
        "print(sys.version_info[0], sys.version_info[1], int(ok))\n"
    )
    try:
        out = subprocess.run(
            [exe, "-c", code],
            capture_output=True, text=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if out.returncode != 0:
            return None
        major, minor, ok = out.stdout.split()
        return (int(major), int(minor), ok == "1")
    except Exception:
        return None


def _candidates() -> List[str]:
    """本机上所有可能的 Python 3 可执行文件。"""
    if platform.system() == "Windows":
        return [f for f in (shutil.which(n) for n in ("py", "python3", "python")) if f]

    out: List[str] = []
    for p in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"):
        if os.access(p, os.X_OK):
            out.append(p)
    for name in ("python3.13", "python3.12", "python3.11", "python3.10",
                 "python3.9", "python3"):
        w = shutil.which(name)
        if w:
            out.append(w)
    seen, uniq = set(), []
    for p in out:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def choose(verbose: bool = False) -> Optional[str]:
    """挑出最能用的解释器：优先依赖齐全的，并列时取版本高的。"""
    complete: List[Tuple[str, Tuple[int, int]]] = []
    partial: List[Tuple[str, Tuple[int, int]]] = []

    for exe in _candidates():
        info = _probe(exe)
        if info is None:
            continue
        major, minor, ok = info
        if (major, minor) < MIN_VERSION:
            if verbose:
                print(f"  跳过 {exe}：Python {major}.{minor} 低于最低要求")
            continue
        (complete if ok else partial).append((exe, (major, minor)))
        if verbose:
            print(f"  {exe}：Python {major}.{minor}，依赖{'齐全' if ok else '不全'}")

    pool = complete or partial
    if not pool:
        return None
    pool.sort(key=lambda t: t[1], reverse=True)
    return pool[0][0]


def _launch_code() -> str:
    """在选中的解释器里真正启动 MCMtools 的那段代码。"""
    return (
        "import sys;sys.path.insert(0,sys.argv[1]);"
        "from mcmcore.launcher import main;"
        "raise SystemExit(main(sys.argv[2:]))"
    )


def main(argv: Optional[List[str]] = None) -> int:
    """入口。两种调用形态都要成立：

        python3 core/mcmboot.py [--check]            脚本形式：argv[0] 是脚本路径
        python3 -c "<源码>" <core> <项目> [参数]      -c 形式：argv[0] 是 '-c'

    这两种形态的 argv 布局不一样，必须分开判断，不能统一按 argv[1:] 取：
    脚本形式下首个参数就是选项（如 --check），而 -c 形式下首个参数是 core 路径。
    早先"一律从 argv[1:] 取"的写法会把 --check 当成 core 路径。
    """
    if argv is None:
        argv = list(sys.argv[1:])

    # -c 形式：Python 把 -c 放进 argv[0]，其后才是真实参数。
    invoked_with_c = bool(sys.argv) and sys.argv[0] == "-c"

    if invoked_with_c:
        if not argv:
            return 3  # -c 形式必须给 core 路径
        # 绝对化：子进程会 cd 到项目目录，相对路径届时会解析到别处。
        return _run(os.path.abspath(argv[0]), argv[1:])

    # 脚本形式：core 就是本文件所在目录，参数原样透传。
    core = os.path.dirname(os.path.abspath(__file__))
    return _run(core, argv)


def _run(root: str, rest: List[str]) -> int:

    exe = choose(verbose=bool(os.environ.get("MCM_VERBOSE")))
    if exe is None:
        sys.stderr.write(
            f"MCMtools 需要 Python {MIN_VERSION[0]}.{MIN_VERSION[1]} 或更新版本。\n"
            "没有在本机找到可用的 Python。\n\n"
            "请先安装，然后重新运行：\n"
            "  macOS:   brew install python@3.12\n"
            "  Windows: https://www.python.org/downloads/\n"
            "  Linux:   sudo apt install python3 python3-pip\n"
        )
        return 3

    os.execv(exe, [exe, "-c", _launch_code(), root] + rest)
    return 0  # execv 不返回


if __name__ == "__main__":
    raise SystemExit(main())
