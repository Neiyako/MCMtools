"""fig.correlation_heatmap —— 相关矩阵热图。

色标的选择是这张图的全部
------------------------
相关系数的取值范围是 [-1, 1]，**有符号**，而且正负号就是结论本身
（"这两个变量同向变化" vs "反向变化"）。

用单色渐变（viridis 之类）是这类图最常见的错误：深蓝既可能是 +1
也可能是 -1，读者必须去对照色条才知道方向 —— 而人眼对色条位置
的判断极不可靠，实际结果就是"正相关和负相关在图上看不出区别"。
所以这里固定用发散色图 `RdBu_r`：红=正、蓝=负、白=零，
并且把 vmin/vmax 对称地钉死在 [-1, 1]，让白色**严格**落在 0 上。
（如果按数据实际范围缩放，0.3 和 0.8 都可能被画成白色。）

下三角遮罩
----------
相关矩阵是对称的，上三角和平三角是同一批数字，画两遍纯属浪费。
`lower_only` 打开后遮住上三角，对角线保留 —— 对角线恒为 1，
但保留它能让矩阵的行列边界看得更清楚（也提醒读者这是相关矩阵）。

数据从哪来
----------
    labels       必填，变量名，长度必须等于矩阵边长
    matrix       必填，方阵。可以传二维数组 [[...], ...]，
                 也可以传扁平化的一维序列（按行优先展开，长度 = n*n）
    lower_only   可选，布尔，是否只画下三角，默认 True

meta 里可能有：caption / x_label / y_label / width_in
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

# 发散色图：红色一端是正相关，蓝色一端是负相关，白色落在零点。
_CMAP = "RdBu_r"

# 超过这个规模就不再逐格写数字：格子比字还小时，数字会糊成一片灰。
_ANNOTATE_MAX = 12


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    labels = data.get("labels")
    if labels is None:
        raise ValueError(
            "缺少必填输入 labels：请提供变量名序列，长度等于相关矩阵的边长。"
        )
    labels = [str(v) for v in labels]

    matrix = data.get("matrix")
    if matrix is None:
        raise ValueError(
            "缺少必填输入 matrix：请提供相关矩阵（二维数组 [[...], ...]，"
            "或按行优先展开的一维序列）。"
        )

    arr = _to_square(matrix, len(labels))
    n = arr.shape[0]

    if n < 2:
        raise ValueError(
            "相关矩阵至少要有 2 个变量才有意义（单个变量与自己相关恒为 1）。"
        )

    fig_w = float(meta.get("width_in", 6.4))
    # 方阵配方形画布；再给下方旋转的标签留出空间。
    fig_w = max(fig_w, 0.42 * n + 2.4)
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * 0.82 + 0.6))

    lower_only = data.get("lower_only")
    lower_only = True if lower_only is None else bool(lower_only)

    # 用 masked array 遮罩上三角：比先复制再改值干净，
    # 遮住的格子完全不着色，露出白底，一眼能看出是被刻意省掉的。
    plot_arr = np.ma.masked_invalid(arr)
    if lower_only:
        plot_arr = np.ma.masked_where(
            np.triu(np.ones_like(arr, dtype=bool), k=1), plot_arr
        )

    # vmin/vmax 钉死在 [-1, 1]：相关矩阵的定义域就是它，
    # 让颜色到数值的映射在所有图上一致，读者不用每次重读色条。
    im = ax.imshow(plot_arr, cmap=_CMAP, vmin=-1.0, vmax=1.0, aspect="equal")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    # 横轴标签转 45 度：变量名通常较长，横排会互相压住。
    ax.set_xticklabels([mcmplot.safe(v) for v in labels],
                       rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels([mcmplot.safe(v) for v in labels], fontsize=8)

    # 网格线勾出格子边界，浅色格子之间才分得清。
    ax.set_xticks(np.arange(-0.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", length=0)

    if n <= _ANNOTATE_MAX:
        _annotate(ax, arr, n, lower_only)

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03,
                        ticks=[-1, -0.5, 0, 0.5, 1])
    cbar.set_label(mcmplot.safe(
        meta.get("y_label", "相关系数")), fontsize=8)
    cbar.ax.tick_params(labelsize=8)

    if meta.get("x_label"):
        ax.set_xlabel(mcmplot.safe(meta["x_label"]))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))

    # 说明遮罩和色标方向，省得读者疑惑"为什么是半个方阵"。
    mask_note = "下三角（对称矩阵，上三角与下三角重复）" if lower_only else "完整矩阵"
    ax.annotate(mcmplot.safe(f"红 = 正相关，蓝 = 负相关；{mask_note}"),
                xy=(0.0, -0.34), xycoords="axes fraction",
                ha="left", va="top", fontsize=7, color="#777777")

    fig.tight_layout()
    return fig


def _annotate(ax, arr: np.ndarray, n: int, lower_only: bool) -> None:
    """把数值写进格子里。行优先，与矩阵的直观读法一致。"""
    for i in range(n):
        for j in range(n):
            if lower_only and j > i:
                continue
            v = arr[i, j]
            if not np.isfinite(v):
                continue
            # 白底上写白字等于没写。发散色图的中性色在 0 附近，
            # 所以按 |v| 判断深浅：绝对值大 -> 底色深 -> 用白字。
            color = "white" if abs(float(v)) > 0.6 else "black"
            ax.text(j, i, mcmplot.fmt(v), ha="center", va="center",
                    fontsize=7, color=color)


def _to_square(matrix: Any, n_labels: int) -> np.ndarray:
    """把 matrix 整理成 n×n 的 numpy 数组。

    接受两种形状：二维方阵，以及按行优先展开的一维序列（长度 = n*n）。
    后者是因为很多脚本把矩阵存成一列 CSV 再读回来。
    任何对不上的情况都报错，绝不猜 —— 猜错的矩阵画出来是"看着正常
    但结论全错"的图。
    """
    try:
        arr = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "matrix 里出现了非数值项：相关系数矩阵必须是数值，请检查输入。"
        )

    n = n_labels

    if arr.ndim == 2:
        if arr.shape[0] != arr.shape[1]:
            raise ValueError(
                f"matrix 是 {arr.shape[0]}×{arr.shape[1]}，不是方阵："
                "相关矩阵必须是 n×n 的方阵。"
            )
        if arr.shape[0] != n:
            raise ValueError(
                f"labels 有 {n} 个，matrix 是 {arr.shape[0]}×{arr.shape[1]}，"
                "数量必须一致（每个变量一个标签、矩阵边长等于变量数）。"
            )
        return arr

    if arr.ndim == 1:
        # 扁平形状：必须刚好是 n*n 个数，否则无法还原成 n×n。
        if arr.size != n * n:
            raise ValueError(
                f"labels 有 {n} 个，matrix 扁平展开后有 {arr.size} 个数，"
                f"数量必须一致（应为 {n}×{n}={n * n} 个，按行优先排列）。"
            )
        return arr.reshape(n, n)

    raise ValueError(
        f"matrix 必须是二维数组或按行优先展开的一维序列，当前是 {arr.ndim} 维。"
    )
