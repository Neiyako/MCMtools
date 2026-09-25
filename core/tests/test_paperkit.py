"""论文骨架：章节顺序、填空骨架、篇幅预算。

这个模块的承诺是"给你一张能直接填的卷子"，所以测试围绕四件事：
顺序有语料依据、骨架不覆盖已写内容、占位符能被查出来、篇幅建议存在。
"""

from __future__ import annotations

from typing import List

import pytest

from mcmcore.paperkit import (
    build_sections,
    load_bodies,
    load_spine,
    outline,
    placeholders_in,
    scaffold,
    section_budget,
    section_checklist,
)
from mcmcore.schemas import Paper, PaperSection, SectionKind


class TestSpine:
    def test_spine_is_ordered(self) -> None:
        spine = load_spine()
        assert spine, "章节顺序表不该为空"
        orders = [s["order"] for s in spine]
        assert orders == sorted(orders)

    def test_introduction_comes_first(self) -> None:
        """语料：Introduction 在 108/152 篇里排第一（71.1%）。"""
        first = load_spine()[0]
        assert first["kind"] == "introduction"

    def test_conclusion_precedes_references(self) -> None:
        """语料：这对关系在 15/15 篇里成立，是硬约束。"""
        kinds = [s["kind"] for s in load_spine()]
        assert kinds.index("conclusion") < kinds.index("references")

    def test_literature_review_is_never_templated(self) -> None:
        """Literature Review 在 415 篇里出现 0 次 —— 绝不能出现在骨架里。

        这是最容易犯的错：教科书写法里有"文献综述"，真实竞赛论文没有。
        """
        kinds = [s["kind"] for s in load_spine()]
        titles = " ".join(s.get("title", "") for s in load_spine()).lower()
        assert "literature" not in titles
        assert not any("literature" in k for k in kinds)


class TestBodies:
    def test_every_enabled_section_has_guidance(self) -> None:
        """每个默认启用的节都该有骨架，否则用户面对一个空白框。"""
        bodies = load_bodies()
        missing = [
            s["kind"] for s in load_spine()
            if s.get("enabled") and s["kind"] not in bodies
        ]
        # notations/references 靠自动生成，不要求手写骨架
        missing = [m for m in missing if m not in ("notations", "references",
                                                   "restatement", "appendix",
                                                   "report_on_ai")]
        assert not missing, f"这些节缺少填空骨架：{missing}"

    def test_sections_declare_budget(self) -> None:
        for kind in ("introduction", "model", "sensitivity"):
            assert section_budget(kind), f"{kind} 应有篇幅建议"

    def test_sections_declare_checklist(self) -> None:
        for kind in ("introduction", "assumptions", "model", "sensitivity"):
            assert section_checklist(kind), f"{kind} 应有自查项"

    def test_sensitivity_mentions_fixed_parameters(self) -> None:
        """审计的硬性检查：单因子分析必须说明其他参数不变。"""
        body = load_bodies()["sensitivity"]["body"]
        assert "固定" in body or "保持不变" in body

    def test_no_latex_broken_by_templating(self) -> None:
        """骨架里不能出现未转义的花括号 —— 那会让 LaTeX 编译直接失败。"""
        import re

        for kind, body in load_bodies().items():
            text = body["body"]
            # 占位符 {{x}} 先移除，剩下的裸 { } 必须成对且属于 LaTeX 命令
            stripped = re.sub(r"\{\{[a-zA-Z0-9_]+\}\}", "", text)
            # 允许 \{ \} 转义，以及 \begin{...} \end{...} \label{...} 这类
            opens = stripped.count("{") - stripped.count("\\{")
            closes = stripped.count("}") - stripped.count("\\}")
            assert opens == closes, (
                f"{kind} 的花括号不成对（{{={opens}, }}={closes}）—— "
                "LaTeX 会编译失败"
            )


class TestPlaceholders:
    def test_extracts_placeholder_names(self) -> None:
        assert placeholders_in("本文建立 {{model_name}}。") == ["model_name"]

    def test_empty_body_has_none(self) -> None:
        assert placeholders_in("") == []
        assert placeholders_in(None) == []

    def test_multiple_placeholders(self) -> None:
        got = placeholders_in("{{a}} 和 {{b}} 还有 {{a}}")
        assert got == ["a", "b", "a"]


