"""Phase 3 tests: the experiment runner and the staleness loop.

The most important property under test is stated once and tested from several
angles: **rerunning identical inputs must not mark anything stale**, while
changing an input must. A staleness warning that fires on every rerun is noise,
and noise gets ignored -- which is precisely the failure the mechanism exists to
prevent.
"""

import textwrap
from pathlib import Path

import pytest

from mcmcore.figures import FigureGenerator
from mcmcore.runner import (
    ExperimentRunner,
    StaleReport,
    atom_fingerprint,
    changed_atoms,
    clear_stale,
    condition_string,
    expand_trials,
    mark_stale,
    resolve_held_values,
    stale_artifacts,
)
from mcmcore.schemas import (
    ArtifactBinding,
    Experiment,
    ExperimentKind,
    Figure,
    Parameter,
    ResultAtom,
    Run,
    Table,
    Varied,
)
from mcmcore.store import Store


# --------------------------------------------------------------------------
# Atom identity
# --------------------------------------------------------------------------


class TestAtomFingerprint:
    def test_identical_content_same_fingerprint(self):
        a = ResultAtom(atom_id="R1", name="rmse", value=0.0791, condition="b=1")
        b = ResultAtom(atom_id="R1", name="rmse", value=0.0791, condition="b=1")
        assert atom_fingerprint(a) == atom_fingerprint(b)

    def test_run_id_does_not_affect_fingerprint(self):
        """A rerun must not invalidate artifacts, or the warning becomes noise."""
        a = ResultAtom(atom_id="R1", name="rmse", value=0.0791, run_id="RUN-001")
        b = ResultAtom(atom_id="R1", name="rmse", value=0.0791, run_id="RUN-002")
        assert atom_fingerprint(a) == atom_fingerprint(b)

    def test_experiment_id_does_not_affect_fingerprint(self):
        a = ResultAtom(atom_id="R1", name="x", value=1, experiment_id="E1")
        b = ResultAtom(atom_id="R1", name="x", value=1, experiment_id="E2")
        assert atom_fingerprint(a) == atom_fingerprint(b)

    @pytest.mark.parametrize("field,value", [
        ("value", 0.08),
        ("condition", "b=2"),
        ("unit", "m"),
        ("format", "%.2f"),
        ("name", "mae"),
    ])
    def test_printable_change_alters_fingerprint(self, field, value):
        base = dict(atom_id="R1", name="rmse", value=0.0791, condition="b=1")
        a = ResultAtom(**base)
        b = ResultAtom(**{**base, field: value})
        assert atom_fingerprint(a) != atom_fingerprint(b)

    def test_rendering_change_alters_fingerprint(self):
        a = ResultAtom(atom_id="R1", name="x", value=1)
        b = ResultAtom(atom_id="R1", name="x", value=1, renderings={"pct": "100\\%"})
        assert atom_fingerprint(a) != atom_fingerprint(b)


class TestChangedAtoms:
    def test_no_change(self):
        atoms = [ResultAtom(atom_id="R1", name="x", value=1)]
        assert changed_atoms(atoms, atoms) == []

    def test_value_change_detected(self):
        before = [ResultAtom(atom_id="R1", name="x", value=1)]
        after = [ResultAtom(atom_id="R1", name="x", value=2)]
        assert changed_atoms(before, after) == ["R1"]

    def test_added_atom_detected(self):
        before = [ResultAtom(atom_id="R1", name="x", value=1)]
        after = before + [ResultAtom(atom_id="R2", name="y", value=2)]
        assert changed_atoms(before, after) == ["R2"]

    def test_removed_atom_detected(self):
        before = [ResultAtom(atom_id="R1", name="x", value=1)]
        assert changed_atoms(before, []) == ["R1"]


# --------------------------------------------------------------------------
# Staleness
# --------------------------------------------------------------------------


