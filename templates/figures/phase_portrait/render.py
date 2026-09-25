"""fig.phase_portrait —— 相空间轨迹（相图）。

为什么相图比"两条时间序列"更好用
--------------------------------
把 x(t) 和 y(t) 各画一张图，读者要在两张图之间来回找人眼对不上的同一时刻；
画成相图以后，系统的长期行为（收敛到不动点、进入极限环、发散）直接是
一条曲线的形状，评审一眼就能判断稳定性 —— 这是 ODE 类题目最该给的图。

数据从哪来
----------
data 的键：
    x, y          轨迹坐标序列（同一时刻的配对值）
    t             时间序列（可选）—— 有它就按时序给轨迹上色
    start         起点坐标 [x0, y0]（可选）—— 不给就用序列第一个点
    field_x/field_y  向量场（可选）—— 两个等长的扁平数组，配 u/v 用

meta 里可能有：caption / x_label / y_label / width_in

关于渐变色
----------
用 LineCollection 分段上色而不是 plot 加 colormap：plot 的 color 参数
不接受数组，逐段 plot 在几万个点时会产生同样多的 Line2D 对象，
存 PDF 时会慢到不可接受。LineCollection 是单对象，矢量文件也小得多。
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


def render(data: Dict[str, Any], meta: Dict[str, Any] | None = None):
    meta = meta or {}

    x = [float(v) for v in (data.get("x") or [])]
    if not x:
        raise ValueError("缺少必填输入 x：请提供状态 1 的轨迹序列。")
    y = [float(v) for v in (data.get("y") or [])]
    if not y:
        raise ValueError("缺少必填输入 y：请提供状态 2 的轨迹序列。")
    if len(x) != len(y):
        raise ValueError(
            f"x 有 {len(x)} 个点，y 有 {len(y)} 个点，"
            "相图要求同一时刻的状态配对，数量必须一致。"
        )
    if len(x) < 2:
        # 单点连不成轨迹，画出来是个孤立点，看不出任何动力学行为。
        raise ValueError(
            f"轨迹只有 {len(x)} 个点：相图需要至少 2 个点才能连成轨迹，"
            "请检查时间步长是否设得太粗。"
        )

    t = data.get("t")
    if t is not None and len(t) != len(x):
        raise ValueError(
            f"t 有 {len(t)} 个点，x 有 {len(x)} 个点，数量必须一致。"
        )

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 5.6), 4.4))

    field_x, field_y = data.get("field_x"), data.get("field_y")
    if (field_x is None) != (field_y is None):
        raise ValueError(
            "field_x 和 field_y 必须同时提供：向量场需要两个分量，"
            "只给一个无法确定箭头方向。"
        )

    import numpy as np
    from matplotlib.collections import LineCollection

    # 向量场画在最底层，而且用淡灰、短箭头：它的作用是给轨迹提供"为什么
    # 会这样走"的背景，一旦画深就会盖过轨迹本身。
    if field_x is not None and field_y is not None:
        fx = np.asarray([float(v) for v in field_x], dtype=float)
        fy = np.asarray([float(v) for v in field_y], dtype=float)
        if fx.size != fy.size:
            raise ValueError(
                f"field_x 有 {fx.size} 个分量，field_y 有 {fy.size} 个分量，"
                "数量必须一致。"
            )
        if fx.size == 0:
            raise ValueError("field_x / field_y 是空数组：请给出向量场分量，或都不传。")
        # 扁平数组按 near-square 重排成网格，这是调用方传网格场最自然的形状。
        ncol = int(round(fx.size ** 0.5))
        while ncol > 1 and fx.size % ncol:
            ncol -= 1
        nrow = fx.size // ncol
        FX = fx[: nrow * ncol].reshape(nrow, ncol)
        FY = fy[: nrow * ncol].reshape(nrow, ncol)
        # 箭头长度按场强归一化，否则强场处的箭头会长到跨过整个图。
        norm = np.hypot(FX, FY)
        scale = float(np.median(norm[norm > 0])) if np.any(norm > 0) else 1.0
        span = max(float(np.ptp(x)), float(np.ptp(y))) or 1.0
        # 场强为 0 的点（不动点）不画箭头：零长箭头画出来是个歪的点，
        # 反而把真正的不动点位置弄得看不清。
        keep = norm > 1e-12
        ax.quiver(FX[keep], FY[keep], FX[keep] / norm[keep],
                  FY[keep] / norm[keep],
                  color="#b8b8b8", alpha=0.75, width=0.0022,
                  scale=32.0 / span * span, scale_units="xy",
                  headwidth=3.2, headlength=4.0, zorder=1)

    # 轨迹按时序渐变：越靠后颜色越暖，"往哪走"就不用额外标箭头了。
    pts = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
    segs = np.stack([pts[:-1], pts[1:]], axis=1)
    if t is not None:
        tv = np.asarray([float(v) for v in t], dtype=float)
        cvals = 0.5 * (tv[:-1] + tv[1:])   # 每段用两端时刻的均值当颜色
    else:
        cvals = np.arange(len(segs), dtype=float)
    lc = LineCollection(segs, cmap="viridis", linewidths=1.9, zorder=3)
    lc.set_array(cvals)
    ax.add_collection(lc)

    # LineCollection 不参与自动缩放，坐标范围要手动定。
    # 留 6% 余量，否则起点/终点标记会被裁掉半个。
    padx = (max(x) - min(x)) * 0.06 or 0.5
    pady = (max(y) - min(y)) * 0.06 or 0.5
    ax.set_xlim(min(x) - padx, max(x) + padx)
    ax.set_ylim(min(y) - pady, max(y) + pady)

    cbar = fig.colorbar(lc, ax=ax, shrink=0.85, pad=0.02, aspect=18)
    cbar.set_label(mcmplot.safe(
        meta.get("x_label") and "时间" or "时间"
    ))
    cbar.ax.tick_params(labelsize=7)

    # 起点用空心圆、终点用实心方块：形状差异在黑白打印时也分得开，
    # 只靠颜色区分的话，黑白版论文里两个标记会变成一样的灰点。
    start = data.get("start")
    if start is not None and len(start) >= 2:
        x0, y0 = float(start[0]), float(start[1])
    else:
        x0, y0 = x[0], y[0]
    ax.plot([x0], [y0], "o", ms=9, mfc="none", mec="#c0392b", mew=1.6,
            zorder=4)
    ax.annotate("初态", xy=(x0, y0), xytext=(7, 7), textcoords="offset points",
                fontsize=8, color="#c0392b", zorder=4)
    ax.plot([x[-1]], [y[-1]], "s", ms=7.5, color="#1f4e79", zorder=4)
    ax.annotate("终态", xy=(x[-1], y[-1]), xytext=(7, -11),
                textcoords="offset points", fontsize=8, color="#1f4e79",
                zorder=4)

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "状态 x")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "状态 y")))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3, zorder=0)
    # 相图的两个轴是同一量纲的状态，等比例才不会把极限环画成椭圆。
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    return fig
