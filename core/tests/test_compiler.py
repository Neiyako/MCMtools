"""Phase 2 tests: the paper compiler.

The central claim under test: a number in the paper is a REFERENCE, never a
literal, and the pipeline reports honestly when something is missing.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from mcmcore.compiler import (
    NumberMacros,
    PaperCompiler,
    count_pdf_pages,
    find_engine,
    find_bare_numbers,
    macro_name,
    model_macros,
    notations_rows,
    render_main_tex,
    render_references_bib,
    render_table_latex,
    resolve,
)
from mcmcore.compiler.numbers import check_section_body
from mcmcore.mathstore import MathContent
from mcmcore.schemas import (
    ArtifactBinding,
    Figure,
    Paper,
    PaperSection,
    Reference,
    ResultAtom,
    SectionKind,
    Symbol,
    Table,
)
from mcmcore.store import Store


# --------------------------------------------------------------------------
# Macro naming
# --------------------------------------------------------------------------


class TestMacroName:
    """A LaTeX control sequence may contain letters only -- no digits."""

    def test_digits_are_spelled_out(self):
        assert macro_name("RES-0142") == "numRESZeroOneFourTwo"

    def test_separators_are_dropped(self):
        assert macro_name("EXP-026-R3") == "numEXPZeroTwoSixRThree"

    def test_suffix_is_appended(self):
        assert macro_name("RES-0142", "Pct") == "numRESZeroOneFourTwoPct"

    def test_result_is_letters_only(self):
        for aid in ("RES-0142", "A-1", "x_9", "9"):
            assert macro_name(aid).isalpha(), aid

    def test_never_empty(self):
        assert macro_name("---")


class TestNumberMacros:
    def test_primary_macro_from_format(self):
        nm = NumberMacros().add_all(
            [ResultAtom(atom_id="RES-0142", name="rmse", value=0.079123, format="%.4f")]
        )
        assert nm.macros["numRESZeroOneFourTwo"] == "0.0791"

    def test_named_renderings_become_separate_macros(self):
        """The corpus reports 83.77 % and 0.8377 for the same quantity."""
        nm = NumberMacros().add_all([
            ResultAtom(
                atom_id="RES-0204", name="acc", value=0.8377, format="%.4f",
                renderings={"pct": "83.77\\%"},
            )
        ])
        assert nm.macros["numRESZeroTwoZeroFour"] == "0.8377"
        assert nm.macros["numRESZeroTwoZeroFourPct"] == "83.77\\%"

    def test_owner_lookup_for_auditing(self):
        nm = NumberMacros().add_all(
            [ResultAtom(atom_id="RES-0142", name="x", value=1)]
        )
        assert nm.atom_for("numRESZeroOneFourTwo") == "RES-0142"
        assert nm.atom_for("nope") is None

    def test_duplicate_values_detected(self):
        nm = NumberMacros().add_all([
            ResultAtom(atom_id="R1", name="a", value=5),
            ResultAtom(atom_id="R2", name="b", value=5),
        ])
        dupes = nm.duplicate_values()
        assert "5" in dupes
        assert set(dupes["5"]) == {"R1", "R2"}

    def test_emitted_latex_is_loadable_shape(self):
        nm = NumberMacros().add_all(
            [ResultAtom(atom_id="RES-0142", name="x", value=1)]
        )
        text = nm.to_latex()
        assert r"\newcommand{\numRESZeroOneFourTwo}{1}" in text
        assert text.count("{") == text.count("}")

    def test_percent_in_string_value_is_escaped(self):
        nm = NumberMacros().add_all(
            [ResultAtom(atom_id="R1", name="x", value="42%")]
        )
        assert nm.macros["numROne"] == r"42\%"


# --------------------------------------------------------------------------
# Bare-number detection
# --------------------------------------------------------------------------


class TestBareNumbers:
    def test_plain_number_is_flagged(self):
        found = find_bare_numbers("The RMSE is 0.0832 overall.")
        assert [t for t, _ in found] == ["0.0832"]

    def test_macro_reference_is_not_flagged(self):
        assert find_bare_numbers(r"The RMSE is \numRESZeroOneFourTwo{}.") == []

    def test_lit_escape_hatch(self):
        assert find_bare_numbers(r"We use \lit{5}-fold validation.") == []

    def test_cite_and_ref_arguments_ignored(self):
        assert find_bare_numbers(r"See \cite{smith2020} and \ref{tab:1}.") == []

    def test_comment_ignored(self):
        assert find_bare_numbers("% 2022 was the year\nReal text.") == []

    def test_includegraphics_ignored(self):
        assert find_bare_numbers(r"\includegraphics[width=0.8\linewidth]{a.pdf}") == []

    def test_section_id_carried_into_finding(self):
        out = check_section_body("SEC-010", "We found 42 items.")
        assert out and out[0][0] == "NUMERIC_UNBOUND"
        assert "SEC-010" in out[0][1]

    def test_integer_flagged_too(self):
        assert [t for t, _ in find_bare_numbers("There are 7 clusters.")] == ["7"]


# --------------------------------------------------------------------------
# Resolver
# --------------------------------------------------------------------------


class TestResolver:
    def _resolve(self, models=None, sections=None, atoms=None, figures=None,
                 tables=None, references=None, paper=None):
        return resolve(
            models or [], sections or [], atoms or [], figures or [],
            tables or [], references or [], paper or Paper(),
        )

    def test_dangling_figure_binding_reported(self):
        ctx = self._resolve(figures=[Figure(id="FIG-01", bindings=[ArtifactBinding(atom_id="R99")])])
        assert any(c == "FIGURE_DANGLING_ATOM" for c, _ in ctx.problems)

    def test_dangling_table_binding_reported(self):
        ctx = self._resolve(tables=[Table(id="T1", columns=[{"header": "x", "atom_id": "R99"}])])
        assert any(c == "TABLE_DANGLING_ATOM" for c, _ in ctx.problems)

    def test_missing_citation_reported(self):
        ctx = self._resolve(sections=[PaperSection(id="S1", title="I", body=r"\cite{ghost}")])
        assert any(c == "XREF_BROKEN_CITATION" for c, _ in ctx.problems)

    def test_existing_citation_ok(self):
        ctx = self._resolve(
            sections=[PaperSection(id="S1", title="I", body=r"\cite{real}")],
            references=[Reference(key="real", title="T")],
        )
        assert not any(c == "XREF_BROKEN_CITATION" for c, _ in ctx.problems)

    def test_model_section_needs_no_model_record(self):
        """模型章节不再要求项目里存在对应的 Model 记录。

        拆掉模型层之后，`template_ref` 只是指向章节模板的普通引用，
        不再是"必须存在的模型 id"。所以带 template_ref 的模型章节
        不该产生任何解析问题。
        """
        ctx = self._resolve(sections=[
            PaperSection(id="S1", kind=SectionKind.MODEL, title="M",
                         template_ref="M99")
        ])
        assert not any(c == "SECTION_MODEL_UNRESOLVED" for c, _ in ctx.problems)

    def test_ai_undisclosed_reported(self):
        paper = Paper(ai_usage={"ai_used": True})
        ctx = self._resolve(paper=paper)
        assert any(c == "AI_USE_UNDISCLOSED" for c, _ in ctx.problems)

    def test_ai_disclosed_is_clean(self):
        paper = Paper(
            ai_usage={"ai_used": True},
            sections=[PaperSection(id="S1", kind=SectionKind.REPORT_ON_AI,
                                   title="Report on Use of AI", enabled=True)],
        )
        ctx = self._resolve(paper=paper)
        assert not any(c == "AI_USE_UNDISCLOSED" for c, _ in ctx.problems)

    def test_sections_sorted_by_order(self):
        ctx = self._resolve(sections=[
            PaperSection(id="B", title="B", order=20),
            PaperSection(id="A", title="A", order=10),
        ])
        assert [s.id for s in ctx.sections] == ["A", "B"]

    def test_macros_built_from_atoms(self):
        ctx = self._resolve(atoms=[ResultAtom(atom_id="R1", name="x", value=1)])
        assert "numROne" in ctx.macros


class TestModelMacros:
    """模型名宏：让改名一处改、处处生效。

    拆掉模型层之后，宏改为按 **kind=model 的章节** 生成 ——
    论文里真正的"模型一/模型二"就是这些章节标题。
    """

    @staticmethod
    def _sec(order, title):
        return PaperSection(id=f"SEC-{order:03d}", kind=SectionKind.MODEL,
                            title=title, level=1, order=order, enabled=True)

    def test_labels_follow_section_titles(self):
        sections = [self._sec(10, "Model I"), self._sec(20, "Model II")]
        macros = model_macros(sections)
        assert macros["modelI"] == "Model I"
        assert macros["modelII"] == "Model II"

    def test_roman_numeral_for_tenth_model(self):
        sections = [self._sec(i * 10, f"Model {i}") for i in range(1, 11)]
        assert "modelX" in model_macros(sections)

    def test_no_model_sections_means_no_macros(self):
        """没有模型章节时不该凭空造宏 —— 空字典，不是报错。"""
        assert model_macros([]) == {}

    def test_non_model_sections_are_ignored(self):
        intro = PaperSection(id="SEC-001", kind=SectionKind.INTRODUCTION,
                             title="Introduction", level=1, order=10, enabled=True)
        assert model_macros([intro]) == {}


class TestNotationsRows:
    """符号表是符号的视图，由 math/ 生成。"""

    @staticmethod
    def _math(*symbols):
        return MathContent(symbols=list(symbols))

    def test_units_default_to_dimensionless(self):
        math = self._math(Symbol(id="S1", glyph="x", meaning="a ratio"))
        assert notations_rows(math) == [("$x$", "a ratio", "/")]

    def test_unit_preserved(self):
        math = self._math(Symbol(id="S1", glyph="v", meaning="speed", unit="m/s"))
        assert notations_rows(math)[0][2] == "m/s"

    def test_redefined_symbol_is_annotated_not_dropped(self):
        """4% 的论文会合法地复用符号 —— 标注出来，不要丢掉。"""
        math = self._math(
            Symbol(id="S1", glyph="gamma", meaning="boredom"),
            Symbol(id="S2", glyph="gamma", meaning="risk weight"),
        )
        rows = notations_rows(math)
        assert len(rows) == 2
        assert "含义不同" in rows[1][1]

    def test_math_glyph_not_double_wrapped(self):
        math = self._math(Symbol(id="S1", glyph="$\\beta$", meaning="x"))
        assert notations_rows(math)[0][0] == "$\\beta$"

    def test_empty_symbol_table_gives_no_rows(self):
        assert notations_rows(MathContent()) == []


# --------------------------------------------------------------------------
# Renderer
# --------------------------------------------------------------------------


class TestRenderer:
    def test_preamble_matches_official_comap(self):
        tex = render_main_tex(Paper(), resolve([], [], [], [], [], [], Paper()))
        assert r"\documentclass[12pt]{article}" in tex
        assert r"\usepackage{newtxtext}" in tex
        assert r"\usepackage{newtxmath}" in tex
        assert r"\rhead{Page \thepage}" in tex

    def test_lit_macro_is_defined(self):
        tex = render_main_tex(Paper(), resolve([], [], [], [], [], [], Paper()))
        assert r"\newcommand{\lit}[1]{#1}" in tex

    def test_summary_sheet_is_a_form_not_a_heading(self):
        paper = Paper(summary={"problem_letter": "C", "team_control_number": "2307166"})
        tex = render_main_tex(paper, resolve([], [], [], [], [], [], paper))
        assert "Problem Chosen" in tex
        assert "Team Control Number" in tex
        assert "2307166" in tex
        assert r"\section{Summary}" not in tex

    def test_generated_inputs_referenced(self):
        tex = render_main_tex(Paper(), resolve([], [], [], [], [], [], Paper()))
        assert r"\input{generated/numbers.tex}" in tex
        assert r"\input{generated/models.tex}" in tex

    def test_disabled_sections_commented_out(self):
        paper = Paper(sections=[
            PaperSection(id="S1", title="Hidden", enabled=False, body="secret"),
        ])
        tex = render_main_tex(paper, resolve([], paper.sections, [], [], [], [], paper))
        assert "% [disabled] Hidden" in tex

    def test_notations_section_autogenerated_with_disclaimer(self):
        math = MathContent(symbols=[Symbol(id="S1", glyph="x", meaning="thing")])
        paper = Paper(sections=[PaperSection(
            id="S1", kind=SectionKind.NOTATIONS, title="Notations",
            order=1, generated=True, enabled=True)])
        tex = render_main_tex(
            paper, resolve(math, paper.sections, [], [], [], [], paper)
        )
        assert "longtable" in tex
        assert "not listed here" in tex

    def test_ai_report_lists_entries(self):
        paper = Paper(
            summary={"problem_letter": "C", "team_control_number": "1234567"},
            ai_usage={"ai_used": True, "entries": [
                {"tool": "DeepSeek", "phase": "pre_competition", "purpose": "development"}]},
            sections=[PaperSection(id="S1", kind=SectionKind.REPORT_ON_AI,
                                   title="Report on Use of AI", order=1,
                                   generated=True, enabled=True)],
        )
        tex = render_main_tex(paper, resolve([], paper.sections, [], [], [], [], paper))
        assert "DeepSeek" in tex
        assert "pre\\_competition" in tex or "pre_competition" in tex

    def test_ai_report_when_no_ai_used(self):
        paper = Paper(sections=[PaperSection(
            id="S1", kind=SectionKind.REPORT_ON_AI, title="Report on Use of AI",
            order=1, generated=True, enabled=True)])
        tex = render_main_tex(paper, resolve([], paper.sections, [], [], [], [], paper))
        assert "No AI tools were used" in tex

    def test_references_emit_bibtex(self):
        bib = render_references_bib([
            Reference(key="smith2020", title="A Paper", authors=["A Smith"], year=2020)
        ])
        assert "@article{smith2020," in bib
        assert "author = {A Smith}" in bib

    def test_ai_reference_is_marked(self):
        bib = render_references_bib([Reference(key="ai1", title="T", ai_generated=True)])
        assert "COMAP policy" in bib


# --------------------------------------------------------------------------
# Table rendering
# --------------------------------------------------------------------------


class TestTableRendering:
    def test_bound_cells_use_macros(self):
        t = Table(
            id="TAB-01", caption="Params", label="tab:p",
            columns=[{"header": "Name"}, {"header": "Value", "atom_id": "R1"}],
            rows=[{"literal": "beta", "atom_ids": ["R1"]}],
            bindings=[ArtifactBinding(atom_id="R1")],
        )
        tex = render_table_latex(t, NumberMacros())
        assert r"\numROne{}" in tex
        assert r"\label{tab:p}" in tex

    def test_caption_escaped(self):
        t = Table(id="T1", caption="A & B", columns=[{"header": "x"}], rows=[])
        assert r"A \& B" in render_table_latex(t, NumberMacros())

    def test_empty_table_still_valid_latex(self):
        tex = render_table_latex(Table(id="T1"), NumberMacros())
        assert r"\begin{table}" in tex
        assert r"\end{table}" in tex


# --------------------------------------------------------------------------
# Page counting -- regression: /Count also appears on /Outlines
# --------------------------------------------------------------------------


class TestPageCounting:
    def test_missing_file_returns_none(self, tmp_path):
        assert count_pdf_pages(tmp_path / "nope.pdf") is None

    def test_uncompressed_page_tree(self, tmp_path):
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-1.4\n<< /Type /Pages /Count 7 /Kids [] >>\n")
        assert count_pdf_pages(pdf) == 7

    def test_outlines_count_is_not_mistaken_for_pages(self, tmp_path):
        """A bare 'max /Count' heuristic reported 10 pages for a 4-page document.

        /Count on /Outlines is the BOOKMARK count. Only /Type /Pages counts.
        """
        pdf = tmp_path / "b.pdf"
        pdf.write_bytes(
            b"%PDF-1.4\n"
            b"<< /Type /Pages /Count 4 /Kids [1 0 R] >>\n"
            b"<< /Type /Outlines /Count 10 /First 2 0 R >>\n"
        )
        assert count_pdf_pages(pdf) == 4

    def test_falls_back_to_page_object_count(self, tmp_path):
        pdf = tmp_path / "c.pdf"
        pdf.write_bytes(b"%PDF-1.4\n" + b"<< /Type /Page >>\n" * 3)
        assert count_pdf_pages(pdf) == 3


# --------------------------------------------------------------------------
# Engine discovery
# --------------------------------------------------------------------------


class TestEngineDiscovery:
    def test_finds_pdflatex_when_installed(self):
        found = find_engine("pdflatex")
        if found is None:
            pytest.skip("no TeX installation on this machine")
        assert Path(found).exists()

    def test_missing_engine_returns_none(self):
        assert find_engine("definitely-not-a-real-engine-xyz") is None


# --------------------------------------------------------------------------
# Full build (requires a TeX installation)
# --------------------------------------------------------------------------


needs_tex = pytest.mark.skipif(
    find_engine("pdflatex") is None, reason="pdflatex not installed"
)


@needs_tex
class TestRealBuild:
    def _project(self, tmp_path):
        st = Store.init(tmp_path, "build-test")
        # 符号表搬到项目级的 math/ 里。
        content = st.math.load()
        content.symbols.append(Symbol(id="S1", glyph="x", meaning="a quantity", unit="/"))
        st.math.save(content)
        st.append_atoms([
            ResultAtom(atom_id="RES-0001", name="rmse", value=0.0791,
                       format="%.4f", unit="/", condition="baseline"),
        ])
        st.save_paper(Paper(
            paper_id="P1",
            summary={"problem_letter": "C", "team_control_number": "2307166"},
            sections=[
                PaperSection(id="SEC-010", kind=SectionKind.INTRODUCTION,
                             title="Introduction", order=10,
                             body=r"The error is \numRESZeroZeroZeroOne{}."),
                PaperSection(id="SEC-020", kind=SectionKind.NOTATIONS,
                             title="Notations", order=20, generated=True),
                PaperSection(id="SEC-030", kind=SectionKind.REFERENCES,
                             title="References", order=30, generated=True),
            ],
        ))
        return st

    def test_build_produces_pdf_with_page_count(self, tmp_path):
        st = self._project(tmp_path)
        result = PaperCompiler(st).build()
        assert result.ok, result.messages
        assert result.pdf_path.exists()
        assert result.page_count is not None and result.page_count >= 1

    def test_page_count_matches_latex_log(self, tmp_path):
        """Cross-check our counter against pdflatex's own report."""
        import re

        st = self._project(tmp_path)
        result = PaperCompiler(st).build()
        log = (result.build_dir / "main.log").read_text(errors="replace")
        m = re.search(r"Output written on main\.pdf \((\d+) pages?", log)
        assert m, "no page count in the LaTeX log"
        assert result.page_count == int(m.group(1))

    def test_number_macro_resolves_in_pdf_text(self, tmp_path):
        import fitz

        st = self._project(tmp_path)
        result = PaperCompiler(st).build()
        text = "".join(p.get_text() for p in fitz.open(str(result.pdf_path)))
        assert "0.0791" in text, "the number macro did not expand"

    def test_page_count_persisted_to_paper(self, tmp_path):
        st = self._project(tmp_path)
        result = PaperCompiler(st).build()
        assert st.load_paper().build.page_count == result.page_count

    def test_build_without_engine_still_writes_tex(self, tmp_path):
        st = self._project(tmp_path)
        result = PaperCompiler(st, engine="definitely-not-real").build()
        assert not result.ok
        assert (result.build_dir / "main.tex").exists()
        assert any("not found" in w for w in result.warnings)


