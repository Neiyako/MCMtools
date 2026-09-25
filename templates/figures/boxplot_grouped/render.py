"""fig.boxplot_grouped —— 分组箱线图，并标注中位数差。

数据从哪来
----------
data 是一个 dict，键是模板声明的输入名：

    groups             分组名序列（长度 G），或 dict{组名: 该组数值列表}
    values             与 groups 平行的一维数值序列（长度 N），
                       或 dict{组名: 该组数值列表}，或二维序列 [G][*]
    median_annotation  中位数差的标注文本/数值（可选，scalar）

模板里 groups 与 values 都是 optional: false，所以两种常见形状都收：
"平行数组"（groups[i] 是 values[i] 所属的组）和"字典"（组名 -> 数值列表）。
真正的分布数据只有一份，本文件按形状自己认。

绑定哪个 ResultAtom 由上层决定；本文件只负责把图画出花来。

统一约定（所有图模板都遵守）
    render(data, meta) -> matplotlib Figure
    meta 里可能有：caption / x_label / y_label / width_in
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402

_PRIMARY = "#1f4e79"


def _as_groups(data: Dict[str, Any]) -> "tuple[List[str], List[List[float]]]":
    """把声明形状整理成 (组名列表, 每组数值列表)。"""
    groups = data.get("groups")
    values = data.get("values")

    if groups is None:
        raise ValueError("boxplot_grouped 缺少必填输入 groups（分组名）。")
    if values is None:
        raise ValueError("boxplot_grouped 缺少必填输入 values（各组的数值）。")

    # 形状一：values 是 dict{组名: 数值列表}，groups 可以缺省或只用来定顺序。
    if isinstance(values, dict):
        order = list(groups) if not isinstance(groups, dict) else list(groups.keys())
        order = [str(g) for g in order]
        names = [g for g in order if g in values] or [str(k) for k in values.keys()]
        series = [[float(v) for v in values[g]] for g in names]
        return names, series

    # 形状二：values 是二维序列，一行一组，与 groups 一一对应。
    if values and isinstance(values[0], (list, tuple)):
        names = [str(g) for g in groups]
        series = [[float(v) for v in row] for row in values]
        if len(names) != len(series):
            raise ValueError(
                f"groups 有 {len(names)} 组，values 有 {len(series)} 组，数量必须一致。"
            )
        return names, series

    # 形状三（模板字面形状）：groups 与 values 平行，values[i] 属于 groups[i]。
    if isinstance(groups, dict):
        # groups 是 dict、values 是扁平序列时，用 values 的长度对齐每组。
        names = [str(k) for k in groups.keys()]
        series = []
        for k in groups.keys():
            n = len(groups[k])
            series.append([float(v) for v in values[:n]])
            values = values[n:]
        return names, series

    if len(groups) != len(values):
        # 不猜用户想怎样，直接说清楚哪里对不上。
        raise ValueError(
            f"groups 有 {len(groups)} 个，values 有 {len(values)} 个，数量必须一致"
            "（或把 values 传成 dict{组名: 数值列表}）。"
        )

    buckets: "Dict[str, List[float]]" = {}
    for g, v in zip(groups, values):
        buckets.setdefault(str(g), []).append(float(v))
    names = list(buckets.keys())
    return names, [buckets[n] for n in names]


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}
    names, series = _as_groups(data)

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 3.7))

    bp = ax.boxplot(series, patch_artist=True, widths=0.55)
    for box in bp["boxes"]:
        box.set(facecolor="#cfe0f0", edgecolor=_PRIMARY, linewidth=1.2)
    for key in ("whiskers", "caps"):
        for art in bp[key]:
            art.set(color=_PRIMARY, linewidth=1.2)
    for med in bp["medians"]:
        med.set(color="#b03030", linewidth=1.6)
    for flier in bp["fliers"]:
        flier.set(marker="o", markersize=3, markerfacecolor="#777777",
                  markeredgecolor="none")

    # 每个箱子上标组名，读者不用回去翻图例。
    ax.set_xticks(range(1, len(names) + 1))
    ax.set_xticklabels(names)
    ax.set_xlabel(meta.get("x_label", "分组"))
    ax.set_ylabel(meta.get("y_label", "指标值"))

    # median_annotation 是 optional: true，没给就不标。
    ann = data.get("median_annotation")
    if ann is not None:
        text = ann if isinstance(ann, str) else f"中位数差 {_fmt(ann)}"
        if not isinstance(ann, str):
            # 数值时给个完整句子，免得图注只有裸数字。
            text = f"Median difference = {_fmt(ann)}"
        ax.annotate(text, xy=(0.5, 0.96), xycoords="axes fraction",
                    ha="center", va="top", fontsize=9, color="#b03030",
                    bbox={"boxstyle": "round,pad=0.3", "fc": "#fdf3f3",
                          "ec": "#b03030", "lw": 0.8})

    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    ax.grid(alpha=0.3, axis="y")
    ax.set_axisbelow(True)
    fig.tight_layout()
    return fig


def _fmt(v: Any) -> str:
    """数字格式化：太小或太大的值用科学计数法，否则保留 4 位有效数字。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != 0 and (abs(f) < 1e-3 or abs(f) >= 1e5):
        return f"{f:.2e}"
    return f"{f:.4g}"
