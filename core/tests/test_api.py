"""Phase 4 tests: the API layer and the strict submission gate.

Two properties matter more than the rest and are tested directly:

1. **No endpoint can write a ResultAtom.** The architecture doc states this as a
   hard constraint, and it is what makes the single source of truth
   trustworthy: if an HTTP client could edit a result, the number in the paper
   would stop being the number the experiment produced.
2. **The strict gate agrees with the auditor.** A gate that can say "submit"
   while the auditor says "not ready" is worse than no gate.
"""

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from mcmcore.api import create_app  # noqa: E402
from mcmcore.runner import mark_stale, stale_artifacts  # noqa: E402
from mcmcore.schemas import (  # noqa: E402
    ArtifactBinding,
    Experiment,
    ExperimentKind,
    Figure,
    Parameter,
    ResultAtom,
    Varied,
)
from mcmcore.state import build_overview  # noqa: E402
from mcmcore.store import Store  # noqa: E402
from mcmcore.validate import audit_project  # noqa: E402


EXP_SCRIPT = '''
def run(params):
    beta = params.get("beta") or 0.1
    return {"atoms": [
        {"name": "peak", "value": beta * 1000, "unit": "count", "format": "%.1f"},
    ]}
'''


@pytest.fixture()
def project(tmp_path):
    """A small but real project: model, experiment, script, bound figure."""
    st = Store.init(tmp_path, "api-test")

    script = st.root / "experiments" / "e.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(EXP_SCRIPT, encoding="utf-8")

    # 参数现在住在项目级的 params/ 里，不再挂在 Model 下面。
    st.params.upsert(Parameter(id="P1", name="gamma", value=0.0177, source="fitted"))

    st.save_experiment(Experiment(
        id="EXP-001", kind=ExperimentKind.SENSITIVITY_OAT,         varied=[Varied(name="beta", values=[0.1, 0.2])],
        held_fixed=["gamma"], entrypoint="experiments/e.py:run",
    ))
    return st


@pytest.fixture()
def client(project):
    return TestClient(create_app(project.root))


# --------------------------------------------------------------------------
# The hard constraint
# --------------------------------------------------------------------------


class TestResultsAreNotWritable:
    """No endpoint may mutate a ResultAtom."""

    def test_no_route_writes_results(self, project):
        app = create_app(project.root)
        offenders = []
        for r in app.routes:
            if not hasattr(r, "methods"):
                continue
            writes = set(r.methods) & {"POST", "PUT", "PATCH", "DELETE"}
            if writes and "results" in str(r.path):
                offenders.append((sorted(writes), str(r.path)))
        assert offenders == [], f"result-writing routes exist: {offenders}"

    def test_put_on_an_atom_is_rejected(self, client, project):
        project.append_atoms([ResultAtom(atom_id="R1", name="x", value=1)])
        r = client.put("/api/results/R1", json={"value": 999})
        assert r.status_code in (404, 405)
        assert client.get("/api/results/R1").json()["value"] == 1

    def test_post_to_results_is_rejected(self, client):
        assert client.post("/api/results", json={"atom_id": "X"}).status_code in (404, 405)


# --------------------------------------------------------------------------
# Read endpoints
# --------------------------------------------------------------------------


