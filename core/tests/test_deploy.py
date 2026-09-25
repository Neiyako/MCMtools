"""部署自检。

"拷过去就能用"是个承诺，而它最容易在**拷贝过程**上破功，不是代码上。
我自己就踩过：rsync 排除规则写错，只拷过去 templates/paper，
74 个模板变 7 个 —— 服务照常启动、接口照常响应、**全程不报错**。
用户要到想画图时才发现少了一半模板。

所以自检必须能数出"少了多少"，而不只是"文件在不在"。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mcmcore.deploy import REQUIRED, TEMPLATE_KINDS, inspect

REPO = Path(__file__).resolve().parents[2]


def _make_deploy(tmp_path: Path, drop=(), mode: str = "copy") -> Path:
    """把仓库按需拷成一个"部署副本"，用来验证自检能不能发现问题。"""
    dest = tmp_path / "deploy"
    shutil.copytree(
        REPO, dest,
        ignore=shutil.ignore_patterns(
            "__pycache__", "node_modules", ".pytest_cache", "*.pyc"),
    )
    for rel in drop:
        p = dest / rel
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    return dest


class TestHealthyDeployment:
    def test_real_repo_passes(self) -> None:
        """当前仓库本身必须是一份可部署的目录。"""
        rep = inspect(REPO)
        assert rep.ok(), "本仓库没通过部署自检：\n" + "\n".join(
            f.line() for f in rep.failures)

    def test_finds_all_required_files(self) -> None:
        rep = inspect(REPO)
        names = {f.name for f in rep.findings}
        for _rel, desc in REQUIRED:
            assert desc in names

    def test_reports_template_count(self) -> None:
        """自检要数模板，而不是只看目录在不在。"""
        rep = inspect(REPO)
        detail = " ".join(f.detail for f in rep.findings)
        assert "个（" in detail, f"没有报告模板数量：{detail}"


class TestDetectsBrokenCopy:
    """这几条对应真实会发生的拷贝事故。"""

    def test_missing_template_section_fails(self, tmp_path) -> None:
        """漏拷 templates/figures —— 我真实踩过的那次。"""
        dest = _make_deploy(tmp_path, drop=["templates/figures"])
        rep = inspect(dest)
        assert not rep.ok()
        joined = " ".join(f"{f.name} {f.detail}" for f in rep.failures)
        assert "模板" in joined

    def test_empty_templates_dir_fails(self, tmp_path) -> None:
        dest = _make_deploy(tmp_path, drop=["templates"])
        rep = inspect(dest)
        assert not rep.ok()

    def test_missing_core_fails(self, tmp_path) -> None:
        dest = _make_deploy(tmp_path, drop=["core/mcmcore/api.py"])
        rep = inspect(dest)
        assert not rep.ok()

    def test_missing_web_fails(self, tmp_path) -> None:
        dest = _make_deploy(tmp_path, drop=["web/app.js"])
        rep = inspect(dest)
        assert not rep.ok()

    def test_lost_exec_permission_warns(self, tmp_path) -> None:
        """从压缩包解出来常丢执行权限。不是致命的，但要说。"""
        dest = _make_deploy(tmp_path)
        (dest / "start").chmod(0o644)
        rep = inspect(dest)
        joined = " ".join(f"{f.name} {f.detail}" for f in rep.warnings)
        assert "执行权限" in joined
        # 只是提示，不该判失败 —— start.sh 还能用
        assert rep.ok()


class TestExitCode:
    """脚本靠退出码判断，这个不能错。"""

    def test_deploy_command_exits_zero_on_healthy(self) -> None:
        r = subprocess.run(
            [sys.executable, str(REPO / "core" / "mcm"), "deploy"],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_broken_copy_exits_nonzero(self, tmp_path) -> None:
        dest = _make_deploy(tmp_path, drop=["templates/figures"])
        r = subprocess.run(
            [sys.executable, str(dest / "core" / "mcm"), "deploy"],
            capture_output=True, text=True)
        assert r.returncode != 0, "模板缺失时应该返回非零退出码"

    def test_doctor_deploy_is_an_alias(self) -> None:
        r = subprocess.run(
            [sys.executable, str(REPO / "core" / "mcm"), "doctor", "--deploy"],
            capture_output=True, text=True)
        assert r.returncode == 0
        assert "部署自检" in r.stdout


class TestTemplateSectionList:
    def test_all_kinds_exist_in_repo(self) -> None:
        reg = REPO / "templates"
        for kind in TEMPLATE_KINDS:
            if kind == "code":
                continue      # 代码模板是可选分区
            assert (reg / kind).is_dir(), f"templates/{kind} 不存在"
