"""fig.sensitivity_line —— 单因子敏感性曲线。

数据从哪来
----------
data 是一个 dict，键是模板声明的输入名：

    x         自变量序列（如 beta 的取值）
    y         对应的指标序列（如峰值人数）
    series    分组名（可选，多组时画多条线）
    baseline  参考值（可选，画一条水平虚线）

绑定的 ResultAtom 由上层整理成这个形状后传进来；本文件不关心它们
从哪个实验来，只负责把图画出花来。

为什么模板要带代码
------------------
早先的模板只有元数据（声明有哪些输入），真正的绘制逻辑写死在
core/mcmcore/figures.py 里，靠 template_id 分支。那样"新增一个图模板"
等于改核心源码 —— 库再大也只能用已接线的几个。
现在每个模板自带 render()，加模板就是加一个目录。

统一约定（所有图模板都遵守）
    render(data, meta) -> matplotlib Figure
    meta 里可能有：caption / x_label / y_label / width_in
"""

from __future__ import annotations

from typing import Any, Dict

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402


def render(data: Dict[str, Any], meta: Dict[str, Any] | None = None):
    meta = meta or {}
    y = list(data.get("y") or [])
    if not y:
        # 没数据时不能画一张空图 —— 那看起来像"成功但没结果"，
        # 比直接报错更难排查。
        raise ValueError("缺少必填输入 y：请提供要画成曲线的指标序列。")
    x = list(data.get("x") or range(len(y)))
    if len(x) != len(y):
        # 不猜用户想怎样，直接说清楚哪里对不上。
        raise ValueError(f"x 有 {len(x)} 个点，y 有 {len(y)} 个点，数量必须一致。")

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 3.7))

    series = data.get("series")
    if series:
        # 按分组名切成多条线
        groups: Dict[str, list] = {}
        for i, name in enumerate(series):
            groups.setdefault(str(name), []).append(i)
        for name, idx in groups.items():
            ax.plot([x[i] for i in idx], [y[i] for i in idx],
                    "o-", lw=2, markersize=6, label=name)
        ax.legend(frameon=False)
    else:
        ax.plot(x, y, "o-", lw=2, color="#1f4e79", markersize=6)
        # 标注每个点，读者不用去对照数字表
        for xi, yi in zip(x, y):
            ax.annotate(mcmplot.fmt(yi), xy=(xi, yi), xytext=(0, 7),
                        textcoords="offset points", ha="center",
                        fontsize=8, color="#1f4e79")

    # 基线：论文里常画一条参考线说明"不干预会怎样"
    baseline = data.get("baseline")
    if baseline is not None:
        ax.axhline(float(baseline), ls="--", lw=1.2, color="#b03030")
        ax.annotate(f"baseline {mcmplot.fmt(baseline)}", xy=(0.99, float(baseline)),
                    xycoords=("axes fraction", "data"), ha="right", va="bottom",
                    fontsize=8, color="#b03030")

    ax.set_xlabel(meta.get("x_label", "参数取值"))
    ax.set_ylabel(meta.get("y_label", "指标"))
    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