class TestMarkStale:
    def _store_with_figure(self, tmp_path, atom_ids):
        st = Store.init(tmp_path, "t")
        st.append_atoms([
            ResultAtom(atom_id=a, name=a.lower(), value=1, unit="-")
            for a in atom_ids
        ])
        st.save_figure(Figure(
            id="FIG-01", bindings=[ArtifactBinding(atom_id=a) for a in atom_ids],
            status="generated",
        ))
        return st

    def test_bound_figure_becomes_stale(self, tmp_path):
        st = self._store_with_figure(tmp_path, ["R1"])
        rep = mark_stale(st, ["R1"])
        assert rep.stale_figures == ["FIG-01"]
        assert st.load_figure("FIG-01").status.value == "stale"

    def test_unbound_figure_unaffected(self, tmp_path):
        st = self._store_with_figure(tmp_path, ["R1"])
        rep = mark_stale(st, ["R99"])
        assert rep.stale_figures == []
        assert st.load_figure("FIG-01").status.value == "generated"

    def test_empty_change_marks_nothing(self, tmp_path):
        st = self._store_with_figure(tmp_path, ["R1"])
        rep = mark_stale(st, [])
        assert rep.total == 0
        assert rep.summary() == "no results changed; nothing is stale"

    def test_table_becomes_stale_via_cell_binding(self, tmp_path):
        st = Store.init(tmp_path, "t")
        st.append_atoms([ResultAtom(atom_id="R1", name="x", value=1, unit="-")])
        st.save_table(Table(
            id="TAB-01", columns=[{"header": "v", "atom_id": "R1"}],
            status="generated",
        ))
        rep = mark_stale(st, ["R1"])
        assert rep.stale_tables == ["TAB-01"]

    def test_stale_artifacts_query(self, tmp_path):
        st = self._store_with_figure(tmp_path, ["R1"])
        mark_stale(st, ["R1"])
        figs, tabs = stale_artifacts(st)
        assert [f.id for f in figs] == ["FIG-01"]

    def test_clear_stale_resets_status(self, tmp_path):
        st = self._store_with_figure(tmp_path, ["R1"])
        mark_stale(st, ["R1"])
        n = clear_stale(st)
        assert n == 1
        assert st.load_figure("FIG-01").status.value == "generated"

    def test_summary_mentions_counts(self, tmp_path):
        st = self._store_with_figure(tmp_path, ["R1"])
        rep = mark_stale(st, ["R1"])
        assert "1 figure" in rep.summary()


# --------------------------------------------------------------------------
# Protocol expansion
# --------------------------------------------------------------------------


class TestExpandTrials:
    def test_oat_yields_one_trial_per_value(self):
        e = Experiment(
            id="E", kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[Varied(name="beta", values=[0.1, 0.2, 0.3])],
            held_fixed=["gamma"],
        )
        trials = expand_trials(e)
        assert [t["beta"] for t in trials] == [0.1, 0.2, 0.3]

    def test_grid_yields_cartesian_product(self):
        e = Experiment(
            id="E", kind=ExperimentKind.SENSITIVITY_GRID,
            varied=[Varied(name="a", values=[1, 2, 3]), Varied(name="b", values=[10, 20])],
        )
        assert len(expand_trials(e)) == 6

    def test_oat_with_two_axes_flattens_to_one_at_a_time(self):
        """OAT means one axis at a time, holding the others at their first value."""
        e = Experiment(
            id="E", kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[Varied(name="a", values=[1, 2]), Varied(name="b", values=[3, 4])],
            held_fixed=["c"],
        )
        trials = expand_trials(e)
        assert len(trials) == 4
        # Each trial varies exactly one of a/b away from its base value.
        bases = {"a": 1, "b": 3}
        for t in trials:
            moved = [k for k in ("a", "b") if t[k] != bases[k]]
            assert len(moved) <= 1

    def test_range_with_step_inclusive(self):
        e = Experiment(
            id="E", kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[Varied(name="x", range=[0.0, 1.0], step=0.25)],
        )
        assert [t["x"] for t in expand_trials(e)] == [0.0, 0.25, 0.5, 0.75, 1.0]

    def test_no_varied_axis_yields_one_default_trial(self):
        e = Experiment(id="E", kind=ExperimentKind.SCENARIO)
        assert expand_trials(e) == [{}]

    def test_held_values_resolved_from_params(self):
        """固定值从项目参数区解析 —— 模型层没了也一样能用。"""
        params = [Parameter(id="P1", name="gamma", value=0.0177)]
        e = Experiment(
            id="E", kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[Varied(name="beta", values=[0.1])], held_fixed=["gamma"],
        )
        trials = expand_trials(e, params)
        assert trials[0]["gamma"] == 0.0177

    def test_held_values_none_without_params(self):
        e = Experiment(
            id="E", kind=ExperimentKind.SENSITIVITY_OAT,
            varied=[Varied(name="b", values=[1])], held_fixed=["gamma"],
        )
        assert expand_trials(e)[0]["gamma"] is None

    def test_unresolvable_held_name_is_none_not_error(self):
        """固定了一个参数表里没有的名字：记 None，不报错。

        要求协议里每个名字都能解析出来太严了 —— 有些量本来就是
        符号而非参数。
        """
        vals = resolve_held_values(
            Experiment(id="E", held_fixed=["nonexistent"]), []
        )
        assert vals == {"nonexistent": None}


