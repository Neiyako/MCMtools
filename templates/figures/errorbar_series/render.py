"""fig.errorbar_series —— 带误差带的均值曲线。

为什么默认画误差带而不是误差棒
------------------------------
误差棒在单条曲线上很清楚，但三条以上就会在交叉处糊成一片，
读者分不清哪根棒属于哪条线。误差带（fill_between）用色块表达同一个
区间，多条时靠透明度叠色也能区分，是蒙特卡洛和交叉验证结果更稳的画法。
误差棒仍然保留一个开关（meta["show_bars"]）：点数很少（< 12）时
带子太宽反而看不出趋势，这时棒才是对的。

数据从哪来
----------
data 的键：
    x                横轴
    mean             均值序列
    std              标准差序列
    lower / upper    自定义上下界（可选）—— 给了就优先于 mean±std，
                     例如要画 95% 置信区间而不是 ±1 个标准差
    series           分组名（可选）—— 多组时画多条带

meta 里可能有：caption / x_label / y_label / width_in / show_bars
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

# 多组时的配色：饱和度接近的一组，叠在一起透明度不同也能分开。
PALETTE = ["#1f4e79", "#c0392b", "#2e7d32", "#8e44ad", "#e08a1e", "#0e7c86"]


def _clean(key: str, values: Any, n_expected: int) -> List[float]:
    """把输入转成 float 列表并校验长度。

    单独抽出来是因为 mean/std/lower/upper 四个序列的校验完全一样，
    复制四遍的话以后改错误消息一定会漏掉其中一处。
    """
    if values is None or len(values) == 0:
        raise ValueError(f"缺少必填输入 {key}：请提供对应的数值序列。")
    out = [float(v) for v in values]
    if len(out) != n_expected:
        raise ValueError(
            f"{key} 有 {len(out)} 个点，x 有 {n_expected} 个点，数量必须一致。"
        )
    return out


def render(data: Dict[str, Any], meta: Dict[str, Any] | None = None):
    meta = meta or {}

    x = [float(v) for v in (data.get("x") or [])]
    if not x:
        raise ValueError("缺少必填输入 x：请提供横轴取值序列。")

    mean = _clean("mean", data.get("mean"), len(x))

    # std 声明为必填。允许"没有 std 就不画带子"会让缺了方差的调用
    # 悄悄退化成普通折线图，看起来完全正常，但结论里的"±"就没有依据了。
    std = _clean("std", data.get("std"), len(x))

    lower_raw, upper_raw = data.get("lower"), data.get("upper")
    if (lower_raw is None) != (upper_raw is None):
        # 只给一边是没法画带的，也不能拿 std 去补另一边 —— 那是两种含义。
        raise ValueError(
            "lower 和 upper 必须同时提供：只给一个边界无法确定误差区间，"
            "请补齐另一个，或都不传改用 mean±std。"
        )
    if lower_raw is not None:
        lower = _clean("lower", lower_raw, len(x))
        upper = _clean("upper", upper_raw, len(x))
        # 上下界写反是最常见的调用错误，画出来是负高度的带子，
        # 在图上表现为一条反色的线，很容易被当成"数据正常"。
        bad = [i for i in range(len(x)) if lower[i] > upper[i]]
        if bad:
            raise ValueError(
                f"第 {bad[0]} 个点的 lower={mcmplot.fmt(lower[bad[0]])} "
                f"大于 upper={mcmplot.fmt(upper[bad[0]])}，上下界写反了。"
            )
        band_label = "自定义区间"
    else:
        lower = [m - s for m, s in zip(mean, std)]
        upper = [m + s for m, s in zip(mean, std)]
        band_label = "均值 ± 标准差"

    series = data.get("series")
    if series and len(series) != len(x):
        raise ValueError(
            f"series 有 {len(series)} 个，x 有 {len(x)} 个点，数量必须一致。"
        )

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.6), 3.9))

    groups: Dict[str, List[int]] = {}
    if series:
        # 组名顺序按首次出现，不排序 —— 用户给的顺序往往就是他想让读者
        # 看到的顺序。
        for i, name in enumerate(series):
            groups.setdefault(str(name), []).append(i)
    else:
        groups[""] = list(range(len(x)))

    show_bars = bool(meta.get("show_bars")) or len(x) < 12

    for k, (name, idx) in enumerate(groups.items()):
        color = PALETTE[k % len(PALETTE)]
        gx = [x[i] for i in idx]
        gm = [mean[i] for i in idx]
        glo = [lower[i] for i in idx]
        ghi = [upper[i] for i in idx]

        # 误差带先画、线后画：线压在带上，读者先看到趋势再看不确定性。
        ax.fill_between(gx, glo, ghi, color=color, alpha=0.18, linewidth=0)
        ax.plot(gx, gm, "-", lw=1.9, color=color)

        # 点很少时带子太宽会把趋势埋掉，这时补上误差棒把区间"钉"在采样点上。
        if show_bars:
            ax.errorbar(gx, gm, yerr=[[m - l for m, l in zip(gm, glo)],
                                      [u - m for m, u in zip(gm, ghi)]],
                        fmt="none", ecolor=color, elinewidth=1.0,
                        capsize=2.5, alpha=0.8)

        # 图例只出现一次：带子和线是同一条数据，做两个图例项会让人
        # 以为画了两条序列。
        plot_label = mcmplot.safe(name) if name else mcmplot.safe(
            meta.get("y_label", "均值")
        )
        ax.plot([], [], "-", lw=1.9, color=color, label=plot_label)

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "样本序号")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "均值")))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3)
    # 图例里带上"这是什么区间"，否则 ±std 还是 95%CI 只能靠正文解释。
    ax.legend(frameon=False, fontsize=8,
              title=mcmplot.safe(band_label) if len(groups) > 1 else None)
    if len(groups) == 1:
        ax.annotate(mcmplot.safe(band_label), xy=(0.99, 0.96),
                    xycoords="axes fraction", ha="right", va="top",
                    fontsize=8, color="#555555")
    fig.tight_layout()
    return fig
