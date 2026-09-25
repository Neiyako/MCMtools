"""fig.model_metric_radar —— 多模型多指标的归一化雷达对比。

和 fig.radar_compare 的分工
--------------------------
radar_compare 比的是**方案**（同一套权重下的候选），model_metric_radar
比的是**模型**，而模型评估里有一类特有的坑：指标方向不一致。
准确率、F1 越大越好，RMSE、MAE、耗时越小越好。如果照原值直接画，
RMSE 小的那个好模型会在图上缩成一个小三角形，读者会得出"它最差"的
相反结论。所以这里必须能声明哪些指标是**越小越好**，声明后
该维按 1 - 归一化 翻转，让所有维度都变成"越大越好"再叠放。

归一化的代价（诚实说明）
------------------------
min-max 归一化会放大本就接近的指标。如果某个指标上所有模型几乎一样，
归一化后会被拉成 0 和 1 的巨大差异。评审若追问，应回到原始指标表。
这是雷达图的固有缺陷，不是本实现的 bug —— 页面上会标出每个顶点的
原始数值，方便对照。

数据从哪来
----------
data 的键：
    metrics          指标名列表（至少 3 个，否则不成形状）
    models           模型名列表，个数 = scores 的行数
    scores           二维数组，第 i 行是模型 i 在各指标上的原始值
    lower_is_better  与 metrics 等长的真/假标记（可选），为真的指标越小越好

meta 里可能有：caption / width_in / max_models
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

# 超过这个数量的模型，形状会叠成一团墨。
_MAX_MODELS = 6

_PALETTE = ["#1f4e79", "#c0504d", "#9bbb59", "#8064a2",
            "#4bacc6", "#f79646"]


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    metrics = data.get("metrics")
    if not metrics:
        raise ValueError(
            "缺少必填输入 metrics：请提供指标名列表，至少 3 个，"
            "例如 ['准确率','召回率','F1','推理耗时']。"
        )
    metrics = [mcmplot.safe(str(m)) for m in metrics]
    n_dim = len(metrics)
    if n_dim < 3:
        raise ValueError(
            f"metrics 只有 {n_dim} 个：雷达图至少需要 3 个指标才能围成形状，"
            "两个指标请改用 fig.dumbbell 或 fig.bar_comparison。"
        )

    models = data.get("models")
    if not models:
        raise ValueError(
            "缺少必填输入 models：请提供模型名列表，个数要等于 scores 的行数。"
        )
    models = [mcmplot.safe(str(m)) for m in models]

    scores = data.get("scores")
    if scores is None:
        raise ValueError(
            "缺少必填输入 scores：请提供二维数组，第 i 行是模型 i 在各指标上的"
            f"原始值，行数等于 models（{len(models)}），列数等于 metrics（{n_dim}）。"
        )
    try:
        arr = np.asarray(scores, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(
            "scores 不是数值二维数组：请检查是否有某一行长度不一致或混入了文字。"
        )
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.size == 0:
        raise ValueError(f"scores 必须是二维数组且非空，当前形状 {arr.shape}。")
    if not np.all(np.isfinite(arr)):
        raise ValueError(
            "scores 里有空值：每个模型在每个指标上都必须有一个数值，"
            "没测的指标请补测或从 metrics 里去掉。"
        )

    if arr.shape[0] != len(models):
        raise ValueError(
            f"scores 有 {arr.shape[0]} 行，models 有 {len(models)} 个："
            "每个模型一行得分，数量必须一致。"
        )
    if arr.shape[1] != n_dim:
        raise ValueError(
            f"scores 每行有 {arr.shape[1]} 个值，metrics 有 {n_dim} 个："
            "每个模型都要给出所有指标的得分。"
        )
    if len(models) > _MAX_MODELS:
        raise ValueError(
            f"模型有 {len(models)} 个，超过 {_MAX_MODELS} 个时形状会叠成一团。"
            "请分批对比，或改用表格列出全部指标。"
        )

    # 指标方向：越小越好的指标要翻转，否则好模型会画成小三角形。
    flags = [False] * n_dim
    if data.get("lower_is_better") is not None:
        raw = list(data["lower_is_better"])
        if len(raw) != n_dim:
            raise ValueError(
                f"lower_is_better 有 {len(raw)} 项，metrics 有 {n_dim} 个："
                "每个指标都要标明是越大越好还是越小越好。"
            )
        flags = [bool(v) for v in raw]

    # min-max 归一化到 [0, 1]。极值取**该维在所有模型上的极值**，
    # 这样径向刻度在全图统一，不同模型可以直接比大小。
    norm = np.zeros_like(arr)
    for j in range(n_dim):
        col = arr[:, j]
        lo, hi = float(col.min()), float(col.max())
        if hi == lo:
            # 所有模型在这一维完全相同：归一化没有信息可给，
            # 统一给 0.5 而不是 0 或 1 —— 后者会凭空制造出差异。
            norm[:, j] = 0.5
        else:
            norm[:, j] = (col - lo) / (hi - lo)
        if flags[j]:
            norm[:, j] = 1.0 - norm[:, j]

    angles = np.linspace(0, 2 * np.pi, n_dim, endpoint=False).tolist()
    angles_closed = angles + angles[:1]

    width = float(meta.get("width_in", 6.2))
    fig, ax = plt.subplots(figsize=(width, width * 0.86),
                           subplot_kw={"projection": "polar"})
    # 从 12 点方向顺时针排，"第一个指标在最上面"符合读雷达图的习惯。
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    # 攒下所有数值标注，最后统一避让
    _value_anns = []
    for i in range(len(models)):
        vals = norm[i].tolist()
        closed = vals + vals[:1]
        color = _PALETTE[i % len(_PALETTE)]
        ax.plot(angles_closed, closed, "-", lw=1.8, color=color,
                label=models[i])
        ax.fill(angles_closed, closed, color=color, alpha=0.13)

        # 顶点旁标原始值：形状可以骗人，数字不会。
        # 先按默认位置放下，等整张图画完再统一做避让（见下方 _spread_labels）。
        for j in range(n_dim):
            ann = ax.annotate(mcmplot.fmt(arr[i, j]),
                              xy=(angles[j], vals[j]), xytext=(4, 4),
                              textcoords="offset points", fontsize=6.5,
                              color=color)
            _value_anns.append(ann)

    # 指标名带方向提示：读图的人必须知道哪一维是"越小越好"。
    tick_labels = [m + ("（越小越好）" if flags[j] else "")
                   for j, m in enumerate(metrics)]
    ax.set_xticks(angles)
    ax.set_xticklabels(tick_labels, fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=7)
    ax.tick_params(pad=2)

    ax.legend(frameon=False, fontsize=8, loc="upper right",
              bbox_to_anchor=(1.22, 1.12))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")),
                     fontsize=10, pad=16)
    fig.tight_layout()
    mcmplot.spread_labels(fig, _value_anns)
    return fig
