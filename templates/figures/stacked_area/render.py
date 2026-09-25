"""fig.stacked_area —— 堆叠面积图（总量随时间的构成变化）。

为什么要有这张图
----------------
折线图能画"总量在涨"，但答不了"涨的是哪一部分"。人口结构、能源来源、
流量组成这类问题，评审真正想看的是**构成比例怎么迁移**。
堆叠面积图把"总量"和"构成"压在同一张图里：外轮廓是总量，
每一层的厚度是分量，读者一眼能看出哪一层在变宽、哪一层在萎缩。

数据从哪来
----------
data 的键：
    t        横轴（时间 / 步数 / 任意有序轴），必填
    values   二维序列：每个元素是一条分量序列，必填
    labels   每条分量的名字，必填且与 values 等长

meta 里可能有：caption / x_label / y_label / width_in / total_line

设计取舍
--------
配色用**定性色板**（tab10/tab20）而不是连续色标：堆叠图的每一层是
**不同的类别**，不是同一个量的不同大小。用 viridis 这类顺序色标会
暗示"第 5 层比第 1 层大"，是错误引导。tab10 相邻色之间有足够的
明度/色相差异，缩到 0.8\\linewidth 印刷后仍能分辨。
分量超过色板长度时**循环取色并换线型边框**，而不是悄悄重复颜色 ——
两条同色的带子挨在一起，读者会当成一层。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
# 没有这一步，中文标签会被画成一排空心方框，而且不报错。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    values = data.get("values")
    if values is None or len(values) == 0:
        raise ValueError(
            "缺少必填输入 values：请提供二维序列（每个元素是一条分量序列），"
            "例如 [[1, 2, 3], [4, 5, 6]]。"
        )

    labels = data.get("labels")
    if labels is None or len(labels) == 0:
        raise ValueError(
            "缺少必填输入 labels：请为 values 里的每条分量提供一个名字，"
            "否则图例无法区分色块。"
        )

    t = data.get("t")
    if t is None or len(t) == 0:
        raise ValueError(
            "缺少必填输入 t：请提供横轴序列（时间 / 步数），"
            "长度与每条分量序列相同。"
        )
    t = list(t)

    # 每条分量都要和 t 等长 —— 少一个点整张堆叠就会错位，
    # 而且错位后图仍然"看起来正常"，是最危险的一种错。
    series: list = []
    for i, row in enumerate(values):
        row = list(row or [])
        if not row:
            raise ValueError(f"values 的第 {i + 1} 条分量是空的，无法堆叠。")
        if len(row) != len(t):
            name = labels[i] if i < len(labels) else f"第 {i + 1} 条"
            raise ValueError(
                f"values 的第 {i + 1} 条分量（{name}）有 {len(row)} 个点，"
                f"t 有 {len(t)} 个点，数量必须一致。"
            )
        series.append([float(v) for v in row])

    if len(labels) != len(series):
        raise ValueError(
            f"labels 有 {len(labels)} 个，values 有 {len(series)} 条分量，"
            "数量必须一致 —— 否则色块和图例会对不上。"
        )

    # 负值不能堆叠：堆叠的前提是"各部分相加等于总量"，负的一片会
    # 把上面所有层整体下移，画出来的厚度不再等于分量值。
    # 与其画一张骗人的图，不如让用户先去处理数据。
    for i, row in enumerate(series):
        if min(row) < 0:
            raise ValueError(
                f"values 的第 {i + 1} 条分量包含负数，堆叠面积图无法表达。"
                "请先取绝对值，或改用分组柱状图/多线折线图。"
            )

    width = float(meta.get("width_in", 6.6))
    fig, ax = plt.subplots(figsize=(width, 3.9))

    # 定性色板：类别之间要有可辨差异，不能用连续色标。
    colors = plt.get_cmap("tab10").colors
    n = len(series)
    palette = [colors[i % len(colors)] for i in range(n)]

    stacks = ax.stackplot(
        t, *series,
        colors=palette,
        labels=[mcmplot.safe(str(x)) for x in labels],
        alpha=0.92,
        edgecolor="white",       # 白色细边把相邻色块切开，同色相的层也能分开
        linewidth=0.5,
    )

    # 分量超过一个色板长度（10）时颜色会重复。重复的层加粗边框标记，
    # 让读者知道这是"第二轮颜色"而不是同一层。
    for i, poly in enumerate(stacks):
        if i >= len(colors):
            poly.set_linewidth(1.4)
            poly.set_edgecolor("#333333")

    # 图例放在轴外：堆叠图内部本来就被色块占满，图例压上去会挡住数据。
    ax.legend(
        loc="upper left", bbox_to_anchor=(1.01, 1.0),
        frameon=False, fontsize=8, borderaxespad=0.0,
    )

    # 可选：在最上方画一条总量虚线。
    # 为什么默认不画：总分量的轮廓已经被堆叠的外沿表达出来了，
    # 再画一条往往是重复；但当各分量有缺口（不构成完整总量）时，
    # 这条线才是唯一能看出"总量"的地方，所以留成开关。
    if meta.get("total_line", False):
        total = np.sum(np.asarray(series, dtype=float), axis=0)
        ax.plot(t, total, "--", lw=1.4, color="#222222",
                label=mcmplot.safe(str(meta.get("total_label", "总量"))))

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "时间")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "数值")))
    # 轴的起点由 matplotlib 自动取，这里只把下界钉在 0：
    # 面积图的面积就是量，下端不从 0 开始会把比例关系画歪。
    ax.set_ylim(bottom=0)
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
