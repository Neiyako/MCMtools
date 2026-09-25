"""fig.pareto_frontier —— 双目标权衡的帕累托前沿。

这张图为什么值得单独做一个模板
------------------------------
优化类题目的核心结论不是"我选了解 A"，而是"在 A 和 B 之间只能这样换"。
语料里几乎没有论文画这张图，代价是评审看不到取舍 —— 只有一个孤零零的
最优解，读者无法判断它是不是运气好。这张图的全部价值在于把**被支配的点**
一并画出来：有了灰点当背景，前沿线才显得是"顶出来的"，而不是随手连的。

数据从哪来
----------
data 的键：
    x             目标 1 的取值，越大越好或越小越好都行，模板不替用户改符号
    y             目标 2 的取值
    frontier_idx  哪些下标属于前沿（可选）—— 给了就用，不给就自己算
    label         每个点的名字（可选）—— 只标注前沿点，标全部会糊成一片

meta 里可能有：caption / x_label / y_label / width_in

关于"自己算前沿"
----------------
不给 frontier_idx 时按最大化的语义算：点 i 被支配，当且仅当存在 j 使
x_j >= x_i 且 y_j >= y_i 且至少一个严格大。这是最小化题目最常踩的坑 ——
如果用户的目标是越小越好，请先自己取负号再传进来，或者直接传 frontier_idx。
模板不提供 sense 参数：一个"猜方向"的开关猜错时图看起来照样正常，
却会给出完全相反的结论，这种错误比报错危险得多。
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


def _pareto_front(xs: List[float], ys: List[float]) -> List[int]:
    """返回不被任何点支配的下标（最大化语义）。

    朴素 O(n^2)：设计点通常几百个，向量化带来的那点速度不值得多一层
    索引绕晕后来改代码的人。点超过几千个时再换排序扫描的写法。
    """
    n = len(xs)
    on_front = []
    for i in range(n):
        dominated = False
        for j in range(n):
            if i == j:
                continue
            # j 在两个目标上都不差，且至少有一个更好 -> i 被支配
            if xs[j] >= xs[i] and ys[j] >= ys[i] and (xs[j] > xs[i] or ys[j] > ys[i]):
                dominated = True
                break
        if not dominated:
            on_front.append(i)
    return on_front


def render(data: Dict[str, Any], meta: Dict[str, Any] | None = None):
    meta = meta or {}

    x = [float(v) for v in (data.get("x") or [])]
    if not x:
        # 空图看起来像"跑成功了但没结果"，比直接报错难查得多。
        raise ValueError("缺少必填输入 x：请提供第一个目标的取值序列。")
    y = [float(v) for v in (data.get("y") or [])]
    if not y:
        raise ValueError("缺少必填输入 y：请提供第二个目标的取值序列。")
    if len(x) != len(y):
        raise ValueError(
            f"x 有 {len(x)} 个点，y 有 {len(y)} 个点，数量必须一致。"
        )

    label = list(data.get("label") or [])
    if label and len(label) != len(x):
        raise ValueError(
            f"label 有 {len(label)} 个，x 有 {len(x)} 个点，数量必须一致。"
        )

    frontier_idx = data.get("frontier_idx")
    if frontier_idx is None:
        front = _pareto_front(x, y)
    else:
        front = []
        for raw in frontier_idx:
            i = int(raw)
            if i < 0 or i >= len(x):
                raise ValueError(
                    f"frontier_idx 里有下标 {i}，但只有 {len(x)} 个点，"
                    "下标必须在 0 到点数-1 之间。"
                )
            front.append(i)
        if not front:
            raise ValueError(
                "frontier_idx 是空列表：要么给出至少一个前沿点下标，"
                "要么整个不传，让模板自己算前沿。"
            )

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 4.2))

    front_set = set(front)
    rest = [i for i in range(len(x)) if i not in front_set]

    # 被支配的点：小而灰，并且透明。它们是背景而不是信息 ——
    # 一旦画得和前沿点一样重，读者会以为两者同等重要。
    if rest:
        ax.plot([x[i] for i in rest], [y[i] for i in rest], "o", ms=4.0,
                color="#9aa0a6", alpha=0.55, mec="none",
                label=mcmplot.safe(f"被支配解 (n={len(rest)})"))

    # 前沿点按 x 排序后再连线：散点集合本身没有顺序，连线顺序错了
    # 会连出一条自交的"面条"，比不连线更误导。
    front_sorted = sorted(front, key=lambda i: (x[i], y[i]))
    ax.plot([x[i] for i in front_sorted], [y[i] for i in front_sorted],
            "-", lw=1.6, color="#c0392b", alpha=0.85, zorder=2)
    ax.plot([x[i] for i in front_sorted], [y[i] for i in front_sorted],
            "o", ms=8.0, color="#c0392b", mec="white", mew=0.9, zorder=3,
            label=mcmplot.safe(f"帕累托前沿 (n={len(front)})"))

    # 只标前沿点。全部标注在几百个设计点上会变成一团黑，
    # 而读者真正想读的点名只有前沿那几个。
    if label:
        for i in front_sorted:
            ax.annotate(mcmplot.safe(str(label[i])), xy=(x[i], y[i]),
                        xytext=(6, 6), textcoords="offset points",
                        fontsize=8, color="#7b241c")

    # 前沿是"右上角的天花板"：画一条淡对角线示意改进方向，
    # 评审一眼就知道哪边更好，不用去读坐标轴。
    if len(front_sorted) >= 2:
        i0, i1 = front_sorted[0], front_sorted[-1]
        ax.annotate("", xy=(x[i1], y[i1]), xytext=(x[i0], y[i0]),
                    arrowprops=dict(arrowstyle="->", color="#c0392b",
                                    lw=1.0, alpha=0.35, ls="--"))

    # 支配关系的方向提示放在空白角：这张图的重点就是"往上往右更好"。
    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "目标 1")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "目标 2")))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.tight_layout()
    return fig
