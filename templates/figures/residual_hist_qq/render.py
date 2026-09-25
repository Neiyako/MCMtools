"""fig.residual_hist_qq —— 残差诊断组合图（直方图 + Q-Q 图）。

为什么这两张必须放在一起
------------------------
它们回答的是同一个问题的两半：

    直方图  残差的**分布形状**对不对（是不是单峰、有没有偏斜、有几个峰）
    Q-Q 图  残差的**尾部**对不对（正态假设在两端成不成立）

只看直方图会漏掉尾部偏离 —— 而回归的置信区间和显著性检验恰恰
依赖尾部。只看 Q-Q 图会漏掉多峰 —— 多峰说明还有没被模型抓住的结构。
论文里把两张并排画在一起，读者一眼就能给出"这个拟合能不能信"的判断。

三个子图不是更好
----------------
常见的作法是再加一张"残差 vs 预测值"看异方差。这里**故意不加**：
三张图并排后每张只有 2 英寸宽，直方图的分箱变得毫无意义。
异方差请用 fig.residual（残差对预测值散点），那是它专门解决的问题。

样本量的诚实处理
----------------
少于 8 个残差时不画 Q-Q 图 —— 理论分位数只有 8 个点，连成的线
在视觉上"很直"，会给出虚假的正态印象。此时改成在右图写一句
明确说明，而不是画一条骗人的线。

数据从哪来
----------
data 的键：
    residual  残差序列（观测值减预测值）
    bins      直方图分箱数（可选）

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

# 少于这个样本量就不画 Q-Q 图。理由见模块开头。
_MIN_FOR_QQ = 8


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    residual = list(data.get("residual") or [])
    if not residual:
        raise ValueError(
            "缺少必填输入 residual：请提供残差序列（观测值减预测值），"
            "例如 [0.3, -0.2, 0.1, ...]，至少 3 个点才能看出分布形状。"
        )
    try:
        r = np.asarray(residual, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "residual 必须是数值序列：请检查序列里是否混入了文字或空缺。"
        )
    if r.ndim != 1:
        raise ValueError(
            f"residual 必须是一维序列，当前形状 {r.shape}。"
        )
    if not np.all(np.isfinite(r)):
        raise ValueError(
            "residual 里有空值：每个点都要有一个实际残差才能统计分布，"
            "算不出残差的点请先从序列里去掉。"
        )
    if r.size < 3:
        raise ValueError(
            f"residual 只有 {r.size} 个点：至少需要 3 个残差才能看出"
            "分布形状，两个点连直方图都画不出来。"
        )

    width = float(meta.get("width_in", 6.6))
    fig, (ax_h, ax_q) = plt.subplots(1, 2, figsize=(width, 3.6))

    # -- 左：残差直方图 --------------------------------------------------
    n = r.size
    bins = data.get("bins")
    if bins is None:
        # 分箱数按样本量的平方根取，这是最通用的经验规则；
        # 固定 10 箱在小样本上会把形状切碎，在大样本上又太粗。
        bins = int(np.clip(np.ceil(np.sqrt(n)), 4, 40))
    bins = int(bins)
    if bins < 2:
        raise ValueError(
            f"bins 是 {bins}：至少要分成 2 箱才叫直方图，请给一个不小于 2 的整数。"
        )

    ax_h.hist(r, bins=bins, color="#1f4e79", alpha=0.78,
              edgecolor="white", linewidth=0.6)
    # 零线：残差诊断的基准，偏离 0 越远越说明模型有系统偏差。
    ax_h.axvline(0, color="#c0504d", lw=1.4, ls="--")
    mean = float(np.mean(r))
    ax_h.axvline(mean, color="#f79646", lw=1.4, ls="-")
    ax_h.annotate(f"均值 {mcmplot.fmt(mean)}",
                  xy=(mean, 1.0), xycoords=("data", "axes fraction"),
                  xytext=(4, -4), textcoords="offset points",
                  fontsize=7.5, color="#b35c00", va="top")
    ax_h.set_xlabel(mcmplot.safe(meta.get("x_label", "残差")))
    ax_h.set_ylabel(mcmplot.safe(meta.get("y_label", "频数")))
    ax_h.set_title("残差分布", fontsize=9)
    ax_h.grid(alpha=0.3, axis="y")

    # -- 右：正态 Q-Q 图 -------------------------------------------------
    if n >= _MIN_FOR_QQ:
        _qq_plot(ax_q, r)
        ax_q.set_title("正态 Q-Q 图", fontsize=9)
    else:
        # 样本太少，画出来的"直线"没有意义。如实说明，不画假的。
        ax_q.text(0.5, 0.5,
                  f"残差只有 {n} 个点\n"
                  f"少于 {_MIN_FOR_QQ} 个时 Q-Q 图不可靠，故不绘制。\n"
                  "建议增加样本量后重跑。",
                  ha="center", va="center", fontsize=9,
                  color="#8a6d3b", transform=ax_q.transAxes, wrap=True)
        ax_q.set_xticks([])
        ax_q.set_yticks([])
        ax_q.set_title("正态 Q-Q 图（样本不足）", fontsize=9)

    if meta.get("caption"):
        fig.suptitle(mcmplot.safe(meta["caption"].rstrip(".")), fontsize=10)
    fig.tight_layout()
    return fig


def _qq_plot(ax, r) -> None:
    """在 ax 上画正态 Q-Q 图。

    横轴是理论分位数（正态），纵轴是样本分位数，按 (i-0.5)/n 取位置 ——
    这个偏移量避免了 i/n 在最大点上把分位数推到无穷。
    """
    n = r.size
    s = np.sort(r)
    # 用 (i-0.5)/n 而不是 i/(n+1)：前者在两端更稳，是常见的默认。
    probs = (np.arange(1, n + 1) - 0.5) / n
    theoretical = _norm_ppf(probs)

    # 参考线用数据自己拟合：把样本分位数对理论分位数做最小二乘。
    # 斜率就是标准差，截距就是均值 —— 和"正态假设成立时的直线"一致。
    slope, intercept = np.polyfit(theoretical, s, 1)
    xs = np.array([theoretical.min(), theoretical.max()])
    ax.plot(xs, slope * xs + intercept, "-", lw=1.4, color="#c0504d",
            label='正态参考线')
    ax.plot(theoretical, s, "o", ms=3.2, color="#1f4e79",
            alpha=0.8, label="样本分位数")

    ax.set_xlabel("理论分位数（正态）")
    ax.set_ylabel(mcmplot.safe("样本分位数"))
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax.grid(alpha=0.3)


def _norm_ppf(p):
    """标准正态分位函数（逆 CDF）。

    不引入 scipy：整个模板库只依赖 numpy/matplotlib，加一个重量级依赖
    只为算一条参考线不划算。这里用 Acklam 的有理逼近，全区间内
    相对误差优于 1.15e-9，对一张图远远够用。
    """
    p = np.asarray(p, dtype=float)
    # 把概率夹在开区间里，避免 log(0)
    p = np.clip(p, 1e-12, 1 - 1e-12)

    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]

    plow = 0.02425
    phigh = 1 - plow
    out = np.zeros_like(p)

    # 下尾
    lo = p < plow
    if np.any(lo):
        q = np.sqrt(-2 * np.log(p[lo]))
        out[lo] = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                  ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    # 上尾
    hi = p > phigh
    if np.any(hi):
        q = np.sqrt(-2 * np.log(1 - p[hi]))
        out[hi] = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                   ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    # 中段
    mid = ~(lo | hi)
    if np.any(mid):
        q = p[mid] - 0.5
        rr = q * q
        out[mid] = (((((a[0] * rr + a[1]) * rr + a[2]) * rr + a[3]) * rr + a[4]) * rr + a[5]) * q / \
                   (((((b[0] * rr + b[1]) * rr + b[2]) * rr + b[3]) * rr + b[4]) * rr + 1)
    return out
