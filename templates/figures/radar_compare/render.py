"""fig.radar_compare —— 雷达图（多方案 × 多指标综合对比）。

为什么要有这张图
----------------
评价类题目的结论通常是"方案 A 在成本上最优、方案 B 在可靠性上最优"，
用表格读起来要在几列数字之间来回扫。雷达图把每个方案画成一个形状，
"谁在哪一维上鼓出来"直接变成视觉上的凸起，是评价章节最有说服力的一张图。

**必须做归一化，否则这张图会骗人**
----------------------------------
成本（万元，量级 1e2）和可靠性（无量纲，量级 0~1）画在同一根轴系上时，
如果不归一化，半径完全由量级大的那个指标决定，可靠性那根轴上的差异
被压成一条几乎重合的线 —— 图看着没问题，结论全错。
所以这里在函数内做 min-max 归一化，把每一维线性映射到 [0, 1]：

    v' = (v - min) / (max - min)

min/max 取**该维在所有方案上的极值**，因此径向刻度在全图统一，
不同方案之间可以直接比大小。原始数值会标在每个顶点旁（用 mcmplot.fmt
格式化），这样读者既能看到形状，也能读到真实尺度。

已知的代价（诚实说明）：min-max 会放大接近的指标。如果某一维上所有
方案本就几乎相同，归一化后会被拉成 0 和 1 的巨大差异。评审若追问，
应回到原始数值表。这是雷达图的固有缺陷，不是本实现的 bug。

数据从哪来
----------
data 的键：
    categories  指标名列表，长度 = 维数（至少 3 维，否则不成形状）
    series      二维序列：每个元素是一个方案在各维上的得分，必填
    labels      方案名列表，与 series 等长

meta 里可能有：caption / x_label / width_in / max_series
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# 超过这个数量的方案，形状会叠成一团墨，宁可提醒用户换图。
_MAX_SERIES = 8


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    categories = data.get("categories")
    if categories is None or len(categories) == 0:
        raise ValueError(
            "缺少必填输入 categories：请提供指标名列表，"
            "例如 ['成本', '可靠性', '响应速度', '覆盖范围']。"
        )
    categories = [mcmplot.safe(str(c)) for c in categories]
    n_dim = len(categories)
    if n_dim < 3:
        # 两维画出来是一条线段，"雷达"的形状特征完全消失，不如用条形图。
        raise ValueError(
            f"categories 只有 {n_dim} 个指标，雷达图至少需要 3 个维度。"
            "两维对比请改用 fig.bar_comparison。"
        )

    series = data.get("series")
    if series is None or len(series) == 0:
        raise ValueError(
            "缺少必填输入 series：请提供二维序列（每个元素是一个方案在各维上的得分），"
            "例如 [[9, 7, 8, 6], [6, 9, 5, 9]]。"
        )

    labels = data.get("labels")
    if labels is None or len(labels) == 0:
        raise ValueError(
            "缺少必填输入 labels：请为每个方案提供一个名字，否则图例无法区分。"
        )

    rows: list = []
    for i, row in enumerate(series):
        row = list(row or [])
        if len(row) != n_dim:
            name = labels[i] if i < len(labels) else f"第 {i + 1} 个"
            raise ValueError(
                f"series 的第 {i + 1} 个方案（{name}）有 {len(row)} 个得分，"
                f"categories 有 {n_dim} 个指标，数量必须一致。"
            )
        rows.append([float(v) for v in row])

    if len(labels) != len(rows):
        raise ValueError(
            f"labels 有 {len(labels)} 个，series 有 {len(rows)} 个方案，数量必须一致。"
        )

    limit = int(meta.get("max_series", _MAX_SERIES))
    if len(rows) > limit:
        raise ValueError(
            f"series 有 {len(rows)} 个方案，超过雷达图可读上限 {limit} 个。"
            "请先筛选出候选方案，或改用分组柱状图。"
        )

    mat = np.asarray(rows, dtype=float)          # (n_series, n_dim)

    # 各维 min-max 归一化。见文件头说明：不归一化，量级大的指标会独占半径。
    lo = mat.min(axis=0)
    hi = mat.max(axis=0)
    span = hi - lo
    # 全方案同值的维度除以 0 会得到 nan，整张图会变成空白。
    # 这种维度没有区分度，统一置 0.5（所有方案并列居中），并在图上保留。
    safe_span = np.where(span == 0, 1.0, span)
    norm = (mat - lo) / safe_span
    norm[:, span == 0] = 0.5

    # 极坐标：角度按维数均分，首尾相接（闭合）—— 不闭合的话雷达图
    # 会缺一条边，形状看起来是"开口"的，读者会以为少了一个指标。
    angles = np.linspace(0, 2 * np.pi, n_dim, endpoint=False).tolist()
    angles_closed = angles + angles[:1]

    width = float(meta.get("width_in", 6.0))
    fig = plt.figure(figsize=(width, width * 0.92))
    ax = fig.add_subplot(111, projection="polar")

    colors = plt.get_cmap("tab10").colors
    for i, name in enumerate(labels):
        vals = norm[i].tolist()
        vals_closed = vals + vals[:1]
        color = colors[i % len(colors)]
        ax.plot(angles_closed, vals_closed, "-", lw=1.8, color=color,
                label=mcmplot.safe(str(name)))
        # 半透明填充：多个方案叠在一起时，实心色会互相盖住，
        # 透明填充能看出"谁在哪个方向包住了谁"。
        ax.fill(angles_closed, vals_closed, color=color, alpha=0.14)

    # 径向刻度固定成 0/0.5/1，因为归一化后所有维共用同一量纲。
    # 写明"归一化"三个字，避免读者把它当成原始得分。
    ax.set_ylim(0, 1)
    ax.set_yticks([0.0, 0.5, 1.0])
    ax.set_yticklabels(["0", "0.5", "1.0"], fontsize=7, color="#666666")
    ax.set_xticks(angles)
    ax.set_xticklabels(categories, fontsize=8)
    # 指标名离圆心远一点，不然会和最外圈的网格线叠在一起。
    # pad 还要更大些：最外圈顶点上的数值标注会被这个距离压到。
    ax.tick_params(axis="x", pad=10)

    # 原始数值标在顶点旁：归一化会掩盖真实尺度，标数值是对它的补偿。
    # 多个系列的分数接近时这些数字会重合（实测三个落在同一像素），
    # 所以最后统一做一次避让。
    _value_anns = []
    for i in range(len(labels)):
        for j in range(n_dim):
            _value_anns.append(ax.annotate(
                mcmplot.fmt(mat[i, j]),
                xy=(angles[j], norm[i, j]),
                xytext=(3, 3), textcoords="offset points",
                fontsize=6, color="#444444", alpha=0.9,
            ))

    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.10),
              frameon=False, fontsize=8)
    # 半径轴标签放在图外，说明刻度是归一化后的相对值。
    ax.set_ylabel(mcmplot.safe(str(meta.get("y_label", "归一化得分（各维 min-max）"))),
                  fontsize=8, labelpad=22)
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")), pad=16)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    mcmplot.spread_labels(fig, _value_anns)
    return fig