class TestReadEndpoints:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_state_shape(self, client):
        d = client.get("/api/state").json()
        for key in ("phase", "problem", "counts", "steps", "blockers"):
            assert key in d
        assert isinstance(d["steps"], list) and d["steps"]

    def test_state_phase_starts_at_problem_selection(self, client):
        assert client.get("/api/state").json()["phase"] == "problem_selection"

    def test_step_status_tracks_content(self, client):
        """fixture 里定义了参数和实验，别的都没有。"""
        d = client.get("/api/state").json()
        by_key = {s["key"]: s["status"] for s in d["steps"]}
        assert by_key["params"] == "done"
        assert by_key["experiments"] == "done"
        for key in ("data", "results", "paper"):
            assert by_key[key] == "todo", key

    def test_params_endpoint(self, client):
        d = client.get("/api/params").json()
        assert [p["name"] for p in d["parameters"]] == ["gamma"]

    def test_math_endpoint(self, client):
        d = client.get("/api/math").json()
        assert "symbols" in d and "summary" in d

    def test_put_param_rejects_a_bad_source_with_422(self, client):
        r = client.put("/api/params/beta", json={"value": 0.1, "source": "瞎写的"})
        assert r.status_code == 422
        assert "无效" in r.json()["detail"]

    def test_missing_experiment_endpoint_is_404(self, client):
        assert client.get("/api/experiments/NOPE").status_code == 404

    def test_missing_experiment_is_404(self, client):
        assert client.get("/api/experiments/NOPE").status_code == 404

    def test_missing_result_is_404(self, client):
        assert client.get("/api/results/NOPE").status_code == 404

    def test_trials_expands_the_protocol(self, client):
        rows = client.get("/api/experiments/EXP-001/trials").json()
        assert len(rows) == 2
        assert rows[0]["index"] == 1
        assert "beta=0.1" in rows[0]["condition"]

    def test_trials_carry_resolved_held_values(self, client):
        rows = client.get("/api/experiments/EXP-001/trials").json()
        assert "gamma=0.0177(fixed)" in rows[0]["condition"]

    def test_notations_is_never_exhaustive(self, client):
        """All 56% of papers with a notation table call it non-exhaustive."""
        d = client.get("/api/notations").json()
        assert d["exhaustive"] is False
        assert d["disclaimer"]

    def test_paper_and_budget(self, client):
        assert client.get("/api/paper").status_code == 200
        b = client.get("/api/paper/budget").json()
        assert "budget" in b and "pages" in b

    def test_audit_returns_a_verdict(self, client):
        d = client.post("/api/audit").json()
        assert d["verdict"]
        assert "summary" in d


# --------------------------------------------------------------------------
# Mutating endpoints return consequences
# --------------------------------------------------------------------------


class TestMutationReturnsFindings:
    """Every mutating endpoint returns the affected findings (doc constraint 3)."""

    def test_lock_problem_returns_findings(self, client):
        r = client.post("/api/project/lock",
                        json={"problem_id": "PROB-2025-A", "team_number": "2400996"})
        assert r.status_code == 200
        assert "findings" in r.json()
        assert r.json()["project"]["locked_problem_id"] == "PROB-2025-A"

    def test_lock_moves_phase_to_build(self, client):
        client.post("/api/project/lock", json={"problem_id": "PROB-2025-A"})
        assert client.get("/api/state").json()["phase"] == "build"

    def test_put_param_returns_findings(self, client):
        r = client.put("/api/params/gamma", json={"value": 0.02, "source": "fitted"})
        assert r.status_code == 200
        assert "findings" in r.json()

    def test_put_symbol_returns_findings(self, client):
        r = client.put("/api/math/symbols/SYM-001",
                       json={"glyph": "beta", "meaning": "传播率"})
        assert r.status_code == 200
        assert r.json()["symbol"]["glyph"] == "beta"

    def test_put_symbol_rejects_a_blank_glyph_with_422(self, client):
        """schema 校验失败要返回 422 加原因，而不是 500。"""
        r = client.put("/api/math/symbols/SYM-001",
                       json={"glyph": "   ", "meaning": "x"})
        assert r.status_code == 422

    def test_put_section_returns_findings(self, client, project):
        from mcmcore.schemas import Paper, PaperSection, SectionKind

        project.save_paper(Paper(sections=[
            PaperSection(id="SEC-010", kind=SectionKind.INTRODUCTION,
                         title="Intro", order=10, body="x"),
        ]))
        r = client.put("/api/paper/sections/SEC-010", json={"title": "Renamed"})
        assert r.status_code == 200
        assert r.json()["section"]["title"] == "Renamed"
        assert "findings" in r.json()

    def test_put_unknown_section_is_404(self, client):
        assert client.put("/api/paper/sections/NOPE", json={"title": "x"}).status_code == 404

    def test_ai_usage_returns_findings(self, client):
        r = client.post("/api/paper/ai-usage", json={"ai_used": True})
        assert r.status_code == 200
        assert "findings" in r.json()

    def test_ai_usage_recomputes_compliance(self, client):
        """Recording AI use without a disclosure section must produce an error."""
        r = client.post("/api/paper/ai-usage", json={"ai_used": True})
        codes = [f["code"] for f in r.json()["findings"]["errors"]]
        assert "AI_USE_UNDISCLOSED" in codes


