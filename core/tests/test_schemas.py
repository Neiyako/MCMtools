"""Schema tests.

These encode the *anti-over-engineering* decisions as executable assertions:
the modal real paper must validate without supplying taxonomy fields.
"""

import pytest
from pydantic import ValidationError

from mcmcore.mathstore import MathContent
from mcmcore.schemas import (
    Assumption,
    Dataset,
    Experiment,
    ExperimentKind,
    Figure,
    Parameter,
    ResultAtom,
    Role,
    Run,
    Scope,
    Severity,
    SummarySheet,
    Symbol,
    Validation,
    ValidationKind,
    Verdict,
)
from mcmcore.validate import AuditReport, Finding


# --------------------------------------------------------------------------
# The central design claim: a MODAL paper validates with no taxonomy supplied
# --------------------------------------------------------------------------


class TestModalPaperValidates:
    """A paper like most of the corpus -- flat symbol list, unnumbered
    assumptions, no validation section -- must load without friction."""

    def test_bare_math_content_is_valid(self):
        """空项目（还没有符号和公式）必须能正常构造。"""
        m = MathContent()
        assert m.symbols == []
        assert m.equations == []
        assert m.assumptions == []

    def test_symbol_role_defaults_to_unknown(self):
        """Only a minority of papers separate state from parameter."""
        s = Symbol(id="S1", glyph="x", meaning="population")
        assert s.role is Role.UNKNOWN
        assert s.time_varying is False

    def test_assumption_scope_defaults_to_unknown(self):
        """Only 11% of papers use model-scoped language."""
        a = Assumption(id="A1", text="The data are accurate.")
        assert a.scope is Scope.UNKNOWN
        assert a.label is None
        assert a.justification is None

    def test_notation_table_defaults_to_non_exhaustive(self):
        """语料里近乎通用的声明：符号表不是权威定义。"""
        m = MathContent()
        assert m.notation_table.exhaustive is False

    def test_result_atom_accepts_string_value(self):
        atom = ResultAtom(atom_id="RES-01", name="verdict", value="high")
        assert atom.rendered() == "high"
        assert atom.numeric() is None


# --------------------------------------------------------------------------
# The mechanism that makes single-sourced numbers work
# --------------------------------------------------------------------------


class TestResultAtom:
    def test_rendering_uses_format(self):
        a = ResultAtom(atom_id="R1", name="rmse", value=0.079123, format="%.4f")
        assert a.rendered() == "0.0791"

    def test_default_format(self):
        a = ResultAtom(atom_id="R1", name="x", value=42.271)
        assert a.rendered() == "42.27"

    def test_named_alternate_rendering(self):
        """The corpus reports the same quantity as '83.77 %' and '0.8377'."""
        a = ResultAtom(
            atom_id="R1",
            name="accuracy",
            value=0.8377,
            renderings={"pct": "83.77\\%", "unit": "0.8377"},
        )
        assert a.rendered("pct") == "83.77\\%"
        assert a.rendered("unit") == "0.8377"
        assert a.rendered() == "0.8377"

    def test_numeric_extraction(self):
        assert ResultAtom(atom_id="R1", name="x", value=5).numeric() == 5.0
        assert ResultAtom(atom_id="R2", name="x", value="0.5").numeric() == 0.5
        assert ResultAtom(atom_id="R3", name="x", value="high").numeric() is None

    def test_bool_is_not_numeric(self):
        """True must not silently become 1.0 in an audit."""
        assert ResultAtom(atom_id="R1", name="x", value=True).numeric() is None


# --------------------------------------------------------------------------
# Experiment: the OAT invariant is the signature of a real sensitivity study
# --------------------------------------------------------------------------


class TestExperiment:
    def test_oat_with_invariant_is_ok(self):
        e = Experiment(
            id="EXP-01",
            kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[{"name": "beta", "values": [0.1, 0.2]}],
            held_fixed=["grid logic", "initial capital"],
        )
        assert e.held_fixed_ok()

    def test_oat_without_invariant_is_flagged(self):
        e = Experiment(
            id="EXP-01",
            kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[{"name": "beta", "values": [0.1, 0.2]}],
        )
        assert not e.held_fixed_ok()

    def test_oat_with_two_axes_is_flagged(self):
        e = Experiment(
            id="EXP-01",
            kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[{"name": "a", "values": [1]}, {"name": "b", "values": [2]}],
            held_fixed=["c"],
        )
        assert not e.held_fixed_ok()

    def test_n_trials_from_values(self):
        e = Experiment(
            id="E",
            varied=[{"name": "a", "values": [1, 2, 3]}],
            n_runs=2,
        )
        assert e.n_trials() == 6

    def test_n_trials_from_range(self):
        e = Experiment(
            id="E",
            varied=[{"name": "a", "range": [0.0, 1.0], "step": 0.25}],
        )
        # 0.00, 0.25, 0.50, 0.75, 1.00
        assert e.n_trials() == 5

    def test_ablation_is_modelled_as_variant(self):
        """'ablation' appears 0 times in the corpus, but 34% of papers do it."""
        e = Experiment(
            id="EXP-09",
            kind=ExperimentKind.MODEL_COMPARISON,
            variant_of="EXP-01",
            removed_components=["vaccination term"],
        )
        assert e.variant_of == "EXP-01"
        assert e.status.value == "planned"

    def test_rejected_experiment_is_representable(self):
        """The best paper documents two rejected methods before the accepted one."""
        e = Experiment(
            id="EXP-03",
            kind=ExperimentKind.OPTIMIZATION_RUN,
            status="rejected",
            failure_reason="250 variables; we have to give up",
        )
        assert e.status.value == "rejected"
        assert e.failure_reason


