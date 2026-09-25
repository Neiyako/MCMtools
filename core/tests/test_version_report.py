"""版本号与诊断报告。

这两样东西是给"以后打补丁的人"用的：
* 版本号回答"用户手上是哪一份"
* 诊断报告回答"他的现场是什么样"

没有它们，每次报 bug 都要来回问好几轮。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import mcmcore
from mcmcore import git_revision, version_string

REPO = Path(__file__).resolve().parents[2]
MCM = REPO / "core" / "mcm"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MCM), *args],
                          capture_output=True, text=True)


class TestVersion:
    def test_version_is_semver_like(self) -> None:
        parts = mcmcore.__version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts), mcmcore.__version__

    def test_version_string_contains_base(self) -> None:
        assert version_string(with_rev=False) == mcmcore.__version__

    def test_version_string_never_raises(self) -> None:
        """不在 git 仓库里也必须能拿到版本。"""
        assert version_string()
        assert isinstance(version_string(), str)

    def test_git_revision_degrades_gracefully(self) -> None:
        """没有 git / 不是仓库时返回 None，不抛异常。"""
        rev = git_revision()
        assert rev is None or isinstance(rev, str)

    def test_cli_version_flag(self) -> None:
        r = _run("--version")
        assert r.returncode == 0
        assert mcmcore.__version__ in r.stdout

    def test_cli_short_version_flag(self) -> None:
        r = _run("-V")
        assert r.returncode == 0
        assert "MCMtools" in r.stdout

    def test_version_flag_does_not_need_a_subcommand(self) -> None:
        """--version 不该要求合法子命令，否则报 bug 的人拿不到版本号。"""
        r = _run("--version")
        assert "invalid choice" not in (r.stdout + r.stderr)

    def test_api_reports_same_version(self) -> None:
        """API 里的版本不能是另一个写死的字面量。"""
        src = (REPO / "core" / "mcmcore" / "api.py").read_text()
        assert "version=version_string()" in src


class TestReport:
    def test_report_runs_without_project(self) -> None:
        r = _run("report")
        assert r.returncode == 0, r.stderr
        assert "诊断报告" in r.stdout

    def test_report_includes_version_and_env(self) -> None:
        r = _run("report")
        for needle in ("版本", "Python", "系统"):
            assert needle in r.stdout

    def test_report_includes_dependency_checks(self) -> None:
        r = _run("report")
        assert "依赖" in r.stdout

    def test_report_includes_deploy_checks(self) -> None:
        r = _run("report")
        assert "目录完整性" in r.stdout

    def test_report_with_project_shows_counts(self, tmp_path) -> None:
        from mcmcore.store import Store

        Store.init(tmp_path, "report-test")
        r = _run("report", "--project", str(tmp_path))
        assert r.returncode == 0, r.stderr
        assert "章节" in r.stdout
        assert "图" in r.stdout

    def test_report_does_not_leak_prose(self, tmp_path) -> None:
        """报告里只该有计数，不该有论文正文 —— 那是用户的私有内容。"""
        from mcmcore.store import Store

        st = Store.init(tmp_path, "leak-test")
        paper = st.load_paper()
        if paper.sections:
            paper.sections[0].body = "这是不该出现在报告里的正文内容"
            st.save_paper(paper)
        r = _run("report", "--project", str(tmp_path))
        assert "不该出现在报告里" not in r.stdout

    def test_report_can_write_to_file(self, tmp_path) -> None:
        out = tmp_path / "diag.txt"
        r = _run("report", "--out", str(out))
        assert r.returncode == 0
        assert out.is_file()
        assert "诊断报告" in out.read_text(encoding="utf-8")

    def test_report_bad_project_path_does_not_crash(self, tmp_path) -> None:
        """给一个不存在的目录也要出报告，而不是崩掉。"""
        r = _run("report", "--project", str(tmp_path / "nope"))
        assert r.returncode == 0
        assert "诊断报告" in r.stdout
