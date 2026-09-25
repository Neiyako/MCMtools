"""fig.gantt_schedule —— 甘特图（调度方案 / 排班计划）。

为什么要有这张图
----------------
调度优化题目的答案天然是一张时间表。用表格给的话，评审要在几十行
"开始-结束"之间自己脑补重叠关系；甘特图把同一资源的任务画在同一条
水平线上，冲突（同一条线在同一时刻有两根柱子）和空闲（线中间的空档）
一眼就能看见 —— 这两件事恰好是调度模型的核心结论。

数据从哪来
----------
data 的键：
    tasks      任务名（每条一行），必填
    starts     开始时间，必填
    durations  持续时间，必填
    groups     分组名（可选）—— 同一组的任务同色

横轴单位由调用方决定（小时 / 天 / 周），通过 meta["x_label"] 写清楚。
论文里**必须**写单位，否则"工期 12"没人知道是 12 小时还是 12 天。

设计取舍
--------
- 纵轴从上到下：按人阅读顺序，第一个任务在最上面。matplotlib 的
  barh 默认 y 向上增长，所以这里把 y 轴反向。
- 颜色按**组**给而不是按任务给：调度图里读者关心的是"这条产线/这辆车
  什么时候忙"，同一资源同色才能把一条水平带读成一个整体。
- 不放任务名以外的数值标注：柱子长度本身就是数值，再标一遍开始/结束
  会让图糊掉。精确值由 Results 表负责，图只负责表达"形状"。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    tasks_raw = data.get("tasks")
    if tasks_raw is None or len(tasks_raw) == 0:
        raise ValueError(
            "缺少必填输入 tasks：请提供任务名列表，每个任务对应图上的一行。"
        )
    tasks = [mcmplot.safe(str(t)) for t in tasks_raw]

    starts_raw = data.get("starts")
    if starts_raw is None or len(starts_raw) == 0:
        raise ValueError(
            "缺少必填输入 starts：请提供每个任务的开始时间（横轴单位由 x_label 指定）。"
        )

    durations_raw = data.get("durations")
    if durations_raw is None or len(durations_raw) == 0:
        raise ValueError(
            "缺少必填输入 durations：请提供每个任务的持续时间，与 starts 一一对应。"
        )

    try:
        starts = [float(v) for v in starts_raw]
        durations = [float(v) for v in durations_raw]
    except (TypeError, ValueError):
        raise ValueError(
            "starts / durations 里含有非数字：请确认每项都是可比较的数值"
            "（时间要先转成小时/天这类数值，日期字符串不能直接画）。"
        )

    n = len(tasks)
    # 三个必填输入必须一一对应。数量对不上时如果截断到最短，
    # 会画出一张"少了几个任务"的图 —— 而调度图少一个任务，结论就不成立了。
    if len(starts) != n:
        raise ValueError(
            f"starts 有 {len(starts)} 个，tasks 有 {n} 个，数量必须一致。"
        )
    if len(durations) != n:
        raise ValueError(
            f"durations 有 {len(durations)} 个，tasks 有 {n} 个，数量必须一致。"
        )

    for i, d in enumerate(durations):
        if d <= 0:
            # 零时长或者负时长的柱子在图上宽度为 0 或反向，
            # 读者会以为漏画了。这种情况几乎都是数据没算完。
            raise ValueError(
                f"任务「{tasks[i]}」的 duration 是 {mcmplot.fmt(d)}，"
                "必须大于 0（零时长任务在图上画不出柱子）。"
            )

    groups_raw = data.get("groups")
    groups: Optional[List[str]] = None
    if groups_raw is not None and len(groups_raw) > 0:
        if len(groups_raw) != n:
            raise ValueError(
                f"groups 有 {len(groups_raw)} 个，tasks 有 {n} 个，数量必须一致。"
            )
        groups = [mcmplot.safe(str(g)) for g in groups_raw]

    width = float(meta.get("width_in", 6.6))
    # 行数多的时候画布要长，否则每根柱子被压成一条线，任务名也挤在一起。
    height = max(2.6, min(11.0, 0.34 * n + 1.4))
    fig, ax = plt.subplots(figsize=(width, height))

    ypos = list(range(n))

    if groups:
        # 分组着色：同一组一个颜色，图例显示组名。
        # 顺序按首次出现，不排序 —— 用户给的顺序通常对应现实里的资源编号。
        order: List[str] = []
        for g in groups:
            if g not in order:
                order.append(g)
        cmap = plt.get_cmap("tab10")
        color_of = {g: cmap(i % 10) for i, g in enumerate(order)}
        colors = [color_of[g] for g in groups]
    else:
        # 没有分组信息时统一用一个中性蓝：不硬造分组，
        # 随机配色会让读者以为颜色有含义。
        colors = ["#1f4e79"] * n
        order = []

    ax.barh(
        ypos, durations, left=starts, height=0.62,
        color=colors, edgecolor="white", linewidth=0.7,
    )

    # 纵轴从上往下：第一个任务在顶部。
    ax.set_yticks(ypos)
    ax.set_yticklabels(tasks, fontsize=8)
    ax.invert_yaxis()
    ax.set_ylim(n - 0.5, -0.5)

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "时间（小时）")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "任务")))

    if groups:
        handles = [mpatches.Patch(facecolor=color_of[g], label=g) for g in order]
        # 图例放轴外：调度图的绘图区会被柱子填满，压在数据上会挡住任务。
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0),
                  frameon=False, fontsize=8, title=mcmplot.safe(
                      str(meta.get("group_label", "分组"))),
                  title_fontsize=8)

    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    return fig
