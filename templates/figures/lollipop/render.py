"""fig.lollipop —— 火柴棒图（排序后的对比）。

为什么比柱状图好
----------------
条目一多（15 个以上），柱状图的柱子会细成一条线，而柱子本身占的面积
并没有传递任何信息 —— 读者看的只是"端点在哪"。火柴棒图只留下
一条细杆加一个圆点，同样的画布能多放一倍条目，标签也不再挤在一起。
排序之后，"前几名是谁"直接就是从上往下读。

高亮而不是删减
--------------
常见需求是"把重点条目挑出来"。这里**不删掉其它条目** ——
删了读者就不知道重点是在什么背景下突出的。改为把关心的条目换色、
其余保留灰色，并给出图例。

数据从哪来
----------
data 的键：
    categories   条目名称
    values       各条目的数值（长度与 categories 一致）
    highlight    与 categories 等长的真/假标记（可选），为真的条目高亮
    highlight_label  高亮条目的图例名（可选）

meta 里可能有：caption / x_label / y_label / width_in / top_n / ascending
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

_COLOR_DIM = "#adb5bd"
_COLOR_HI = "#c0504d"
_COLOR_LINE = "#6c757d"


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    categories = data.get("categories")
    if not categories:
        raise ValueError(
            "缺少必填输入 categories：请提供条目名称列表，"
            "例如 ['因素A','因素B','因素C']。"
        )
    categories = [mcmplot.safe(str(c)) for c in categories]

    values = list(data.get("values") or [])
    if not values:
        raise ValueError(
            "缺少必填输入 values：请提供各条目的数值序列，长度要等于 categories。"
        )
    if len(values) != len(categories):
        raise ValueError(
            f"values 有 {len(values)} 个，categories 有 {len(categories)} 个："
            "每个条目对应一个数值，数量必须一致。"
        )
    try:
        vals = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "values 必须是数值序列：请检查是否混入了文字或空缺。"
        )
    if not np.all(np.isfinite(vals)):
        raise ValueError(
            "values 里有空值：每个条目都要有一个实际数值才能排序。"
        )

    # 高亮标记：与 categories 等长。长度对不上要报错，
    # 静默按最短的截断会让高亮错位到别的条目上。
    highlight = data.get("highlight")
    flags = [False] * len(categories)
    if highlight is not None:
        highlight = list(highlight)
        if len(highlight) != len(categories):
            raise ValueError(
                f"highlight 有 {len(highlight)} 项，categories 有 "
                f"{len(categories)} 个：高亮标记要和条目一一对应。"
            )
        flags = [bool(h) for h in highlight]

    # 默认降序（数值大的在上），排名类图从最重要读到最不重要。
    ascending = bool(meta.get("ascending", False))
    order = sorted(range(len(categories)), key=lambda i: vals[i],
                   reverse=not ascending)

    # top_n 只**标注**前 n 名的数值，不删条目 —— 条目被删读者就
    # 不知道重点是在什么背景下突出的。
    top_n = meta.get("top_n")
    if top_n is None:
        top_n = max(3, len(order) // 3)
    top_n = int(top_n)

    width = float(meta.get("width_in", 6.0))
    height = max(2.6, 0.30 * len(categories) + 1.4)
    fig, ax = plt.subplots(figsize=(width, height))

    ypos = {i: len(order) - 1 - pos for pos, i in enumerate(order)}
    any_hi = any(flags)

    for i in range(len(categories)):
        y = ypos[i]
        hot = flags[i]
        color = _COLOR_HI if hot else _COLOR_DIM
        # 杆 + 点：这正是一根"火柴"。
        ax.plot([0, vals[i]], [y, y], "-", lw=1.5 if hot else 1.0,
                color=color, alpha=0.9 if hot else 0.7, zorder=2)
        ax.scatter([vals[i]], [y], s=58 if hot else 38, color=color,
                   zorder=3, edgecolors="white", linewidths=0.8)
        # 只给前几名标数字：全标会糊成一片，而读者只需要知道头部多大。
        if ypos[i] >= len(order) - top_n:
            ax.annotate(mcmplot.fmt(vals[i]),
                        xy=(vals[i], y), xytext=(6, 0),
                        textcoords="offset points", ha="left", va="center",
                        fontsize=7.5,
                        color=_COLOR_HI if hot else "#495057")

    ax.set_yticks([ypos[i] for i in range(len(categories))])
    ax.set_yticklabels([categories[i] for i in range(len(categories))],
                       fontsize=8)
    ax.set_ylim(-0.7, len(categories) - 0.3)
    # 左边界留 0：火柴棒的杆要从一条共同的基线长出来，
    # 不固定 0 点的话杆的长度就不再可比。
    ax.set_xlim(left=min(0.0, float(vals.min())) * 1.08,
                right=float(vals.max()) * 1.18 if vals.max() > 0 else 0.1)
    ax.axvline(0, color="#495057", lw=0.9, zorder=1)

    if any_hi:
        label = mcmplot.safe(str(data.get("highlight_label") or "重点条目"))
        ax.scatter([], [], s=58, color=_COLOR_HI, label=label)
        ax.scatter([], [], s=38, color=_COLOR_DIM, label="其余条目")
        ax.legend(frameon=False, fontsize=8, loc="lower right")

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "数值")))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    return fig
