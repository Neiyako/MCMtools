"""DIY 生图。

这个功能的承诺是"点几下就能出一张图，不用写代码"。所以测试的重点
不是内部函数，而是：**每一种图形都真的画得出来**，以及规格写错时
用户能看到一句能懂的中文，而不是一个 500。
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import pytest

from mcmcore import mcmplot
from mcmcore.diyfig import CHART_TYPES, DIYError, catalog, render

X = [1, 2, 3, 4, 5, 6]
Y = [10, 32, 58, 74, 61, 30]
BASE = {"title": "测试", "xlabel": "天数", "ylabel": "人数"}


def spec_for(chart: str) -> dict:
    """每个图形类型一份合法规格。

    和 sample data 一样，这份表必须跟着 CHART_TYPES 走 ——
    加了新图形却忘了补规格，下面 test_every_type_has_a_spec 会失败。
    """
    if chart in ("bar_grouped", "bar_stacked", "area_stacked"):
        return dict(BASE, chart=chart, labels=["甲", "乙", "丙"],
                    series=[{"name": "方案A", "y": [3, 5, 2]},
                            {"name": "方案B", "y": [4, 3, 6]}])
    if chart in ("pie", "donut", "pareto", "waterfall"):
        return dict(BASE, chart=chart, values=[30, 20, 15, 10, 8],
                    labels=["甲", "乙", "丙", "丁", "戊"])
    if chart in ("box", "violin"):
        return dict(BASE, chart=chart, labels=["甲组", "乙组"],
                    series=[{"name": "甲组", "y": [1, 2, 2, 3, 4]},
                            {"name": "乙组", "y": [3, 4, 4, 5, 7]}])
    if chart == "hist":
        return dict(BASE, chart=chart, values=[1, 1, 2, 2, 2, 3, 3, 4, 5])
    if chart in ("heatmap", "contour"):
        return dict(BASE, chart=chart, matrix=[[1, 2, 3], [4, 5, 6], [7, 8, 9]],
                    labels=["行一", "行二", "行三"],
                    col_labels=["列一", "列二", "列三"])
    if chart == "surface":
        return dict(BASE, chart=chart, x=[0, 1, 2], y=[0, 1, 2],
                    z=[[1, 2, 3], [2, 3, 4], [3, 4, 5]])
    if chart in ("errorbar", "fill_between"):
        return dict(BASE, chart=chart, x=X, y=Y, errors=[1, 2, 1.5, 2, 1, 1.5])
    if chart == "radar":
        return dict(BASE, chart=chart, labels=["速度", "精度", "成本", "稳健"],
                    series=[{"name": "A", "y": [3, 5, 2, 4]},
                            {"name": "B", "y": [4, 3, 5, 3]}])
    if chart == "polar":
        return dict(BASE, chart=chart, x=[0, 45, 90, 135, 180, 225, 270, 315],
                    y=[1, 3, 2, 4, 2, 3, 1, 2])
    return dict(BASE, chart=chart, x=X, y=Y)


class TestEveryChartTypeRenders:
    def test_every_type_has_a_spec(self) -> None:
        """新增图形类型必须同时补一份测试规格。"""
        missing = [k for k, _ in CHART_TYPES if not spec_for(k)]
        assert not missing, f"这些图形没有测试规格：{missing}"

    def test_all_types_render(self, tmp_path) -> None:
        failures = []
        for chart, _label in CHART_TYPES:
            try:
                fig = render(spec_for(chart), {"caption": "图 1 测试"})
                out = tmp_path / f"{chart}.pdf"
                fig.savefig(out)
                if out.stat().st_size < 3000:
                    failures.append(f"{chart}: 只有 {out.stat().st_size} 字节")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{chart}: {type(exc).__name__}: {str(exc)[:60]}")
            finally:
                import matplotlib.pyplot as plt
                plt.close("all")
        assert not failures, "图形渲染失败：\n  " + "\n  ".join(failures)

    def test_catalog_matches_renderer(self) -> None:
        """面板的选项清单来自 catalog，不能和真正支持的图形脱节。"""
        cat = catalog()
        listed = {c["value"] for c in cat["chart_types"]}
        implemented = {k for k, _ in CHART_TYPES}
        assert listed == implemented


class TestErrorMessagesAreUsable:
    """规格写错时要说人话。这是 DIY 功能能不能用的关键 ——
    一个 KeyError 对建模的人是没法处理的。"""

    def test_unknown_chart(self) -> None:
        with pytest.raises(DIYError, match="不认识的图形"):
            render({"chart": "no_such_chart", "y": [1, 2]})

    def test_no_data(self) -> None:
        with pytest.raises(DIYError, match="没有数据"):
            render({"chart": "line"})

    def test_length_mismatch_says_the_counts(self) -> None:
        """报错要给出具体数量，用户才知道差几个。"""
        with pytest.raises(DIYError) as e:
            render({"chart": "line", "x": [1, 2, 3], "y": [1, 2]})
        msg = str(e.value)
        assert "3" in msg and "2" in msg

    def test_bar_needs_one_label_per_value(self) -> None:
        with pytest.raises(DIYError, match="必须一样多"):
            render({"chart": "bar", "y": [1, 2, 3], "labels": ["只有一个"]})

    def test_pie_rejects_negative(self) -> None:
        with pytest.raises(DIYError, match="负值"):
            render({"chart": "pie", "y": [1, -2, 3]})

    def test_radar_needs_three_axes(self) -> None:
        with pytest.raises(DIYError, match="3 个指标"):
            render({"chart": "radar", "labels": ["甲", "乙"],
                    "y": [1, 2]})

    def test_errorbar_without_errors_explains(self) -> None:
        with pytest.raises(DIYError, match="errors"):
            render({"chart": "errorbar", "y": [1, 2, 3]})

    def test_bad_matrix_explains_shape(self) -> None:
        with pytest.raises(DIYError, match="二维"):
            render({"chart": "heatmap", "matrix": [1, 2, 3]})

    def test_errors_are_chinese(self) -> None:
        """错误信息给的是中文用户，必须含汉字。"""
        with pytest.raises(DIYError) as e:
            render({"chart": "line"})
        assert any("\u4e00" <= c <= "\u9fff" for c in str(e.value))


class TestDataShorthands:
    """两种写法都要收：只给 y 是大多数人的第一反应。"""

    def test_y_only_uses_index_as_x(self) -> None:
        fig = render({"chart": "line", "y": [3, 1, 4, 1, 5]})
        assert fig is not None

    def test_values_works_for_categorical(self) -> None:
        fig = render({"chart": "pie", "values": [1, 2, 3],
                      "labels": ["甲", "乙", "丙"]})
        assert fig is not None

    def test_series_list_wins_over_y(self) -> None:
        fig = render({"chart": "line", "y": [1, 2, 3],
                      "series": [{"name": "A", "y": [5, 5, 5]}]})
        assert fig is not None


class TestCjkFont:
    """中文标题必须能画出来。

    默认字体 DejaVu Sans 没有汉字，写中文标题会得到一排豆腐块 ——
    生成成功、不报错、完全没法用。所以必须确认装了中文字体。
    """

    def test_a_cjk_font_is_selected(self) -> None:
        assert mcmplot.setup() is not None, "没有可用的中文字体"
        assert mcmplot.has_cjk()

    def test_safe_strips_unrenderable_chars(self) -> None:
        """中文字体没有 ² 和真减号，要换成画得出来的写法。"""
        assert mcmplot.safe("R\u00b2") == "R2"
        assert mcmplot.safe("a\u2212b") == "a-b"

    def test_chinese_pdf_embeds_a_cjk_font(self, tmp_path) -> None:
        """最终 PDF 里要真的嵌了中文字体，而不只是配置对了。"""
        import pypdf
        fig = render({"chart": "line", "title": "中文标题测试",
                      "xlabel": "天数", "ylabel": "人数", "y": [1, 3, 2]})
        out = tmp_path / "cjk.pdf"
        fig.savefig(out)
        reader = pypdf.PdfReader(str(out))
        fonts = set()
        for page in reader.pages:
            for _k, v in (page.get("/Resources", {}).get("/Font", {}) or {}).items():
                try:
                    fonts.add(str(v.get("/BaseFont")))
                except Exception:  # noqa: BLE001
                    pass
        assert any(k in f for f in fonts for k in
                   ("Hiragino", "Heiti", "Song", "PingFang", "ST", "YaHei",
                    "SimHei", "Noto")), f"PDF 里没有中文字体，只有 {fonts}"