# --------------------------------------------------------------------------
# Strictness: typos must be loud
# --------------------------------------------------------------------------


class TestStrictness:
    def test_unknown_field_is_rejected(self):
        """手写 YAML 里的错别字必须报错，不能被静默忽略。"""
        with pytest.raises(ValidationError):
            Symbol(id="S1", glyph="x", meanng="typo")

    def test_missing_required_field_is_rejected(self):
        with pytest.raises(ValidationError):
            Symbol(id="S1")

    def test_blank_symbol_glyph_is_rejected(self):
        with pytest.raises(ValidationError):
            Symbol(id="S1", glyph="   ", meaning="x")


# --------------------------------------------------------------------------
# Audit report
# --------------------------------------------------------------------------


class TestAuditReport:
    def test_clean_report_is_ready(self):
        r = AuditReport()
        assert r.ok()
        assert r.verdict() is Verdict.READY

    def test_warnings_give_human_review_not_failure(self):
        r = AuditReport()
        r.warn("X", "something")
        assert r.ok()
        assert r.verdict() is Verdict.READY_FOR_HUMAN_REVIEW

    def test_errors_block(self):
        r = AuditReport()
        r.error("X", "broken")
        assert not r.ok()
        assert r.verdict() is Verdict.NOT_READY

    def test_summary_line(self):
        r = AuditReport()
        r.error("A", "e")
        r.warn("B", "w")
        # 摘要行面向用户，已中文化；这里断言的是"它同时报出了错误和警告"。
        line = r.summary_line()
        assert "1 个错误" in line and "1 个警告" in line

    def test_finding_dict_shape(self):
        f = Finding(Severity.WARNING, "CODE", "msg", "SUBJ")
        d = f.as_dict()
        assert d == {
            "severity": "warning",
            "code": "CODE",
            "subject": "SUBJ",
            "message": "msg",
        }


# --------------------------------------------------------------------------
# Dataset
# --------------------------------------------------------------------------


class TestDataset:
    def test_schema_alias_round_trips(self):
        """'schema' is reserved on BaseModel, so the field is aliased."""
        d = Dataset(dataset_id="DS-001", name="raw", schema=[{"name": "x", "dtype": "float64"}])
        dumped = d.model_dump(by_alias=True)
        assert "schema" in dumped
        assert dumped["schema"][0]["name"] == "x"

    def test_versioned_id(self):
        d = Dataset(dataset_id="DS-001", name="raw", version=3)
        assert d.versioned_id() == "DS-001@3"

    def test_total_rows(self):
        d = Dataset(
            dataset_id="DS-001",
            name="raw",
            files=[{"path": "a.csv", "rows": 10}, {"path": "b.csv", "rows": 5}],
        )
        assert d.total_rows() == 15


# --------------------------------------------------------------------------
# Figure staleness -- the anti-screenshot mechanism
# --------------------------------------------------------------------------


class TestFigureStaleness:
    def test_stale_when_bound_atom_changes(self):
        f = Figure(id="FIG-01", bindings=[{"atom_id": "R1"}, {"atom_id": "R2"}])
        assert f.is_stale_if(["R2"])
        assert not f.is_stale_if(["R9"])

    def test_unbound_figure_is_not_stale(self):
        f = Figure(id="FIG-01")
        assert not f.is_stale_if(["R1"])


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------


class TestRun:
    def test_failed_run_retains_diagnostics(self):
        r = Run(
            run_id="RUN-1",
            experiment_id="EXP-01",
            status="failed",
            exit_code=1,
            stderr_tail="ZeroDivisionError",
        )
        assert r.status.value == "failed"
        assert r.stderr_tail


# --------------------------------------------------------------------------
# Summary sheet placeholder detection
# --------------------------------------------------------------------------


class TestSummaryPlaceholder:
    """A single letter A-F is a VALID problem letter, not a placeholder.

    Regression test: an earlier version treated "C" as filler and therefore
    failed every correctly filled-in summary sheet.
    """

    @pytest.mark.parametrize("letter", ["A", "B", "C", "D", "E", "F"])
    def test_real_problem_letters_are_not_placeholders(self, letter):
        s = SummarySheet(problem_letter=letter, team_control_number="2400001")
        assert not s.is_placeholder()

    def test_shipped_template_defaults_are_placeholders(self):
        s = SummarySheet(problem_letter="ABCDEF", team_control_number="1111111")
        assert s.is_placeholder()

    def test_empty_is_a_placeholder(self):
        assert SummarySheet().is_placeholder()

    def test_repeated_digit_team_number_is_a_placeholder(self):
        assert SummarySheet(problem_letter="C", team_control_number="2222222").is_placeholder()

    def test_non_numeric_team_number_is_a_placeholder(self):
        assert SummarySheet(problem_letter="C", team_control_number="XXXXXXX").is_placeholder()

    def test_real_control_number_passes(self):
        assert not SummarySheet(problem_letter="C", team_control_number="2307166").is_placeholder()
