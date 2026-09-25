"""fig.confidence_band —— 带置信区间的折线（均值线 + 上下界填充）。

为什么论文里几乎每张预测图都该有它
----------------------------------
只画一条均值线会传递一个错误信号：读者会以为模型"知道"那个值。
而模型给出的是一个区间。把上下界填成色带，读者能直接看出
"哪一段预测得准、哪一段其实是猜的"—— 这恰恰是评审最想知道的。

上界小于下界必须报错
--------------------
上界/下界填反了不会报错，matplotlib 照画，只是色带**翻到线的另一侧**，
看起来像"预测区间在均值下方"，结论完全反了。而且这种错误在图上
不显眼，很容易一路进到论文里。所以这里逐点比较，填反就报错并指出
是第几个点。

数据从哪来
----------
data 的键：
    x           横轴（时间或参数）
    mean        均值/中心轨迹
    lower       置信下界（逐点不大于 upper）
    upper       置信上界（逐点不小于 lower）
    observed    实测序列（可选），叠成散点做对照
    confidence  置信水平（可选），如 0.95，只用于图例文字

meta 里可能有：caption / x_label / y_label / width_in
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

_COLOR_LINE = "#1f4e79"
_COLOR_BAND = "#7ba7cc"
_COLOR_OBS = "#c0504d"


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    x = data.get("x")
    if x is None or len(list(x)) == 0:
        raise ValueError(
            "缺少必填输入 x：请提供横轴序列（时间或参数），"
            "例如 [1, 2, 3, 4, 5]。"
        )
    x = list(x)

    mean = list(data.get("mean") or [])
    if not mean:
        raise ValueError(
            "缺少必填输入 mean：请提供均值/中心轨迹序列，长度要等于 x。"
        )
    lower = list(data.get("lower") or [])
    if not lower:
        raise ValueError(
            "缺少必填输入 lower：请提供置信下界序列，长度要等于 x。"
            "只有均值线请改用 fig.timeseries。"
        )
    upper = list(data.get("upper") or [])
    if not upper:
        raise ValueError(
            "缺少必填输入 upper：请提供置信上界序列，长度要等于 x。"
            "只有均值线请改用 fig.timeseries。"
        )

    n = len(x)
    for key, seq in (("mean", mean), ("lower", lower), ("upper", upper)):
        if len(seq) != n:
            raise ValueError(
                f"{key} 有 {len(seq)} 个点，x 有 {n} 个点：数量必须一致。"
            )

    try:
        m = np.asarray(mean, dtype=float)
        lo = np.asarray(lower, dtype=float)
        hi = np.asarray(upper, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "mean / lower / upper 必须是数值序列：请检查是否混入了文字或空缺。"
        )
    for key, arr in (("mean", m), ("lower", lo), ("upper", hi)):
        if not np.all(np.isfinite(arr)):
            raise ValueError(
                f"{key} 里有空值：每一期都要有数值才能连成曲线，"
                "缺失的期请先补齐或从 x 里去掉。"
            )

    # 上下界填反是最危险的错误：图照样画，但色带翻到另一侧，
    # 结论完全反了。逐点查，并指出是第几个点。
    bad = np.where(hi < lo)[0]
    if bad.size:
        i = int(bad[0])
        raise ValueError(
            f"upper 在第 {i + 1} 个点（x={mcmplot.fmt(x[i])}）上小于 lower："
            f"lower={mcmplot.fmt(lo[i])}，upper={mcmplot.fmt(hi[i])}。"
            "上下界填反了，请检查两列是否写颠倒。"
        )

    width = float(meta.get("width_in", 6.6))
    fig, ax = plt.subplots(figsize=(width, 3.9))

    conf = data.get("confidence")
    if conf is not None:
        try:
            conf_pct = f"{float(conf) * 100:.0f}%"
        except (TypeError, ValueError):
            conf_pct = str(conf)
        band_label = f"{conf_pct} 置信区间"
    else:
        band_label = "置信区间"

    # 先填带再画线：线的图层在上，不会被色带盖住。
    ax.fill_between(x, lo, hi, color=_COLOR_BAND, alpha=0.28,
                    linewidth=0, label=band_label)
    ax.plot(x, m, "-", lw=2.0, color=_COLOR_LINE, label="均值")

    observed = data.get("observed")
    if observed is not None:
        observed = list(observed)
        if len(observed) != n:
            raise ValueError(
                f"observed 有 {len(observed)} 个点，x 有 {n} 个点：数量必须一致。"
            )
        ax.plot(x, observed, "o", ms=2.8, color=_COLOR_OBS, alpha=0.7,
                label="实测",
                markevery=max(1, n // 120))

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "时间")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "数值")))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.legend(frameon=False, fontsize=8, loc="best")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
