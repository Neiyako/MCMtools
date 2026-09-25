"""fig.waterfall_contribution —— 贡献分解瀑布图。

这张图解决什么问题
------------------
敏感性分析有两种讲法：一种是"参数抖动 ±10% 时输出怎么变"（折线），
另一种是"总量相对基准差了多少，这差值是哪些因素凑出来的"（瀑布）。
后者才是论文结论段要的那句话 —— 一张瀑布图把"总变化 = 各因素贡献之和"
变成了肉眼可核对的事实，评审不用去加表格里的数字。

数据从哪来
----------
data 的键：
    labels       各因素的名字，顺序就是柱子的顺序
    values       各因素的贡献，可正可负（通常来自基准情景的差值）
    base         起始值（可选，默认 0）—— 给 0 时就是"从零累加到总量"
    total_label  总量柱的名字（可选）

meta 里可能有：caption / x_label / y_label / width_in

配色约定
--------
增加蓝、减少红。这是财务瀑布图的通用语言，评审不需要看图例。
总量柱单独用深灰 —— 它不是"因素"，画成同色会让人以为它也是一个贡献项。
"""

from __future__ import annotations

from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402

UP_COLOR = "#2e6f9e"     # 增加
DOWN_COLOR = "#c0392b"   # 减少
TOTAL_COLOR = "#4a4a4a"  # 总量柱：不是因素，颜色必须区分开


def render(data: Dict[str, Any], meta: Dict[str, Any] | None = None):
    meta = meta or {}

    labels = [mcmplot.safe(str(s)) for s in (data.get("labels") or [])]
    if not labels:
        raise ValueError(
            "缺少必填输入 labels：请给出每个因素的名字，顺序与 values 一致。"
        )

    raw_values = data.get("values")
    if raw_values is None or len(raw_values) == 0:
        raise ValueError(
            "缺少必填输入 values：请给出各因素对总量的贡献（可正可负）。"
        )
    values = [float(v) for v in raw_values]
    if len(values) != len(labels):
        raise ValueError(
            f"labels 有 {len(labels)} 个，values 有 {len(values)} 个，数量必须一致。"
        )

    # base 显式用 "is None" 判断：base=0.0 是完全合法的起点，
    # 用 or 会把 0 当成"没给"，然后悄悄用别的默认值。
    base_raw = data.get("base")
    base = 0.0 if base_raw is None else float(base_raw)
    total_label = mcmplot.safe(str(data.get("total_label") or "总量"))

    n = len(values)
    # 柱子顺序：起点 -> n 个因素 -> 总量
    positions = list(range(n + 2))
    bottoms: List[float] = []
    heights: List[float] = []
    colors: List[str] = []

    # 起点柱：从 0 画到 base。没有它，读者不知道各因素是"在什么基础上"加减的。
    bottoms.append(0.0)
    heights.append(base)
    colors.append(TOTAL_COLOR)

    running = base
    for v in values:
        # 悬空柱：bottom 取累积到上一个因素为止的值，柱子本身的高度是
        # 贡献的绝对值。直接画 v（带符号）在 v<0 时会从底部往上翻，
        # 看起来像增加，是这张图最容易画错的地方。
        bottoms.append(min(running, running + v))
        heights.append(abs(v))
        colors.append(UP_COLOR if v >= 0 else DOWN_COLOR)
        running += v

    total = base + sum(values)
    bottoms.append(0.0)
    heights.append(total)
    colors.append(TOTAL_COLOR)

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.6), 4.1))
    ax.bar(positions, heights, bottom=bottoms, width=0.62, color=colors,
           edgecolor="white", linewidth=0.8, zorder=3)

    # 柱子之间的虚线连接：瀑布图的"瀑布"感全靠它，
    # 没有连线就退化成一张普通柱状图，累加关系看不出来。
    levels = [base] + [bottoms[i] + heights[i] for i in range(1, n + 1)]
    for i in range(n):
        level = base + sum(values[: i + 1])
        ax.plot([i - 0.31, i + 1 + 0.31], [level, level], ls=":", lw=0.9,
                color="#8a8a8a", zorder=1)

    # 柱顶标数值。标签本身也随正负分色，扫一眼就知道哪几个因素是主因。
    tick_labels = ["基准"] + labels + [total_label]
    for i, (b, h) in enumerate(zip(bottoms, heights)):
        if i == 0:
            text = mcmplot.fmt(base)          # 起点柱顶 = 起点值本身
        elif i == n + 1:
            text = mcmplot.fmt(total)          # 总量柱顶 = 累计结果
        else:
            v = values[i - 1]
            # 贡献为 0（该因素没起作用）时不要标成 "-0"，直接写 0。
            text = ("+" if v > 0 else "") + mcmplot.fmt(v)
        ax.annotate(text, xy=(i, b + h), xytext=(0, 4),
                    textcoords="offset points", ha="center", fontsize=8,
                    color=colors[i])

    # 基准水平线：一眼看出哪些因素把总量推到了起点之上/之下。
    ax.axhline(base, ls="--", lw=1.0, color="#b03030", alpha=0.7, zorder=2)
    ax.annotate(f"基准 {mcmplot.fmt(base)}", xy=(0.995, base),
                xycoords=("axes fraction", "data"), ha="right", va="bottom",
                fontsize=8, color="#b03030")

    ax.axhline(0.0, lw=0.9, color="#444444", zorder=2)
    ax.set_xticks(positions)
    # 因素多的时候横排字会叠在一起，超过 6 个就转 30 度。
    ax.set_xticklabels(tick_labels, rotation=30 if n > 6 else 0,
                       ha="right" if n > 6 else "center")
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "数值")))
    if meta.get("x_label"):
        ax.set_xlabel(mcmplot.safe(meta["x_label"]))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))

    # 自定义图例：默认图例只认颜色，这里三种颜色对应三种语义，
    # 必须写清楚，否则读者会把总量柱也当成一个因素。
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=UP_COLOR),
        plt.Rectangle((0, 0), 1, 1, color=DOWN_COLOR),
        plt.Rectangle((0, 0), 1, 1, color=TOTAL_COLOR),
    ]
    ax.legend(handles, ["增加", "减少", "基准 / 总量"], frameon=False,
              fontsize=8, loc="best")
    ax.grid(alpha=0.3, axis="y", zorder=0)
    fig.tight_layout()
    return fig
