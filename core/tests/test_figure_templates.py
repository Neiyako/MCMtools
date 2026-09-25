"""图模板冒烟测试：每个模板都必须真的画得出图。

为什么需要这个文件
------------------
模板库的价值完全取决于"拿来就能用"。一个模板只要参数名对不上、
或者遇到某类数据就崩，用户就会退回自己写脚本 —— 那这个库就白建了。

所以这里对**每一个**模板做一次真实渲染，并且明确检查三件事：

1. 能画出图（不是只 import 成功 —— import 成功不代表画得出来）
2. 中文标签不缺字形（缺字形时 matplotlib 只警告不报错，
   结果图上是一排方框，等你排完版才发现）
3. 缺必填输入时报的是**中文错误**，不是 KeyError

用例里的键必须与 template.yaml 里声明的输入名一致。写错键名时
模板会抛"缺少必填输入"，那正是它该做的 —— 但这个测试会失败，
提醒我把用例改对。
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Any, Dict

import pytest

FIG_DIR = Path(__file__).resolve().parents[2] / "templates" / "figures"
sys.path.insert(0, str(FIG_DIR))

import mcmplot  # noqa: E402

mcmplot.setup()

# 模板模块名都叫 render.py。普通 import 会让它们互相顶掉
# （第二个 import 拿到的是第一个的缓存），所以必须按路径 +
# 唯一模块名加载。
import importlib.util  # noqa: E402


def load_template(name: str):
    path = FIG_DIR / name / "render.py"
    if not path.is_file():
        pytest.skip(f"{name} 还没有 render.py")
    spec = importlib.util.spec_from_file_location(f"mcmfig_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 每个模板一组能画出来的最小输入。键名严格对应 template.yaml 的 inputs。
CASES: Dict[str, Dict[str, Any]] = {
    "bar_comparison": {"categories": ["甲", "乙", "丙"], "values": [3, 5, 4],
                       "errors": [0.3, 0.5, 0.4]},
    "boxplot_grouped": {"groups": ["甲", "甲", "乙", "乙"], "values": [1.0, 2.0, 3.0, 4.0]},
    "convergence": {"iterations": list(range(20)),
                    "objective": [1 / (i + 1) for i in range(20)],
                    "converged_at": 10},
    "heatmap_matrix": {"matrix": [[1, 2], [3, 4]],
                       "row_labels": ["甲", "乙"], "col_labels": ["X", "Y"]},
    "scatter_matrix": {"frame": {"甲": [1, 2, 3, 4], "乙": [2, 3, 4, 5]}},
    "pred_vs_actual": {"actual": [1, 2, 3, 4, 5],
                       "predicted": [1.1, 1.9, 3.2, 3.8, 5.1]},
    "residual": {"predicted": [1, 2, 3, 4, 5],
                 "residual": [0.1, -0.2, 0.05, 0.3, -0.1]},
    "sensitivity_line": {"x": [0.1, 0.2, 0.3], "y": [10, 20, 15]},
    "network_graph": {"nodes": ["甲", "乙", "丙"], "edges": [["甲", "乙"], ["乙", "丙"]]},
    "map_choropleth": {"regions": ["甲", "乙", "丙"], "values": [1, 2, 3]},
}

# flowchart / model_structure 是 drawio 图（生成可编辑的 .drawio 文件，
# 不是位图），不属于 matplotlib 渲染路径，另有测试覆盖。


REQUIRED_CASES = {
    "bar_comparison": {},
    "boxplot_grouped": {},
    "convergence": {},
    "heatmap_matrix": {},
    "scatter_matrix": {},
    "pred_vs_actual": {},
    "residual": {},
    "sensitivity_line": {},
    "network_graph": {},
    "map_choropleth": {},
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_template_renders(name: str, tmp_path: Path) -> None:
    """每个模板都要能真的画出一张 PDF。"""
    mod = load_template(name)
    fig = mod.render(dict(CASES[name]), {"caption": f"{name} 中文标题"})
    out = tmp_path / f"{name}.pdf"
    fig.savefig(out)
    mcmplot.close(fig)          # 不关的话跨用例累积，matplotlib 会警告内存
    assert out.is_file() and out.stat().st_size > 1000, f"{name} 生成的 PDF 异常"


@pytest.mark.parametrize("name", sorted(CASES))
def test_template_has_no_missing_glyphs(name: str, tmp_path: Path) -> None:
    """中文标签不能缺字形。

    matplotlib 遇到没有的字形只发警告、照样出图 —— 图上是一排方框。
    这类问题在论文排版完之后才会被发现，所以在这里拦住。
    """
    mod = load_template(name)
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=".*missing from font.*")
        fig = mod.render(dict(CASES[name]), {"caption": f"{name} 中文标题",
                                             "x_label": "横轴", "y_label": "纵轴"})
        fig.savefig(tmp_path / f"{name}_glyph.pdf")
        mcmplot.close(fig)


@pytest.mark.parametrize("name", sorted(REQUIRED_CASES))
def test_missing_required_input_gives_chinese_error(name: str) -> None:
    """缺必填输入要报中文错误，而不是 KeyError 或画出一张空图。"""
    mod = load_template(name)
    with pytest.raises(Exception) as exc:
        mod.render({}, {})
    msg = str(exc.value)
    assert any("\u4e00" <= ch <= "\u9fff" for ch in msg), (
        f"{name} 的错误信息不是中文：{msg[:80]}"
    )


def test_all_registered_templates_have_code() -> None:
    """注册表里声明了模板，就必须有对应的 render.py。"""
    missing = [
        d.name for d in sorted(FIG_DIR.iterdir())
        if d.is_dir() and (d / "template.yaml").is_file()
        and not (d / "render.py").is_file()
        and d.name not in DRAWIO_TEMPLATES
    ]
    assert not missing, f"以下模板只有元数据、没有绘制代码：{missing}"


# --------------------------------------------------------------- drawio 图
# 流程图和技术路线图走的是"生成可编辑源文件"这条路，不是 matplotlib。
# 它们必须能打开继续编辑 —— 答辩前一定会改。

import xml.etree.ElementTree as ET  # noqa: E402


def test_flowchart_writes_valid_drawio(tmp_path: Path) -> None:
    mod = load_template("flowchart")
    out = mod.render_to_file(
        {"nodes": [{"id": "n1", "label": "读入数据", "kind": "input"},
                   {"id": "n2", "label": "建立模型", "kind": "process"},
                   {"id": "n3", "label": "输出结果", "kind": "output"}],
         "edges": [["n1", "n2"], ["n2", "n3", "通过"]]},
        str(tmp_path), "flow",
    )
    root = ET.parse(out["drawio"]).getroot()
    vertices = [c for c in root.findall(".//mxCell") if c.get("vertex")]
    edges = [c for c in root.findall(".//mxCell") if c.get("edge")]
    assert len(vertices) == 3
    assert len(edges) == 2
    # 中文标签要能写进文件（write_text 没指定编码时会按系统默认来，
    # 在中文 Windows 上就乱了，所以这里检查实际落盘的内容）
    assert "读入数据" in Path(out["drawio"]).read_text(encoding="utf-8")


def test_model_structure_defaults_kind(tmp_path: Path) -> None:
    """没写 kind 的模块也要能画出来，不能因为缺字段就崩。"""
    mod = load_template("model_structure")
    out = mod.render_to_file(
        {"models": [{"id": "m1", "label": "数据预处理"},
                    {"id": "m2", "label": "优化模型"}],
         "flows": [["m1", "m2", "清洗后数据"]]},
        str(tmp_path), "struct",
    )
    root = ET.parse(out["drawio"]).getroot()
    assert len([c for c in root.findall(".//mxCell") if c.get("vertex")]) == 2


def test_dangling_edge_is_dropped_not_crashed(tmp_path: Path) -> None:
    """边指向不存在的节点：跳过这条边，而不是让整张图失败。"""
    mod = load_template("flowchart")
    out = mod.render_to_file(
        {"nodes": [{"id": "n1", "label": "甲"}],
         "edges": [["n1", "幽灵节点"]]},
        str(tmp_path), "dangling",
    )
    root = ET.parse(out["drawio"]).getroot()
    assert len([c for c in root.findall(".//mxCell") if c.get("edge")]) == 0


def test_drawio_templates_reject_empty_input() -> None:
    for name in ("flowchart", "model_structure"):
        mod = load_template(name)
        with pytest.raises(ValueError) as exc:
            mod.build({}, {})
        assert any("\u4e00" <= ch <= "\u9fff" for ch in str(exc.value))


def test_no_template_uses_unrenderable_glyphs() -> None:
    """模板源码里不能出现中文字体画不出的字符。

    这类问题**不报错**：图上只是印出一排空心方框，PDF 照样生成，
    等你排完版才发现。实测 Hiragino Sans GB 缺 `²`（R² 的上标）
    和 `−`（U+2212 数学减号），而这两个在科研图里极其常用。

    检查的是源码字面量 —— 用 mcmplot.safe() 包过的运行期字符串不受影响。
    """
    bad_chars = {
        "\u00b2": "上标 2（R²）",
        "\u00b3": "上标 3",
        "\u00b9": "上标 1",
        "\u2212": "数学减号 U+2212",
        "\u207b": "上标负号",
    }
    offenders = []
    for d in sorted(FIG_DIR.iterdir()):
        src = d / "render.py"
        if not src.is_file():
            continue
        text = src.read_text(encoding="utf-8")
        for ch, label in bad_chars.items():
            if ch in text:
                offenders.append(f"{d.name}/render.py 含 {label} ({ch!r})")
    assert not offenders, (
        "以下模板用了画不出来的字符，请改用 mcmplot.safe() 或 ASCII 写法：\n  "
        + "\n  ".join(offenders)
    )


def test_safe_replaces_known_bad_glyphs() -> None:
    assert mcmplot.safe("R\u00b2") == "R^2"
    assert mcmplot.safe("a\u2212b") == "a-b"
    # 正常中文和希腊字母不该被改动
    assert mcmplot.safe("峰值人数 σ=0.9") == "峰值人数 σ=0.9"


# --------------------------------------------------------------------------
# 绑定语义：这几条都是实操中真实踩出来的坑
# --------------------------------------------------------------------------


class TestBindingSemantics:
    """图绑错了会画出一张**看着正常但结论错**的图，比报错危险得多。"""

    def _gen(self, tmp_path):
        from mcmcore.store import Store
        from mcmcore.figures import FigureGenerator

        # 必须 Store.init：临时目录还不是一个项目，Store.open 会拒绝。
        st = Store.init(tmp_path / "proj", project_id="TEST")
        return st, FigureGenerator(st)

    def test_series_binding_reads_a_real_column(self, tmp_path) -> None:
        """序列绑定要能取到整条曲线。"""
        import csv
        from mcmcore.schemas import Figure, ArtifactBinding

        st, gen = self._gen(tmp_path)
        out = st.root / "code" / "output"
        out.mkdir(parents=True)
        with (out / "traj.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["day", "observed", "predicted"])
            for i in range(5):
                w.writerow([i, 100 + i, 90 + i])

        st.save_figure(Figure(id="FIG-001", template_id="fig.pred_vs_actual",
            bindings=[
                ArtifactBinding(atom_id="S1", role="actual", source="artifact",
                                artifact_path="traj.csv", column="observed"),
                ArtifactBinding(atom_id="S2", role="predicted", source="artifact",
                                artifact_path="traj.csv", column="predicted"),
            ]))
        data = gen._collect_bindings(st.load_figure("FIG-001"), {})
        assert data["actual"] == [100.0, 101.0, 102.0, 103.0, 104.0]
        assert data["predicted"] == [90.0, 91.0, 92.0, 93.0, 94.0]

    def test_identical_actual_and_predicted_is_refused(self, tmp_path) -> None:
        """actual 和 predicted 绑到同一批数会画出一条完美对角线，
        标着 R²=1、RMSE=0 —— 那不是拟合好，是绑错了。必须拦住。"""
        import csv
        from mcmcore.schemas import Figure, ArtifactBinding
        from mcmcore.figures import NoBoundData

        st, gen = self._gen(tmp_path)
        out = st.root / "code" / "output"
        out.mkdir(parents=True)
        with (out / "t.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["v"])
            w.writerows([[i] for i in range(5)])

        st.save_figure(Figure(id="FIG-001", template_id="fig.pred_vs_actual",
            bindings=[
                ArtifactBinding(atom_id="S1", role="actual", source="artifact",
                                artifact_path="t.csv", column="v"),
                ArtifactBinding(atom_id="S2", role="predicted", source="artifact",
                                artifact_path="t.csv", column="v"),
            ]))
        with pytest.raises(NoBoundData) as exc:
            gen._collect_bindings(st.load_figure("FIG-001"), {})
        assert "同一批数据" in str(exc.value)

    def test_structural_figure_needs_no_data(self, tmp_path) -> None:
        """流程图是结构图，本来就没有数据可绑，不该被当成坏绑定。"""
        from mcmcore.schemas import Figure

        st, gen = self._gen(tmp_path)
        st.save_figure(Figure(id="FIG-002", template_id="fig.flowchart", bindings=[]))
        assert gen._collect_bindings(st.load_figure("FIG-002"), {}) == {}

    def test_literal_binding_passes_structure_through(self, tmp_path) -> None:
        """结构图的节点是人写的，不是从数据算的。"""
        from mcmcore.schemas import Figure, ArtifactBinding

        st, gen = self._gen(tmp_path)
        nodes = [{"id": "n1", "label": "开始"}, {"id": "n2", "label": "结束"}]
        st.save_figure(Figure(id="FIG-003", template_id="fig.flowchart",
            bindings=[ArtifactBinding(atom_id="L1", role="nodes",
                                      source="literal", value=nodes)]))
        data = gen._collect_bindings(st.load_figure("FIG-003"), {})
        assert data["nodes"] == nodes

    def test_missing_artifact_column_says_what_is_wrong(self, tmp_path) -> None:
        """取不到列时要指名道姓，不能只说"绑定失效"。"""
        from mcmcore.schemas import Figure, ArtifactBinding
        from mcmcore.figures import NoBoundData

        st, gen = self._gen(tmp_path)
        st.save_figure(Figure(id="FIG-004", template_id="fig.pred_vs_actual",
            bindings=[ArtifactBinding(atom_id="S1", role="actual", source="artifact",
                                      artifact_path="nope.csv", column="x")]))
        with pytest.raises(NoBoundData) as exc:
            gen._collect_bindings(st.load_figure("FIG-004"), {})
        assert "nope.csv" in str(exc.value)
