"""fig.bar_comparison —— 跨候选项的指标对比柱状图。

数据从哪来
----------
data 是一个 dict，键是模板声明的输入名：

    categories  类别名序列（如模型名、情景名），长度 N
    values      与 categories 一一对应的指标值，长度 N
    errors      误差/标准差序列（可选），长度 N；给了就画误差棒
    series      分组名序列（可选），长度 N；多组时并排分组画柱子

前三个是模板 required_inputs；`series` 模板没声明，但按题目要求支持分组。
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
import numpy as np  # noqa: E402

_PRIMARY = "#1f4e79"


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    # categories / values 是模板标了 optional: false 的输入，缺了就直说。
    if not data.get("categories"):
        raise ValueError("bar_comparison 缺少必填输入 categories（类别名序列）。")
    if data.get("values") is None:
        raise ValueError("bar_comparison 缺少必填输入 values（指标值序列）。")

    labels = [str(c) for c in data["categories"]]
    # 只绑了一个结果原子时，values 是一个数而不是列表。
    # 这种情况直接报清楚，别让 float(v) 抛出一句莫名其妙的
    # "'float' object is not iterable"。
    raw_values = data["values"]
    if isinstance(raw_values, (int, float)):
        raise ValueError(
            "values 只收到一个数值。柱状图至少需要两组对比，"
            "请绑定多个结果原子，或改用单值展示的模板。"
        )
    values = [float(v) for v in raw_values]
    if len(labels) != len(values):
        # 不猜用户想怎样，直接说清楚哪里对不上。
        raise ValueError(
            f"categories 有 {len(labels)} 个，values 有 {len(values)} 个，数量必须一致。"
        )

    # errors 是 optional: true，没给就静默不画误差棒。
    errors = data.get("errors")
    if errors is not None:
        errors = [float(e) for e in errors]
        if len(errors) != len(values):
            raise ValueError(
                f"errors 有 {len(errors)} 个，values 有 {len(values)} 个，数量必须一致。"
            )

    series = data.get("series")
    if series is not None:
        series = [str(s) for s in series]
        if len(series) != len(values):
            raise ValueError(
                f"series 有 {len(series)} 个，values 有 {len(values)} 个，数量必须一致。"
            )

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 3.7))

    if series:
        # 分组柱：按 series 切分，同一类别下并排。
        names = list(dict.fromkeys(series))
        idx = np.arange(len(labels))
        total_w = 0.8
        w = total_w / len(names)
        for k, name in enumerate(names):
            vals, errs, offs = [], [], []
            for i, s in enumerate(series):
                if s == name:
                    vals.append(values[i])
                    errs.append(None if errors is None else errors[i])
                    offs.append(idx[i] - total_w / 2 + w * (k + 0.5))
            if not vals:
                continue
            yerr = None if errors is None else [0.0 if e is None else e for e in errs]
            ax.bar(offs, vals, width=w, label=name, yerr=yerr,
                   capsize=3 if yerr is not None else 0,
                   color=_PRIMARY if k == 0 else None,
                   error_kw={"ecolor": "#555555", "lw": 1})
        # 类别名回填到刻度上；categories 本身重复（每个 series 各报一次）时取唯一。
        uniq = list(dict.fromkeys(labels))
        ax.set_xticks([idx[labels.index(u)] for u in uniq])
        ax.set_xticklabels(uniq)
        ax.legend(frameon=False)
    else:
        # 普通柱：一次画完，顺带把数值标在柱顶，读者不用去对照数字表。
        xpos = np.arange(len(labels))
        ax.bar(xpos, values, width=0.6, color=_PRIMARY,
               yerr=errors, capsize=3 if errors is not None else 0,
               error_kw={"ecolor": "#555555", "lw": 1})
        ax.set_xticks(xpos)
        ax.set_xticklabels(labels)
        for xi, yi in zip(xpos, values):
            ax.annotate(_fmt(yi), xy=(xi, yi), xytext=(0, 4 if yi >= 0 else -12),
                        textcoords="offset points", ha="center",
                        fontsize=8, color=_PRIMARY)

    ax.set_ylabel(meta.get("y_label", "指标值"))
    if meta.get("x_label"):
        ax.set_xlabel(meta["x_label"])
    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    ax.grid(alpha=0.3, axis="y")
    ax.set_axisbelow(True)
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
