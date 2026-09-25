"""The paper compiler: six-stage pipeline from object model to measured PDF.

    1 Resolve   objects -> render context (+ reference checks)
    2 Generate  figures and tables
    3 Render    main.tex, generated/*.tex, references.bib
    4 Compile   pdflatex (or latexmk)
    5 Measure   page count against the 25-page budget
    6 Verify    hand off to the audit engine

Page measurement is a first-class stage, not an afterthought: 72.1% of
2022-2025 papers are EXACTLY 25 pages, so the budget is a hard constraint that
must be visible on every build.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..schemas import (
    Figure,
    Paper,
    PaperSection,
    Reference,
    ResultAtom,
    Table,
)
from ..store import Store
from .artifacts import ArtifactGenerator
from .numbers import check_section_body
from .renderer import render_main_tex, render_models_tex, render_references_bib
from .resolver import ResolvedContext, resolve

# TeX Live on macOS installs here but often is not on PATH.
_TEX_SEARCH = [
    "/Library/TeX/texbin",
    "/usr/local/texlive/2024/bin/universal-darwin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
]


def find_engine(name: str) -> Optional[str]:
    """Locate a TeX engine, checking standard install locations."""
    found = shutil.which(name)
    if found:
        return found
    for d in _TEX_SEARCH:
        candidate = Path(d) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


@dataclass
class BuildResult:
    """Outcome of one compile."""

    ok: bool = False
    build_dir: Optional[Path] = None
    pdf_path: Optional[Path] = None
    page_count: Optional[int] = None
    page_limit: int = 25
    engine: Optional[str] = None
    passes: int = 0
    log_tail: str = ""
    messages: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    findings: List[Dict[str, str]] = field(default_factory=list)
    context: Optional[ResolvedContext] = None

    @property
    def pages_remaining(self) -> Optional[int]:
        if self.page_count is None:
            return None
        return self.page_limit - self.page_count

    def summary(self) -> str:
        if not self.ok:
            return f"build FAILED ({self.engine or 'no engine'})"
        rem = self.pages_remaining
        budget = (
            f"{self.page_count}/{self.page_limit} pages"
            if self.page_count is not None
            else "page count unknown"
        )
        if rem is not None and rem >= 0:
            return f"{budget} ({rem} remaining)"
        if rem is not None:
            return f"{budget} (OVER by {-rem})"
        return budget


# --------------------------------------------------------------------------
# Page counting
# --------------------------------------------------------------------------

_PAGE_RE = re.compile(rb"/Type\s*/Page[^s]")
# The page-tree node is "/Type /Pages" and its /Count is the true page total.
# NOTE: /Count ALSO appears on /Outlines (bookmark count). A bare "max /Count"
# heuristic is therefore wrong: it reported 10 pages for a 4-page document.
_PAGES_NODE_RE = re.compile(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)")
_PAGES_NODE_RE2 = re.compile(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b")


def _flate_streams(data: bytes):
    """Yield the decompressed body of every FlateDecode stream.

    Modern pdfTeX writes the page tree inside a COMPRESSED object stream, so a
    plain byte scan of the file finds no ``/Type /Page`` at all. Measured on a
    real build: 0 matches raw, 4 matches after inflating.
    """
    import zlib

    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        try:
            yield zlib.decompress(data[start:end])
        except zlib.error:
            continue


def count_pdf_pages(pdf_path: Path) -> Optional[int]:
    """Count pages in a PDF with no third-party dependency.

    Strategy, in order of reliability:
      1. The ``/Count`` of the page-tree node (``/Type /Pages``), taking the
         maximum across nodes since intermediate nodes carry subtotals.
      2. A count of ``/Type /Page`` leaf objects.
    Both are searched in the raw bytes AND inside decompressed object streams,
    because pdfTeX compresses the page tree by default.

    Only the page tree is consulted. ``/Count`` also appears on ``/Outlines``,
    where it means the number of bookmarks, so a generic scan over-counts.
    """
    try:
        data = pdf_path.read_bytes()
    except OSError:
        return None

    blobs = [data] + list(_flate_streams(data))

    tree_counts = []
    page_objects = 0
    for blob in blobs:
        tree_counts.extend(int(c) for c in _PAGES_NODE_RE.findall(blob))
        tree_counts.extend(int(c) for c in _PAGES_NODE_RE2.findall(blob))
        page_objects += len(_PAGE_RE.findall(blob))

    if tree_counts:
        # Intermediate /Pages nodes carry subtotals; the root carries the total.
        return max(tree_counts)
    return page_objects or None


# --------------------------------------------------------------------------
# Compiler
# --------------------------------------------------------------------------


class PaperCompiler:
    """Compiles a project's Paper into a PDF."""

    def __init__(self, store: Store, engine: str = "pdflatex", keep_build: bool = True) -> None:
        self.store = store
        self.engine_name = engine
        self.keep_build = keep_build

    # -- public API --------------------------------------------------------
    def build(self, clean: bool = True) -> BuildResult:
        result = BuildResult(page_limit=self.store.load_paper().latex.page_limit)
        paper = self.store.load_paper()

        # ---- stage 1: resolve ------------------------------------------
        ctx = resolve(
            math=self.store.math.load(),
            sections=paper.sections,
            atoms=self.store.load_atoms(),
            figures=self.store.list_figures(),
            tables=self.store.list_tables(),
            references=self.store.load_references(),
            paper=paper,
        )
        result.context = ctx
        result.messages.append(
            f"[1/6] Resolved .......... {len(ctx.math.symbols)} symbols, "
            f"{len(ctx.math.equations)} equations, "
            f"{len(ctx.sections)} sections, "
            f"{len(ctx.macros)} number macros"
        )
        for code, msg in ctx.problems:
            if code == "AI_USE_UNDISCLOSED":
                result.findings.append({"severity": "error", "code": code, "message": msg})

        # ---- stage 2: generate artifacts -------------------------------
        build_dir = self.store.root / "build"
        if clean and build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "generated").mkdir(exist_ok=True)

        gen = ArtifactGenerator(ctx, build_dir, self.store.root)
        gen.generate_all(self.store.list_tables())
        result.warnings.extend(gen.warnings)
        for fig in ctx.figures:
            fig.available = fig.id in gen.available

        # Stale artifacts are a defect the build must surface: a figure whose
        # bound numbers changed since it was rendered no longer matches the
        # paper, which is exactly the divergence this toolchain exists to stop.
        from ..runner import stale_artifacts

        stale_figs, stale_tabs = stale_artifacts(self.store)
        for fig in stale_figs:
            result.findings.append({
                "severity": "warning",
                "code": "FIG_STALE",
                "message": (
                    f"Figure {fig.id} is stale: a bound ResultAtom changed since "
                    "it was generated. Regenerate it before submitting."
                ),
            })
        for tab in stale_tabs:
            result.findings.append({
                "severity": "warning",
                "code": "TAB_STALE",
                "message": (
                    f"Table {tab.id} is stale: a bound ResultAtom changed since "
                    "it was generated."
                ),
            })
        if stale_figs or stale_tabs:
            result.warnings.append(
                f"{len(stale_figs) + len(stale_tabs)} artifact(s) are STALE. "
                "Run 'mcm artifact regenerate'."
            )
        result.messages.append(
            f"[2/6] Generated ......... {len(gen.figures_written)} figures, "
            f"{len(gen.tables_written)} tables"
        )

        # ---- stage 3: render -------------------------------------------
        (build_dir / "generated" / "numbers.tex").write_text(
            ctx.macros.to_latex(), encoding="utf-8"
        )
        (build_dir / "generated" / "models.tex").write_text(
            render_models_tex(ctx.sections), encoding="utf-8"
        )
        (build_dir / "generated" / "references.bib").write_text(
            render_references_bib(ctx.references), encoding="utf-8"
        )
        (build_dir / "main.tex").write_text(
            render_main_tex(paper, ctx), encoding="utf-8"
        )
        result.messages.append(
            f"[3/6] Rendered .......... main.tex + {len(ctx.sections)} sections, "
            f"{len(ctx.references)} references"
        )

        # ---- numeric audit of prose bodies -----------------------------
        for section in ctx.sections:
            if section.generated or not section.body:
                continue
            for code, msg in check_section_body(section.id, section.body):
                result.findings.append(
                    {"severity": "warning", "code": code, "message": msg}
                )

        # ---- stage 4: compile ------------------------------------------
        result.build_dir = build_dir
        engine = find_engine(self.engine_name)
        result.engine = engine
        if engine is None:
            result.messages.append(
                f"[4/6] Compile ........... SKIPPED ({self.engine_name} not found)"
            )
            result.warnings.append(
                f"LaTeX engine '{self.engine_name}' not found; the .tex sources "
                "were generated but no PDF was produced."
            )
            return result

        passes = self._run_tex(engine, build_dir, result)
        result.passes = passes
        if passes == 0:
            result.messages.append("[4/6] Compile ........... FAILED")
            return result
        result.messages.append(
            f"[4/6] Compiled .......... {self.engine_name} x{passes}"
        )

        pdf = build_dir / "main.pdf"
        if not pdf.exists():
            result.warnings.append("Compilation reported success but no main.pdf exists.")
            return result
        result.pdf_path = pdf
        result.ok = True

        # ---- stage 5: measure ------------------------------------------
        pages = count_pdf_pages(pdf)
        result.page_count = pages
        if pages is not None:
            paper.build.page_count = pages
            paper.build.pdf_path = str(pdf.relative_to(self.store.root))
            self.store.save_paper(paper)
            result.messages.append(f"[5/6] Measured ........... {result.summary()}")
        else:
            result.messages.append("[5/6] Measured ........... page count unavailable")

        # ---- stage 6: verify -------------------------------------------
        result.messages.append(
            f"[6/6] Verify ............. {len(result.findings)} finding(s) from the compiler"
        )
        return result

    # -- engine invocation -------------------------------------------------
    def _run_tex(self, engine: str, build_dir: Path, result: BuildResult) -> int:
        """Run pdflatex repeatedly until references stabilise.

        Three passes is the conventional count for a document with a TOC, cross
        references and a bibliography. We stop early if the log says the
        rerun warning is gone.
        """
        max_passes = 3
        for i in range(1, max_passes + 1):
            proc = subprocess.run(
                [
                    engine,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-file-line-error",
                    "main.tex",
                ],
                cwd=str(build_dir),
                capture_output=True,
                timeout=180,
            )
            log = build_dir / "main.log"
            text = log.read_text(errors="replace") if log.exists() else ""
            if proc.returncode != 0:
                result.log_tail = _tail(proc.stdout.decode(errors="replace"), 40)
                result.warnings.append(
                    f"{self.engine_name} failed on pass {i}. See build/main.log."
                )
                return 0
            if "Rerun to get" not in text and "Label(s) may have changed" not in text:
                return i
        return max_passes


def _tail(text: str, n: int) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[-n:])