# --------------------------------------------------------------------------
# Artifacts must actually reach the document
# --------------------------------------------------------------------------


class TestArtifactPlacement:
    """Regression: figures were generated but never placed into the PDF."""

    def _paper_with_figure(self):
        paper = Paper(sections=[
            PaperSection(id="SEC-050", kind=SectionKind.MODEL, title="Model",
                         order=50, body=r"See Figure~\ref{fig:s}."),
        ])
        fig = Figure(id="FIG-01", caption="Cap", label="fig:s",
                     file="figures/FIG-01.pdf", bindings=[ArtifactBinding(atom_id="R1")])
        return paper, fig

    def test_cited_figure_is_included(self):
        paper, fig = self._paper_with_figure()
        ctx = resolve([], paper.sections, [], [fig], [], [], paper)
        ctx.figures[0].available = True  # the generator found a real file
        tex = render_main_tex(paper, ctx)
        assert r"\includegraphics" in tex
        assert "fig:s" in tex

    def test_missing_figure_renders_a_visible_placeholder(self):
        """A missing figure must not silently vanish; it shows a loud box."""
        paper, fig = self._paper_with_figure()
        ctx = resolve([], paper.sections, [], [fig], [], [], paper)
        ctx.figures[0].available = False
        tex = render_main_tex(paper, ctx)
        assert r"\includegraphics" not in tex
        assert "MISSING FIGURE" in tex

    def test_uncited_figure_is_still_placed(self):
        """A bound artifact must never be silently dropped from the document."""
        paper = Paper(sections=[
            PaperSection(id="SEC-050", title="Model", order=50, body="No refs here."),
        ])
        fig = Figure(id="FIG-09", caption="Orphan", label="fig:o",
                     file="figures/FIG-09.pdf", bindings=[ArtifactBinding(atom_id="R1")])
        ctx = resolve([], paper.sections, [], [fig], [], [], paper)
        tex = render_main_tex(paper, ctx)
        assert "FIG-09" in tex or "fig:o" in tex

    def test_cited_table_is_input(self):
        paper = Paper(sections=[
            PaperSection(id="SEC-050", title="Model", order=50,
                         body=r"See Table~\ref{tab:t}."),
        ])
        tab = Table(id="TAB-07", caption="T", label="tab:t",
                    columns=[{"header": "x", "atom_id": "R1"}])
        ctx = resolve([], paper.sections, [], [], [tab], [], paper)
        tex = render_main_tex(paper, ctx)
        assert r"\input{tables/TAB-07.tex}" in tex

    def test_uncited_table_is_still_placed(self):
        paper = Paper(sections=[
            PaperSection(id="SEC-050", title="Model", order=50, body="None."),
        ])
        tab = Table(id="TAB-08", label="tab:u", columns=[{"header": "x"}])
        ctx = resolve([], paper.sections, [], [], [tab], [], paper)
        tex = render_main_tex(paper, ctx)
        assert "TAB-08" in tex

    def test_cites_helper_matches_multiple_labels(self):
        from mcmcore.compiler.renderer import _cites

        assert _cites(r"\ref{fig:a,fig:b}", "fig:b")
        assert not _cites(r"\ref{fig:a}", "fig:b")
        assert not _cites("", "fig:a")
