"""fig.histogram_distribution —— 单变量分布直方图。

为什么要有这张图
----------------
语料里 35.5% 的 Outstanding 论文都画了某个量的分布。它回答的是
"这个指标长什么样"：是不是对称、有没有双峰、长尾有多长。
只看均值会把这些信息全丢掉 —— 两个均值相同的样本，一个是
正态一个是双峰，结论完全不同。

纵轴到底是什么意思
------------------
这是这张图最容易出错的地方。直方图有两种纵轴：

* `density=True`：纵轴是**概率密度**，柱子的**面积**才是概率，
  不是柱子高度。这时候柱高可以大于 1（数据很集中时），
  和"频率"完全对不上，标成"频数"就是错的。
* `density=False`：纵轴是**计数**，柱子高度就是落进这个区间的样本数。

这里固定用 density=True，因为要能和拟合密度曲线、KDE 曲线叠在一起 ——
三条曲线的纵轴必须是同一个量纲才能比。既然选了密度，纵轴标签就
老老实实写"概率密度"，绝不敢写"频数"。

数据从哪来
----------
    values      必填，一维数值序列
    bins        可选，分箱数（标量）；不给就用 Freedman-Diaconis 规则自动定
    fit_curve   可选，拟合密度曲线在**每个箱中心**处的 y 值（长度 = 箱数）
    kde_x       可选，密度曲线的横坐标；给了它就用它当曲线的横轴

fit_curve 与 kde_x 是一对：fit_curve 的长度等于实际分箱数，横轴默认
取箱中心；kde_x 覆盖横轴时，fit_curve 就必须与 kde_x 等长。两种都收，
但长度对不上会明确报错 —— 硬猜横轴会让曲线错位，那是静默的错误。

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

_PRIMARY = "#1f4e79"      # 直方图主体：冷色，不抢眼
_FIT = "#c0392b"          # 拟合曲线：暖色，从柱子里跳出来
_MEAN = "#e07b39"         # 均值：虚线，和实线的中位数区分开
_MEDIAN = "#2e7d32"       # 中位数：实线

# 样本少于这个数就不画拟合曲线了：几个点拟合出来的密度肉眼看不出意义，
# 画上去反而让评审以为结论有统计支撑。
_MIN_N_FOR_FIT = 20


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    values = _to_float_list(data.get("values"))
    if not values:
        raise ValueError(
            "缺少必填输入 values：请提供要统计分布的一维数值序列（例如各样本的指标值）。"
        )
    if len(values) < 2:
        # 一个点画不出分布，也没有中位数可言；画出来是一根柱子的空图。
        raise ValueError(
            f"values 只有 {len(values)} 个观测，画不出分布：至少需要 2 个观测值。"
        )

    arr = np.asarray(values, dtype=float)

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 3.9))

    bins = _resolve_bins(data.get("bins"), arr)

    # density=True：纵轴是概率密度而不是频数。选它是因为要叠拟合曲线 ——
    # 频数轴上千，密度轴是零点几，两条线放一起没法比。
    counts, edges, _ = ax.hist(
        arr, bins=bins, density=True, color="#cfe0f0",
        edgecolor=_PRIMARY, linewidth=0.8, label="经验分布",
    )

    _draw_fit(ax, data, edges)

    mean_v = float(np.mean(arr))
    median_v = float(np.median(arr))

    # 均值和中位数用不同线型：实线 vs 虚线。即使黑白打印、或者读者是色盲，
    # 也能靠线型分辨 —— 论文图表必须考虑灰度打印。
    ax.axvline(mean_v, color=_MEAN, ls="--", lw=1.5,
               label=f"均值 {mcmplot.fmt(mean_v)}")
    ax.axvline(median_v, color=_MEDIAN, ls="-", lw=1.5,
               label=f"中位数 {mcmplot.fmt(median_v)}")

    # 偏度用中位数与均值的偏离方向说明，比给一个裸数字直观得多：
    # 均值在中位数右边就是右偏（长尾拖向大值）。
    if abs(mean_v - median_v) > 1e-12 * max(1.0, abs(median_v)):
        direction = "右偏" if mean_v > median_v else "左偏"
        ax.annotate(
            mcmplot.safe(f"{direction}：均值{'>' if mean_v > median_v else '<'}中位数"),
            xy=(0.98, 0.62), xycoords="axes fraction",
            ha="right", va="top", fontsize=8, color="#555555",
        )

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "取值")))
    # 纵轴写"概率密度"而不是"频数"：直方图开了 density=True，
    # 柱高是密度，面积才是概率，标成频数是常见但致命的错误。
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "概率密度")))
    ax.set_ylim(bottom=0)  # 密度不会为负，从 0 起画才不误导

    # 偏度小字固定打在右上角，所以有它时把图例让到左上，两者不叠字。
    legend_loc = "upper left" if _has_annotation(mean_v, median_v) else "upper right"
    ax.legend(frameon=False, fontsize=8, loc=legend_loc)

    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3, axis="y")
    ax.set_axisbelow(True)
    fig.tight_layout()
    return fig


def _has_annotation(mean_v: float, median_v: float) -> bool:
    """均值与中位数是否足够不同（决定是否画偏度小字）。"""
    return abs(mean_v - median_v) > 1e-12 * max(1.0, abs(median_v))


def _draw_fit(ax, data: Dict[str, Any], edges: np.ndarray) -> None:
    """叠加拟合密度曲线（可选）。

    fit_curve 的长度必须等于实际箱数；如果还给了 kde_x，横轴就用 kde_x。
    长度对不上时直接报错 —— 曲线错位半格在图上完全看不出来，
    但读者会据此读出错误的峰位置。
    """
    fit = data.get("fit_curve")
    if fit is None:
        return

    fit = _to_float_list(fit)
    if not fit:
        return

    kde_x = data.get("kde_x")
    n_bins = len(edges) - 1

    if kde_x is not None:
        kde_x = _to_float_list(kde_x)
        if len(kde_x) != len(fit):
            raise ValueError(
                f"kde_x 有 {len(kde_x)} 个点，fit_curve 有 {len(fit)} 个点，"
                "数量必须一致（fit_curve 是在 kde_x 各点处的密度值）。"
            )
        xs = np.asarray(kde_x, dtype=float)
    else:
        if len(fit) != n_bins:
            raise ValueError(
                f"fit_curve 有 {len(fit)} 个点，但直方图分了 {n_bins} 个箱，"
                "数量必须一致（fit_curve 默认画在每个箱的中心）；"
                "若曲线横轴不是箱中心，请同时提供等长的 kde_x。"
            )
        # 箱中心：相邻边界的中点，是最自然的横坐标。
        xs = (edges[:-1] + edges[1:]) / 2.0

    ax.plot(xs, fit, "-", lw=1.8, color=_FIT, label="拟合密度")


def _resolve_bins(raw: Any, arr: np.ndarray) -> Any:
    """确定分箱数。

    默认走 Freedman-Diaconis 规则 —— 它按 IQR 自适应，
    比固定 10 个箱子更不容易在小样本上画出假的锯齿。
    IQR 为 0（数据几乎全相同）时退回平方根规则，否则会除零。
    """
    if raw is not None:
        try:
            n = int(raw)
        except (TypeError, ValueError):
            raise ValueError(
                f"bins 必须是整数或分箱边界序列，当前是 {raw!r}。"
            )
        if n < 1:
            raise ValueError(f"bins 必须至少为 1，当前是 {n}。")
        if n > len(arr):
            # 箱数比样本还多会画出一堆只有 0 或 1 个点的柱子，形状全是噪声。
            raise ValueError(
                f"bins={n} 超过了观测数 {len(arr)}：箱数不能多于观测数，"
                "否则每个箱里不足一个点，直方图会变成噪声。"
            )
        return n

    q75, q25 = np.percentile(arr, [75, 25])
    iqr = float(q75 - q25)
    if iqr > 0:
        width = 2.0 * iqr / (len(arr) ** (1.0 / 3.0))
        span = float(np.max(arr) - np.min(arr))
        if width > 0 and span > 0:
            n = int(np.ceil(span / width))
            # 夹到合理区间：太少的箱看不出形状，太多的箱全是毛刺。
            return int(min(max(n, 5), 60))
    return int(min(max(int(np.sqrt(len(arr))), 5), 60))


def _to_float_list(raw: Any) -> List[float]:
    """把输入转成 float 列表，顺便挡住空值和不可转的脏数据。"""
    if raw is None:
        return []
    out: List[float] = []
    for v in raw:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            raise ValueError(
                f"values 里出现了非数值项 {v!r}：分布图只能接受数值序列，"
                "请先清洗缺失值。"
            )
    return out
