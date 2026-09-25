"""fig.surface_3d —— 双参数响应曲面。

数据从哪来
----------
data 的键：
    x       参数 1 的取值（一维，长度 = z 的列数）
    y       参数 2 的取值（一维，长度 = z 的行数）
    z       目标值，二维 z[i][j] 对应 (x[j], y[i])
    z_label z 轴的量名（可选）—— 曲面图丢了单位就没法读

meta 里可能有：caption / x_label / y_label / width_in

为什么默认视角是 (28, -58)
--------------------------
matplotlib 默认的 30/-60 会把远处那片曲面压扁，横轴刻度挤在一起。
抬高到 28 度、方位收到 -58 度，是"既能看出峰在哪、又不至于把网格
看出摩尔纹"的位置。曲面一旦被参数覆盖就不是默认值了，所以这里
把默认值写死，让同一批图在论文里长得一样。
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
        raise ValueError("缺少必填输入 x：请提供第一个参数的取值序列。")
    y = [float(v) for v in (data.get("y") or [])]
    if not y:
        raise ValueError("缺少必填输入 y：请提供第二个参数的取值序列。")

    z_raw = data.get("z")
    if z_raw is None or len(z_raw) == 0:
        raise ValueError(
            "缺少必填输入 z：请提供二维响应值 z[i][j]，"
            "第 i 行对应 y[i]、第 j 列对应 x[j]。"
        )
    z: List[List[float]] = [[float(v) for v in row] for row in z_raw]

    # 曲面必须铺满网格，缺一行就会画出一块空洞，而且不报错。
    if len(z) != len(y):
        raise ValueError(
            f"z 有 {len(z)} 行，y 有 {len(y)} 个取值，行数必须等于 y 的长度。"
        )
    widths = {len(row) for row in z}
    if len(widths) != 1:
        # 参差不齐的二维数组是网格生成写错时的典型症状，直接点出来。
        raise ValueError(
            f"z 每行的列数不一致（出现了 {sorted(widths)} 种）："
            "z 必须是规整的二维网格。"
        )
    if widths.pop() != len(x):
        raise ValueError(
            f"z 每行有 {len(z[0])} 列，x 有 {len(x)} 个取值，列数必须等于 x 的长度。"
        )

    fig = plt.figure(figsize=(meta.get("width_in", 6.2), 4.9))
    ax = fig.add_subplot(111, projection="3d")

    # 两个参数一共只有一两个取值时曲面退化成一条线或一个点，
    # 这不是"能画但难看"，而是网格根本没扫开，图传达的是假信息。
    if len(x) < 2 or len(y) < 2:
        raise ValueError(
            f"x 有 {len(x)} 个取值、y 有 {len(y)} 个取值，"
            "响应曲面至少需要在每个参数上取 2 个点（实际建议 >= 8 个）才能成形。"
        )

    import numpy as np

    X, Y = np.meshgrid(np.asarray(x), np.asarray(y))
    Z = np.asarray(z)

    surf = ax.plot_surface(X, Y, Z, cmap="viridis", rstride=1, cstride=1,
                           linewidth=0.15, edgecolor="#3a3a3a",
                           antialiased=True, alpha=0.95)
    # 等高线投影放在 0.06 处而不是紧贴底面：贴底会被曲面的前缘挡住，
    # 而这篇论文想让人同时读到"峰在哪"和"等高线的形状"。
    zmin, zmax = float(Z.min()), float(Z.max())
    pad = (zmax - zmin) * 0.06 if zmax > zmin else 1.0
    ax.contour(X, Y, Z, zdir="z", offset=zmin - pad, cmap="viridis",
               levels=10, linewidths=0.8)

    cbar = fig.colorbar(surf, ax=ax, shrink=0.62, pad=0.09, aspect=16)
    cbar.set_label(mcmplot.safe(
        meta.get("z_label") or data.get("z_label") or "目标值"
    ))
    cbar.ax.tick_params(labelsize=7)

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "参数 1")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "参数 2")))
    ax.set_zlabel(mcmplot.safe(
        meta.get("z_label") or data.get("z_label") or "目标值"
    ))
    # 默认视角把曲面压得太扁，刻度会挤在一起；这组角度是能同时
    # 看清峰位和网格走向的位置。
    ax.view_init(elev=28, azim=-58)
    # 3D 轴的背景板是灰的，和矢量图的纯白纸面不一致，去掉更干净。
    ax.xaxis.pane.set_alpha(0.0)
    ax.yaxis.pane.set_alpha(0.0)
    ax.zaxis.pane.set_alpha(0.0)
    ax.grid(alpha=0.3)

    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")), pad=12)
    fig.tight_layout()
    return fig
