"""打包成 app 之后仍然要成立的两件事。

用户的原话是"一键部署之后打包成了桌面 app，原本的路径设置和模板存放
就失效了……路径和模板都要在 app 内可见，最好增加 app 内写程序跑数据的
功能"。所以这里盯两条链：

1. **路径可见**：程序实际在用的路径能被读出来（/api/system），
   而且它报的模板数和注册表真的加载到的一致 —— 不是另算一份。
   两份算法迟早不一致，那比不显示更糟。

2. **app 内写程序跑数据**：骨架 → 生成脚本 → 页内编辑 → 保存 → 运行
   → 出结果数字。这条链断在任何一环，"在 app 里跑数据"就是空话。

路径解析本身（root.py 的优先级、打包回退）另有 test_paths.py 盯着；
这里只测面板拿到的那个视图和端到端的动作。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def client(tmp_path):
    from fastapi.testclient import TestClient

    from mcmcore.api import create_app
    from mcmcore.store import Store

    st = Store.init(tmp_path, "app-workflow-test")
    return TestClient(create_app(st.root))


class TestSystemPaths:
    """/api/system：路径"不见了"时的第一诊断入口。"""

    def test_reports_every_path_the_ui_shows(self, client) -> None:
        d = client.get("/api/system").json()
        for key in ("repo_root", "templates_root", "templates_exists",
                    "templates_total", "templates_per_kind", "web_root",
                    "web_exists", "user_dir", "user_templates_root",
                    "project_root", "data_dir", "readonly",
                    "python", "python_version"):
            assert key in d, f"/api/system 少了 {key}"

    def test_template_count_matches_the_registry(self, client) -> None:
        """页面上的模板数必须就是注册表真正加载到的数量。

        这两者一旦对不上，用户就会看到"明明有 101 个模板，
        界面说只有 8 个"—— 而这正是路径出错时最迷惑的症状。
        """
        d = client.get("/api/system").json()
        listed = client.get("/api/templates").json()
        listed = listed if isinstance(listed, list) else listed.get("templates", [])
        assert d["templates_total"] == len(listed)

    def test_per_kind_matches_the_per_kind_endpoint(self, client) -> None:
        """分区计数必须和按 kind 查出来的条数一致。

        这里盯的是一个真实的旧 bug：分区计数一度用单数 kind 当目录名
        （figure 而不是 figures），于是除 paper/code 外全部报 0。
        """
        d = client.get("/api/system").json()
        for kind, n in (d.get("templates_per_kind") or {}).items():
            rows = client.get(f"/api/templates?kind={kind}").json()
            rows = rows if isinstance(rows, list) else rows.get("templates", [])
            assert n == len(rows), f"{kind}：/api/system 说 {n}，实际 {len(rows)}"

    def test_templates_root_really_holds_templates(self, client) -> None:
        """报出来的路径得真的存在，不能是一条看着对的字符串。"""
        import os

        d = client.get("/api/system").json()
        assert d["templates_exists"] is True
        assert d["templates_total"] > 0
        assert os.path.isdir(d["templates_root"])

    def test_user_template_dir_is_where_diy_writes(
            self, client, tmp_path, monkeypatch) -> None:
        """自定图存哪儿，路径页说的和实际写的必须是同一个地方。

        app 包内是只读的，所以自定图必须落到用户目录 —— 这两处各说
        各话的话，用户存完图会找不到它。

        这里把用户目录指到临时目录：真去写 ~/.mcmtools 会污染开发机，
        而且在沙箱里根本写不进去（那会让测试测的是权限不是逻辑）。
        """
        import os

        user_dir = tmp_path / "userdir"
        monkeypatch.setenv("MCMTOOLS_USER_DIR", str(user_dir))

        d = client.get("/api/system").json()
        # 路径页报的用户目录必须随环境变量走，而不是报一个写不进去的默认值
        assert os.path.realpath(d["user_templates_root"]) == os.path.realpath(
            str(user_dir / "templates"))
        assert os.path.realpath(d["user_dir"]) == os.path.realpath(str(user_dir))

        r = client.post("/api/diy/save", json={
            "name": "paths_check",
            "spec": {"chart": "line", "title": "t", "y": [1, 2, 3]},
        })
        assert r.status_code == 200, r.text
        # 存出来的模板确实落在路径页报的那个目录下
        written = [os.path.join(dirpath, f)
                   for dirpath, _, files in os.walk(user_dir)
                   for f in files]
        assert written, f"自定图没写进 {user_dir}"
        assert any("diy_paths_check" in os.path.basename(
            os.path.dirname(w)) or "diy_paths_check" in w for w in written)


class TestSnippetWorkflow:
    """骨架 → 脚本 → 编辑 → 运行 这一条链。"""

    def test_lists_runnable_skeletons(self, client) -> None:
        rows = client.get("/api/snippets").json()
        assert len(rows) > 0
        # 每个骨架都要给出源码，否则"看骨架源码"是空的
        for t in rows:
            assert t.get("template_id")
            assert t.get("source"), f"{t.get('template_id')} 没有源码"

    def test_creates_an_experiment_with_a_runnable_script(self, client) -> None:
        r = client.post("/api/experiments/from-snippet", json={
            "snippet_id": "code.sensitivity_analysis",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        exp = d["experiment"]
        # entrypoint 必须是后端能认的协议形态
        assert exp["entrypoint"].endswith("run.py:run")
        # 脚本内容要真的是可运行的适配层，不是一条路径
        src = d["script_source"]
        assert len(src) > 500
        assert "def run(trial: Dict[str, Any]) -> Dict[str, Any]:" in src
        assert '"atoms"' in src or "'atoms'" in src
        assert d["script_rel"].endswith("run.py")

    def test_script_reads_back_identically(self, client) -> None:
        d = client.post("/api/experiments/from-snippet",
                        json={"snippet_id": "code.sensitivity_analysis"}).json()
        eid = d["experiment"]["id"]
        got = client.get(f"/api/experiments/{eid}/script").json()
        assert got["exists"] is True
        assert got["source"] == d["script_source"]

    def test_bad_syntax_is_rejected_with_a_line_number(self, client) -> None:
        """语法错误必须在保存时拦下，并指出行号。

        不能让它先落盘、等运行时才报——那时用户已经以为改好了。
        """
        d = client.post("/api/experiments/from-snippet",
                        json={"snippet_id": "code.sensitivity_analysis"}).json()
        eid = d["experiment"]["id"]
        r = client.put(f"/api/experiments/{eid}/script",
                       json={"source": "def run(trial)\n    return {}"})
        assert r.status_code == 422
        assert "1" in r.json()["detail"]          # 行号
        # 而且原文件不能被写坏
        still = client.get(f"/api/experiments/{eid}/script").json()["source"]
        assert "def run(trial" in still
        assert still == d["script_source"]

    def test_edit_then_run_produces_atoms(self, client) -> None:
        """改脚本 → 跑 → 出结果数字。这是"app 内跑数据"的最小闭环。"""
        d = client.post("/api/experiments/from-snippet", json={
            "snippet_id": "code.sensitivity_analysis",
            "varied": [{"name": "w", "values": "0.1,0.5,1.0"}],
        }).json()
        eid = d["experiment"]["id"]
        assert d["parameter_names"] == ["w"]

        # 改一处真的会改变结果的地方
        src = d["script_source"]
        edited = src.replace("return float(np.exp(-w * float(np.mean(x))))",
                             "return float(np.mean(x) ** 2 - w)", 1)
        assert "np.mean(x) ** 2 - w" in edited
        assert edited != src, "测试没改到模型的返回式"
        assert client.put(f"/api/experiments/{eid}/script",
                          json={"source": edited}).status_code == 200

        run = client.post(f"/api/experiments/{eid}/run", json={})
        assert run.status_code == 202, run.text   # 运行是异步受理，返回 202
        runs = run.json()["runs"]
        assert len(runs) == 3
        assert all(r["status"] == "success" for r in runs), \
            [r.get("stderr_tail") for r in runs if r["status"] != "success"]

        atoms = [a for a in client.get("/api/results").json()
                 if a["experiment_id"] == eid]
        assert len(atoms) == 6        # 3 次试验 × (score + param)
        scores = sorted(a["value"] for a in atoms if a["name"] == "score")
        # 均值约 0.9 上下，平方后约 0.81，减去 w=0.1/0.5/1.0
        assert scores[0] == pytest.approx(scores[-1] - 0.9, abs=0.25)

    def test_entrypoint_is_filled_when_created_by_hand(self, client) -> None:
        """手写的实验没有 entrypoint 时，存一次脚本要能把它补上。

        否则用户写完脚本、点运行，得到的是"没有入口"——
        而文件明明就在那儿。
        """
        exp = client.post("/api/experiments", json={
            "label": "手写", "kind": "simulation",
        }).json()
        eid = exp.get("id") or exp.get("experiment", {}).get("id")
        r = client.put(f"/api/experiments/{eid}/script",
                       json={"source": "def run(trial):\n    return "
                                      "{'atoms': [{'name': 'x', 'value': 1}]}\n"})
        assert r.status_code == 200, r.text
        got = client.get(f"/api/experiments/{eid}/script").json()
        assert got.get("entrypoint", "").endswith("run.py:run")
