"""fig.residual —— 残差诊断图（残差 vs 拟合值 / 残差 vs 序号）。

数据从哪来
----------
data 是一个 dict，键是模板声明的输入名：

    predicted  拟合值（或预测值）序列，必填，作横轴
    residual   对应的残差序列，必填，长度必须与 predicted 一致
    std        残差标准差 sigma（可选）。给了就画 ±2sigma 的虚线带，
               不给自己估：sigma = sqrt(sum(r^2) / (n - 1))。
    index      横轴序号（可选）。给了就改画"残差 vs 序号"，
               用来查随时间/顺序变化的系统性偏差（自相关）。
    zero_line  是否画 0 参考线；可选，默认画，传 False 关掉。
    series     分组名（可选），按组配色，用于比较不同模型/数据集的残差。

图上还标出 sigma（虚线半宽）和落在 ±2sigma 之外的离群点个数 —— 正态假设下
大约 5% 的点应该在外面，明显更多说明模型漏掉了结构。

统一约定（所有图模板都遵守）
    render(data, meta) -> matplotlib Figure
    meta 里可能有：caption / x_label / y_label / width_in
"""

from __future__ import annotations

from typing import Any, Dict, Optional

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

_PRIMARY = "#1f4e79"
_PALETTE = [_PRIMARY, "#b03030", "#2e7d32", "#8a6d3b", "#6a3d9a", "#c46a1f"]


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    pred = data.get("predicted")
    resid = data.get("residual")
    if pred is None:
        raise ValueError("缺少必填输入 predicted：请提供拟合值（或预测值）序列。")
    if resid is None:
        raise ValueError("缺少必填输入 residual：请提供残差序列。")

    p = _as_float_list(pred, "predicted")
    r = _as_float_list(resid, "residual")
    if len(p) != len(r):
        raise ValueError(
            f"predicted 有 {len(p)} 个点，residual 有 {len(r)} 个点，数量必须一致。"
        )
    if len(p) == 0:
        raise ValueError("predicted/residual 都是空的：至少需要一个残差点。")

    # 给了 index 就画"残差 vs 序号"，否则默认"残差 vs 拟合值"
    index = data.get("index")
    if index is not None:
        x = _as_float_list(index, "index")
        if len(x) != len(r):
            raise ValueError(
                f"index 有 {len(x)} 个点，residual 有 {len(r)} 个点，数量必须一致。"
            )
        x_label = meta.get("x_label", "样本序号")
    else:
        x = p
        x_label = meta.get("x_label", "拟合值")

    series = data.get("series")
    if series is not None:
        s = list(series)
        if len(s) != len(r):
            raise ValueError(
                f"series 有 {len(s)} 项，但 residual 有 {len(r)} 项，数量必须一致。"
            )
    else:
        s = None

    # sigma：优先用调用方给的，否则从残差自己估
    sigma = data.get("std", data.get("sigma"))
    if sigma is None:
        sigma = float(np.sqrt(np.sum(np.square(r)) / max(len(r) - 1, 1)))
    else:
        try:
            sigma = float(sigma)
        except (TypeError, ValueError):
            raise ValueError(f"std 必须是数值，当前是 {sigma!r}。")
        if sigma <= 0:
            raise ValueError(f"std 必须为正数，当前是 {sigma}。")

    width = float(meta.get("width_in", 6.0))
    fig, ax = plt.subplots(figsize=(width, max(3.7, width * 0.62)))

    if s is not None:
        groups: Dict[str, list] = {}
        for i, name in enumerate(s):
            groups.setdefault(str(name), []).append(i)
        for k, (name, idx) in enumerate(groups.items()):
            ax.scatter([x[i] for i in idx], [r[i] for i in idx], s=28,
                       color=_PALETTE[k % len(_PALETTE)], alpha=0.8,
                       edgecolors="none", label=name, zorder=3)
        ax.legend(frameon=False, fontsize=8)
    else:
        ax.scatter(x, r, s=28, color=_PRIMARY, alpha=0.8,
                   edgecolors="none", zorder=3)

    # 0 线：残差均值应落在 0 上
    if data.get("zero_line", True) is not False:
        ax.axhline(0.0, color="#333333", lw=1.2, zorder=2)

    # ±2sigma：正态假设下的近似 95% 区间
    for k, ls in ((2.0, "--"), (1.0, ":")):
        ax.axhline(k * sigma, ls=ls, lw=1.0, color="#b03030", alpha=0.8, zorder=1)
        ax.axhline(-k * sigma, ls=ls, lw=1.0, color="#b03030", alpha=0.8, zorder=1)
    ax.annotate(f"+2sigma = {_fmt(2 * sigma)}", xy=(0.99, 2 * sigma),
                xycoords=("axes fraction", "data"), ha="right", va="bottom",
                fontsize=8, color="#b03030")
    ax.annotate(f"-2sigma = {_fmt(-2 * sigma)}", xy=(0.99, -2 * sigma),
                xycoords=("axes fraction", "data"), ha="right", va="top",
                fontsize=8, color="#b03030")

    outside = int(np.sum(np.abs(np.asarray(r)) > 2 * sigma))
    ax.annotate(f"sigma = {_fmt(sigma)}\n±2sigma 之外 {outside}/{len(r)} 点",
                xy=(0.03, 0.97), xycoords="axes fraction", ha="left", va="top",
                fontsize=9, color="#333333",
                bbox=dict(boxstyle="round,pad=0.35", fc="white",
                          ec="#cccccc", alpha=0.9))

    ax.set_xlabel(x_label)
    ax.set_ylabel(meta.get("y_label", "残差"))
    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def _as_float_list(values: Any, name: str) -> list:
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise ValueError(
            f"{name} 必须是数值序列，当前是 {type(values).__name__}。"
        )
    out = []
    for v in values:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            raise ValueError(f"{name} 里含有非数值元素 {v!r}，无法画残差图。")
    return out


def _fmt(v: Any) -> str:
    """数字格式化：太小或太大的值用科学计数法，否则保留 4 位有效数字。

    统一走 mcmplot.fmt，保证全库图上的数字长得一样。
    """
    return mcmplot.fmt(v)