# --------------------------------------------------------------------------
# The run pipeline through the API
# --------------------------------------------------------------------------


class TestRunEndpoint:
    def test_dry_run_produces_trials_and_no_atoms(self, client, project):
        r = client.post("/api/experiments/EXP-001/run", json={"dry_run": True})
        assert r.status_code == 202
        assert project.load_atoms() == []

    def test_real_run_produces_atoms(self, client, project):
        r = client.post("/api/experiments/EXP-001/run", json={})
        assert r.status_code == 202
        d = r.json()
        assert len(d["runs"]) == 2
        assert len(d["atoms"]) == 2
        assert len(project.load_atoms()) == 2

    def test_run_reports_findings(self, client):
        d = client.post("/api/experiments/EXP-001/run", json={}).json()
        assert d["findings"] is not None

    def test_run_on_missing_experiment_is_404(self, client):
        assert client.post("/api/experiments/NOPE/run", json={}).status_code == 404

    def test_run_missing_entrypoint_is_422(self, client, project):
        e = project.load_experiment("EXP-001")
        e.entrypoint = None
        project.save_experiment(e)
        assert client.post("/api/experiments/EXP-001/run", json={}).status_code == 422

    def test_rerun_is_stable(self, client, project):
        client.post("/api/experiments/EXP-001/run", json={})
        d = client.post("/api/experiments/EXP-001/run", json={}).json()
        assert d["changed_atoms"] == []
        assert d["stale"] == {"figures": [], "tables": []}

    def test_results_endpoint_filters_by_experiment(self, client):
        client.post("/api/experiments/EXP-001/run", json={})
        rows = client.get("/api/experiments/EXP-001/results").json()
        assert len(rows) == 2
        assert all(r["experiment_id"] == "EXP-001" for r in rows)

    def test_changed_parameter_makes_figure_stale(self, client, project):
        client.post("/api/experiments/EXP-001/run", json={})
        ids = [a.atom_id for a in project.load_atoms()]
        project.save_figure(Figure(
            id="FIG-01", status="generated",
            bindings=[ArtifactBinding(atom_id=i) for i in ids],
        ))

        # 改参数现在直接打 /api/params/{name}，不再通过模型层。
        r = client.put("/api/params/gamma", json={"value": 0.09, "source": "fitted"})
        assert r.status_code == 200

        d = client.post("/api/experiments/EXP-001/run", json={}).json()
        assert d["stale"]["figures"] == ["FIG-01"]


# --------------------------------------------------------------------------
# Staleness and regeneration
# --------------------------------------------------------------------------


class TestStaleEndpoints:
    def test_stale_listing_empty_initially(self, client):
        d = client.get("/api/figures/stale").json()
        assert d == {"figures": [], "tables": []}

    def test_stale_listing_after_a_change(self, client, project):
        project.append_atoms([ResultAtom(atom_id="R1", name="x", value=1)])
        project.save_figure(Figure(
            id="FIG-01", status="generated",
            bindings=[ArtifactBinding(atom_id="R1")],
        ))
        mark_stale(project, ["R1"])
        d = client.get("/api/figures/stale").json()
        assert [f["id"] for f in d["figures"]] == ["FIG-01"]

    def test_regenerate_unknown_figure_is_404(self, client):
        assert client.post("/api/figures/NOPE/regenerate", json={}).status_code == 404

    def test_regenerate_clears_stale(self, client, project):
        project.append_atoms([ResultAtom(atom_id="R1", name="peak", value=5.0,
                                         unit="x", condition="beta=0.1")])
        project.save_figure(Figure(
            id="FIG-01", template_id="fig.bar_comparison", status="stale",
            caption="c", bindings=[ArtifactBinding(atom_id="R1", role="y")],
        ))
        r = client.post("/api/figures/FIG-01/regenerate", json={"only_stale": True})
        assert r.status_code == 200
        assert r.json()["regenerated"] == ["FIG-01"]
        assert r.json()["still_stale"] == []


