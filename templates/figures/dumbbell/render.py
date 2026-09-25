"""fig.dumbbell —— 哑铃图（两个时点/两种方案的连线对比）。

为什么不用分组柱状图
--------------------
分组柱把"改造前"和"改造后"画成两根并排的柱子，读者的眼睛要在两列之间
来回跳，还得自己心算差值 —— 而这张图想说的恰恰就是**差值**。
哑铃图把两个点用一条线连起来：线的方向就是增减，线的长度就是幅度，
"哪一项改善最大"直接变成图上最长的那根线。

哪个是主色
----------
右端的点（after）用主色，左端（before）用灰色。理由是论文里
"改造后的结果"才是结论，"改造前"只是参照。

数据从哪来
----------
data 的键：
    categories     对比对象的名称
    before         第一个时点的数值（长度与 categories 一致）
    after          第二个时点的数值（长度与 categories 一致）
    before_label   第一端的图例名（可选），如 "改造前"
    after_label    第二端的图例名（可选），如 "改造后"

meta 里可能有：caption / x_label / y_label / width_in / sort / delta_label
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

_COLOR_BEFORE = "#9aa5b1"
_COLOR_AFTER = "#1f4e79"
_COLOR_UP = "#c0504d"     # 增加：暖色
_COLOR_DOWN = "#2e7d32"   # 减少：冷色


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    categories = data.get("categories")
    if not categories:
        raise ValueError(
            "缺少必填输入 categories：请提供对比对象的名称列表，"
            "例如 ['北京','上海','广东']。"
        )
    categories = [mcmplot.safe(str(c)) for c in categories]

    before = list(data.get("before") or [])
    if not before:
        raise ValueError(
            "缺少必填输入 before：请提供第一个时点/方案的数值序列，"
            "长度要等于 categories。"
        )
    after = list(data.get("after") or [])
    if not after:
        raise ValueError(
            "缺少必填输入 after：请提供第二个时点/方案的数值序列，"
            "长度要等于 categories。"
        )

    n = len(categories)
    if len(before) != n:
        raise ValueError(
            f"before 有 {len(before)} 个值，categories 有 {n} 个：数量必须一致。"
        )
    if len(after) != n:
        raise ValueError(
            f"after 有 {len(after)} 个值，categories 有 {n} 个：数量必须一致。"
        )

    try:
        b = np.asarray(before, dtype=float)
        a = np.asarray(after, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "before / after 必须是数值序列：请检查是否混入了文字或空缺。"
        )
    if not (np.all(np.isfinite(b)) and np.all(np.isfinite(a))):
        raise ValueError(
            "before / after 里有空值：每一端都要有一个实际数值才能连线。"
        )

    before_label = mcmplot.safe(str(data.get("before_label") or "方案一"))
    after_label = mcmplot.safe(str(data.get("after_label") or "方案二"))

    # 排序：默认按差值从大到小，读者第一眼看到的就是变化最大的那项。
    order = list(range(n))
    if meta.get("sort", True):
        order.sort(key=lambda i: abs(a[i] - b[i]), reverse=True)

    width = float(meta.get("width_in", 6.0))
    height = max(2.6, 0.42 * n + 1.5)
    fig, ax = plt.subplots(figsize=(width, height))

    ys = list(range(n))
    for pos, i in enumerate(order):
        y = n - 1 - pos            # 差值最大的排最上面
        lo, hi = (b[i], a[i]) if b[i] <= a[i] else (a[i], b[i])
        # 连线颜色表示方向：涨用暖色，跌用冷色，让"改善/恶化"一眼可辨。
        color = _COLOR_UP if a[i] >= b[i] else _COLOR_DOWN
        ax.plot([lo, hi], [y, y], "-", lw=2.4, color=color, alpha=0.55,
                solid_capstyle="round", zorder=2)
        ax.scatter([b[i]], [y], s=52, color=_COLOR_BEFORE, zorder=3,
                   edgecolors="white", linewidths=0.8)
        ax.scatter([a[i]], [y], s=52, color=_COLOR_AFTER, zorder=4,
                   edgecolors="white", linewidths=0.8)

        # 差值标在线的上方。用 ASCII 的 + / - 而不是箭头符号：
        # 箭头在部分中文字体里缺字形，会变成方框，而 + / - 一定有。
        delta = a[i] - b[i]
        if delta > 0:
            sign = "+"
        elif delta < 0:
            sign = "-"
        else:
            sign = ""
        ax.annotate(f"{sign}{mcmplot.fmt(abs(delta))}",
                    xy=((lo + hi) / 2.0, y),
                    xytext=(0, 7), textcoords="offset points",
                    ha="center", fontsize=7.5, color=color)

    ax.set_yticks(ys)
    ax.set_yticklabels([categories[i] for i in reversed(order)])
    ax.set_ylim(-0.7, n - 0.3)

    # 图例用空点，只为说明两种颜色各代表哪一端。
    ax.scatter([], [], s=52, color=_COLOR_BEFORE, label=before_label)
    ax.scatter([], [], s=52, color=_COLOR_AFTER, label=after_label)
    ax.legend(frameon=False, fontsize=8, loc="best")

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "数值")))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    return fig
