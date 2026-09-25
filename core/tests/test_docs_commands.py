"""文档和面板里提到的命令，必须真的存在。

这条规则的由来是一次真实的用户端阻断：面板的数据页写着
"用命令行导入：./core/mcm data add <文件>"，而这条命令**从来没有过**。
用户照着做只会得到 argparse 的 "invalid choice"，然后卡在那里。

写文档的人（包括我自己）很容易把"打算做的"当成"已经有的"。
所以让机器来核对。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from mcmcore.cli import build_parser

REPO = Path(__file__).resolve().parents[2]
MCM = REPO / "core" / "mcm"

# 只扫这些地方：都是直接展示给用户看的
SCAN = [
    REPO / "README.md",
    REPO / "docs" / "workbench-guide.md",
    REPO / "docs" / "project-layout.md",
    REPO / "docs" / "CONTRIBUTING.md",
    REPO / "web" / "app.js",
    REPO / "web" / "strings.js",
]

# 架构文档记录的是设计草案，其中标注"未实现"的不算承诺
SKIP_FILES = {REPO / "docs" / "mcmtools-architecture.md"}

# 已知的合法"非子命令"写法：mcm 本身、文件路径等
IGNORE = {"mcm"}


def _known_subcommands() -> set:
    """从真实的 parser 里取子命令，而不是维护一份可能过期的副本。"""
    p = build_parser()
    for action in p._actions:
        if hasattr(action, "choices") and action.choices:
            names = set(action.choices.keys())
            if "template" in names or "deploy" in names:
                return names
    return set()


def _scan_commands():
    """找出形如 `./core/mcm <词>` 的调用，返回 (文件, 完整匹配, 子命令)。"""
    pat = re.compile(r"\./core/mcm\s+([a-zA-Z][\w-]*)")
    hits = []
    for f in SCAN:
        if f in SKIP_FILES or not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        for m in pat.finditer(text):
            sub = m.group(1)
            if sub in IGNORE:
                continue
            # 取整行，供报错时定位
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            line = text[line_start:line_end if line_end != -1 else None]
            hits.append((f, sub, line.strip()))
    return hits


class TestDocumentedCommandsExist:
    def test_parser_has_subcommands(self) -> None:
        """自检：拿不到子命令列表的话，下面的测试会变成假绿。"""
        subs = _known_subcommands()
        assert "deploy" in subs
        assert "template" in subs
        assert len(subs) > 10

    def test_every_documented_command_exists(self) -> None:
        known = _known_subcommands()
        bad = []
        for f, sub, line in _scan_commands():
            if sub not in known:
                bad.append(f"{f.relative_to(REPO)}: ./core/mcm {sub}  ← {line}")
        assert not bad, (
            "文档/面板里提到了不存在的命令，用户照着做会失败：\n  "
            + "\n  ".join(bad)
        )

    def test_scan_actually_finds_something(self) -> None:
        """自检：正则写错的话会一条都扫不到，测试就成了摆设。"""
        assert len(_scan_commands()) >= 5

    def test_data_import_is_reachable(self) -> None:
        """数据集以前只能读不能写，提示还是个不存在的命令。"""
        from fastapi.testclient import TestClient

        import tempfile

        from mcmcore.api import create_app
        from mcmcore.store import Store

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "p"
            Store.init(root, "data-import")
            c = TestClient(create_app(root))

            csv = Path(td) / "d.csv"
            csv.write_text("a,b\n1,x\n2,y\n", encoding="utf-8")
            r = c.post("/api/datasets/import", json={"path": str(csv)})
            assert r.status_code == 200, r.text
            assert r.json()["rows"] == 2
            assert len(r.json()["columns"]) == 2
            assert len(c.get("/api/datasets").json()) == 1

    def test_data_import_rejects_missing_file(self) -> None:
        from fastapi.testclient import TestClient

        import tempfile

        from mcmcore.api import create_app
        from mcmcore.store import Store

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "p"
            Store.init(root, "data-missing")
            c = TestClient(create_app(root))
            r = c.post("/api/datasets/import", json={"path": str(Path(td) / "no.csv")})
            assert r.status_code == 404
            assert "找不到" in r.json()["detail"]

    def test_data_import_rejects_unsupported_type(self) -> None:
        from fastapi.testclient import TestClient

        import tempfile

        from mcmcore.api import create_app
        from mcmcore.store import Store

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "p"
            Store.init(root, "data-type")
            c = TestClient(create_app(root))
            f = Path(td) / "d.xlsx"
            f.write_bytes(b"PK\x03\x04")
            r = c.post("/api/datasets/import", json={"path": str(f)})
            assert r.status_code == 422
            assert "CSV" in r.json()["detail"]

    def test_data_import_bad_kind_rejected(self) -> None:
        from fastapi.testclient import TestClient

        import tempfile

        from mcmcore.api import create_app
        from mcmcore.store import Store

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "p"
            Store.init(root, "data-kind")
            c = TestClient(create_app(root))
            csv = Path(td) / "d.csv"
            csv.write_text("a\n1\n", encoding="utf-8")
            r = c.post("/api/datasets/import",
                       json={"path": str(csv), "kind": "随便编的"})
            assert r.status_code == 422