# --------------------------------------------------------------------------
# The strict gate
# --------------------------------------------------------------------------


class TestStrictGate:
    def test_gate_reports_readiness(self, client):
        d = client.get("/api/audit/strict").json()
        assert "ready_to_submit" in d
        assert isinstance(d["strict_codes"], list) and d["strict_codes"]

    def test_gate_agrees_with_the_auditor(self, client, project):
        """A gate that says 'submit' while the auditor says 'not ready' is broken."""
        gate = client.get("/api/audit/strict").json()
        report = audit_project(project)
        if report.errors:
            assert gate["ready_to_submit"] is False

    def test_stale_figure_blocks_submission(self, client, project):
        project.append_atoms([ResultAtom(atom_id="R1", name="x", value=1)])
        project.save_figure(Figure(
            id="FIG-01", status="generated",
            bindings=[ArtifactBinding(atom_id="R1")],
        ))
        mark_stale(project, ["R1"])

        gate = client.get("/api/audit/strict").json()
        assert gate["ready_to_submit"] is False
        assert "FIG_STALE" in [f["code"] for f in gate["promoted_warnings"]]

    def test_audit_detects_staleness_independently(self, project):
        """The auditor must not rely on a build having been run."""
        project.append_atoms([ResultAtom(atom_id="R1", name="x", value=1)])
        project.save_figure(Figure(
            id="FIG-01", status="generated",
            bindings=[ArtifactBinding(atom_id="R1")],
        ))
        mark_stale(project, ["R1"])
        rep = audit_project(project)
        assert any(f.code == "FIG_STALE" for f in rep.findings)

    def test_incomplete_project_is_not_submittable(self, client):
        """An empty paper is genuinely not submittable, and the gate says so."""
        gate = client.get("/api/audit/strict").json()
        assert gate["ready_to_submit"] is False
        codes = [f["code"] for f in gate["errors"]]
        assert "SUMMARY_PLACEHOLDER" in codes
        assert "MISSING_REFERENCES" in codes

    def test_gate_explains_every_refusal(self, client):
        """A refusal with no listed reason is unusable."""
        gate = client.get("/api/audit/strict").json()
        if not gate["ready_to_submit"]:
            assert gate["errors"] or gate["promoted_warnings"]


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


class TestExport:
    def test_pdf_export_404_without_a_build(self, client):
        r = client.get("/api/export/pdf")
        assert r.status_code == 404
        assert "build" in r.json()["detail"]

    def test_bundle_is_a_valid_zip(self, client):
        import io
        import zipfile

        r = client.get("/api/export/bundle")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert zf.testzip() is None
        names = zf.namelist()
        assert "audit.json" in names
        assert "README.txt" in names
        audit = json.loads(zf.read("audit.json"))
        assert "verdict" in audit and "findings" in audit


# --------------------------------------------------------------------------
# Overview payload (Core, shared by CLI and API)
# --------------------------------------------------------------------------


