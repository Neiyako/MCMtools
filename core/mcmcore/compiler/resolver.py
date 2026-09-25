"""Stage 1 of the paper compiler: resolve the object graph into a render context.

Everything the renderer needs, gathered and cross-checked once. Doing this as a
separate stage means a broken reference is reported BEFORE LaTeX is invoked,
with a message that names the object, rather than as a cryptic TeX error.

Corpus grounding for the model-name macros: papers reference models by short
name inside prose ("Based on these two models (TCM & RCM) ...", "substituting
the results of Model I into Model II"), so model names and acronyms must be
macros too -- renaming a model in `model.yaml` must update every mention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..mathstore import MathContent
from ..schemas import (
    AIUsage,
    Figure,
    Paper,
    PaperSection,
    Reference,
    ResultAtom,
    SectionKind,
    Symbol,
    Table,
)
from .numbers import NumberMacros, macro_name


@dataclass
class ResolvedFigure:
    """A figure ready to be emitted, with its LaTeX label."""

    id: str
    label: str
    caption: str
    file: Optional[str]
    template_id: str
    atom_ids: List[str] = field(default_factory=list)
    width: float = 0.8  # fraction of \linewidth
    available: bool = False  # True once a real file is present in the build


@dataclass
class ResolvedTable:
    id: str
    label: str
    caption: str
    latex_path: Optional[str]
    template_id: str
    atom_ids: List[str] = field(default_factory=list)


@dataclass
class ResolvedContext:
    """Everything the renderer and the auditor need, resolved once."""

    # 数学内容（符号、公式、假设）现在是项目级的，不再按模型分组。
    math: MathContent = field(default_factory=MathContent)
    sections: List[PaperSection] = field(default_factory=list)
    atoms: List[ResultAtom] = field(default_factory=list)
    figures: List[ResolvedFigure] = field(default_factory=list)
    tables: List[ResolvedTable] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    ai_usage: AIUsage = field(default_factory=AIUsage)
    macros: NumberMacros = field(default_factory=NumberMacros)

    # diagnostics gathered during resolution
    problems: List[Tuple[str, str]] = field(default_factory=list)  # (code, message)

    def atom_by_id(self, atom_id: str) -> Optional[ResultAtom]:
        for a in self.atoms:
            if a.atom_id == atom_id:
                return a
        return None

    def figure_by_id(self, fig_id: str) -> Optional[ResolvedFigure]:
        for f in self.figures:
            if f.id == fig_id:
                return f
        return None

    def table_by_id(self, tab_id: str) -> Optional[ResolvedTable]:
        for t in self.tables:
            if t.id == tab_id:
                return t
        return None


def _slug(text: str) -> str:
    """Make a LaTeX-label-safe slug."""
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in "-_ ":
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "x"


def resolve(
    math: MathContent,
    sections: List[PaperSection],
    atoms: List[ResultAtom],
    figures: List[Figure],
    tables: List[Table],
    references: List[Reference],
    paper: Paper,
) -> ResolvedContext:
    """Build the render context and collect resolution problems.

    ``sections`` is a convenience for callers that already hold a section list.
    When it is empty, the Paper's own sections are used: passing ``paper`` with
    populated sections and an empty ``sections`` argument must not silently
    produce a document with no sections (and a spurious AI-disclosure error).
    """
    if not sections:
        sections = list(paper.sections)
    ctx = ResolvedContext(
        math=math,
        sections=sorted(sections, key=lambda s: (s.order, s.id)),
        atoms=list(atoms),
        references=list(references),
        ai_usage=paper.ai_usage,
        macros=NumberMacros().add_all(list(atoms)),
    )

    atom_ids = {a.atom_id for a in atoms}

    # -- figures -----------------------------------------------------------
    for f in figures:
        bound = [b.atom_id for b in f.bindings]
        for aid in bound:
            if aid not in atom_ids:
                ctx.problems.append((
                    "FIGURE_DANGLING_ATOM",
                    f"Figure {f.id} binds to unknown result atom '{aid}'.",
                ))
        ctx.figures.append(
            ResolvedFigure(
                id=f.id,
                label=f.label or f"fig:{_slug(f.id)}",
                caption=f.caption or "",
                file=f.file,
                template_id=f.template_id,
                atom_ids=bound,
                width=0.8,
            )
        )

    # -- tables ------------------------------------------------------------
    for t in tables:
        bound = t.bound_atom_ids()
        for aid in bound:
            if aid not in atom_ids:
                ctx.problems.append((
                    "TABLE_DANGLING_ATOM",
                    f"Table {t.id} binds to unknown result atom '{aid}'.",
                ))
        ctx.tables.append(
            ResolvedTable(
                id=t.id,
                label=t.label or f"tab:{_slug(t.id)}",
                caption=t.caption or "",
                latex_path=t.file or f"tables/{t.id}.tex",
                template_id=t.template_id,
                atom_ids=bound,
            )
        )

    # -- citation keys -----------------------------------------------------
    ref_keys = {r.key for r in references}
    for s in ctx.sections:
        if not s.body:
            continue
        for key in _extract_cite_keys(s.body):
            if key not in ref_keys:
                ctx.problems.append((
                    "XREF_BROKEN_CITATION",
                    f"Section '{s.id}' cites '{key}', which is not in references.",
                ))

    # -- figure/table references ------------------------------------------
    all_labels = {f.label for f in ctx.figures} | {t.label for t in ctx.tables}
    for s in ctx.sections:
        if not s.body:
            continue
        for ref in _extract_ref_keys(s.body):
            if ref not in all_labels and not ref.startswith(("sec:", "eq:")):
                ctx.problems.append((
                    "XREF_BROKEN",
                    f"Section '{s.id}' references '{ref}', which is not a known "
                    "figure or table label.",
                ))

    # -- AI compliance cross-check ----------------------------------------
    if paper.ai_usage.requires_disclosure():
        if not any(
            s.kind == SectionKind.REPORT_ON_AI and s.enabled for s in ctx.sections
        ):
            ctx.problems.append((
                "AI_USE_UNDISCLOSED",
                "AI usage is recorded but no enabled 'Report on Use of AI' "
                "section exists. COMAP requires it after the solution.",
            ))

    return ctx


def _extract_cite_keys(body: str) -> List[str]:
    import re

    keys: List[str] = []
    for m in re.finditer(r"\\cite[a-z]*\{([^}]*)\}", body):
        keys.extend(k.strip() for k in m.group(1).split(",") if k.strip())
    return keys


def _extract_ref_keys(body: str) -> List[str]:
    import re

    keys: List[str] = []
    for m in re.finditer(r"\\(?:ref|eqref|autoref)\{([^}]*)\}", body):
        keys.extend(k.strip() for k in m.group(1).split(",") if k.strip())
    return keys


# --------------------------------------------------------------------------
# Model name macros
# --------------------------------------------------------------------------


def model_macros(sections: List[PaperSection]) -> Dict[str, str]:
    """按「模型章节」生成 ``\\modelI`` 这类宏，让改名能一处改、处处生效。

    原来这是按 Model 对象生成的。拆掉模型层之后改为**按章节**：
    论文里真正的"模型一/模型二"就是那些 kind=model 的章节标题。
    这反而更准 —— 语料里 86% 的论文会给模型起名，而起名的位置
    就是章节标题。
    """
    macros: Dict[str, str] = {}
    model_sections = [s for s in sections if s.kind == SectionKind.MODEL]
    for i, sec in enumerate(model_sections, start=1):
        macro_name(f"M{i}")  # 复用数字拼写规则，保持一致
        stem = f"model{_roman(i)}"
        label = (sec.title or f"Model {_roman(i)}").strip()
        macros[stem] = label
        macros[f"{stem}Name"] = label
    return macros


def _roman(n: int) -> str:
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


# --------------------------------------------------------------------------
# Notations table (auto-generated from model-scoped symbols)
# --------------------------------------------------------------------------

NOTATION_DISCLAIMER = (
    "There are some variables that are not listed here and will be "
    "discussed in detail in each section."
)


def notations_rows(math: MathContent) -> List[Tuple[str, str, str]]:
    """由符号表生成符号表行。

    符号表是符号的**视图**，绝不手写 —— 手写必然与正文脱节。
    56% 的论文有符号表，且每一篇都声明它不穷尽。
    """
    rows: List[Tuple[str, str, str]] = []
    seen: Dict[str, str] = {}
    for s in math.symbols:
        if s.glyph in seen:
            # 同一个符号两种含义：标注出来而不是丢掉。审计会另外报错。
            note = f"{s.meaning}（另一处含义不同）"
            rows.append((_tex(s.glyph), note, s.unit or "/"))
            continue
        seen[s.glyph] = s.id
        rows.append((_tex(s.glyph), s.meaning, s.unit or "/"))
    return rows


def _tex(sym: str) -> str:
    """Wrap a symbol glyph so it renders as math."""
    stripped = sym.strip()
    if stripped.startswith("$") and stripped.endswith("$"):
        return stripped
    return f"${stripped}$"
