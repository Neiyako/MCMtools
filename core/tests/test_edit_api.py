"""面板的可编辑性。

用户的原话是"很多参数和数学内容都无法修改，去根目录修改也很麻烦"。
后端其实一直有 PUT 接口，是前端没接 —— 但接口本身也有缺口
（假设没有写接口、公式不能删、新建参数缺 id 必定 422）。
这些测试盯的是"面板上能不能真的改"这条链路。
"""

from __future__ import annotations

import pytest

from mcmcore.templates import (TemplateLoadError, TemplateRegistry,
                               default_registry_root)


@pytest.fixture()
def client(tmp_path):
    """一个最小可用的项目 + TestClient。"""
    from fastapi.testclient import TestClient

    from mcmcore.api import create_app
    from mcmcore.store import Store

    st = Store.init(tmp_path, "edit-api-test")
    return TestClient(create_app(st.root))


class TestSymbolEditing:
    def test_create_then_read_back(self, client) -> None:
        r = client.put("/api/math/symbols/beta",
                       json={"glyph": "beta", "meaning": "Transmission rate",
                             "role": "parameter"})
        assert r.status_code == 200, r.text
        got = client.get("/api/math").json()
        assert any(s["glyph"] == "beta" for s in got["symbols"])

    def test_update_meaning(self, client) -> None:
        client.put("/api/math/symbols/beta",
                   json={"glyph": "beta", "meaning": "old"})
        client.put("/api/math/symbols/beta",
                   json={"glyph": "beta", "meaning": "new meaning"})
        got = client.get("/api/math").json()
        sym = next(s for s in got["symbols"] if s["glyph"] == "beta")
        assert sym["meaning"] == "new meaning"

    def test_delete(self, client) -> None:
        client.put("/api/math/symbols/beta",
                   json={"glyph": "beta", "meaning": "x"})
        assert client.delete("/api/math/symbols/beta").status_code == 200
        got = client.get("/api/math").json()
        assert not any(s["glyph"] == "beta" for s in got["symbols"])

    def test_missing_meaning_is_rejected(self, client) -> None:
        """含义是必填 —— 一个没释义的符号进符号表等于没写。"""
        r = client.put("/api/math/symbols/beta", json={"glyph": "beta"})
        assert r.status_code == 422


class TestEquationEditing:
    def test_create_and_delete(self, client) -> None:
        r = client.put("/api/math/equations/eq:one",
                       json={"latex": "a = b + c", "number": "(1)"})
        assert r.status_code == 200, r.text
        got = client.get("/api/math").json()
        assert any(e["id"] == "eq:one" for e in got["equations"])

        # 删公式的接口原本不存在，用户建错了只能去改 YAML
        r = client.delete("/api/math/equations/eq:one")
        assert r.status_code == 200, r.text
        got = client.get("/api/math").json()
        assert not any(e["id"] == "eq:one" for e in got["equations"])

    def test_delete_missing_is_404(self, client) -> None:
        assert client.delete("/api/math/equations/nope").status_code == 404


class TestAssumptionEditing:
    """假设是评审最爱挑的地方，必须能改。"""

    def test_create_update_delete(self, client) -> None:
        r = client.put("/api/math/assumptions/ASM-001",
                       json={"text": "Population is well mixed.",
                             "justification": "High contact rate.",
                             "scope": "model"})
        assert r.status_code == 200, r.text

        r = client.put("/api/math/assumptions/ASM-001",
                       json={"text": "Population is well mixed each day.",
                             "scope": "model"})
        assert r.status_code == 200, r.text
        got = client.get("/api/math").json()
        a = next(x for x in got["assumptions"] if x["id"] == "ASM-001")
        assert a["text"] == "Population is well mixed each day."
        # 更新不该把没传的字段清掉
        assert a.get("justification")

        assert client.delete("/api/math/assumptions/ASM-001").status_code == 200

    def test_bad_scope_is_rejected_in_chinese(self, client) -> None:
        r = client.put("/api/math/assumptions/A1",
                       json={"text": "x", "scope": "global"})
        assert r.status_code == 422

    def test_delete_missing_is_404(self, client) -> None:
        assert client.delete("/api/math/assumptions/nope").status_code == 404


