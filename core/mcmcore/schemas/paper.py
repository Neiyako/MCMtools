"""Artifact schemas: Figure, Table, Citation, Reference, Paper.

The organizing idea: a figure or table is a GENERATED ARTIFACT bound to
ResultAtoms, never a screenshot pasted into the document. The corpus shows why
this matters -- 74% of embedded images are under 500px wide, and only 37% of
figures are ever cross-referenced in the text.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import Field

from .common import (
    ArtifactStatus,
    CitationStyle,
    Identified,
    MCMBase,
    SectionKind,
)


class ArtifactBinding(MCMBase):
    """Binds one role in an artifact to one ResultAtom.

    Binding (rather than embedding values) is what makes STALE detection
    possible: when the atom changes, every artifact bound to it is stale.
    """

    atom_id: str = Field(..., min_length=1)
    role: str = Field(
        default="input",
        description="x | y | series | label | cell | error | matrix | input.",
    )
    format: Optional[str] = Field(
        default=None, description="Per-cell override, e.g. '%.4f'."
    )
    # ---- 序列绑定 ----
    # ResultAtom 是**标量**：它是"实验跑完得到的一个数"。
    # 但真实论文里的图绝大多数是**曲线**：400 天的观测 vs 预测、
    # 迭代收敛轨迹、残差序列。这些数据不在原子里，在运行产出的 CSV 里。
    #
    # 所以绑定要能指到"某次运行产出的某个文件的某一列"。
    # 只指原子的话，pred_vs_actual 这种图就只能拿到两个标量，
    # 画出来是"一个点"，而用户以为自己画的是拟合效果 —— 这是错图。
    source: str = Field(
        default="atom",
        description="atom | artifact。artifact 表示绑到运行产出文件的某一列。",
    )
    artifact_path: Optional[str] = Field(
        default=None,
        description="相对运行目录的产物路径，如 trajectory.csv。",
    )
    column: Optional[str] = Field(
        default=None, description="取该文件的哪一列。",
    )
    run_id: Optional[str] = Field(
        default=None, description="指定某次运行；留空则用该实验最近一次成功的运行。",
    )
    # ---- 字面数据 ----
    # 有些图的内容是**人写的**，不是从数据算的：流程图的节点和连线、
    # 结构图的模块划分。这类内容没有"列"可绑，只能直接存。
    # 存进绑定里而不是另开一个字段，是为了让一张图的所有输入
    # 都在这一个地方看得全 —— 图和数据分两处存最容易失配。
    value: Optional[object] = Field(
        default=None,
        description="字面数据（结构图的节点表等）。与 source=literal 搭配使用。",
    )

    def is_series(self) -> bool:
        """是不是"从文件取一列"的序列绑定。"""
        return self.source == "artifact"

    def is_literal(self) -> bool:
        """是不是直接写死在绑定里的字面数据（结构图用）。"""
        return self.source == "literal"


class Figure(Identified):
    """A generated visual artifact."""

    template_id: str = Field(
        default="fig.sensitivity_line",
        description="From the Figure Template Registry.",
    )
    experiment_id: Optional[str] = None
    model_id: Optional[str] = None
    bindings: List[ArtifactBinding] = Field(default_factory=list)
    file: Optional[str] = Field(default=None, description="Relative path to the output.")
    format: str = Field(default="pdf", description="pdf (vector) | png (raster fallback).")
    width_in: float = 6.0
    dpi: Optional[int] = None
    caption: Optional[str] = None
    caption_source: str = Field(default="human", description="human | template_suggested")
    label: Optional[str] = Field(default=None, description="LaTeX label, e.g. 'fig:cost_sens'.")
    referenced_in: List[str] = Field(
        default_factory=list,
        description=(
            "Section ids where this figure is cited. Empty is a real defect "
            "class but only a WARNING: 63% of Outstanding figures are uncited."
        ),
    )
    status: ArtifactStatus = ArtifactStatus.MISSING
    generated_at: Optional[str] = None

    def is_stale_if(self, changed_atom_ids: List[str]) -> bool:
        bound = {b.atom_id for b in self.bindings}
        return bool(bound & set(changed_atom_ids))


class Table(Identified):
    """A generated tabular artifact, bound cell-by-cell to ResultAtoms."""

    template_id: str = Field(default="tab.metric_comparison")
    experiment_id: Optional[str] = None
    model_id: Optional[str] = None
    columns: List[Dict[str, object]] = Field(
        default_factory=list,
        description="[{header, atom_id?, literal?, format?}]",
    )
    rows: List[Dict[str, object]] = Field(
        default_factory=list,
        description="[{literal: 'Lasso', atom_ids: [...]}] or [{cell_atoms: {...}}]",
    )
    bindings: List[ArtifactBinding] = Field(default_factory=list)
    file: Optional[str] = None
    caption: Optional[str] = None
    label: Optional[str] = None
    referenced_in: List[str] = Field(default_factory=list)
    status: ArtifactStatus = ArtifactStatus.MISSING
    generated_at: Optional[str] = None

    def bound_atom_ids(self) -> List[str]:
        ids = [b.atom_id for b in self.bindings]
        for col in self.columns:
            if col.get("atom_id"):
                ids.append(str(col["atom_id"]))
        for row in self.rows:
            for aid in row.get("atom_ids", []) or []:
                ids.append(str(aid))
        return ids


class Reference(MCMBase):
    """A bibliography entry.

    COMAP requires AI tools to be listed in References, so ``ai_generated``
    exists to make that checkable.
    """

    key: str = Field(..., min_length=1, description="BibTeX key.")
    type: str = Field(default="article")
    title: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    bibtex: Optional[str] = None
    ai_generated: bool = Field(
        default=False,
        description="COMAP: AI tools must be cited inline AND listed in References.",
    )
    url: Optional[str] = None


class Citation(MCMBase):
    """An in-text citation marker.

    References are 100% cited in text (707/707 in a 60-paper sample), which is
    why citation integrity is fully enforceable -- unlike figures (37%) and
    tables (33%).
    """

    key: str = Field(..., min_length=1)
    section_id: Optional[str] = None
    context: Optional[str] = None
    style: CitationStyle = CitationStyle.NUMERIC


class PaperSection(Identified):
    """One section of the paper."""

    kind: SectionKind = SectionKind.OTHER
    title: str = Field(..., min_length=1)
    level: int = Field(default=1, ge=1, le=3)
    order: int = 0
    template_ref: Optional[str] = None
    enabled: bool = True
    body: Optional[str] = Field(
        default=None, description="Prose with result references, e.g. \\numRES0142{}."
    )
    generated: bool = Field(
        default=False,
        description="True for auto-generated sections (notations, references, TOC).",
    )


class AIToolEntry(MCMBase):
    """One AI tool use, for the COMAP-mandated "Report on Use of AI"."""

    tool: str = Field(..., min_length=1)
    version: Optional[str] = None
    purpose: str = Field(
        default="development",
        description="development | template_generation | code_generation | testing "
        "| debugging | documentation | polishing",
    )
    phase: str = Field(
        default="pre_competition",
        description="pre_competition | competition. Competition use REQUIRES disclosure.",
    )
    queries: List[Dict[str, str]] = Field(default_factory=list)
    in_report: bool = Field(
        default=False, description="Did any AI output land inside the 25-page report?"
    )


class AIUsage(MCMBase):
    """The COMAP AI-compliance record.

    Policy: disclose the tool, cite it in References, and append a page-limit
    EXEMPT "Report on Use of AI" section after the 25-page solution.
    """

    ai_used: bool = False
    entries: List[AIToolEntry] = Field(default_factory=list)

    def competition_use(self) -> List[AIToolEntry]:
        return [e for e in self.entries if e.phase == "competition"]

    def requires_disclosure(self) -> bool:
        return self.ai_used or bool(self.entries)


class LatexConfig(MCMBase):
    documentclass: str = "[12pt]{article}"
    packages: List[str] = Field(
        default_factory=lambda: [
            "geometry",
            "newtxtext",
            "amsmath",
            "amssymb",
            "amsthm",
            "newtxmath",
            "graphicx",
            "fancyhdr",
        ]
    )
    engine: str = Field(default="pdflatex", description="pdflatex | xelatex")
    bib: Optional[str] = None
    toc: bool = Field(
        default=True, description="Universal in 2022-2025 (100% of 86 papers)."
    )
    page_limit: int = Field(
        default=25,
        description="HARD. 72.1% of 2022-2025 papers are exactly 25 pages (IQR [25,25]).",
    )


class BuildState(MCMBase):
    last_built: Optional[str] = None
    pdf_path: Optional[str] = None
    page_count: Optional[int] = None

    def pages_remaining(self, limit: int) -> Optional[int]:
        if self.page_count is None:
            return None
        return limit - self.page_count


class SummarySheet(MCMBase):
    """Page 1 is the COMAP FORM, not a section.

    76.6% of papers carry it. The official template defines the layout:
    \\Problem, \\Team, a 3-column header table, and \\rhead{Page \\thepage}.
    """

    problem_letter: Optional[str] = Field(default=None, description="A-F.")
    team_control_number: Optional[str] = None
    body: Optional[str] = None
    key_words: List[str] = Field(default_factory=list)

    def is_placeholder(self) -> bool:
        """Detect unfilled summary-sheet fields.

        A valid problem letter is a single character A-F, so the letter is only
        a placeholder when it is ABSENT. The team control number is the real
        signal: the shipped template defaults to 1111111, and COMAP numbers are
        all-digits and not a repeated single digit.
        """
        letter = (self.problem_letter or "").strip().upper()
        num = (self.team_control_number or "").strip()

        if not letter or letter not in set("ABCDEF"):
            return True
        if not num or num in {"1111111", "0000000"}:
            return True
        if not num.isdigit():
            return True
        # A single repeated digit is filler, never a real control number.
        if len(set(num)) == 1:
            return True
        return False


class Paper(MCMBase):
    """The paper record: the template/content boundary made explicit."""

    paper_id: str = Field(default="PAPER-001")
    problem_id: Optional[str] = None
    locked: bool = False
    summary: SummarySheet = Field(default_factory=SummarySheet)
    sections: List[PaperSection] = Field(default_factory=list)
    latex: LatexConfig = Field(default_factory=LatexConfig)
    build: BuildState = Field(default_factory=BuildState)
    ai_usage: AIUsage = Field(default_factory=AIUsage)

    def ordered_sections(self) -> List[PaperSection]:
        return sorted(self.sections, key=lambda s: (s.order, s.id))

    def enabled_sections(self) -> List[PaperSection]:
        return [s for s in self.ordered_sections() if s.enabled]

    def section_ids(self) -> List[str]:
        return [s.id for s in self.sections]

    def find_section(self, section_id: str) -> Optional[PaperSection]:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None
