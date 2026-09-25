"""fig.pred_vs_actual —— 预测值 vs 真实值散点图（带 y=x 参考线）。

数据从哪来
----------
data 是一个 dict，键是模板声明的输入名：

    actual         真实值序列，必填
    predicted      对应的预测值序列，必填，长度必须与 actual 一致
    identity_line  是否画 y=x 参考线；可选，默认画。
                   传 False 关掉；传数字则把参考线改成 y = 该值 * x 的过原点直线。
    series         分组名（可选）。给了就按组用不同颜色画，图例标出组名，
                   这是"训练集/测试集""不同模型"对比的标准画法。

图上除了散点还写两个数（论文里几乎必写）：
    R^2  决定系数，1 - SS_res/SS_tot
    RMSE 均方根误差，单位与真实值相同

分组时，每个组既给出自己的 R^2/RMSE，也在图例里汇总；不分组时只给一个总指标。

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

# 主序列固定用这个深蓝，全库统一
_PRIMARY = "#1f4e79"
# 分组时循环使用的配色，第一色与主序列一致
_PALETTE = [_PRIMARY, "#b03030", "#2e7d32", "#8a6d3b", "#6a3d9a", "#c46a1f"]


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    actual = data.get("actual")
    predicted = data.get("predicted")
    if actual is None:
        raise ValueError("缺少必填输入 actual：请提供真实值序列。")
    if predicted is None:
        raise ValueError("缺少必填输入 predicted：请提供预测值序列。")

    a = _as_float_list(actual, "actual")
    p = _as_float_list(predicted, "predicted")
    if len(a) != len(p):
        raise ValueError(
            f"actual 有 {len(a)} 个点，predicted 有 {len(p)} 个点，数量必须一致。"
        )
    if len(a) == 0:
        raise ValueError("actual/predicted 都是空的：至少需要一个数据点才能画拟合散点图。")

    series = data.get("series")
    if series is not None:
        s = list(series)
        if len(s) != len(a):
            raise ValueError(
                f"series 有 {len(s)} 项，但 actual 有 {len(a)} 项，数量必须一致。"
            )
    else:
        s = None

    width = float(meta.get("width_in", 6.0))
    fig, ax = plt.subplots(figsize=(width, max(3.7, width * 0.75)))

    # R^2 需要 SS_tot 不为 0
    ss_tot = float(np.sum((np.asarray(a) - np.mean(a)) ** 2))
    if ss_tot == 0:
        raise ValueError(
            "actual 的所有取值都相同，R^2 没有定义"
            "（真实值方差为 0），请检查数据是否填错。"
        )

    lines = []
    if s is not None:
        groups: Dict[str, list] = {}
        for i, name in enumerate(s):
            groups.setdefault(str(name), []).append(i)
        for k, (name, idx) in enumerate(groups.items()):
            color = _PALETTE[k % len(_PALETTE)]
            xs = [a[i] for i in idx]
            ys = [p[i] for i in idx]
            ax.scatter(xs, ys, s=34, color=color, alpha=0.85,
                       edgecolors="white", linewidths=0.4, label=name, zorder=3)
            r2, rmse = _metrics(a, p, idx)
            lines.append(f"{name}: R^2={_fmt(r2)}, RMSE={_fmt(rmse)}")
    else:
        ax.scatter(a, p, s=34, color=_PRIMARY, alpha=0.85,
                   edgecolors="white", linewidths=0.4, zorder=3)
        r2, rmse = _metrics(a, p, None)
        lines.append(f"R^2 = {_fmt(r2)}")
        lines.append(f"RMSE = {_fmt(rmse)}")

    # 参考线：默认 y = x，表示"预测完全准确"
    identity = data.get("identity_line", True)
    slope = None
    if identity is None or identity is True:
        slope = 1.0
    elif identity is False:
        slope = None
    else:
        try:
            slope = float(identity)
        except (TypeError, ValueError):
            slope = 1.0

    if slope is not None:
        lo = min(min(a), min(p))
        hi = max(max(a), max(p))
        pad = (hi - lo) * 0.08 or max(abs(hi), 1.0) * 0.08
        lo, hi = lo - pad, hi + pad
        ax.plot([lo, hi], [lo * slope, hi * slope], ls="--", lw=1.2,
                color="#999999", zorder=1,
                label="y = x" if slope == 1.0 else f"y = {_fmt(slope)}x")
        ax.set_xlim(lo, hi)
        ax.set_ylim(min(lo * slope, lo), max(hi * slope, hi))

    # 指标写在左上角（右下角通常被离群点占着）
    ax.annotate("\n".join(lines), xy=(0.03, 0.97), xycoords="axes fraction",
                ha="left", va="top", fontsize=9, color="#333333",
                bbox=dict(boxstyle="round,pad=0.35", fc="white",
                          ec="#cccccc", alpha=0.9))

    ax.set_xlabel(meta.get("x_label", "真实值"))
    ax.set_ylabel(meta.get("y_label", "预测值"))
    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    ax.grid(alpha=0.3)
    # 没分组、又关掉了参考线时图例是空的，matplotlib 会发警告，干脆不画。
    handles, _ = ax.get_legend_handles_labels()
    if handles:
        ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    return fig


def _metrics(actual, predicted, idx) -> tuple:
    """返回 (R^2, RMSE)；idx 为 None 时用全部点。"""
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if idx is not None:
        a = a[idx]
        p = p[idx]
    resid = a - p
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((a - np.mean(a)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return r2, rmse


def _as_float_list(values: Any, name: str) -> list:
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise ValueError(
            f"{name} 必须是数值序列，当前是 {type(values).__name__}"
            "（如果是标量，请先展开成序列）。"
        )
    out = []
    for v in values:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            raise ValueError(f"{name} 里含有非数值元素 {v!r}，无法计算 R^2 和 RMSE。")
    return out


def _fmt(v: Any) -> str:
    """数字格式化：太小或太大的值用科学计数法，否则保留 4 位有效数字。

    统一走 mcmplot.fmt，保证全库图上的数字长得一样。
    """
    return mcmplot.fmt(v)
