# -*- coding: utf-8 -*-
"""图论最短路与网络分析 —— 代码骨架（可直接复制使用）

【解决什么问题】
  把对象和关系抽象成图（节点 + 边），然后回答：
  * 两点之间最省的路怎么走（Dijkstra）
  * 全网任意两点距离、网络中心性
  * 最小生成树（用最少的边连通所有节点，如铺管网、建基站）

  本骨架全部用 numpy 手写，不依赖 networkx，比赛环境可直接跑。
  如果装了 networkx，`networkx_crosscheck()` 会做交叉验证。

【要改哪几行】
  1. `build_graph()` —— 换成你的节点与边（含权重）
  2. `SOURCE`, `TARGET` —— 起终点
  3. `DIRECTED` —— True 有向图 / False 无向图

【输入】节点列表 + 带权边列表
【输出】最短路路径与长度、全源距离矩阵、中心性排名、网络图

【注意】下面的网络是模拟的，替换成你的数据。
"""

from __future__ import annotations

import heapq
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


# --------------------------------------------------------------------------
# mcmplot 引导
# --------------------------------------------------------------------------
def _bootstrap_mcmplot() -> bool:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        cand = parent / "core"
        if (cand / "mcmcore" / "mcmplot.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            return True
    return False


HAS_MCMPLOT = _bootstrap_mcmplot()
try:
    import mcmcore.mcmplot as mcmplot
except ImportError:
    mcmplot = None


# --------------------------------------------------------------------------
# 输出目录：默认写到系统临时目录，**不污染模板库**。
# 想把图留下来，就设环境变量 MCM_CODE_OUT 指向你自己的目录：
#     MCM_CODE_OUT=./my_out python3 snippet.py
# --------------------------------------------------------------------------
OUTDIR = Path(os.environ.get("MCM_CODE_OUT", tempfile.mkdtemp(prefix="mcm_code_")))


def out_path(name: Optional[str] = None, default: str = "output.png") -> str:
    """把输出文件名解析到 OUTDIR 下，并确保该目录存在。"""
    OUTDIR.mkdir(parents=True, exist_ok=True)
    return str(OUTDIR / (name or default))


def safe(text: object) -> str:
    return mcmplot.safe(text) if mcmplot is not None else str(text)


# ============================== 参数区（改这里）=============================
NODES = ["A", "B", "C", "D", "E", "F", "G", "H"]

# 边：(起点, 终点, 权重=距离/时间/成本)
EDGES: List[Tuple[str, str, float]] = [
    ("A", "B", 4.0), ("A", "C", 2.0),
    ("B", "C", 5.0), ("B", "D", 10.0),
    ("C", "E", 3.0), ("E", "D", 4.0),
    ("D", "F", 11.0), ("E", "F", 5.0),
    ("F", "G", 3.0), ("E", "G", 9.0),
    ("G", "H", 6.0), ("D", "H", 14.0),
]

SOURCE = "A"
TARGET = "H"
DIRECTED = False         # False = 无向图（边两个方向都能走）


# ============================== 1. 建图 ====================================
def build_graph(nodes: List[str], edges: List[Tuple[str, str, float]],
                directed: bool
                ) -> Tuple[Dict[str, List[Tuple[str, float]]], np.ndarray]:
    """建邻接表 + 邻接矩阵。

    为什么两个都要：Dijkstra 用邻接表快（只遍历真实存在的边），
    算全源最短路（Floyd）用矩阵方便。
    """
    idx = {n: i for i, n in enumerate(nodes)}
    k = len(nodes)

    adj: Dict[str, List[Tuple[str, float]]] = {n: [] for n in nodes}
    INF = np.inf
    W = np.full((k, k), INF)
    np.fill_diagonal(W, 0.0)

    for u, v, w in edges:
        if u not in idx or v not in idx:
            print(f"  [警告] 边 ({u},{v}) 含未知节点，已跳过")
            continue
        adj[u].append((v, float(w)))
        W[idx[u], idx[v]] = min(W[idx[u], idx[v]], float(w))
        if not directed:
            adj[v].append((u, float(w)))
            W[idx[v], idx[u]] = min(W[idx[v], idx[u]], float(w))

    return adj, W


# ============================== 2. Dijkstra ================================
def dijkstra(adj: Dict[str, List[Tuple[str, float]]],
             source: str
             ) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
    """堆优化 Dijkstra，返回 (到各点的最短距离, 前驱表用于回溯路径)。

    贪心策略：每次从未确定的点里取距离最小的，松弛它的邻居。
    用优先队列后复杂度 O(E log V)。
    要求边权**非负** —— 有负权要用 Bellman-Ford。

    为什么不用 Floyd 求单源：Floyd 是 O(V³)，点数一大就慢。
    """
    dist: Dict[str, float] = {n: np.inf for n in adj}
    prev: Dict[str, Optional[str]] = {n: None for n in adj}
    dist[source] = 0.0

    pq: List[Tuple[float, str]] = [(0.0, source)]
    settled = set()

    while pq:
        d, u = heapq.heappop(pq)
        if u in settled:
            continue                     # 过期条目，跳过
        settled.add(u)

        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    return dist, prev


def reconstruct_path(prev: Dict[str, Optional[str]],
                     source: str, target: str) -> List[str]:
    """从前往表回溯路径。"""
    if source == target:
        return [source]
    path = []
    cur: Optional[str] = target
    seen = set()
    while cur is not None:
        if cur in seen:                  # 防御：理论上不该出现环
            return []
        seen.add(cur)
        path.append(cur)
        if cur == source:
            break
        cur = prev.get(cur)
    else:
        return []
    if path[-1] != source:
        return []
    return list(reversed(path))


# ============================== 3. Floyd ===================================
def floyd_warshall(W: np.ndarray) -> np.ndarray:
    """全源最短路（动态规划）。

    思想：允许经过前 k 个点作为中转，逐步放宽。
    对稠密图或需要所有点对距离时用它。
    复杂度 O(V³)，点数超过 ~500 就要考虑换方法。
    """
    D = W.astype(float).copy()
    n = D.shape[0]
    for k in range(n):
        # 向量化松弛：D[i,j] = min(D[i,j], D[i,k] + D[k,j])
        D = np.minimum(D, D[:, k][:, None] + D[k, :][None, :])
    return D


# ============================== 4. 最小生成树 ==============================
def mst_kruskal(nodes: List[str],
                edges: List[Tuple[str, str, float]]) -> List[Tuple[str, str, float]]:
    """Kruskal 最小生成树：按边权从小到大加，不成环就保留。

    用并查集判断环。典型应用：铺最省的光纤/管道把所有城市连起来。
    """
    parent = {n: n for n in nodes}

    def find(x: str) -> str:
        # 路径压缩
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a: str, b: str) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[ra] = rb
        return True

    chosen = []
    for u, v, w in sorted(edges, key=lambda e: e[2]):
        if union(u, v):
            chosen.append((u, v, w))
        if len(chosen) == len(nodes) - 1:
            break
    return chosen


