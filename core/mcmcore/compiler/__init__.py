"""Phase 2: the paper compiler.

Six-stage pipeline from the object model to a measured PDF:

    1 Resolve   objects -> render context (+ reference checks)
    2 Generate  figures and tables
    3 Render    main.tex, generated/*.tex, references.bib
    4 Compile   pdflatex / latexmk
    5 Measure   page count against the 25-page budget
    6 Verify    findings handed to the audit engine

The mechanism that matters: a number in the paper is a REFERENCE, never a
literal. ResultAtoms become LaTeX macros, so an updated result cannot leave a
stale figure behind in the prose.
"""

from .artifacts import ArtifactGenerator, figure_include, render_table_latex
from .compiler import BuildResult, PaperCompiler, count_pdf_pages, find_engine
from .numbers import NumberMacros, check_section_body, find_bare_numbers, macro_name
from .renderer import render_main_tex, render_models_tex, render_references_bib
from .resolver import ResolvedContext, model_macros, notations_rows, resolve

__all__ = [
    "ArtifactGenerator", "figure_include", "render_table_latex",
    "BuildResult", "PaperCompiler", "count_pdf_pages", "find_engine",
    "NumberMacros", "check_section_body", "find_bare_numbers", "macro_name",
    "render_main_tex", "render_models_tex", "render_references_bib",
    "ResolvedContext", "model_macros", "notations_rows", "resolve",
]
