"""fig.qq_plot —— 正态 Q-Q 图，验证残差正态性。

这张图在做什么
--------------
把样本从小到大排好，和"同样本量的标准正态"的理论分位数一一配对：
横轴是理论分位数，纵轴是样本分位数。样本服从正态分布时，
这些点应当落在一条直线上。点偏离直线的方式直接指出问题：

* 两端向上翘  -> 右偏长尾（有几个特别大的值）
* 两端向下垂  -> 左偏长尾
* 两端离直线很远而中间贴合 -> 峰度不对（重尾或轻尾）
* 整体呈 S 形  -> 分布的尾部比正态更快衰减（轻尾）

为什么不用 scipy
----------------
scipy 是重型依赖，而这个模板只需要一个函数：正态分布的分位数函数。
Python 3.8+ 标准库的 `statistics.NormalDist().inv_cdf()` 就是它。
少一个第三方依赖，用户在只装了 matplotlib 的环境里也能直接跑。
顺带一提，标准误差公式 SE(p_i) = sqrt(p(1-p)/n) / phi(z_i) 里要用到
标准正态**密度**，而 NormalDist 没有 pdf —— 自己写 exp(-z^2/2)/sqrt(2pi)
一行就够，没必要为它引入整个 scipy.stats。

为什么要算"排名"而不是直接排序取分位数
--------------------------------------
样本分位数不能用 (i-1)/(n-1) 直接算：这样会用到 1.0，
而 inv_cdf(1.0) 是 +inf，图上会出现一个跑到无穷远的点。
这里用 Blom 的绘图位置 (i - 0.375) / (n + 0.25)，
它把端点收在 (0,1) 开区间内，是 Q-Q 图的通行做法。

数据从哪来
----------
    values       必填，一维数值序列（通常是回归残差）
    confidence   可选，置信带的置信水平，默认 0.95；给 0 则不画置信带

meta 里可能有：caption / x_label / y_label / width_in
"""

from __future__ import annotations

import math
from statistics import NormalDist
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

_POINT = "#1f4e79"
_LINE = "#b03030"
_BAND = "#9db8d2"

# 样本少于这个数时置信带没有意义（区间宽到能装下整个坐标系），不画。
_MIN_N_FOR_BAND = 8

# Blom 绘图位置，见模块头注释。
_BLOM_A = 0.375


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    values = _to_float_list(data.get("values"))
    if not values:
        raise ValueError(
            "缺少必填输入 values：请提供要检验正态性的样本序列（通常是回归残差）。"
        )
    n = len(values)
    if n < 3:
        # 两个点永远共线，Q-Q 图恒为直线，什么也检验不出来。
        raise ValueError(
            f"values 只有 {n} 个观测：至少需要 3 个观测才能看出是否偏离正态，"
            "否则任意两个点都连成直线。"
        )

    arr = np.sort(np.asarray(values, dtype=float))

    # 理论分位数：Blom 绘图位置 -> 标准正态反函数。
    nd = NormalDist()
    probs = [((i + 1) - _BLOM_A) / (n + 1 - 2 * _BLOM_A) for i in range(n)]
    theoretical = np.asarray([nd.inv_cdf(p) for p in probs], dtype=float)

    # 45 度参考线：用样本均值/标准差把样本标准化，
    # 这样参考线就是 y = x，读者能直接看出"点在线的上方还是下方"。
    mean_v = float(np.mean(arr))
    sd_v = float(np.std(arr, ddof=1)) if n > 1 else 1.0
    if sd_v <= 0:
        # 全相同的样本：标准化会除零。此时样本没有任何变异，
        # 正态性检验本就无从谈起，直接说清楚。
        raise ValueError(
            "values 的样本标准差为 0（所有取值相同）：无法做正态性检验，"
            "请检查这一列是不是被误传了常量。"
        )
    standardized = (arr - mean_v) / sd_v

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 5.2), 4.6))

    lo = float(min(theoretical.min(), standardized.min()))
    hi = float(max(theoretical.max(), standardized.max()))
    pad = 0.08 * (hi - lo if hi > lo else 1.0)
    lo, hi = lo - pad, hi + pad

    confidence = data.get("confidence")
    if confidence is None:
        confidence = 0.95
    confidence = float(confidence)
    if confidence > 0 and n >= _MIN_N_FOR_BAND:
        _draw_band(ax, theoretical, n, confidence, lo, hi)

    # 参考线画在散点下面：点被线穿过会让"点偏没偏离"变得难判断。
    ax.plot([lo, hi], [lo, hi], "-", lw=1.3, color=_LINE,
            label="正态参考线 (y = x)", zorder=2)
    ax.scatter(theoretical, standardized, s=16, color=_POINT,
               alpha=0.8, edgecolors="none", zorder=3, label="样本分位数")

    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)

    ax.set_xlabel(mcmplot.safe(
        meta.get("x_label", "理论分位数（标准正态）")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "样本分位数（标准化）")))

    # 样本量 + 偏度/峰度：Q-Q 图看形状，这两个数给形状一个可引用的定量说法。
    # 论文里不能只写"点大致在直线上"，得有个数。
    ax.annotate(mcmplot.safe(_stats_text(arr, n)), xy=(0.03, 0.97),
                xycoords="axes fraction", ha="left", va="top", fontsize=8,
                color="#444444",
                bbox={"boxstyle": "round,pad=0.35", "fc": "white",
                      "ec": "#cccccc", "lw": 0.8, "alpha": 0.9})

    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.set_aspect("equal", adjustable="box")  # 45 度线在屏幕上才真的是 45 度
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)

    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    fig.tight_layout()
    return fig


