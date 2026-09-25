"""fig.heatmap_matrix —— 矩阵热力图（双参数响应面 / 相关系数矩阵）。

数据从哪来
----------
data 是一个 dict，键是模板声明的输入名：

    matrix          二维数组（list of lists），必填；行是第一个参数，列是第二个参数
    labels          行/列标签（可选）；可以是一个 list（行列共用），
                    也可以是 {"rows": [...], "cols": [...]} 分别指定
    colorbar_label  色条标题（可选），如 "分解速率" 或 "Pearson 相关系数"

典型用途：参数网格扫描（p × n 的响应面）、变量之间的相关系数矩阵。
行列数不一致、矩阵为空时直接报错，不做任何猜测。

怎么选色
--------
带负值的矩阵（相关矩阵、差值场）用发散色标 "RdBu_r"，零点落在白色上；
全为同号的矩阵（速率、浓度）用顺序色标 "viridis"。
矩阵不超过 12×12 时把数值写进格子里，更大的矩阵只画颜色，避免糊成一团。

统一约定（所有图模板都遵守）
    render(data, meta) -> matplotlib Figure
    meta 里可能有：caption / title / width_in / cmap / x_label / y_label
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
# 没有这一步，中文标签会被画成一排空心方框，而且不报错。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# 超过这个规模的矩阵就不再逐格标注数值了，否则字会挤成一坨。
_ANNOTATE_MAX = 12


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    matrix = data.get("matrix")
    if matrix is None:
        raise ValueError("缺少必填输入 matrix：请提供二维数组（list of lists）。")
    try:
        arr = np.asarray(matrix, dtype=float)
    except ValueError:
        # 每行长度不一样（锯齿矩阵）时 numpy 会抛原始英文异常，
        # 这里换成能直接照着改的中文说明。
        raise ValueError(
            "matrix 不是规则的二维数组：各行的列数必须相同，请检查是否有某一行少填或多填了数据。"
        )
    if arr.ndim == 1:
        # 单行/单列也允许，补成真正的二维
        arr = arr.reshape(1, -1)
    if arr.ndim != 2:
        raise ValueError(
            f"matrix 必须是二维数组，当前是 {arr.ndim} 维，形状 {arr.shape}。"
        )
    if arr.size == 0:
        raise ValueError("matrix 是空的：至少需要一行一列的数据。")

    n_rows, n_cols = arr.shape

    row_labels, col_labels = _labels(data.get("labels"), n_rows, n_cols)

    # 带负号的数据用发散色标，否则用顺序色标；调用方也能自己指定。
    cmap = meta.get("cmap")
    if not cmap:
        cmap = "RdBu_r" if (arr < 0).any() else "viridis"

    width = float(meta.get("width_in", 6.0))
    # 矩阵越高越宽，画布跟着长一点，格子才不会被压扁。
    height = max(2.8, min(9.0, width * n_rows / max(n_cols, 1) + 1.3))
    fig, ax = plt.subplots(figsize=(width, height))

    # vmin/vmax 关于 0 对称，发散色标的中性色才落在 0 上
    vmax = float(np.nanmax(np.abs(arr))) or 1.0
    if cmap.endswith("_r") and (arr < 0).any():
        im = ax.imshow(arr, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
    else:
        im = ax.imshow(arr, cmap=cmap, aspect="auto")

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(col_labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(row_labels, fontsize=8)

    if meta.get("x_label"):
        ax.set_xlabel(meta["x_label"])
    if meta.get("y_label"):
        ax.set_ylabel(meta["y_label"])

    # 格子小的时候把数值写上去，读者不用去对照色条
    if n_rows <= _ANNOTATE_MAX and n_cols <= _ANNOTATE_MAX:
        lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
        mid = (lo + hi) / 2.0
        for i in range(n_rows):
            for j in range(n_cols):
                v = arr[i, j]
                if not np.isfinite(v):
                    continue
                # 深色底用白字，浅色底用黑字
                color = "white" if _is_dark(v, lo, hi, mid, cmap) else "black"
                ax.text(j, i, _fmt(v), ha="center", va="center",
                        fontsize=7, color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cbar.set_label(str(data.get("colorbar_label") or meta.get("colorbar_label") or ""))
    cbar.ax.tick_params(labelsize=8)

    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    fig.tight_layout()
    return fig


def _labels(raw: Any, n_rows: int, n_cols: int):
    """把 labels 输入整理成 (row_labels, col_labels)。

    labels 可以缺省、可以是长度等于行数或列数的 list、也可以是
    {"rows": [...], "cols": [...]}。长度对不上就报错，不静默截断。
    """
    if raw is None:
        return [str(i + 1) for i in range(n_rows)], [str(j + 1) for j in range(n_cols)]

    if isinstance(raw, dict):
        rows = raw.get("rows")
        cols = raw.get("cols")
    else:
        seq = list(raw)
        # 行列数相同时一个列表两边共用；否则按长度判断它是行标签还是列标签
        if n_rows == n_cols:
            rows = cols = seq
        elif len(seq) == n_rows:
            rows, cols = seq, None
        elif len(seq) == n_cols:
            rows, cols = None, seq
        else:
            rows = cols = None
            raise ValueError(
                f"labels 有 {len(seq)} 项，但矩阵是 {n_rows}×{n_cols}："
                "既不是行数也不是列数，无法对应，请检查标签。"
            )

    row_labels = [str(v) for v in rows] if rows is not None else [str(i + 1) for i in range(n_rows)]
    col_labels = [str(v) for v in cols] if cols is not None else [str(j + 1) for j in range(n_cols)]

    if len(row_labels) != n_rows:
        raise ValueError(
            f"行标签有 {len(row_labels)} 个，矩阵有 {n_rows} 行，数量必须一致。"
        )
    if len(col_labels) != n_cols:
        raise ValueError(
            f"列标签有 {len(col_labels)} 个，矩阵有 {n_cols} 列，数量必须一致。"
        )
    return row_labels, col_labels


def _is_dark(v: float, lo: float, hi: float, mid: float, cmap: str) -> bool:
    """粗判某个数值在色标上是否落在深色区，用来决定文字用白还是黑。"""
    if hi == lo:
        return True
    if cmap.endswith("_r") and lo < 0 < hi:
        # 发散色标：离 0 越远颜色越深
        return abs(v - mid) > (hi - lo) * 0.35
    # 顺序色标（viridis）：值越大越深
    return (v - lo) / (hi - lo) > 0.6


def _fmt(v: Any) -> str:
    """数字格式化：太小或太大的值用科学计数法，否则保留 4 位有效数字。

    统一走 mcmplot.fmt，保证全库图上的数字长得一样。
    """
    return mcmplot.fmt(v)