class TestConditionString:
    def test_names_varied_and_marks_fixed(self):
        s = condition_string({"beta": 0.1, "gamma": 0.0177}, ["beta"], ["gamma"])
        assert "beta=0.1" in s
        assert "gamma=0.0177(fixed)" in s

    def test_omits_none_values(self):
        s = condition_string({"beta": 0.1, "gamma": None}, ["beta"], ["gamma"])
        assert "gamma" not in s

    def test_empty_is_default(self):
        assert condition_string({}, [], []) == "default"

    def test_scientific_notation_for_very_small_values(self):
        s = condition_string({"lambda": 1.04e-03}, ["lambda"], [])
        assert "1.04e-03" in s

    def test_plain_decimal_for_mid_range_values(self):
        """0.0177 is more readable than 1.77e-02, so %g wins above the cutoff."""
        assert condition_string({"g": 1.77e-02}, ["g"], []) == "g=0.0177"


# --------------------------------------------------------------------------
# The runner
# --------------------------------------------------------------------------


EXP_SCRIPT = '''
def run(params):
    beta = params.get("beta") or 0.1
    return {"atoms": [
        {"name": "peak", "value": beta * 1000, "unit": "count", "format": "%.1f"},
    ]}
'''


def _project_with_experiment(tmp_path, body=EXP_SCRIPT, values=(0.1, 0.2)):
    st = Store.init(tmp_path, "run-test")
    script = st.root / "experiments" / "e.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(body, encoding="utf-8")

    # 参数现在住在项目级的 params/ 里，不再挂在 Model 下面。
    st.params.upsert(Parameter(id="P1", name="gamma", value=0.0177, source="fitted"))

    st.save_experiment(Experiment(
        id="EXP-001", kind=ExperimentKind.SENSITIVITY_OAT,         varied=[Varied(name="beta", values=list(values))],
        held_fixed=["gamma"],
        entrypoint="experiments/e.py:run",
    ))
    return st


class TestRunner:
    def test_runs_and_records_atoms(self, tmp_path):
        st = _project_with_experiment(tmp_path)
        out = ExperimentRunner(st).run("EXP-001")
        assert out.ok, out.error
        assert len(out.runs) == 2
        assert len(out.atoms) == 2

    def test_atom_ids_are_stable_across_reruns(self, tmp_path):
        """Regression: hashing the condition made reruns accumulate atoms."""
        st = _project_with_experiment(tmp_path)
        r = ExperimentRunner(st)
        r.run("EXP-001")
        first = {a.atom_id for a in st.load_atoms()}
        r.run("EXP-001")
        second = {a.atom_id for a in st.load_atoms()}
        assert first == second

    def test_rerun_with_identical_inputs_marks_nothing_stale(self, tmp_path):
        """The property that keeps the stale warning meaningful."""
        st = _project_with_experiment(tmp_path)
        r = ExperimentRunner(st)
        r.run("EXP-001")
        out = r.run("EXP-001")
        assert out.changed == []
        assert out.stale.total == 0

    def test_changed_input_invalidates_bound_figure(self, tmp_path):
        st = _project_with_experiment(tmp_path)
        r = ExperimentRunner(st)
        r.run("EXP-001")

        # Bind a figure to the produced atoms, then change an input.
        ids = [a.atom_id for a in st.load_atoms()]
        st.save_figure(Figure(
            id="FIG-01", bindings=[ArtifactBinding(atom_id=i) for i in ids],
            status="generated",
        ))
        st.save_experiment(Experiment(
            id="EXP-001", kind=ExperimentKind.SENSITIVITY_OAT,             varied=[Varied(name="beta", values=[0.9, 0.95])],
            held_fixed=["gamma"], entrypoint="experiments/e.py:run",
        ))
        out = r.run("EXP-001")
        assert out.changed
        assert out.stale.stale_figures == ["FIG-01"]

    def test_dry_run_writes_nothing(self, tmp_path):
        st = _project_with_experiment(tmp_path)
        out = ExperimentRunner(st).run("EXP-001", dry_run=True)
        assert out.ok
        assert st.load_atoms() == []
        assert st.load_runs() == []

    def test_missing_entrypoint_is_a_clean_error(self, tmp_path):
        st = _project_with_experiment(tmp_path)
        e = st.load_experiment("EXP-001")
        e.entrypoint = None
        st.save_experiment(e)
        out = ExperimentRunner(st).run("EXP-001")
        assert not out.ok
        assert "entrypoint" in (out.error or "")

    def test_missing_script_is_a_clean_error(self, tmp_path):
        st = _project_with_experiment(tmp_path)
        e = st.load_experiment("EXP-001")
        e.entrypoint = "experiments/ghost.py:run"
        st.save_experiment(e)
        out = ExperimentRunner(st).run("EXP-001")
        assert not out.ok
        assert "not found" in (out.error or "")

    def test_failing_trial_is_recorded_not_crashed(self, tmp_path):
        body = "def run(p):\n    raise ValueError('boom')\n"
        st = _project_with_experiment(tmp_path, body=body)
        out = ExperimentRunner(st).run("EXP-001")
        assert out.ok  # the runner survived
        failed = [r for r in out.runs if r.status.value == "failed"]
        assert len(failed) == 2
        assert "boom" in (failed[0].stderr_tail or "")

    def test_failed_run_writes_a_traceback_log(self, tmp_path):
        body = "def run(p):\n    raise ValueError('boom')\n"
        st = _project_with_experiment(tmp_path, body=body)
        out = ExperimentRunner(st).run("EXP-001")
        logs = list((st.root / "results" / "logs").glob("*.log"))
        assert logs, "no traceback log written for a failed run"
        assert "ValueError" in logs[0].read_text()

    def test_run_records_resolved_parameters(self, tmp_path):
        st = _project_with_experiment(tmp_path)
        out = ExperimentRunner(st).run("EXP-001")
        params = out.runs[0].resolved_parameters
        assert "beta" in params and "gamma" in params

    def test_experiment_status_updated(self, tmp_path):
        st = _project_with_experiment(tmp_path)
        ExperimentRunner(st).run("EXP-001")
        assert st.load_experiment("EXP-001").status.value == "completed"

    def test_condition_carries_the_trial_parameters(self, tmp_path):
        st = _project_with_experiment(tmp_path)
        ExperimentRunner(st).run("EXP-001")
        conds = {a.condition for a in st.load_atoms()}
        assert any("beta=0.1" in c for c in conds)
        assert any("beta=0.2" in c for c in conds)

    def test_bad_return_type_is_an_error(self, tmp_path):
        st = _project_with_experiment(tmp_path, body="def run(p):\n    return 'nope'\n")
        out = ExperimentRunner(st).run("EXP-001")
        assert out.ok  # run recorded as failed, runner survived
        assert all(r.status.value == "failed" for r in out.runs)

    def test_atom_without_value_is_rejected(self, tmp_path):
        """A malformed atom must fail that run loudly, not write a null result."""
        body = 'def run(p):\n    return {"atoms": [{"name": "x"}]}\n'
        st = _project_with_experiment(tmp_path, body=body)
        out = ExperimentRunner(st).run("EXP-001")
        assert all(r.status.value == "failed" for r in out.runs)
        assert st.load_atoms() == []