def _draw_band(ax, theoretical: np.ndarray, n: int, confidence: float,
               lo: float, hi: float) -> None:
    """画点态置信带（正态的 1-alpha 分位点标准误）。

    SE(p_i) = sqrt(p_i (1-p_i) / n) / phi(z_i)，
    其中 phi 是标准正态密度。带子的宽度在两端张开、中间收窄 ——
    这正是"尾部本来就不稳"的直观体现，读者不会因为几个尾部点
    落在带外就过度解读。
    """
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    xs = np.linspace(lo, hi, 200)
    # NormalDist.cdf 只接受标量（传数组会抛 TypeError），所以这里用
    # numpy 化过的 erf 自己算正态累积分布；密度同样一行搞定。
    # 为这两个短公式再引入 scipy.special 不划算，也违背"不依赖 scipy"的约定。
    probs = 0.5 * (1.0 + np.vectorize(math.erf)(xs / math.sqrt(2.0)))
    phi = np.exp(-0.5 * xs ** 2) / math.sqrt(2.0 * math.pi)
    # phi 极小时（远离均值）SE 会炸开，夹一下避免带子撑满整个图。
    phi = np.clip(phi, 1e-6, None)
    se = np.sqrt(np.clip(probs * (1 - probs), 0.0, None) / n) / phi
    se = np.clip(se, 0.0, (hi - lo))  # 带上界，图上不至于只剩一条带子

    ax.fill_between(xs, xs - z * se, xs + z * se, color=_BAND, alpha=0.3,
                    linewidth=0, zorder=1,
                    label=f"{int(confidence * 100)}% 置信带")


def _stats_text(arr: np.ndarray, n: int) -> str:
    """样本量 + 偏度 + 峰度（超额峰度，正态为 0）。"""
    m = float(np.mean(arr))
    s = float(np.std(arr, ddof=0))
    if s <= 0:
        return f"n = {n}"
    z = (arr - m) / s
    skew = float(np.mean(z ** 3))
    # 用超额峰度：正态分布是 0，读者不用去记"正态峰度是 3"这件事。
    kurt = float(np.mean(z ** 4)) - 3.0
    return f"n = {n}\n偏度 = {mcmplot.fmt(skew)}\n峰度 = {mcmplot.fmt(kurt)}"


def _to_float_list(raw: Any) -> List[float]:
    """把输入转成 float 列表，挡住空值和不可转的脏数据。"""
    if raw is None:
        return []
    out: List[float] = []
    for v in raw:
        try:
            fv = float(v)
        except (TypeError, ValueError):
            raise ValueError(
                f"values 里出现了非数值项 {v!r}：Q-Q 图只能接受数值序列，"
                "请先清洗缺失值。"
            )
        if not math.isfinite(fv):
            # inf / nan 会让排序和 inv_cdf 全乱掉，而且画出来是个静默的空点。
            raise ValueError(
                f"values 里出现了非有限值 {v!r}：请先剔除缺失值或无穷值。"
            )
        out.append(fv)
    return out