class TestOverview:
    def test_counts_are_computed_not_declared(self, project):
        project.append_atoms([ResultAtom(atom_id="R1", name="x", value=1)])
        ov = build_overview(project)
        assert ov.counts["result_atoms"] == 1

    def test_every_blocker_has_an_action(self, project):
        """A blocker without a next action is a complaint, not a blocker."""
        project.append_atoms([ResultAtom(atom_id="R1", name="x", value=1)])
        project.save_figure(Figure(
            id="FIG-01", status="generated",
            bindings=[ArtifactBinding(atom_id="R1")],
        ))
        mark_stale(project, ["R1"])
        ov = build_overview(project, audit_project(project))
        assert ov.blockers, "expected at least the stale figure"
        for b in ov.blockers:
            assert b.action, f"blocker {b.code} has no action"
            assert b.message

    def test_errors_sort_before_warnings(self, project):
        project.append_atoms([ResultAtom(atom_id="R1", name="x", value=1)])
        project.save_figure(Figure(
            id="FIG-01", status="generated",
            bindings=[ArtifactBinding(atom_id="R1")],
        ))
        mark_stale(project, ["R1"])
        ov = build_overview(project, audit_project(project))
        sevs = [b.severity for b in ov.blockers]
        assert sevs == sorted(sevs, key=lambda s: 0 if s == "error" else 1)

    def test_problem_lock_reflected(self, project):
        from mcmcore.schemas import ProjectPhase

        cfg = project.layout.load_config()
        cfg.locked_problem_id = "PROB-2025-A"
        cfg.team_control_number = "2400996"
        cfg.phase = ProjectPhase.BUILD
        project.layout.save_config(cfg)

        ov = build_overview(project)
        assert ov.phase == "build"
        assert ov.problem["locked"] is True
        assert ov.problem["team_number"] == "2400996"
        assert ov.steps[0]["status"] == "done"


# --------------------------------------------------------------------------
# 生图工作台：模板清单与预览
# --------------------------------------------------------------------------


class TestWorkbench:
    def test_lists_figure_templates(self, client):
        rows = client.get("/api/templates?kind=figure").json()
        assert len(rows) >= 12
        assert all(r["template_id"].startswith("fig.") for r in rows)

    def test_every_listed_template_reports_whether_it_has_code(self, client):
        """面板要如实标出"只有说明、没有代码"的模板，
        否则用户点了预览才发现画不出来。"""
        rows = client.get("/api/templates?kind=figure").json()
        assert all(isinstance(r["has_code"], bool) for r in rows)
        assert any(r["has_code"] for r in rows)

    def test_get_one_template_declares_inputs(self, client):
        d = client.get("/api/templates/fig.sensitivity_line").json()
        assert d["template_id"] == "fig.sensitivity_line"
        names = [i["name"] for i in d["inputs"]]
        assert "x" in names and "y" in names
        assert d["has_code"] is True

    def test_unknown_template_is_404(self, client):
        assert client.get("/api/templates/fig.nope").status_code == 404

    def test_preview_returns_a_pdf(self, client):
        r = client.post("/api/templates/fig.sensitivity_line/preview",
                        json={"data": {"x": [1, 2, 3], "y": [3, 2, 1]},
                              "meta": {"caption": "测试"}})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")

    def test_preview_bad_data_is_422_with_chinese_reason(self, client):
        """数据对不上要给中文原因，不是 500 —— 工作台把它显示给用户。"""
        r = client.post("/api/templates/fig.sensitivity_line/preview",
                        json={"data": {"x": [1, 2], "y": [1, 2, 3]}})
        assert r.status_code == 422
        assert "数量必须一致" in r.json()["detail"]

    def test_preview_missing_input_is_422(self, client):
        r = client.post("/api/templates/fig.bar_comparison/preview", json={"data": {}})
        assert r.status_code == 422
        assert "categories" in r.json()["detail"]

    def test_drawio_template_returns_editable_xml(self, client):
        """流程图必须返回可编辑源文件，不是位图 —— 答辩前一定会改。"""
        r = client.post("/api/templates/fig.flowchart/preview",
                        json={"backend": "drawio",
                              "data": {"nodes": [{"id": "n1", "label": "开始"}],
                                       "edges": []}})
        assert r.status_code == 200
        assert b"<mxfile" in r.content
        assert "开始" in r.content.decode("utf-8")
