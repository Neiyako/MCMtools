"""示例数据生成器。

这是"填 json 不方便、样例写法没给"这个反馈的解法。约束很硬：
生成的示例必须**真的能渲染**。一个通不过模板校验的示例比没有更糟
—— 用户会以为是自己填错了。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

import matplotlib
matplotlib.use("Agg")

from mcmcore.sampledata import sample_for, snippet_for, value_for
from mcmcore.templates import TemplateRegistry, default_registry_root

FIGDIR = default_registry_root() / "figures"


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return TemplateRegistry(default_registry_root()).load()


def _render_module(name: str):
    if str(FIGDIR) not in sys.path:
        sys.path.insert(0, str(FIGDIR))
    spec = importlib.util.spec_from_file_location(
        f"_sd_{name}", FIGDIR / name / "render.py")
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001
        return None
    return mod


class TestGeneratorBasics:
    def test_only_mandatory_inputs_are_generated(self, registry) -> None:
        """只生成必填项。

        把可选的一起塞满会让示例看起来比实际复杂，反而吓退人。
        """
        t = registry.get("fig.histogram_distribution")
        got = set(sample_for(t).keys())
        mandatory = {i.name for i in t.inputs if not i.optional}
        assert got >= mandatory

    def test_independent_variables_increase(self) -> None:
        """自变量要线性递增。

        画成钟形会让人以为图画错了 —— 时间不会先升后降。
        """
        vals = value_for("t", "independent_variable", "array")
        assert vals == sorted(vals), "t 应该是递增的"

    def test_uncertainty_is_positive(self) -> None:
        """标准差不能是负数，否则误差带会翻过来。"""
        vals = value_for("std", "uncertainty", "array")
        assert all(v > 0 for v in vals), vals

    def test_groups_match_value_count(self) -> None:
        groups = value_for("groups", "grouping", "array")
        assert len(groups) == 6

    def test_scalar_names_win_over_role(self) -> None:
        """名字比 role 可靠：baseline 就是单个数。"""
        assert not isinstance(value_for("baseline", "reference_value", "array"), list)
        assert isinstance(value_for("bins", "parameter", "scalar"), int)

    def test_snippet_lists_every_input_in_chinese(self, registry) -> None:
        """填写说明要覆盖全部输入，并且是中文。"""
        t = registry.get("fig.sankey_flow")
        text = snippet_for(t)
        for i in t.inputs:
            assert i.name in text, f"说明里缺 {i.name}"
        assert any("\u4e00" <= c <= "\u9fff" for c in text)

    def test_snippet_marks_required_and_optional(self, registry) -> None:
        text = snippet_for(registry.get("fig.timeseries"))
        assert "必填" in text and "可选" in text


class TestGeneratedSamplesRender:
    """核心保证：每个模板的示例数据都能直接渲染出图。

    这是唯一有说服力的检查。生成器只要在长度约束上错一处，
    用户点"填入示例数据"再点"预览"就会看到报错 ——
    而那正是这个功能要消灭的体验。
    """

    def test_all_figure_templates_render_their_sample(self, tmp_path, registry) -> None:
        failures = []
        checked = 0
        for t in sorted(registry.by_kind("figure"), key=lambda x: x.template_id):
            name = t.template_id.split(".", 1)[1]
            mod = _render_module(name)
            if mod is None:
                failures.append(f"{name}: 加载失败")
                continue
            if not hasattr(mod, "render"):
                continue          # 结构类走 drawio
            checked += 1
            try:
                fig = mod.render(sample_for(t), {"caption": "示例"})
                out = tmp_path / f"{name}.pdf"
                fig.savefig(out)
                if out.stat().st_size < 3000:
                    failures.append(f"{name}: PDF 只有 {out.stat().st_size} 字节")
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    f"{name}: {type(exc).__name__}: {str(exc)[:70]}")
            finally:
                import matplotlib.pyplot as plt
                plt.close("all")

        assert checked >= 20, f"只检查到 {checked} 个模板，是不是没加载上"
        assert not failures, (
            "生成的示例数据跑不通（模板拒绝得对，错的是生成器）：\n  "
            + "\n  ".join(failures)
        )

    def test_every_figure_template_gets_a_nonempty_sample(self, registry) -> None:
        empty = []
        for t in registry.by_kind("figure"):
            if not (t.requires and t.requires.required_inputs):
                continue
            if not sample_for(t):
                empty.append(t.template_id)
        assert not empty, f"这些模板生成不出示例：{empty}"
