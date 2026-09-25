"""实验的创建与运行。

这是一次真实用户端走查查出来的：实验页只在**列出**已有实验，
空项目下就是一句"还没有定义实验"，没有任何新建入口；后端也只有
"运行"没有"创建"。新用户因此永远跑不出第一个结果，整条
"结果追踪"链在最开头就断了。

这组测试保证"能建出第一个实验"不再退化。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mcmcore.api import create_app
from mcmcore.store import Store
from mcmcore.templates import TemplateRegistry, default_registry_root


def _client(td: str, name: str = "exp"):
    from fastapi.testclient import TestClient

    root = Path(td) / name
    Store.init(root, name)
    return TestClient(create_app(root))


class TestCreateExperiment:
    def test_list_available_templates(self) -> None:
        """面板的下拉要用它；空的话用户选不到模板。"""
        reg = TemplateRegistry(default_registry_root()).load_strict()
        exps = [t for t in reg.all() if getattr(t.kind, "value", t.kind) == "experiment"]
        assert len(exps) >= 9, f"只有 {len(exps)} 个实验模板"

    def test_create_minimal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments", json={"label": "敏感性", "kind": "sensitivity_oat"})
            assert r.status_code == 200, r.text
            assert r.json()["experiment"]["id"] == "EXP-001"
            assert len(c.get("/api/experiments").json()) == 1

    def test_ids_increment(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            for i in (1, 2, 3):
                r = c.post("/api/experiments", json={"label": f"e{i}", "kind": "other"})
                assert r.json()["experiment"]["id"] == f"EXP-{i:03d}"

    def test_varied_parsed_into_trials(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments", json={
                "label": "sweep", "kind": "sensitivity_oat",
                "varied": [{"name": "w", "values": [0.1, 0.5, 1.0]}],
            })
            assert r.status_code == 200, r.text
            trials = c.get("/api/experiments/EXP-001/trials").json()
            assert len(trials) == 3

    def test_varied_without_values_rejected(self) -> None:
        """没有取值的话实验只会跑一次，出图也没有横轴。"""
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments", json={
                "label": "x", "kind": "other", "varied": [{"name": "w"}],
            })
            assert r.status_code == 422
            assert "取值" in r.json()["detail"]

    def test_bad_kind_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments", json={"label": "x", "kind": "编的"})
            assert r.status_code == 422
            assert "不认识" in r.json()["detail"]

    def test_duplicate_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            c.post("/api/experiments", json={"label": "a", "kind": "other", "id": "EXP-009"})
            r = c.post("/api/experiments", json={"label": "b", "kind": "other", "id": "EXP-009"})
            assert r.status_code == 409


class TestExperimentTemplates:
    """每个实验模板都要能用来建出实验。

    踩过的坑：模板的 defaults 里有 schema 不认识的键（dispersion_kind），
    而 schema 是 extra="forbid"，直接透传会让**整个模板**建不出来。
    """

    def _tpl_ids(self) -> list:
        reg = TemplateRegistry(default_registry_root()).load_strict()
        return sorted(t.template_id for t in reg.all()
                      if getattr(t.kind, "value", t.kind) == "experiment")

    def test_every_template_creates(self) -> None:
        ids = self._tpl_ids()
        assert ids, "一个实验模板都没有"
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            for tpl in ids:
                r = c.post("/api/experiments", json={"label": tpl, "template_id": tpl})
                assert r.status_code == 200, f"{tpl} 建不出来：{r.text}"

    def test_template_sets_its_own_kind(self) -> None:
        """套了模板就不该还是 other，否则默认出图会跑偏。"""
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments",
                       json={"label": "mc", "template_id": "exp.monte_carlo"})
            assert r.json()["experiment"]["kind"] == "monte_carlo"

    def test_template_defaults_apply(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments",
                       json={"label": "cv", "template_id": "exp.cross_validation"})
            assert r.json()["experiment"]["n_folds"] == 5

    def test_unknown_template_404(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments",
                       json={"label": "x", "template_id": "exp.根本没有"})
            assert r.status_code == 404
            assert "没有这个实验模板" in r.json()["detail"]

    def test_non_experiment_template_rejected(self) -> None:
        """拿图模板当实验模板用，要说清楚而不是崩掉。"""
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments",
                       json={"label": "x", "template_id": "fig.bar_comparison"})
            assert r.status_code == 422
            assert "不是实验模板" in r.json()["detail"]

    def test_user_varied_wins_over_template(self) -> None:
        """用户填了变动轴，就不该被模板默认值盖掉。"""
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            r = c.post("/api/experiments", json={
                "label": "x", "template_id": "exp.monte_carlo",
                "varied": [{"name": "k", "values": [1, 2]}],
            })
            assert r.status_code == 200, r.text
            assert r.json()["experiment"]["varied"][0]["name"] == "k"


class TestDeleteExperiment:
    def test_delete_clean_experiment(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            c.post("/api/experiments", json={"label": "a", "kind": "other"})
            assert c.delete("/api/experiments/EXP-001").status_code == 200
            assert c.get("/api/experiments").json() == []

    def test_delete_missing_404(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            assert c.delete("/api/experiments/EXP-999").status_code == 404

    def test_cannot_delete_experiment_with_runs(self) -> None:
        """跑过的实验直接删会让结果原子变成孤儿，审计会指向不存在的来源。"""
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            c.post("/api/experiments", json={"label": "a", "kind": "other"})
            exp = c.get("/api/experiments/EXP-001").json()
            exp["run_ids"] = ["RUN-001-001"]
            Path(td, "exp", "experiments", "EXP-001", "experiment.yaml").write_text(
                __import__("yaml").safe_dump(exp), encoding="utf-8")
            r = c.delete("/api/experiments/EXP-001")
            assert r.status_code == 409
            assert "运行记录" in r.json()["detail"]


class TestRunNeedsEntrypoint:
    def test_run_without_entrypoint_explains_how_to_fix(self) -> None:
        """报错要告诉用户补什么，而不是只说"没有 entrypoint"。"""
        with tempfile.TemporaryDirectory() as td:
            c = _client(td)
            c.post("/api/experiments", json={"label": "a", "kind": "other"})
            r = c.post("/api/experiments/EXP-001/run")
            assert r.status_code >= 400
            msg = r.json()["detail"]
            assert "entrypoint" in msg
            assert "run.py:run" in msg


class TestRunContract:
    """运行脚本的返回值契约。

    这是用户最容易写错的地方：直觉上想返回 `{"score": 0.79}`，
    但那样会**静默产生 0 个结果原子** —— 实验显示"成功"，
    结果页却是空的。指南里给的模板必须和这里一致。
    """

    def _project_with_script(self, td: str, body: str):
        from fastapi.testclient import TestClient

        root = Path(td) / "p"
        Store.init(root, "contract")
        c = TestClient(create_app(root))
        c.post("/api/problems", json={"letter": "C", "title": "T"})
        c.post("/api/project/lock", json={"problem_id": "PROB-C"})
        c.post("/api/experiments", json={
            "label": "契约", "kind": "sensitivity_oat",
            "varied": [{"name": "w", "values": [0.1, 0.5]}],
        })
        d = root / "experiments" / "EXP-001"
        (d / "run.py").write_text(body, encoding="utf-8")
        y = d / "experiment.yaml"
        y.write_text(y.read_text().replace(
            "entrypoint: null", "entrypoint: experiments/EXP-001/run.py:run"),
            encoding="utf-8")
        return c

    def test_atoms_shape_produces_result_atoms(self) -> None:
        """指南里给用户的写法，必须真的产出原子。"""
        with tempfile.TemporaryDirectory() as td:
            c = self._project_with_script(td, (
                "def run(trial):\n"
                "    w = trial['w']\n"
                "    return {'atoms': [\n"
                "        {'name': 'score', 'value': 1.0 / (1.0 + w),\n"
                "         'macro_alias': 'score'},\n"
                "    ]}\n"
            ))
            r = c.post("/api/experiments/EXP-001/run")
            assert r.status_code in (200, 202), r.text
            results = c.get("/api/results").json()
            atoms = results if isinstance(results, list) else results.get("atoms", [])
            assert len(atoms) == 2, f"应该产出 2 个原子，实际 {len(atoms)}"

    def test_flat_dict_silently_produces_nothing(self) -> None:
        """平铺 dict 不会产出原子 —— 这正是要在文档里写清楚的原因。

        实验状态是 success，用户不会收到任何报错，结果页却是空的。
        """
        with tempfile.TemporaryDirectory() as td:
            c = self._project_with_script(td, (
                "def run(trial):\n"
                "    return {'score': 1.0 / (1.0 + trial['w'])}\n"
            ))
            c.post("/api/experiments/EXP-001/run")
            results = c.get("/api/results").json()
            atoms = results if isinstance(results, list) else results.get("atoms", [])
            assert len(atoms) == 0, "平铺 dict 不该产出原子"

    def test_list_shape_also_works(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            c = self._project_with_script(td, (
                "def run(trial):\n"
                "    return [{'name': 'score', 'value': trial['w']}]\n"
            ))
            c.post("/api/experiments/EXP-001/run")
            results = c.get("/api/results").json()
            atoms = results if isinstance(results, list) else results.get("atoms", [])
            assert len(atoms) == 2

    def test_bad_direction_is_reported(self) -> None:
        """direction 写错要能查出来，而不是静默丢掉。"""
        with tempfile.TemporaryDirectory() as td:
            c = self._project_with_script(td, (
                "def run(trial):\n"
                "    return {'atoms': [{'name': 's', 'value': 1.0,\n"
                "                       'direction': 'higher_better'}]}\n"
            ))
            c.post("/api/experiments/EXP-001/run")
            runs = c.get("/api/runs").json()
            runs = runs if isinstance(runs, list) else runs.get("runs", [])
            assert any(r.get("status") == "failed" for r in runs), \
                "非法 direction 应该让这次运行失败"

    def test_whole_dict_is_passed_as_one_argument(self) -> None:
        """fn(dict(trial))：整份参数字典作为**一个**参数传入。"""
        with tempfile.TemporaryDirectory() as td:
            c = self._project_with_script(td, (
                "def run(trial):\n"
                "    # 位置参数形式，展开关键字会 TypeError\n"
                "    return {'atoms': [{'name': 'k', 'value': trial['w']}]}\n"
            ))
            r = c.post("/api/experiments/EXP-001/run")
            assert r.status_code in (200, 202)
            runs = c.get("/api/runs").json()
            runs = runs if isinstance(runs, list) else runs.get("runs", [])
            assert all(r.get("status") == "success" for r in runs), \
                f"有运行失败：{[r.get('status') for r in runs]}"
