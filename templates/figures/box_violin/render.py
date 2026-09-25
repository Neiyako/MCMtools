"""fig.box_violin —— 箱线 / 小提琴组合图，比较多个分组的分布。

为什么不是纯箱线图
------------------
箱线图只画五个数（min/Q1/中位数/Q3/max），**看不见双峰**。
两个组中位数、四分位数完全一样，但一个是单峰一个是双峰，
箱线图长得一模一样 —— 而这两个组的实际含义天差地别。
小提琴图用核密度把整个形状画出来，双峰一眼可见。

为什么也不是纯小提琴图
----------------------
小提琴图没有刻度感：读者没法从琴身宽度读出中位数到底在哪。
所以这里把箱线图嵌进琴身，再叠一层抖动散点 —— 散点还顺便暴露了
每组的实际样本量（琴身再宽也不能告诉你 n=8 还是 n=800）。

关键取舍：分组多了就不要小提琴
------------------------------
小提琴的宽度需要足够样本才能估出可信的密度。分组一多，每条琴身
被压得很窄，密度曲线互相重叠成一团墨，读者反而什么都读不出来。
所以 **分组数 <= 4 时画小提琴+箱线+散点，> 4 时退化成箱线+散点**。
这是刻意的降级，不是偷懒。

数据从哪来
----------
    groups       必填，"平行数组"形式：groups[i] 是 values[i] 所属的组名，
                 长度与 values 相同（例如 30 个样本分成 3 组就是 30 个组名）
    values       必填，与 groups 平行的一维数值序列
    group_order  可选，指定分组在横轴上的排列顺序；不给就按首次出现排

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

_PRIMARY = "#1f4e79"
_FILL = "#cfe0f0"
_MEDIAN = "#b03030"

# 分组数超过这个值就不再画小提琴：琴身会挤成一片，密度形状反而读不出来。
_MAX_VIOLIN_GROUPS = 4

# 每组散点最多画这么多个。几千个点全画上去只会糊成墨块，
# 抖动散点本来就是为了让读者看见"这组大概有多少个样本"，抽样足够表达。
_MAX_SCATTER_PER_GROUP = 120


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    names, series = _as_groups(data)

    n_groups = len(names)
    fig_w = float(meta.get("width_in", 6.4))
    # 分组越多画布越宽，否则箱体被挤成细条，箱线读不出四分位。
    fig_w = max(fig_w, 1.15 * n_groups + 1.6)
    fig, ax = plt.subplots(figsize=(fig_w, 3.9))

    positions = np.arange(1, n_groups + 1)
    use_violin = n_groups <= _MAX_VIOLIN_GROUPS

    if use_violin:
        _draw_violins(ax, series, positions)

    # 箱线图永远画：它是可读性的底线 —— 就算小提琴形状被样本量带偏，
    # 中位数和四分位距仍然是稳的。
    bp = ax.boxplot(
        series, positions=positions, widths=0.22 if use_violin else 0.5,
        patch_artist=True, showfliers=False,  # 离群点交给抖动散点去表现，避免画两遍
        medianprops={"color": _MEDIAN, "lw": 1.6},
        boxprops={"facecolor": "white" if use_violin else _FILL,
                  "edgecolor": _PRIMARY, "lw": 1.0},
        whiskerprops={"color": _PRIMARY, "lw": 1.0},
        capprops={"color": _PRIMARY, "lw": 1.0},
    )
    if use_violin:
        # 白底箱体压在小提琴上，中位数在图中才看得清。
        for box in bp["boxes"]:
            box.set_alpha(0.85)
    for med in bp["medians"]:
        med.set_zorder(5)

    _draw_jitter(ax, series, positions)

    # 每组上方标样本量：小提琴的宽度受样本量影响很大，
    # 不标 n 的话读者会把"样本少导致的瘦"误读成"方差小"。
    for pos, vals in zip(positions, series):
        ax.annotate(
            mcmplot.safe(f"n={len(vals)}"), xy=(pos, 1.0),
            xycoords=("data", "axes fraction"), xytext=(0, 3),
            textcoords="offset points", ha="center", va="bottom",
            fontsize=7, color="#666666",
        )

    ax.set_xticks(positions)
    ax.set_xticklabels([mcmplot.safe(n) for n in names])
    ax.set_xlim(0.4, n_groups + 0.6)
    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "分组")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "指标值")))

    # 图上写明当前是哪种形态，免得读者以为"没有小提琴"是画错了。
    ax.annotate(
        mcmplot.safe("小提琴 + 箱线 + 散点" if use_violin
                     else f"分组数 > {_MAX_VIOLIN_GROUPS}，只画箱线 + 散点"),
        xy=(0.99, 0.02), xycoords="axes fraction", ha="right", va="bottom",
        fontsize=7, color="#888888",
    )

    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3, axis="y")
    ax.set_axisbelow(True)
    fig.tight_layout()
    return fig


def _draw_violins(ax, series: List[List[float]], positions: np.ndarray) -> None:
    """画小提琴（仅在分组数少时调用）。"""
    shown = False
    for pos, vals in zip(positions, series):
        if len(vals) < 2:
            # 一个点估不出密度，跳过这只琴（箱线图仍然会把它画出来）。
            continue
        parts = ax.violinplot(
            [vals], positions=[pos], widths=0.8,
            showmeans=False, showmedians=False, showextrema=False,
        )
        for body in parts["bodies"]:
            body.set_facecolor(_FILL)
            body.set_edgecolor(_PRIMARY)
            body.set_alpha(0.75)
            body.set_linewidth(1.0)
        shown = True
    if not shown:
        return


def _draw_jitter(ax, series: List[List[float]], positions: np.ndarray) -> None:
    """抖动散点：把每个观测画成一个半透明小点。

    抖动是必要的 —— 数据里相同取值很多（评分类数据尤其如此），
    不抖动的话点会完全重叠，读者看到 5 个点其实有 500 个。
    """
    rng = np.random.default_rng(20240101)  # 固定种子，保证每次出图一模一样
    for pos, vals in zip(positions, series):
        arr = np.asarray(vals, dtype=float)
        if arr.size == 0:
            continue
        if arr.size > _MAX_SCATTER_PER_GROUP:
            idx = rng.choice(arr.size, size=_MAX_SCATTER_PER_GROUP, replace=False)
            arr = arr[np.sort(idx)]
        jitter = rng.uniform(-0.12, 0.12, size=arr.size)
        ax.scatter(pos + jitter, arr, s=5, color="#444444", alpha=0.35,
                   linewidths=0, zorder=4)


def _as_groups(data: Dict[str, Any]):
    """把输入整理成 (组名列表, 每组数值列表)。

    模板声明的是"平行数组"形状（groups[i] 说明 values[i] 属于哪组），
    因为上层从长表整理数据时最自然就是这种形状。同时也接受
    dict{组名: 数值列表}，那是人手写测试数据时更顺手的写法。
    """
    groups = data.get("groups")
    values = data.get("values")

    if groups is None:
        raise ValueError(
            "缺少必填输入 groups：请提供与 values 等长的分组名序列"
            "（groups[i] 表示 values[i] 属于哪一组）。"
        )
    if values is None:
        raise ValueError(
            "缺少必填输入 values：请提供与 groups 等长的数值序列。"
        )

    # 形状一：dict{组名: 数值列表}
    if isinstance(values, dict):
        raw_order = data.get("group_order")
        order = ([str(g) for g in raw_order] if raw_order
                 else [str(k) for k in values.keys()])
        missing = [g for g in order if g not in values]
        if missing:
            raise ValueError(
                f"group_order 里的分组 {missing} 在 values 里不存在，"
                f"values 只有这些分组：{list(values.keys())}。"
            )
        series = [[float(v) for v in values[g]] for g in order]
        return order, series

    groups = list(groups)
    values = list(values)
    if len(groups) != len(values):
        # 平行数组长度不一致时，分组归属会整体错位。
        # 这种错误画出来的图**看着完全正常**，但结论是错的，必须拦住。
        raise ValueError(
            f"groups 有 {len(groups)} 个，values 有 {len(values)} 个，数量必须一致"
            "（groups[i] 必须说明 values[i] 属于哪一组）。"
        )
    if not values:
        raise ValueError("values 是空的：至少需要一个观测值才能画分布。")

    buckets: Dict[str, List[float]] = {}
    for g, v in zip(groups, values):
        try:
            fv = float(v)
        except (TypeError, ValueError):
            raise ValueError(
                f"values 里出现了非数值项 {v!r}：分布图只能接受数值序列，"
                "请先清洗缺失值。"
            )
        buckets.setdefault(str(g), []).append(fv)

    raw_order = data.get("group_order")
    if raw_order:
        wanted = [str(g) for g in raw_order]
        missing = [g for g in wanted if g not in buckets]
        if missing:
            raise ValueError(
                f"group_order 里的分组 {missing} 在 groups 里不存在，"
                f"groups 里实际有：{list(buckets.keys())}。"
            )
        names = [g for g in wanted if g in buckets]
        names += [g for g in buckets if g not in names]  # 没点名的排后面，不丢数据
    else:
        names = list(buckets.keys())  # 按首次出现，尊重用户给的顺序

    return names, [buckets[n] for n in names]
