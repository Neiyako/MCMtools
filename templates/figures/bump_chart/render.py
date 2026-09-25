"""fig.bump_chart —— 排名变化图（bump chart）。

为什么要有这张图
----------------
"谁在上升、谁在掉队"用表格读要一行一行对数字，用折线画又会被量纲掩盖。
排名图把纵轴直接换成**名次**（1 在最上），每条线就是一个对象，
交叉点就是名次互换的那一刻 —— 一眼就能指出转折发生在哪一期。

排名图的头号陷阱：纵轴方向
--------------------------
名次 1 是**最好**的，必须画在**最上面**。matplotlib 默认 y 轴向上递增，
照默认画会得到一张完全颠倒的图：冠军掉到页面底部，读者会得出相反的结论。
所以这里强制 invert_yaxis()，并把刻度设成整数名次。

数据从哪来
----------
data 的键：
    entities  对象名列表，个数 = ranks 的行数
    periods   时期名列表，个数 = ranks 的列数
    ranks     二维数组，第 r 行第 c 列 = 对象 r 在第 c 期的名次（1 为最好）

meta 里可能有：caption / x_label / y_label / width_in / annotate / max_entities
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

# 超过这个数量的对象，线会挤成一团，末尾的标签也会重叠。
_MAX_ENTITIES = 12

# 学术配色，顺序固定 —— 同一张图每次渲染的颜色必须一样。
_PALETTE = ["#1f4e79", "#c0504d", "#9bbb59", "#8064a2",
            "#4bacc6", "#f79646", "#2e7d32", "#8d6e63",
            "#455a64", "#ad1457", "#00838f", "#ef6c00"]


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    ranks = data.get("ranks")
    if ranks is None:
        raise ValueError(
            "缺少必填输入 ranks：请提供二维数组，第 r 行第 c 列是对象 r 在第 c 期的名次，"
            "1 表示最好。例如 [[1,2,3],[3,1,2]]。"
        )
    try:
        arr = np.asarray(ranks, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "ranks 不是数值二维数组：每一行代表一个对象在各期的名次，"
            "请检查是否有某一行长度不一致或混入了文字。"
        )
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.size == 0:
        raise ValueError(
            f"ranks 必须是二维数组且非空，当前形状 {arr.shape}。"
        )
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            "ranks 里有空值或非数字：每个对象在每一期都必须有一个名次，"
            "缺失的那期请补上实际名次，不能留空。"
        )

    n_entities, n_periods = arr.shape

    entities = [mcmplot.safe(str(e)) for e in (data.get("entities") or [])]
    if not entities:
        raise ValueError(
            "缺少必填输入 entities：请提供被排名对象的名称列表，"
            f"个数要等于 ranks 的行数（{n_entities}）。"
        )
    if len(entities) != n_entities:
        raise ValueError(
            f"entities 有 {len(entities)} 个，ranks 有 {n_entities} 行："
            "每个对象一行名次，数量必须一致。"
        )

    periods = [mcmplot.safe(str(p)) for p in (data.get("periods") or [])]
    if not periods:
        raise ValueError(
            "缺少必填输入 periods：请提供时期名列表（如年份、轮次），"
            f"个数要等于 ranks 的列数（{n_periods}）。"
        )
    if len(periods) != n_periods:
        raise ValueError(
            f"periods 有 {len(periods)} 个，ranks 有 {n_periods} 列："
            "每一列代表一期，数量必须一致。"
        )

    if n_entities > _MAX_ENTITIES:
        raise ValueError(
            f"排名的对象有 {n_entities} 个，超过 {_MAX_ENTITIES} 个时连线会糊成一团。"
            "请只保留关注的对象，或改用 fig.lollipop 统计最终排名。"
        )
    if n_periods < 2:
        raise ValueError(
            f"periods 只有 {n_periods} 期：排名变化图至少需要两期才看得出变化，"
            "只有一期请改用 fig.lollipop。"
        )

    width = float(meta.get("width_in", 6.6))
    fig, ax = plt.subplots(figsize=(width, 4.4))

    xs = list(range(n_periods))
    annotate = meta.get("annotate", True)

    for i in range(n_entities):
        ys = arr[i]
        color = _PALETTE[i % len(_PALETTE)]
        ax.plot(xs, ys, "-o", lw=1.8, ms=5.0, color=color,
                markerfacecolor="white", markeredgewidth=1.6,
                markeredgecolor=color, zorder=3)

        # 名字标在线两端，读者不用回头查图例。两端都标是因为
        # 排名图的信息就在"从哪来、到哪去"。
        ax.annotate(entities[i], xy=(xs[0], float(ys[0])),
                    xytext=(-7, 0), textcoords="offset points",
                    ha="right", va="center", fontsize=8, color=color)
        ax.annotate(entities[i], xy=(xs[-1], float(ys[-1])),
                    xytext=(7, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=8, color=color)

        # 名次在期内的数值：默认不写，对象少时才写，否则字会压住线。
        if annotate and n_entities <= 6:
            for c in range(n_periods):
                ax.annotate(mcmplot.fmt(ys[c]), xy=(xs[c], float(ys[c])),
                            xytext=(0, 7), textcoords="offset points",
                            ha="center", fontsize=7, color=color)

    # 名次轴：1 在最上。上下都要留够边，因为名次数字写在点上方 7 点处 ——
    # 只留 0.5 的话，第 1 名正好压在轴顶，数字会被顶到坐标区外面、
    # 和标题叠在一起。这里按对象数动态留白，对象越少每名占的高度越大。
    span = max(1.0, float(np.max(arr)) - float(np.min(arr)))
    pad = max(0.75, span * 0.22)
    lo = max(1.0 - pad * 0.5, float(np.min(arr)) - pad)
    hi = float(np.max(arr)) + pad
    ax.set_ylim(hi, lo)          # 直接倒置，不用 invert_yaxis 更明确
    ticks = list(range(int(np.ceil(lo)), int(np.floor(hi)) + 1))
    if ticks:
        ax.set_yticks(ticks)
        ax.set_yticklabels([f"第 {t} 名" for t in ticks])

    ax.set_xticks(xs)
    ax.set_xticklabels(periods)
    ax.set_xlim(-0.55, n_periods - 0.45)
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "名次")))
    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "时期")))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    return fig


def _fmt(v: Any) -> str:
    """统一走 mcmplot.fmt。"""
    return mcmplot.fmt(v)
