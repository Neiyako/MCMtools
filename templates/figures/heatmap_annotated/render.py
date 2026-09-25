"""fig.heatmap_annotated —— 带数值标注的混淆矩阵 / 交叉表热力图。

和 fig.heatmap_matrix 的分工
---------------------------
heatmap_matrix 画的是**连续量**（相关系数、响应面），颜色本身就是数据，
所以超过 12×12 就不再标数字。混淆矩阵完全不同：它的每一格是一个
**计数**，评审要读的就是"第 3 类被误判成第 5 类多少次"这种具体数字，
颜色只是辅助。所以这里**永远标注数值**，并且默认把对角线以外的
错误格子用更深的边框圈出来 —— 分类报告的重点在错误上。

归一化的取舍
------------
类别样本量不均衡时（比如 900 个负例、100 个正例），原始计数会让
所有错误都挤在样本多的那一行，看不出"哪一类更容易被混淆"。
按行归一化后每一行合计 100%，行与行之间才可比。两种口径都有用，
所以做成开关：normalize 为真时格子里显示百分比，色条也用百分比。

数据从哪来
----------
data 的键：
    matrix       混淆矩阵，第 i 行第 j 列 = 真实类 i 被预测成类 j 的样本数
    row_labels   行标签（真实类别），个数 = 行数
    col_labels   列标签（预测类别），个数 = 列数
    normalize    为真时按行归一化，显示百分比（可选）

meta 里可能有：caption / x_label / y_label / width_in / cmap / show_diagonal
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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

    matrix = data.get("matrix")
    if matrix is None:
        raise ValueError(
            "缺少必填输入 matrix：请提供混淆矩阵，第 i 行第 j 列是"
            "真实类 i 被预测成类 j 的样本数，例如 [[50,5],[3,42]]。"
        )
    try:
        arr = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "matrix 不是数值二维数组：混淆矩阵的每一格都必须是数字，"
            "请检查是否有某行长度不一致或混入了类别文字。"
        )
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.size == 0:
        raise ValueError(
            f"matrix 必须是二维数组且非空，当前形状 {arr.shape}。"
        )
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            "matrix 里有空值：每个格子都要有样本数，没有样本请写 0，不能留空。"
        )
    if (arr < 0).any():
        raise ValueError(
            "matrix 里有负数：混淆矩阵的每一格都是样本计数，不能为负。"
        )

    n_rows, n_cols = arr.shape

    row_labels = _axis_labels(data.get("row_labels"), n_rows, "row_labels", "行")
    col_labels = _axis_labels(data.get("col_labels"), n_cols, "col_labels", "列")

    normalize = bool(data.get("normalize", meta.get("normalize", False)))
    if normalize:
        # 全 0 的行（某个真实类别一个样本都没有）除零会得到 NaN，
        # 这里保留 0，并在图上如实显示 —— 不能悄悄填一个假的比例。
        totals = arr.sum(axis=1, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            shown = np.where(totals > 0, arr / np.where(totals > 0, totals, 1) * 100.0, 0.0)
    else:
        shown = arr

    width = float(meta.get("width_in", 6.0))
    # 类别多的时候画布跟着长，格子才不会被压扁、数字才不会叠在一起。
    height = max(3.2, min(9.5, width * n_rows / max(n_cols, 1) + 1.6))
    fig, ax = plt.subplots(figsize=(width, height))

    # 混淆矩阵永远是"越大越多"，顺序色标才对；发散色标会暗示 0 是中性点，
    # 而 0 在这里恰恰是最淡的那一端。
    cmap = meta.get("cmap") or "Blues"
    im = ax.imshow(shown, cmap=cmap, aspect="auto")

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(col_labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels, fontsize=8)

    # 数值标注：这张图的重点，不设规模上限。
    lo, hi = float(shown.min()), float(shown.max())
    for i in range(n_rows):
        for j in range(n_cols):
            v = shown[i, j]
            # 深色格子用白字：色标的相对位置决定文字颜色，
            # 阈值取 0.6 是因为 Blues 在这个位置之后文字开始读不清。
            dark = hi > lo and (v - lo) / (hi - lo) > 0.6
            ax.text(j, i, _cell_text(arr[i, j], v, normalize),
                    ha="center", va="center", fontsize=7.5,
                    color="white" if dark else "black")

    # 把对角线以外的格子（也就是错误）用方框圈出来。
    # 分类报告的重点是错误分布，这一步让读者不用自己找对角线。
    if meta.get("show_diagonal", True) and n_rows == n_cols:
        for i in range(n_rows):
            for j in range(n_cols):
                if i == j:
                    continue
                if arr[i, j] <= 0:
                    continue          # 没有误判的格子不必圈，圈了反而像有问题
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                           fill=False, edgecolor="#c0504d",
                                           linewidth=1.2, zorder=5))

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "预测类别")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "真实类别")))

    unit = "%" if normalize else "样本数"
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cbar.set_label(mcmplot.safe(unit), fontsize=8)
    cbar.ax.tick_params(labelsize=8)

    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    fig.tight_layout()
    return fig


def _axis_labels(raw: Any, n: int, key: str, cn: str) -> List[str]:
    """整理一维标签。数量对不上就报错，不静默截断或补号。"""
    if not raw:
        raise ValueError(
            f"缺少必填输入 {key}：请提供{cn}标签，个数要等于矩阵的"
            f"{cn}数（{n}）。混淆矩阵不写清类别名，读图的人不知道"
            "第几行对应哪一类。"
        )
    labels = [mcmplot.safe(str(v)) for v in raw]
    if len(labels) != n:
        raise ValueError(
            f"{key} 有 {len(labels)} 个，矩阵有 {n} {cn}：数量必须一致。"
        )
    return labels


def _cell_text(count: float, value: float, normalize: bool) -> str:
    """格子里的文字。

    归一化时同时给出百分比和原始计数（写成 "63%\n(29)"）——
    只看百分比会掩盖"这一格其实只有 3 个样本"这种不稳定的情况。
    """
    if not normalize:
        return mcmplot.fmt(count)
    return f"{value:.0f}%\n({mcmplot.fmt(count)})"