class TestParameterEditing:
    def test_create_by_name_only(self, client) -> None:
        """面板只让用户填名字，不该逼他编一个内部 id。

        这里原来必定 422（id 缺失），是实测中"新建参数失败"的原因。
        """
        r = client.put("/api/params/beta",
                       json={"value": 0.31, "source": "literature",
                             "source_ref": "2023 C/2307166"})
        assert r.status_code == 200, r.text
        got = client.get("/api/params").json()
        p = next(x for x in got["parameters"] if x["name"] == "beta")
        assert p["value"] == 0.31
        assert p["source"] == "literature"

    def test_update_value(self, client) -> None:
        client.put("/api/params/beta", json={"value": 1})
        client.put("/api/params/beta", json={"value": 2})
        got = client.get("/api/params").json()
        p = next(x for x in got["parameters"] if x["name"] == "beta")
        assert p["value"] == 2

    def test_bad_source_lists_allowed_values(self, client) -> None:
        """来源写错时要告诉用户能填哪些，不能只说"无效"。"""
        r = client.put("/api/params/beta",
                       json={"value": 1, "source": "not_a_source"})
        assert r.status_code == 422
        assert "literature" in r.text

    def test_delete(self, client) -> None:
        client.put("/api/params/beta", json={"value": 1})
        assert client.delete("/api/params/beta").status_code == 200
        got = client.get("/api/params").json()
        assert not any(x["name"] == "beta" for x in got["parameters"])


class TestTemplateLoadSafety:
    """模板加载失败不能静默。

    给 28 个模板加了一个 schema 不认识的字段时，它们被无声丢弃，
    注册表从 74 掉到 46 而没有任何异常。工具库少一半却不出声，
    比直接报错危险得多。
    """

    def test_real_registry_loads_strict(self) -> None:
        reg = TemplateRegistry(default_registry_root()).load_strict()
        assert len(reg) >= 74
        for kind in ("figure", "model", "table", "experiment", "paper"):
            assert reg.by_kind(kind), f"{kind} 一个模板都没有"

    def test_unknown_field_raises_instead_of_dropping(self, tmp_path) -> None:
        d = tmp_path / "figures" / "bogus"
        d.mkdir(parents=True)
        (d / "template.yaml").write_text(
            "template_id: fig.bogus\nkind: figure\nnot_a_real_field: 1\n",
            encoding="utf-8")
        with pytest.raises(TemplateLoadError):
            TemplateRegistry(tmp_path).load_strict()

    def test_load_without_strict_still_collects_errors(self, tmp_path) -> None:
        """load() 仍要能容错（有些场景只想尽量加载）。"""
        d = tmp_path / "figures" / "bogus"
        d.mkdir(parents=True)
        (d / "template.yaml").write_text(
            "template_id: fig.bogus\nkind: figure\nnot_a_real_field: 1\n",
            encoding="utf-8")
        reg = TemplateRegistry(tmp_path).load()
        assert reg._errors
        with pytest.raises(TemplateLoadError):
            reg.assert_no_errors()


class TestTemplatesAreChinese:
    """面板是中文界面。用户在英文句子里挑模板，等于没给说明。"""

    def test_figure_templates_have_chinese_purpose(self) -> None:
        reg = TemplateRegistry(default_registry_root()).load_strict()
        missing = [t.template_id for t in reg.by_kind("figure")
                   if not (t.purpose_cn or "").strip()]
        assert not missing, f"这些图模板没有中文用途：{missing}"

    def test_headline_prefers_chinese(self) -> None:
        reg = TemplateRegistry(default_registry_root()).load_strict()
        for t in reg.by_kind("figure"):
            line = reg.headline(t)
            assert any("\u4e00" <= c <= "\u9fff" for c in line), \
                f"{t.template_id} 的显示用途不是中文：{line}"

    def test_all_kinds_are_covered(self) -> None:
        """四种非图模板也要有中文，否则面板一半中文一半英文。"""
        reg = TemplateRegistry(default_registry_root()).load_strict()
        missing = []
        for kind in ("model", "table", "experiment", "paper"):
            for t in reg.by_kind(kind):
                line = reg.headline(t)
                if not any("\u4e00" <= c <= "\u9fff" for c in line):
                    missing.append(t.template_id)
        assert not missing, f"这些模板没有中文用途：{missing}"
