"""fig.cumulative_curve —— 累积曲线（含与参考基线的偏离面积）。

为什么要有这张图
----------------
累积曲线回答的是"前多少个单位贡献了多少总量"。它的信息量和普通折线
完全不同：斜率陡的地方是主要贡献者，斜率平坦的地方是拖后腿的部分。

更重要的是**曲线与参考线之间的面积**。洛伦兹曲线的基尼系数就是这个
面积的两倍；学习曲线里"累积产出 vs 理论下界"的差距也是这个面积。
把面积涂出来，评审不需要读任何数字就能判断"偏离均匀分布有多远" ——
这比在正文里写一个基尼系数值有说服力得多。

数据从哪来
----------
data 的键：
    x             横轴，通常已归一化到 [0, 1]（人口累计比例 / 时间）
    y             累积量，通常也已归一化到 [0, 1]
    reference_x   参考线的横轴（可选）
    reference_y   参考线的纵轴（可选）

参考线可以是洛伦兹图的对角线（y = x）、理论最优学习曲线、
或者任何"如果完全均匀/完全理想会是什么样"的基线。
两条参考轴**同时**给出才画；只给一条会报错而不是猜 ——
猜出来的参考线会把面积涂在错误的位置，而图看起来还是对的。

meta 里可能有：caption / x_label / y_label / width_in / fill / reference_label
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


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    y = data.get("y")
    if y is None or len(y) == 0:
        raise ValueError(
            "缺少必填输入 y：请提供累积量序列（通常是已经累加过的值，"
            "不是每期的增量）。"
        )
    y = [float(v) for v in y]

    x = data.get("x")
    if x is None or len(x) == 0:
        raise ValueError(
            "缺少必填输入 x：请提供与 y 对应的横轴，"
            "例如累计人口比例或时间步。"
        )
    x = [float(v) for v in x]

    if len(x) != len(y):
        raise ValueError(
            f"x 有 {len(x)} 个点，y 有 {len(y)} 个点，数量必须一致。"
        )
    if len(x) < 2:
        # 一个点的"曲线"没法谈斜率，也没法填充面积。
        raise ValueError(
            f"x / y 只有 {len(x)} 个点，累积曲线至少需要 2 个点才能成形。"
        )

    ref_x_raw = data.get("reference_x")
    ref_y_raw = data.get("reference_y")
    if (ref_x_raw is None) != (ref_y_raw is None):
        raise ValueError(
            "reference_x 与 reference_y 必须同时提供（缺一个就不画参考线）。"
            "只想画曲线本身时，请把两个都留空。"
        )

    ref_x = [float(v) for v in ref_x_raw] if ref_x_raw is not None else None
    ref_y = [float(v) for v in ref_y_raw] if ref_y_raw is not None else None
    if ref_x is not None and len(ref_x) != len(ref_y or []):
        raise ValueError(
            f"reference_x 有 {len(ref_x)} 个点，reference_y 有 {len(ref_y or [])} 个点，"
            "数量必须一致。"
        )

    width = float(meta.get("width_in", 6.0))
    fig, ax = plt.subplots(figsize=(width, width * 0.78))

    # 偏离面积先画，压在曲线下面。
    # 为什么必须同 x 网格：fill_between 要求两条线在同一个横坐标上取值，
    # 参考线采样点不一样时直接填会填出锯齿。这里把参考线插值到 x 上。
    # 默认只在给了参考线时填 —— 没有参考线就没有"偏离"可言。
    do_fill = bool(meta.get("fill", ref_x is not None))
    if ref_x is not None and do_fill:
        ry = np.interp(np.asarray(x, dtype=float),
                       np.asarray(ref_x, dtype=float),
                       np.asarray(ref_y, dtype=float))
        cy = np.asarray(y, dtype=float)
        # 填充色表达"偏离"的方向没有正负之分，用中性色；
        # 上/下两种偏离分别用曲线色和参考色，方便正文里指认。
        ax.fill_between(x, cy, ry, where=(cy >= ry),
                        color="#1f4e79", alpha=0.18, linewidth=0,
                        label=mcmplot.safe("高于参考"))
        ax.fill_between(x, cy, ry, where=(cy < ry),
                        color="#c0392b", alpha=0.18, linewidth=0,
                        label=mcmplot.safe("低于参考"))

    if ref_x is not None:
        # 参考线用灰色虚线：它是"本应该是什么样"，不该抢主曲线的视觉重量。
        ax.plot(ref_x, ref_y, "--", lw=1.3, color="#7f7f7f",
                label=mcmplot.safe(str(meta.get("reference_label", "参考基线"))))

    ax.plot(x, y, "-", lw=2.0, color="#1f4e79",
            label=mcmplot.safe(str(meta.get("y_label", "累积量"))))

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "累计比例")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "累积量")))
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
