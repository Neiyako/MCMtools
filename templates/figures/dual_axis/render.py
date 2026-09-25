"""fig.dual_axis —— 双纵轴图（两个量纲不同的序列画在一起）。

这张图最常见的用途，以及它的头号陷阱
------------------------------------
用途是"把驱动量和响应量放在同一根时间轴上"：交易笔数和累计收益、
降雨量和水库水位、投入和产出。两者的量纲差几个数量级，共用一根轴
必然有一条被压成直线，所以各给一根轴。

陷阱是**视觉相关的错觉**：两条曲线的交叉点、谁在谁上面，完全由
两根轴的缩放决定，不是数据本身的性质。把右轴范围改一下，两条线的
相对位置就全变了。评审看到"两条线同步上升"会以为是因果关系，
其实可能只是两个都在涨。所以这里做了三件事：

    1. 左右轴各用各的颜色，线的颜色和对应轴的颜色**绑定**，
       读者不会认错哪条线读哪根轴；
    2. 图里明确写出两根轴各自的量纲标签；
    3. meta 里可以传 note，在图上压一行说明文字。

**不要用这张图暗示因果**。真要论证因果，请用 fig.timeseries 分别画，
或做滞后相关分析。

数据从哪来
----------
data 的键：
    x            横轴（两条序列共用）
    y_left       左轴序列
    y_right      右轴序列
    left_label   左轴名称（含单位，可选）
    right_label  右轴名称（含单位，可选）

meta 里可能有：caption / x_label / width_in / note
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

_COLOR_LEFT = "#1f4e79"
_COLOR_RIGHT = "#c0504d"


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    x = list(data.get("x") or [])
    if not x:
        raise ValueError(
            "缺少必填输入 x：请提供横轴（通常是时间），两条序列共用，"
            "例如 [1, 2, 3, 4, 5]。"
        )

    y_left = list(data.get("y_left") or [])
    if not y_left:
        raise ValueError(
            "缺少必填输入 y_left：请提供左纵轴的序列，长度要等于 x。"
        )
    y_right = list(data.get("y_right") or [])
    if not y_right:
        raise ValueError(
            "缺少必填输入 y_right：请提供右纵轴的序列，长度要等于 x。"
        )

    if len(y_left) != len(x):
        raise ValueError(
            f"y_left 有 {len(y_left)} 个点，x 有 {len(x)} 个点：数量必须一致。"
        )
    if len(y_right) != len(x):
        raise ValueError(
            f"y_right 有 {len(y_right)} 个点，x 有 {len(x)} 个点：数量必须一致。"
        )

    try:
        yl = [float(v) for v in y_left]
        yr = [float(v) for v in y_right]
    except (TypeError, ValueError):
        raise ValueError(
            "y_left / y_right 必须是数值序列：请检查是否混入了文字或空缺。"
        )

    left_label = mcmplot.safe(str(data.get("left_label")
                                  or meta.get("y_label") or "左轴量"))
    right_label = mcmplot.safe(str(data.get("right_label") or "右轴量"))

    width = float(meta.get("width_in", 6.6))
    fig, ax_left = plt.subplots(figsize=(width, 3.9))
    # twinx 共享 x 轴：这正是"同一根时间轴，两根 y 轴"。
    ax_right = ax_left.twinx()

    ln1, = ax_left.plot(x, yl, "-o", lw=1.8, ms=3.6, color=_COLOR_LEFT,
                        label=left_label)
    ln2, = ax_right.plot(x, yr, "-s", lw=1.8, ms=3.4, color=_COLOR_RIGHT,
                         label=right_label)

    # 轴的颜色跟线绑定。不做这一步，读者会默认左轴黑色对应"第一条线"，
    # 而两条线如果换了颜色就彻底对不上。
    ax_left.set_ylabel(left_label, color=_COLOR_LEFT)
    ax_left.tick_params(axis="y", labelcolor=_COLOR_LEFT)
    ax_right.set_ylabel(right_label, color=_COLOR_RIGHT)
    ax_right.tick_params(axis="y", labelcolor=_COLOR_RIGHT)
    ax_left.spines["left"].set_color(_COLOR_LEFT)
    ax_right.spines["right"].set_color(_COLOR_RIGHT)

    ax_left.set_xlabel(mcmplot.safe(meta.get("x_label", "时间")))

    # 两套图例分开画在各自一侧，颜色轴和图例才一一对应。
    ax_left.legend(handles=[ln1], frameon=False, fontsize=8, loc="upper left")
    ax_right.legend(handles=[ln2], frameon=False, fontsize=8, loc="upper right")

    if meta.get("caption"):
        ax_left.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    # 提醒读者两根轴独立缩放，避免把交叉点读成因果。
    note = meta.get("note")
    if note is None:
        note = "左右纵轴量纲不同、各自独立缩放，两条线的相对高低不具有可比性"
    if note:
        ax_left.text(0.5, -0.20, mcmplot.safe(str(note)),
                     transform=ax_left.transAxes, ha="center", va="top",
                     fontsize=7, color="#6c757d")
    ax_left.grid(alpha=0.3)
    fig.tight_layout()
    return fig