# ============================== 5. 中心性 ==================================
def centrality(adj: Dict[str, List[Tuple[str, float]]]) -> List[Dict[str, object]]:
    """算几种常用中心性，识别网络里的关键节点。

    * 度中心性：连接数最多 = 最"活跃"
    * 接近中心性：到其他所有点的平均距离最短 = 信息传得最快
    * 介数中心性：多少条最短路经过它 = 最"卡脖子"（删掉它会瘫痪网络）
    """
    nodes = list(adj.keys())
    n = len(nodes)
    deg = {u: len(adj[u]) for u in nodes}

    # 接近中心性
    closeness = {}
    for u in nodes:
        dist, _ = dijkstra(adj, u)
        finite = [d for v, d in dist.items() if v != u and np.isfinite(d)]
        closeness[u] = (len(finite) / sum(finite)) if finite and sum(finite) > 0 else 0.0

    # 介数中心性（Brandes 简化实现）
    between = {u: 0.0 for u in nodes}
    for s in nodes:
        # 单源最短路计数
        dist, prev = dijkstra(adj, s)
        order = sorted([v for v in nodes if np.isfinite(dist[v])],
                       key=lambda v: -dist[v])
        sigma = {v: 0.0 for v in nodes}
        sigma[s] = 1.0
        for v in sorted([x for x in nodes if np.isfinite(dist[x])],
                        key=lambda x: dist[x]):
            for w, _ in adj[v]:
                if np.isfinite(dist[w]) and abs(dist[w] - (dist[v] + _)) < 1e-12:
                    sigma[w] += sigma[v]

        delta = {v: 0.0 for v in nodes}
        for w in order:
            for v, _ in adj[w]:
                if np.isfinite(dist[w]) and abs(dist[w] - (dist[v] + _)) < 1e-12:
                    if sigma[w] > 0:
                        delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                between[w] += delta[w]

    if not DIRECTED:
        # 无向图每条最短路被算了两遍
        between = {k: v / 2.0 for k, v in between.items()}

    rows = []
    for u in nodes:
        rows.append({
            "节点": u,
            "度": deg[u],
            "度中心性": deg[u] / (n - 1) if n > 1 else 0.0,
            "接近中心性": closeness[u],
            "介数中心性": between[u],
        })

    try:
        import pandas as pd
        return pd.DataFrame(rows).sort_values("介数中心性", ascending=False) \
            .reset_index(drop=True)
    except ImportError:
        rows.sort(key=lambda r: -float(r["介数中心性"]))
        return rows


