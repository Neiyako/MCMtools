"""fig.roc_curve —— ROC 曲线，评价二分类器的判别能力。

为什么 ROC 而不是准确率
-----------------------
准确率依赖于阈值，而阈值是人选的。ROC 把**所有阈值**一起画出来：
横轴假正率、纵轴真正率，曲线越靠近左上角越好。
对角线是随机猜测的基准线 —— 没有这条线，读者无法判断
"曲线看起来挺高"到底是不是真的好。

AUC 写进图例
------------
AUC（曲线下面积）是这张图唯一值得引用的标量。如果只写模型名，
读者还得自己心算曲线下的面积。把 AUC 直接放进图例标签，
论文正文里引用的数字和图上的数字就是同一个来源，
不会出现"图看着还行、正文说 AUC=0.72"的脱节。

多模型怎么画
------------
`series` 给分组名（与 fpr/tpr 等长的平行数组），每个模型一条线、
一种颜色。长表（每个阈值一行，带模型名一列）是上层数据的自然形状，
所以这里按"平行数组"切段，而不是要求传 dict of list。

数据从哪来
----------
    fpr     必填，假正率（0~1），与 tpr 等长
    tpr     必填，真正率（0~1），与 fpr 等长
    series  可选，模型名；与 fpr 等长的平行数组。不给则当成单条曲线
    auc     可选，每个模型的 AUC。给的方式有两种：
              1) 与 series 的分组数量一致（每个模型一个数）
              2) 与 fpr 等长（每个点重复该模型的 AUC）
            两种都收，因为上游产物两种形状都见过。

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

# 多模型时按这个顺序取色。前几个用色相差别大的颜色，
# 黑白打印时靠线型（下面 _LINESTYLES）再区分一层。
_COLORS = ["#1f4e79", "#c0392b", "#2e7d32", "#8e44ad",
           "#e07b39", "#16a085", "#7f8c8d", "#c2185b"]
_LINESTYLES = ["-", "--", "-.", ":"]


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    fpr = _to_float_list(data.get("fpr"), "fpr")
    tpr = _to_float_list(data.get("tpr"), "tpr")

    if not fpr:
        raise ValueError(
            "缺少必填输入 fpr：请提供假正率序列（FPR，0~1，与 tpr 等长）。"
        )
    if not tpr:
        raise ValueError(
            "缺少必填输入 tpr：请提供真正率序列（TPR，0~1，与 fpr 等长）。"
        )
    if len(fpr) != len(tpr):
        raise ValueError(
            f"fpr 有 {len(fpr)} 个点，tpr 有 {len(tpr)} 个点，数量必须一致"
            "（每一对应对同一个阈值）。"
        )

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 5.6), 4.6))

    # 对角线是随机猜测的基准。没有它，曲线的高低就没有参照物。
    ax.plot([0, 1], [0, 1], ls="--", lw=1.2, color="#999999",
            label="随机猜测 (AUC = 0.5)", zorder=1)

    segments = _split_series(data.get("series"), fpr, tpr, data.get("auc"))
    multi = len(segments) > 1

    for idx, (name, seg_fpr, seg_tpr, seg_auc) in enumerate(segments):
        label = _legend_label(name, seg_auc, multi)
        ax.plot(seg_fpr, seg_tpr, _LINESTYLES[idx % len(_LINESTYLES)],
                lw=1.9 if multi else 2.1,
                color=_COLORS[idx % len(_COLORS)],
                label=label, zorder=3 if multi else 2)

    # 坐标轴钉死在 [0,1] 并留一点边：ROC 的定义域就是单位正方形，
    # 自动缩放会让"曲线贴着左上角"这个判断失去参照。
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "假正率 FPR")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "真正率 TPR")))

    # 线宽和颜色在灰度打印下会失效，图例必须放得下完整文字说明。
    ax.legend(frameon=False, fontsize=8,
              loc="lower right" if multi else "lower right")

    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))

    # 理想方向标在角上：审阅者一眼就知道该往哪边看。
    ax.annotate(mcmplot.safe("越靠近左上角越好"),
                xy=(0.04, 0.98), xycoords="axes fraction",
                ha="left", va="top", fontsize=7, color="#888888")

    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)
    fig.tight_layout()
    return fig


def _legend_label(name: str, auc: Optional[float], multi: bool) -> str:
    """图例文字。AUC 有就写进去 —— 那是读者真正要引用的数字。"""
    if auc is None:
        return mcmplot.safe(name) if name else "ROC"
    base = mcmplot.safe(name) if name else "ROC"
    return f"{base} (AUC = {mcmplot.fmt(auc)})"


def _split_series(
    series: Any, fpr: List[float], tpr: List[float], auc: Any
) -> "List[tuple]":
    """按 series 把 fpr/tpr 切成 (模型名, fpr段, tpr段, auc) 四元组列表。

    series 缺省时返回单段。分组顺序按首次出现 ——
    用户给的顺序往往就是他想让读者看到的顺序（通常是最好的模型放最前）。
    """
    aucs = _auc_values(auc)

    if series is None:
        single_auc = aucs[0] if aucs else None
        return [("", fpr, tpr, single_auc)]

    series = [str(s) for s in series]
    if len(series) != len(fpr):
        raise ValueError(
            f"series 有 {len(series)} 个，fpr 有 {len(fpr)} 个，数量必须一致"
            "（series[i] 说明 fpr[i]/tpr[i] 属于哪个模型）。"
        )

    order: List[str] = []
    buckets: Dict[str, List[int]] = {}
    for i, name in enumerate(series):
        if name not in buckets:
            buckets[name] = []
            order.append(name)
        buckets[name].append(i)

    # AUC 的两种给法：每模型一个，或与 fpr 等长（每个点重复）。
    per_segment = len(aucs) == len(order)
    per_point = len(aucs) == len(fpr)

    out = []
    for k, name in enumerate(order):
        idx = buckets[name]
        if not aucs:
            seg_auc = None
        elif per_segment:
            seg_auc = aucs[k]
        elif per_point:
            seg_auc = aucs[idx[0]]
        else:
            # 长度既不是模型数也不是点数：硬猜会把 A 模型的 AUC 标到 B 模型上。
            # 这种错误图上完全看不出来，但正文引用就是错的，必须拦住。
            raise ValueError(
                f"auc 有 {len(aucs)} 个，既不是模型数 {len(order)}，"
                f"也不是 fpr 的点数 {len(fpr)}：无法判断哪个 AUC 属于哪个模型，"
                "请按模型数提供，或提供与 fpr 等长的序列。"
            )
        out.append((name, [fpr[i] for i in idx], [tpr[i] for i in idx], seg_auc))
    return out


def _auc_values(auc: Any) -> List[float]:
    """把 auc 输入统一成 float 列表；标量也当成单元素列表。"""
    if auc is None:
        return []
    if isinstance(auc, (int, float)):
        return [float(auc)]
    return _to_float_list(auc, "auc")


def _to_float_list(raw: Any, name: str) -> List[float]:
    """转 float 列表，挡住不可转的脏数据。"""
    if raw is None:
        return []
    out: List[float] = []
    for v in raw:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            raise ValueError(
                f"{name} 里出现了非数值项 {v!r}：ROC 曲线只能接受数值序列。"
            )
    return out
