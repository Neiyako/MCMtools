"""fig.convergence —— 目标值/误差随迭代次数的收敛曲线。

数据从哪来
----------
data 是一个 dict，键是模板声明的输入名：

    iterations    迭代次数/epoch 序列，长度 N
    objective     对应目标值（或误差）序列，长度 N
    converged_at  收敛发生的位置（可选，scalar）：
                  给了就画竖直虚线 + 水平虚线（末值/收敛值），
                  竖直线的横坐标按这个值来。

`baseline` 模板没声明，但按题目要求支持：给了就画一条水平虚线做参考。
绑定的 ResultAtom 由上层整理成这个形状后传进来；本文件不关心它们
从哪个实验来，只负责把图画出花来。

统一约定（所有图模板都遵守）
    render(data, meta) -> matplotlib Figure
    meta 里可能有：caption / x_label / y_label / width_in
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import matplotlib

matplotlib.use("Agg")

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402

_PRIMARY = "#1f4e79"


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    # iterations / objective 是模板标了 optional: false 的输入，缺了就直说。
    if data.get("iterations") is None:
        raise ValueError("convergence 缺少必填输入 iterations（迭代次数序列）。")
    if data.get("objective") is None:
        raise ValueError("convergence 缺少必填输入 objective（目标值序列）。")

    iters = [float(i) for i in data["iterations"]]
    obj = [float(o) for o in data["objective"]]
    if len(iters) != len(obj):
        # 不猜用户想怎样，直接说清楚哪里对不上。
        raise ValueError(
            f"iterations 有 {len(iters)} 个点，objective 有 {len(obj)} 个点，数量必须一致。"
        )

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 3.7))

    ax.plot(iters, obj, "-", lw=2, color=_PRIMARY, marker="o", markersize=4)

    # baseline 是可选参考线，"不做优化会怎样"。
    baseline = data.get("baseline")
    if baseline is not None:
        baseline = float(baseline)
        ax.axhline(baseline, ls="--", lw=1.2, color="#b03030")
        ax.annotate(f"baseline {_fmt(baseline)}", xy=(0.99, baseline),
                    xycoords=("axes fraction", "data"), ha="right", va="bottom",
                    fontsize=8, color="#b03030")

    # converged_at 是 optional: true，没给就不画收敛标记。
    converged_at = data.get("converged_at")
    if converged_at is not None:
        converged_at = float(converged_at)
        # 收敛值取落在该迭代位置上的目标值；越界时退回末值，不瞎猜。
        converged_val = obj[-1]
        for i, it in enumerate(iters):
            if it >= converged_at:
                converged_val = obj[i]
                break
        ax.axvline(converged_at, ls=":", lw=1.2, color="#2e7d32")
        ax.axhline(converged_val, ls="--", lw=1.2, color="#2e7d32")
        ax.annotate(
            f"迭代 {_fmt(converged_at)} 次收敛于 {_fmt(converged_val)}",
            xy=(converged_at, converged_val), xytext=(8, 10),
            textcoords="offset points", fontsize=8, color="#2e7d32",
        )

    ax.set_xlabel(meta.get("x_label", "迭代次数"))
    ax.set_ylabel(meta.get("y_label", "目标值"))
    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def _fmt(v: Any) -> str:
    """数字格式化：太小或太大的值用科学计数法，否则保留 4 位有效数字。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != 0 and (abs(f) < 1e-3 or abs(f) >= 1e5):
        return f"{f:.2e}"
    return f"{f:.4g}"
