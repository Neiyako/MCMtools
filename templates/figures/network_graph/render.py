"""fig.network_graph —— 节点-连线图，画网络与相互作用关系。

数据从哪来
----------
    nodes      节点名序列，如 ['A', 'B', 'C']
    edges      边，形如 [[源, 目标], ...] 或 [[源, 目标, 权重], ...]
    node_size  每个节点的相对大小（可选，如度中心性）

论文里常见的用法：物种关系网、传播路径、供应链、谁影响谁。

为什么不用 networkx
-------------------
只有几十个节点时，networkx 是多余依赖 —— 而且比赛环境里少一个依赖就少
一个装不上的风险。这里用纯 matplotlib 做环形布局，节点少时比力导向
更好读：位置固定，同一张图每次画出来一样（力导向有随机性，论文里
两张图对不上会很尴尬）。
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}
    nodes = list(data.get("nodes") or [])
    if not nodes:
        raise ValueError("nodes 不能为空：至少要给出一个节点。")

    edges = list(data.get("edges") or [])
    sizes = data.get("node_size")

    n = len(nodes)
    # 环形布局：角度均分，半径固定 —— 位置确定，可复现。
    pos = {
        name: (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n))
        for i, name in enumerate(nodes)
    }

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 5.2))

    # 先画边，节点压在边上，避免线头盖住圆点。
    for e in edges:
        if len(e) < 2:
            continue
        a, b = str(e[0]), str(e[1])
        if a not in pos or b not in pos:
            # 边指向不存在的节点：跳过这一条，但要让用户知道。
            ax.annotate("", xy=(0, 0))
            continue
        w = float(e[2]) if len(e) > 2 else 1.0
        ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]],
                "-", color="#9aa4b2", lw=0.8 + 1.2 * min(w, 4), zorder=1,
                alpha=0.75)

    # 节点大小：有 node_size 就按比例缩放到看得见的区间
    if sizes and len(sizes) == n:
        lo, hi = min(sizes), max(sizes)
        span = (hi - lo) or 1.0
        r = [180 + 620 * (s - lo) / span for s in sizes]
    else:
        r = [420] * n

    ax.scatter([pos[x][0] for x in nodes], [pos[x][1] for x in nodes],
               s=r, c="#1f4e79", zorder=2, edgecolors="white", linewidths=1.2)
    for name in nodes:
        ax.annotate(str(name), xy=pos[name], ha="center", va="center",
                    color="white", fontsize=8, zorder=3)

    ax.set_aspect("equal")
    ax.axis("off")
    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    fig.tight_layout()
    return fig