# ============================== 6. 画图 ====================================
def plot_network(nodes: List[str], edges: List[Tuple[str, str, float]],
                 path: Optional[List[str]] = None,
                 out_png: Optional[str] = None) -> None:
    """画网络图，高亮最短路。用环形布局，避免依赖 networkx。"""
    out_png = out_path(out_png, "graph_network.png")
    if mcmplot is None:
        print("\n[跳过画图] 没找到 mcmplot 模块")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    # 环形布局
    n = len(nodes)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pos = {u: (np.cos(a), np.sin(a)) for u, a in zip(nodes, ang)}

    fig, ax = plt.subplots(figsize=(6.8, 6.4))

    # 先画所有边（灰色细线），加上权重标签
    for u, v, w in edges:
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        ax.plot([x1, x2], [y1, y2], color="#b0b0b0", lw=1.1, zorder=1)
        ax.text((x1 + x2) / 2, (y1 + y2) / 2, f"{w:g}",
                fontsize=7, color="#555555", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none",
                          alpha=0.75))

    # 高亮最短路
    if path and len(path) > 1:
        for a, b in zip(path[:-1], path[1:]):
            x1, y1 = pos[a]
            x2, y2 = pos[b]
            ax.plot([x1, x2], [y1, y2], color="#c0392b", lw=3.0,
                    zorder=2, alpha=0.9)

    # 画节点
    for u in nodes:
        x, y = pos[u]
        on_path = bool(path) and u in path
        ax.scatter([x], [y], s=520 if on_path else 380,
                   color="#c0392b" if on_path else "#4c72b0",
                   zorder=3, edgecolors="white", linewidths=1.6)
        ax.text(x, y, u, fontsize=11, color="white", ha="center",
                va="center", zorder=4, fontweight="bold")

    ax.set_title(safe("网络结构与最短路径（红色为最短路）"))
    ax.axis("equal")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_distance_matrix(nodes: List[str], D: np.ndarray,
                         out_png: Optional[str] = None) -> None:
    """全源最短路距离矩阵热力图。"""
    out_png = out_path(out_png, "graph_distance_matrix.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    Dshow = np.where(np.isfinite(D), D, np.nan)
    fig, ax = plt.subplots(figsize=(6.6, 5.6))
    im = ax.imshow(Dshow, cmap="YlOrRd")
    ax.set_xticks(range(len(nodes)))
    ax.set_yticks(range(len(nodes)))
    ax.set_xticklabels([safe(n) for n in nodes])
    ax.set_yticklabels([safe(n) for n in nodes])
    for i in range(len(nodes)):
        for j in range(len(nodes)):
            v = Dshow[i, j]
            txt = "inf" if np.isnan(v) else f"{v:.0f}"
            ax.text(j, i, txt, ha="center", va="center", fontsize=8,
                    color="black")
    ax.set_title(safe("全源最短距离矩阵"))
    fig.colorbar(im, ax=ax, shrink=0.85, label=safe("最短距离"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("图论最短路与网络分析（网络是模拟的，替换成你的数据）")
    print("=" * 66)

    adj, W = build_graph(NODES, EDGES, DIRECTED)
    n_edges = len(EDGES) * (1 if DIRECTED else 2)
    print(f"\n[图] 节点 {len(NODES)} 个，边 {len(EDGES)} 条"
          f"（{'有向' if DIRECTED else '无向'}，邻接表条目 {n_edges}）")
    print(f"[度分布] " + "  ".join(f"{u}:{len(adj[u])}" for u in NODES))

    # --- 连通性检查 ---
    reach = dijkstra(adj, NODES[0])[0]
    unreachable = [u for u, d in reach.items() if not np.isfinite(d)]
    if unreachable:
        print(f"[警告] 以下节点从 {NODES[0]} 不可达：{unreachable}")
    else:
        print(f"[连通性] 全图连通，从 {NODES[0]} 可达所有节点。")

    # --- Dijkstra 单源最短路 ---
    dist, prev = dijkstra(adj, SOURCE)
    print(f"\n[Dijkstra] 源点 = {SOURCE}")
    print(f"  {'节点':<6}{'最短距离':>12}")
    for u in NODES:
        d = dist[u]
        print(f"  {u:<6}{('inf' if not np.isfinite(d) else f'{d:.2f}'):>12}")

    path = reconstruct_path(prev, SOURCE, TARGET)
    if path:
        print(f"\n[最短路径] {SOURCE} -> {TARGET}")
        print(f"  路径：{' -> '.join(path)}")
        print(f"  总长度：{dist[TARGET]:.2f}")
        # 逐段展示
        for a, b in zip(path[:-1], path[1:]):
            w = next(wt for v, wt in adj[a] if v == b)
            print(f"    {a} -> {b} : {w:g}")
    else:
        print(f"\n[最短路径] {SOURCE} 无法到达 {TARGET}")

    # --- Floyd 全源最短路 ---
    D = floyd_warshall(W)
    print(f"\n[Floyd 全源最短路矩阵]")
    print("      " + "".join(f"{u:>8}" for u in NODES))
    for i, u in enumerate(NODES):
        row = "".join(
            f"{('inf' if not np.isfinite(D[i, j]) else f'{D[i, j]:.0f}'):>8}"
            for j in range(len(NODES)))
        print(f"  {u:<4}{row}")

    # 验证两种算法一致
    if path:
        floyd_val = D[NODES.index(SOURCE), NODES.index(TARGET)]
        agree = np.isclose(floyd_val, dist[TARGET])
        print(f"\n[交叉验证] Dijkstra={dist[TARGET]:.4f}  "
              f"Floyd={floyd_val:.4f}  -> "
              f"{'一致' if agree else '不一致，请检查'}")
    else:
        print("\n[交叉验证] 无路径，跳过对照")

    # 网络直径
    finite = D[np.isfinite(D)]
    if finite.size:
        print(f"\n[网络指标] 直径（最远两点距离）= {finite.max():.2f}")
        print(f"           平均最短路径 = {finite[finite > 0].mean():.4f}")

    # --- 最小生成树 ---
    mst = mst_kruskal(NODES, EDGES)
    mst_cost = sum(w for _, _, w in mst)
    print(f"\n[最小生成树] {len(mst)} 条边，总成本 = {mst_cost:.2f}")
    for u, v, w in mst:
        print(f"    {u} - {v} : {w:g}")

    # --- 中心性 ---
    print(f"\n[节点中心性]")
    cen = centrality(adj)
    try:
        print(cen.to_string(index=False))
        key_node = cen.iloc[0]["节点"]
        print(f"\n  [解读] 介数中心性最高的是 {key_node}，"
              f"它是网络的关键枢纽，一旦中断影响最大。")
    except AttributeError:
        for r in cen:
            print(r)

    plot_network(NODES, EDGES, path)
    plot_distance_matrix(NODES, D)
    return 0


if __name__ == "__main__":
    sys.exit(main())