# --------------------------------------------------------------------------
# Figure regeneration
# --------------------------------------------------------------------------


needs_mpl = pytest.importorskip("matplotlib")


class TestFigureGenerator:
    def _store(self, tmp_path):
        st = Store.init(tmp_path, "fig-test")
        st.append_atoms([
            ResultAtom(atom_id="R1", name="peak", value=100, unit="x",
                       condition="beta=0.1, gamma=0.02(fixed)"),
            ResultAtom(atom_id="R2", name="peak", value=200, unit="x",
                       condition="beta=0.2, gamma=0.02(fixed)"),
        ])
        st.save_figure(Figure(
            id="FIG-01", template_id="fig.sensitivity_line", status="stale",
            caption="Peak vs beta",
            bindings=[ArtifactBinding(atom_id="R1", role="y"),
                      ArtifactBinding(atom_id="R2", role="y")],
        ))
        return st

    def test_regenerate_writes_pdf_and_clears_stale(self, tmp_path):
        st = self._store(tmp_path)
        done = FigureGenerator(st).regenerate()
        assert done == ["FIG-01"]
        fig = st.load_figure("FIG-01")
        assert fig.status.value == "generated"
        assert (st.root / fig.file).exists()
        assert fig.generated_at

    def test_only_stale_by_default(self, tmp_path):
        st = self._store(tmp_path)
        f = st.load_figure("FIG-01")
        f.status = "generated"
        st.save_figure(f)
        assert FigureGenerator(st).regenerate() == []

    def test_all_flag_regenerates_everything(self, tmp_path):
        st = self._store(tmp_path)
        f = st.load_figure("FIG-01")
        f.status = "generated"
        st.save_figure(f)
        assert FigureGenerator(st).regenerate(only_stale=False) == ["FIG-01"]

    def test_unknown_template_falls_back_with_warning(self, tmp_path):
        st = self._store(tmp_path)
        f = st.load_figure("FIG-01")
        f.template_id = "fig.does_not_exist"
        st.save_figure(f)
        gen = FigureGenerator(st)
        assert gen.regenerate() == ["FIG-01"]
        # 消息在本地化时改成了中文；检查"找不到模板"这个语义仍然报出来。
        assert any("找不到模板" in w for w in gen.warnings), gen.warnings

    def test_missing_binding_does_not_crash(self, tmp_path):
        st = self._store(tmp_path)
        f = st.load_figure("FIG-01")
        f.bindings = [ArtifactBinding(atom_id="GHOST")]
        st.save_figure(f)
        gen = FigureGenerator(st)
        assert gen.regenerate() == ["FIG-01"]
