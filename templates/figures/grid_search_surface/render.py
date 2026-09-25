"""fig.grid_search_surface —— 网格搜索结果图（二维响应面 + 一维切片）。

为什么要把两张图并排
--------------------
调参报告最常见的写法是"最优参数是 k=8, b0=0.3"，读者只能相信这个结论。
把搜索**过程**画出来之后，评审能自己判断三件事：

    左边热力图  最优解周围是**一个平台**还是**一根针**。
                平台说明参数不敏感、结论稳健；一根针说明换台机器
                数据抖一下最优解就跑了，这种"最优"不能写进论文。
    右边切片    固定其余参数后，单个参数的响应曲线长什么样。
                曲线是凸的、单调的、还是有多个峰，直接决定了
                "要不要继续细分这个区间"。

所以两张图不是重复，是回答不同的问题。

切片取哪一行
------------
默认取**得分最高**的那一行，因为读者最关心的就是"在最优附近，
横轴这个参数怎么变"。也可以用 slice_index 指定看第几行。
这里不画误差棒 —— 网格搜索的每一格通常只跑一次，没有重复实验
就没有不确定度，硬画一根标准差是编的。

数据从哪来
----------
data 的键：
    param_x       第一个参数的取值列表，长度 = scores 的列数
    param_y       第二个参数的取值列表，长度 = scores 的行数
    scores        网格得分矩阵，第 r 行第 c 列对应 param_y[r] 与 param_x[c]
    slice_index   右图取第几行（可选），缺省取最优行
    metric_label  得分指标名（可选），如 RMSE、F1

meta 里可能有：caption / x_label / y_label / width_in / higher_is_better / cmap
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


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    param_x = data.get("param_x")
    if not param_x:
        raise ValueError(
            "缺少必填输入 param_x：请提供第一个参数的取值列表，"
            "个数要等于 scores 的列数，例如 [1, 2, 4, 8, 16]。"
        )
    param_x = list(param_x)

    param_y = data.get("param_y")
    if not param_y:
        raise ValueError(
            "缺少必填输入 param_y：请提供第二个参数的取值列表，"
            "个数要等于 scores 的行数，例如 [0.1, 0.2, 0.3]。"
        )
    param_y = list(param_y)

    scores = data.get("scores")
    if scores is None:
        raise ValueError(
            "缺少必填输入 scores：请提供网格得分矩阵，"
            "第 r 行第 c 列对应 param_y[r] 与 param_x[c]。"
        )
    try:
        grid = np.asarray(scores, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "scores 不是数值二维数组：请检查是否有某一行长度不一致或混入了文字。"
        )
    if grid.ndim == 1:
        grid = grid.reshape(1, -1)
    if grid.ndim != 2 or grid.size == 0:
        raise ValueError(
            f"scores 必须是二维数组且非空，当前形状 {grid.shape}。"
        )
    if not np.all(np.isfinite(grid)):
        raise ValueError(
            "scores 里有空值：网格的每一格都要有得分，"
            "某个参数组合没跑就请从 param_x / param_y 里去掉它。"
        )

    n_rows, n_cols = grid.shape
    if len(param_x) != n_cols:
        raise ValueError(
            f"param_x 有 {len(param_x)} 个取值，scores 有 {n_cols} 列："
            "每一个横轴参数值对应一列。"
        )
    if len(param_y) != n_rows:
        raise ValueError(
            f"param_y 有 {len(param_y)} 个取值，scores 有 {n_rows} 行："
            "每一个纵轴参数值对应一行。"
        )
    if n_rows < 2 or n_cols < 2:
        raise ValueError(
            f"scores 是 {n_rows}×{n_cols}：网格搜索至少需要 2×2 个参数组合，"
            "单参数的问题请改用 fig.sensitivity_line。"
        )

    try:
        xs = np.asarray(param_x, dtype=float)
        ys = np.asarray(param_y, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "param_x / param_y 必须是数值序列："
            "热力图的坐标轴需要真实数值才能反映参数的疏密，"
            "如果参数是类别（如模型名）请改用 fig.heatmap_annotated。"
        )

    # 越大越好的指标（准确率、F1）和越小越好的指标（RMSE、损失）
    # 对"最优"的定义相反。搞反了会把最差的格子标成最优。
    higher = bool(meta.get("higher_is_better", False))
    metric_label = mcmplot.safe(str(data.get("metric_label") or "得分"))

    # -- 切片行 ---------------------------------------------------------
    slice_index = data.get("slice_index")
    if slice_index is None:
        # 默认取最优行：读者最关心最优附近横轴参数怎么变。
        # 先取每行的极值，再在极值里挑最好的那一行。
        row_extremes = grid.max(axis=1) if higher else grid.min(axis=1)
        slice_index = int(np.argmax(row_extremes) if higher
                          else np.argmin(row_extremes))
    try:
        slice_index = int(slice_index)
    except (TypeError, ValueError):
        raise ValueError(
            f"slice_index 必须是整数行号，当前是 {slice_index!r}。"
            f"取值范围 0 到 {n_rows - 1}。"
        )
    if not (0 <= slice_index < n_rows):
        raise ValueError(
            f"slice_index 是 {slice_index}，超出范围："
            f"param_y 只有 {n_rows} 个取值（行号 0 到 {n_rows - 1}）。"
        )

    width = float(meta.get("width_in", 9.2))
    fig, (ax_h, ax_s) = plt.subplots(
        1, 2, figsize=(width, 3.9), gridspec_kw={"width_ratios": [1.05, 1.0]})

    # -- 左：二维热力图 --------------------------------------------------
    vmin, vmax = float(grid.min()), float(grid.max())
    cmap = meta.get("cmap") or ("viridis" if higher else "viridis_r")
    # extent 用参数的真实取值，格子的疏密才和实际扫描步长一致。
    im = ax_h.imshow(grid, cmap=cmap, aspect="auto", origin="lower",
                     extent=[xs.min(), xs.max(), ys.min(), ys.max()])

    # 标出全局最优点：这是整张图的结论。
    bi, bj = np.unravel_index(int(np.argmax(grid) if higher
                                  else np.argmin(grid)), grid.shape)
    ax_h.scatter([xs[bj]], [ys[bi]], marker="*", s=150,
                 facecolor="#c0504d", edgecolor="white", linewidths=0.8,
                 zorder=5)
    ax_h.annotate(
        f"最优 {metric_label}={mcmplot.fmt(grid[bi, bj])}\n"
        f"({mcmplot.fmt(xs[bj])}, {mcmplot.fmt(ys[bi])})",
        xy=(xs[bj], ys[bi]), xytext=(6, 8), textcoords="offset points",
        fontsize=7.5, color="#8c2f28", zorder=6,
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#c0504d",
                  lw=0.7, alpha=0.85))

    # 切片行的位置画一条水平虚线，把左右两张图联系起来 ——
    # 没有这条线，读者不知道右图取自哪一行。
    ax_h.axhline(ys[slice_index], color="#ffffff", lw=1.4, ls="--", zorder=4)

    ax_h.set_xlabel(mcmplot.safe(meta.get("x_label", "参数一")))
    ax_h.set_ylabel(mcmplot.safe(meta.get("y_label", "参数二")))
    ax_h.set_title(f"{metric_label} 的二维响应面", fontsize=9)
    cbar = fig.colorbar(im, ax=ax_h, fraction=0.046, pad=0.03)
    cbar.set_label(metric_label, fontsize=8)
    cbar.ax.tick_params(labelsize=8)

    # -- 右：一维切片 ----------------------------------------------------
    row = grid[slice_index]
    ax_s.plot(xs, row, "-o", lw=1.9, ms=4.4, color="#1f4e79",
              markerfacecolor="white", markeredgewidth=1.6,
              markeredgecolor="#1f4e79")
    best_col = int(np.argmax(row) if higher else np.argmin(row))
    ax_s.scatter([xs[best_col]], [row[best_col]], marker="*", s=150,
                 facecolor="#c0504d", edgecolor="white", linewidths=0.8,
                 zorder=5)
    ax_s.annotate(f"{mcmplot.fmt(row[best_col])}",
                  xy=(xs[best_col], row[best_col]), xytext=(6, 6),
                  textcoords="offset points", fontsize=7.5, color="#8c2f28")

    ax_s.set_xlabel(mcmplot.safe(meta.get("x_label", "参数一")))
    ax_s.set_ylabel(metric_label)
    ax_s.set_title(f"固定 {mcmplot.safe(meta.get('y_label', '参数二'))}="
                   f"{mcmplot.fmt(ys[slice_index])} 时的切片",
                   fontsize=9)
    ax_s.grid(alpha=0.3)

    if meta.get("caption"):
        fig.suptitle(mcmplot.safe(meta["caption"].rstrip(".")), fontsize=10)
    fig.tight_layout()
    return fig