class TestScaffold:
    def _paper(self) -> Paper:
        return Paper(paper_id="PAPER-001", problem_id="PROB-001")

    def test_adds_missing_sections(self) -> None:
        paper, report = scaffold(self._paper())
        assert report["added"], "空论文应当被补上章节"
        assert len(paper.sections) >= 8

    def test_does_not_overwrite_existing_body(self) -> None:
        """核心承诺：已经写的内容不能被生成的内容冲掉。"""
        paper = self._paper()
        paper.sections = [PaperSection(
            id="SEC-010", kind=SectionKind.INTRODUCTION, title="Introduction",
            level=1, order=10, enabled=True, body="我自己写的引言，别动它。",
        )]
        paper, _ = scaffold(paper)
        intro = [s for s in paper.sections if s.kind == SectionKind.INTRODUCTION][0]
        assert intro.body == "我自己写的引言，别动它。"

    def test_fills_only_empty_bodies(self) -> None:
        paper = self._paper()
        paper.sections = [
            PaperSection(id="SEC-010", kind=SectionKind.INTRODUCTION,
                         title="Introduction", level=1, order=10,
                         enabled=True, body="已有内容"),
            PaperSection(id="SEC-030", kind=SectionKind.ASSUMPTIONS,
                         title="Assumptions", level=1, order=30,
                         enabled=True, body="   "),
        ]
        paper, report = scaffold(paper)
        by_kind = {s.kind: s for s in paper.sections}
        assert by_kind[SectionKind.INTRODUCTION].body == "已有内容"
        assert "假设" in by_kind[SectionKind.ASSUMPTIONS].body
        assert "Assumptions" in report["filled"]

    def test_sections_stay_sorted(self) -> None:
        paper, _ = scaffold(self._paper())
        orders = [s.order for s in paper.sections]
        assert orders == sorted(orders)

    def test_report_counts_placeholders_and_budget(self) -> None:
        paper, report = scaffold(self._paper())
        assert report["total"] >= 8
        assert report["pending_placeholders"] > 0, "新骨架必然有待填占位符"
        assert 10 <= report["budget_pages"] <= 25, "篇幅建议应落在 COMAP 25 页上限内"

    def test_scaffold_is_idempotent(self) -> None:
        """跑两次不该重复加章节。"""
        paper, first = scaffold(self._paper())
        paper, second = scaffold(paper)
        assert second["added"] == []
        assert len(paper.sections) == first["total"]


class TestOutline:
    def test_outline_covers_all_sections(self) -> None:
        paper, _ = scaffold(Paper(paper_id="PAPER-001", problem_id="PROB-001"))
        rows = outline(paper)
        assert len(rows) == len(paper.sections)
        assert all("title" in r and "budget_pages" in r for r in rows)

    def test_outline_reports_placeholders_per_section(self) -> None:
        paper, _ = scaffold(Paper(paper_id="PAPER-001", problem_id="PROB-001"))
        rows = {r["kind"]: r for r in outline(paper)}
        assert rows["introduction"]["placeholders"], "引言应当有待填占位符"


class TestScaffoldHonesty:
    """scaffold 报告的"改了什么"必须是真的。

    否则用户会以为补了内容，实际什么都没发生 —— 比不报告更糟。
    """

    def test_sections_without_a_body_are_not_reported_as_filled(self) -> None:
        """附录、AI 报告这类节本来就没有骨架，不该报成"已填入"。"""
        paper, report = scaffold(Paper(paper_id="PAPER-001", problem_id="PROB-001"))
        assert "Appendix" not in report["filled"]
        assert "Restatement of the Problem" not in report["filled"]

    def test_reported_fills_actually_add_text(self) -> None:
        """凡是报告"填入了"的节，正文必须真的从空变成非空。"""
        paper = Paper(paper_id="PAPER-001", problem_id="PROB-001")
        paper, report = scaffold(paper)
        by_title = {s.title: s for s in paper.sections}
        for title in report["filled"]:
            body = by_title[title].body or ""
            assert body.strip(), f"报告说填了 {title}，但正文还是空的"
            assert "{{" in body or len(body) > 40, f"{title} 填进去的内容没有实质骨架"

    def test_second_run_reports_no_fills(self) -> None:
        """跑第二遍不该再报"填入了" —— 已经填过了。"""
        paper, _ = scaffold(Paper(paper_id="PAPER-001", problem_id="PROB-001"))
        paper, second = scaffold(paper)
        assert second["filled"] == []
