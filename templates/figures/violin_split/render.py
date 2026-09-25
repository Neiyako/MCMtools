"""fig.violin_split —— 两组对照的左右分离小提琴图。

为什么不是两张小提琴并排
------------------------
并排画的时候，读者要在两个独立的形状之间来回扫才能比出"哪边更高、
哪边的尾巴更长"。左右分离把两组放进同一个坐标框、共用一条竖直中线，
差异直接变成"左半边鼓还是右半边鼓"，是两组对照最省力的画法。

必须诚实的地方
--------------
分组超过两组时这张图就失效了 —— 左右只有两个位置。这里**不静默合并
后两组**，而是明确报错让用户改用 fig.box_violin。合并会把"甲、乙、丙"
悄悄画成"甲 vs 乙+丙"，图看着正常，结论全错。

样本太少（每组不到 5 个点）时核密度估计基本是噪声，此时退回画散点 +
中位数横线，并在图里注明"样本过少，未做密度估计"，不硬画一条假的曲线。

数据从哪来
----------
data 的键：
    groups        每个值属于哪一组（长度与 values 一致），只允许两组
    values        要比较分布的数值
    group_labels  两组的显示名（可选），缺省用 groups 里首次出现的两个名字

meta 里可能有：caption / x_label / y_label / width_in
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# 每组少于这个点数就不画密度曲线 —— 核密度估计需要样本支撑，
# 5 个点能"估计"出任意形状，画出来是误导。
_MIN_FOR_KDE = 5

# 左右两半的颜色。左冷右暖，黑白打印时靠深浅也能分开。
_COLOR_LEFT = "#1f4e79"
_COLOR_RIGHT = "#c0504d"


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    values = list(data.get("values") or [])
    if not values:
        raise ValueError(
            "缺少必填输入 values：请提供要比较分布的数值序列，"
            "例如 [12.3, 11.8, 13.1, ...]。"
        )
    groups = list(data.get("groups") or [])
    if not groups:
        raise ValueError(
            "缺少必填输入 groups：请为 values 里的每个数标注它属于哪一组，"
            "长度必须和 values 一致，例如 ['对照组','对照组','实验组',...]。"
        )
    if len(groups) != len(values):
        raise ValueError(
            f"groups 有 {len(groups)} 项，values 有 {len(values)} 个：数量必须一致，"
            "每个数值都要标注它属于哪一组。"
        )

    # 组名按**首次出现**的顺序取，不排序 —— 用户给的顺序就是他想让读者
    # 看到的左右顺序（对照组在左、实验组在右）。
    names: List[str] = []
    for g in groups:
        s = str(g)
        if s not in names:
            names.append(s)
    if len(names) < 2:
        raise ValueError(
            f"groups 里只有 {len(names)} 种取值（{names}）："
            "两组对照图需要恰好两组数据，请检查分组列是否漏标了。"
        )
    if len(names) > 2:
        raise ValueError(
            f"groups 里有 {len(names)} 组（{names}）："
            "左右分离的小提琴图只能对比两组。"
            "三组及以上请改用 fig.box_violin 模板。"
        )

    left = [float(v) for v, g in zip(values, groups) if str(g) == names[0]]
    right = [float(v) for v, g in zip(values, groups) if str(g) == names[1]]

    labels = list(data.get("group_labels") or []) or names
    labels = [mcmplot.safe(str(x)) for x in labels[:2]]
    if len(labels) < 2:
        labels = [mcmplot.safe(names[0]), mcmplot.safe(names[1])]

    width = float(meta.get("width_in", 6.0))
    fig, ax = plt.subplots(figsize=(width, 4.2))

    # 两组共用一条中心线：左边画对照组，右边画对照组。
    # 中线不是"第三组"，它是两半共用的基线。
    center = 0.0
    half = 0.42

    thin = len(left) < _MIN_FOR_KDE or len(right) < _MIN_FOR_KDE
    if thin:
        # 样本太少：画散点。抖动是确定性的（按序号算），
        # 不用随机数 —— 每次渲染出来的图必须一模一样。
        _scatter_half(ax, left, center, -1, _COLOR_LEFT)
        _scatter_half(ax, right, center, +1, _COLOR_RIGHT)
    else:
        _violin_half(ax, left, center, -1, half, _COLOR_LEFT)
        _violin_half(ax, right, center, +1, half, _COLOR_RIGHT)

    # 中位数横线：读者最常引用的一个数就是它，所以画成实线加数值标注。
    for vals, side in ((left, -1), (right, +1)):
        med = float(np.median(vals))
        ax.plot([center + side * 0.02, center + side * (half + 0.06)],
                [med, med], "-", lw=1.4, color="#333333")
        ax.annotate(f"中位数 {mcmplot.fmt(med)}",
                    xy=(center + side * (half + 0.06), med),
                    xytext=(6 * side, 0), textcoords="offset points",
                    fontsize=8, color="#333333", va="center",
                    ha="left" if side > 0 else "right")

    ax.axvline(center, color="#999999", lw=1.0, zorder=0)
    ax.set_xlim(-1.05, 1.05)
    ax.set_xticks([-0.45, 0.45])
    # 左右标签放在外侧，和中线一起说明"哪半边是哪一组"
    ax.set_xticklabels([labels[0], labels[1]])
    ax.text(-0.88, ax.get_ylim()[1], labels[0], fontsize=9,
            color=_COLOR_LEFT, ha="left", va="top", fontweight="bold")
    ax.text(0.88, ax.get_ylim()[1], labels[1], fontsize=9,
            color=_COLOR_RIGHT, ha="right", va="top", fontweight="bold")

    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "数值")))
    if meta.get("x_label"):
        ax.set_xlabel(mcmplot.safe(meta["x_label"]))

    title = meta.get("caption")
    if thin:
        note = "样本过少（每组不足 5 个点），未做密度估计，已改画散点"
        title = f"{title}（{note}）" if title else note
    if title:
        ax.set_title(mcmplot.safe(title.rstrip(".")))
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    return fig


def _violin_half(ax, vals: List[float], center: float, side: int,
                 half: float, color: str) -> None:
    """把一组数据画成朝向 side 的半边小提琴。

    matplotlib 的 violinplot 画的是左右对称的完整形状；这里先画出来，
    再把每一段的顶点压到中线一侧，得到半边。用 clip 之外的做法是因为
    需要形状本身变形，而不只是裁掉一半。
    """
    arr = np.asarray(vals, dtype=float)
    parts = ax.violinplot([arr], positions=[center], widths=2 * half,
                          showextrema=False, showmedians=False)
    for body in parts["bodies"]:
        # 顶点路径的前半是左侧、后半是右侧，都从中线量起。
        verts = body.get_paths()[0].vertices
        verts[:, 0] = center + side * np.abs(verts[:, 0] - center)
        body.set_facecolor(color)
        body.set_edgecolor("#333333")
        body.set_linewidth(0.9)
        body.set_alpha(0.72)


def _scatter_half(ax, vals: List[float], center: float, side: int,
                  color: str) -> None:
    """样本过少时的替代画法：确定性抖动的散点。"""
    n = len(vals)
    # 用序号做成扇形抖动，不引入随机数，保证可复现。
    offsets = [(0.5 if n == 1 else i / (n - 1)) * 0.30 + 0.06 for i in range(n)]
    ax.scatter([center + side * o for o in offsets], vals,
               s=22, color=color, alpha=0.85, zorder=3,
               edgecolors="white", linewidths=0.5)


def _fmt(v: Any) -> str:
    """统一走 mcmplot.fmt，保证全库图上的数字长得一样。"""
    return mcmplot.fmt(v)
