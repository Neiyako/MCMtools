"""Stage 2 of the paper compiler: generate figure and table artifacts.

Two rules from the corpus shape this module:

1. **A figure is generated, never pasted.** 74% of embedded images in the
   corpus are under 500px wide -- the signature of a screenshot. Binding every
   artifact to ResultAtoms means a figure cannot diverge from its numbers.

2. **A table is bound cell-by-cell.** The corpus's best tables carry captions
   that pin the condition ("mean and standard value at year 50 of 30
   independent runs") and print rejected candidates. Cells bound to atoms
   reproduce that automatically.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..schemas import Figure, Table
from .resolver import ResolvedContext, ResolvedFigure, ResolvedTable
from .numbers import NumberMacros


def _latex_escape(text: str) -> str:
    out = text
    for a, b in (("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                 ("_", r"\_"), ("{", r"\{"), ("}", r"\}")):
        out = out.replace(a, b)
    return out


def render_table_latex(table: Table, macros: NumberMacros) -> str:
    """Render one Table record to a standalone LaTeX fragment.

    Column cells and row cells may each reference an atom; the value is pulled
    from the macro table rather than re-typed.
    """
    lines: List[str] = [
        "% GENERATED from the Table record - do not edit by hand.",
        r"\begin{table}[htbp]",
        r"\centering",
    ]

    headers = [str(c.get("header", "")) for c in table.columns]
    if headers:
        spec = "l" * len(headers)
        lines.append(rf"\begin{{tabular}}{{{spec}}}")
        lines.append(r"\toprule")
        lines.append(" & ".join(_latex_escape(h) for h in headers) + r" \\")
        lines.append(r"\midrule")

        for row in table.rows:
            label = row.get("literal")
            cells: List[str] = []
            if label is not None:
                cells.append(_latex_escape(str(label)))

            # A row may bind a list of atoms (one per remaining column), or give
            # explicit per-column values via `cells`.
            explicit = row.get("cells")
            if isinstance(explicit, dict):
                for col in table.columns[1:]:
                    key = str(col.get("header", ""))
                    val = explicit.get(key)
                    if isinstance(val, dict) and val.get("atom_id"):
                        cells.append(f"\\num{_atom_stem(str(val['atom_id']))}{{}}")
                    elif val is not None:
                        cells.append(_latex_escape(str(val)))
                    else:
                        cells.append("--")
            else:
                atom_ids = row.get("atom_ids", []) or []
                fmt = row.get("format")
                for aid in atom_ids:
                    stem = _atom_stem(str(aid))
                    cells.append(f"\\num{stem}{{}}" if not fmt
                                 else f"\\num{stem}{{}}")
                # pad so the table stays rectangular
                while len(cells) < len(headers):
                    cells.append("--")

            lines.append(" & ".join(cells) + r" \\")

        lines.extend([r"\bottomrule", r"\end{tabular}"])

    if table.caption:
        lines.append(rf"\caption{{{_latex_escape(table.caption)}}}")
    if table.label:
        lines.append(rf"\label{{{table.label}}}")
    lines.append(r"\end{table}")
    lines.append("")
    return "\n".join(lines)


def _atom_stem(atom_id: str) -> str:
    """The macro stem for an atom id, matching numbers.macro_name."""
    from .numbers import macro_name

    # macro_name returns e.g. numRESZeroOneFourTwo; strip the leading 'num'
    # because callers write \num<Stem>.
    full = macro_name(atom_id)
    return full[3:] if full.startswith("num") else full


def render_notation_table_latex(ctx: ResolvedContext) -> str:
    """A standalone notations table fragment (also used inside the Notations section)."""
    from .resolver import notations_rows

    rows = notations_rows(ctx.models)
    if not rows:
        return "% (no symbols recorded)\n"
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\begin{tabular}{lll}",
        r"\toprule",
        r"Symbol & Definition & Unit \\",
        r"\midrule",
    ]
    for glyph, meaning, unit in rows:
        lines.append(f"{glyph} & {_latex_escape(meaning)} & {_latex_escape(unit)} \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


class ArtifactGenerator:
    """Produces the on-disk artifacts a build references."""

    def __init__(self, ctx: ResolvedContext, build_dir: Path, project_root: Path) -> None:
        self.ctx = ctx
        self.build_dir = Path(build_dir)
        self.project_root = Path(project_root)
        self.warnings: List[str] = []
        self.figures_written: List[str] = []
        self.tables_written: List[str] = []
        # Figures whose real file exists and was copied into the build tree.
        self.available: set = set()

    def generate_all(self, tables: List[Table]) -> None:
        (self.build_dir / "figures").mkdir(parents=True, exist_ok=True)
        (self.build_dir / "tables").mkdir(parents=True, exist_ok=True)
        self._link_figures()
        self._write_tables(tables)

    # -- figures -----------------------------------------------------------
    def _link_figures(self) -> None:
        """Copy/link existing figure files into the build tree.

        If a figure file is absent, we emit a visible PLACEHOLDER rather than
        failing the build: during a contest a missing figure must not block the
        other 20 pages from compiling. It is reported as a warning and the
        auditor surfaces it as ARTIFACT_MISSING.
        """
        for fig in self.ctx.figures:
            dest = self.build_dir / "figures" / f"{fig.id}.pdf"
            src: Optional[Path] = None
            if fig.file:
                candidate = self.project_root / fig.file
                if candidate.exists():
                    src = candidate
            if src is not None:
                shutil.copy2(src, dest)
                self.figures_written.append(fig.id)
                self.available.add(fig.id)
                continue

            # A placeholder MUST NOT be written as a .pdf: pdflatex would try
            # to parse it and die with an opaque xpdf error. Write LaTeX source
            # instead and let the renderer fall back to a text box.
            self.warnings.append(
                f"Figure {fig.id} has no generated file; the build will show a "
                "placeholder box instead."
            )
            dest = dest.with_suffix(".tex")
            dest.write_text(_placeholder_pdf_source(fig), encoding="utf-8")

    # -- tables ------------------------------------------------------------
    def _write_tables(self, tables: List[Table]) -> None:
        for t in tables:
            path = self.build_dir / "tables" / f"{t.id}.tex"
            path.write_text(
                render_table_latex(t, self.ctx.macros), encoding="utf-8"
            )
            self.tables_written.append(t.id)

        if not tables:
            return
        # A combined include file keeps main.tex readable.
        combined = "\n".join(
            f"\\input{{tables/{t.id}.tex}}" for t in tables
        )
        (self.build_dir / "tables" / "all.tex").write_text(combined + "\n", encoding="utf-8")


def _placeholder_pdf_source(fig: ResolvedFigure) -> str:
    """A LaTeX fragment that renders an obvious placeholder box.

    Deliberately loud: an empty figure that silently compiles is how a
    screenshot-free paper ends up with a hole in it.
    """
    return (
        "% PLACEHOLDER: no generated file for this figure.\n"
        + "\\begin{center}\n"
        + "\\fbox{\\begin{minipage}{0.8\\linewidth}\n"
        + "\\centering\\vspace{2em}\n"
        + f"\\textbf{{[MISSING FIGURE {fig.id}]}}\\\\[0.5em]\n"
        + f"{_latex_escape(fig.caption)}\n"
        + "\\vspace{2em}\n"
        + "\\end{minipage}}\n"
        + "\\end{center}\n"
    )


def figure_include(fig: ResolvedFigure, build_ok: bool) -> str:
    """The LaTeX that places a figure in the document."""
    width = f"{fig.width:.2f}\\linewidth"
    lines = [
        r"\begin{figure}[htbp]",
        r"\centering",
    ]
    if build_ok:
        lines.append(
            rf"\includegraphics[width={width}]{{figures/{fig.id}.pdf}}"
        )
    else:
        lines.append(
            rf"\fbox{{\parbox{{0.8\linewidth}}{{\centering "
            rf"\textbf{{[MISSING FIGURE {fig.id}]}}\\ {_latex_escape(fig.caption)}}}}}"
        )
    if fig.caption:
        lines.append(rf"\caption{{{_latex_escape(fig.caption)}}}")
    if fig.label:
        lines.append(rf"\label{{{fig.label}}}")
    lines.append(r"\end{figure}")
    return "\n".join(lines)
