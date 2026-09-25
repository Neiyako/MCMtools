# -*- coding: utf-8 -*-
"""多目标优化与帕累托前沿 —— 代码骨架（可直接复制使用）

【解决什么问题】
  实际决策很少只有一个目标：成本要低、效果要好、风险要小。
  这些目标互相冲突，不存在唯一最优解，而是**一族权衡解**（帕累托前沿）。

  本骨架给两条路：
  * `nsga2_like()`  —— 手写非支配排序 + 拥挤度距离的遗传算法（无依赖）
  * `weighted_sum()` —— 加权和法扫描权重，快但抓不到凹前沿

  比赛里推荐先跑加权和快速看形状，再用遗传算法拿完整前沿。

【要改哪几行】
  1. `objectives()` —— 你的目标函数，返回要**最小化**的向量
  2. `BOUNDS`       —— 决策变量上下界
  3. `N_POP`, `N_GEN` —— 种群规模与迭代代数

【输入】目标函数 + 决策变量范围
【输出】帕累托前沿点集、转折点（膝点）、前沿图与决策空间图

【注意】下面的问题是模拟的（投资组合：收益 vs 风险），替换成你的目标。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Tuple

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
    """把输出文件名解析到 OUTDIR 下，并确保该目录存在。

    name 为 None 时用 default。函数签名里 out_png 默认是 None，
    走的就是这条路径，最终落到临时目录，不会污染模板库。
    """
    OUTDIR.mkdir(parents=True, exist_ok=True)
    return str(OUTDIR / (name or default))


def safe(text: object) -> str:
    return mcmplot.safe(text) if mcmplot is not None else str(text)


# ============================== 参数区（改这里）=============================
N_VARS = 5                       # 决策变量个数（如 5 类资产的投资比例）
BOUNDS = (0.0, 1.0)              # 每个变量的取值范围
N_POP = 120                      # 种群规模
N_GEN = 80                       # 迭代代数
MUT_RATE = 0.15                  # 变异概率

OBJ_NAMES = ["风险（要小）", "负收益（要小）"]
CN_VARS = ["资产A", "资产B", "资产C", "资产D", "资产E"]

# 模拟的资产收益与协方差（真实问题里用历史数据估）
RNG = np.random.default_rng(2026)
MU = np.array([0.08, 0.12, 0.05, 0.15, 0.09])
_A = RNG.normal(0, 0.05, (N_VARS, N_VARS))
COV = _A @ _A.T + np.diag([0.01, 0.04, 0.005, 0.06, 0.02])


# ============================== 1. 目标函数 ================================
def normalize_weights(x: np.ndarray) -> np.ndarray:
    """把决策变量归一化成"和为 1"的权重。

    投资比例必须满足 sum(w)=1，用归一化代替等式约束，
    比在遗传算法里加惩罚项简单也更稳。
    """
    x = np.clip(x, 0.0, None)
    s = x.sum()
    if s <= 0:
        return np.full(x.size, 1.0 / x.size)
    return x / s


def objectives(x: np.ndarray) -> np.ndarray:
    """两个目标（都要最小化）。

    目标1：组合风险 = w' Σ w
    目标2：负收益  = -w' μ   （收益要最大 => 负收益要最小）

    >>> 换成你的目标 <<<
    """
    w = normalize_weights(x)
    risk = float(w @ COV @ w)
    neg_return = -float(w @ MU)
    return np.array([risk, neg_return])


# ============================== 2. 非支配排序 ==============================
def dominates(a: np.ndarray, b: np.ndarray) -> bool:
    """a 是否支配 b：所有目标不劣于，且至少一个严格更优。"""
    return bool(np.all(a <= b) and np.any(a < b))


def fast_non_dominated_sort(F: np.ndarray) -> List[List[int]]:
    """快速非支配排序，返回各层（front）的索引列表。

    第 0 层就是帕累托前沿：没有任何个体能支配它们。
    """
    n = F.shape[0]
    dominates_list: List[List[int]] = [[] for _ in range(n)]
    dom_count = np.zeros(n, dtype=int)
    fronts: List[List[int]] = [[]]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if dominates(F[i], F[j]):
                dominates_list[i].append(j)
            elif dominates(F[j], F[i]):
                dom_count[i] += 1
        if dom_count[i] == 0:
            fronts[0].append(i)

    k = 0
    while fronts[k]:
        nxt: List[int] = []
        for i in fronts[k]:
            for j in dominates_list[i]:
                dom_count[j] -= 1
                if dom_count[j] == 0:
                    nxt.append(j)
        k += 1
        fronts.append(nxt)

    return [f for f in fronts if f]


def crowding_distance(F: np.ndarray, idx: List[int]) -> np.ndarray:
    """拥挤度距离：让前沿上的点分布均匀，避免全挤在一角。

    对每个目标排序，端点给无穷大（必须保留），中间点累加归一化间隔。
    """
    m = F.shape[1]
    dist = np.zeros(len(idx))
    if len(idx) <= 2:
        return np.full(len(idx), np.inf)

    for obj in range(m):
        vals = F[idx, obj]
        order = np.argsort(vals)
        dist[order[0]] = np.inf
        dist[order[-1]] = np.inf
        span = vals.max() - vals.min()
        if span <= 0:
            continue
        for t in range(1, len(idx) - 1):
            dist[order[t]] += (vals[order[t + 1]] - vals[order[t - 1]]) / span
    return dist


# ============================== 3. 遗传算法 ================================
def nsga2_like(obj: Callable[[np.ndarray], np.ndarray],
               bounds: Tuple[float, float],
               n_vars: int, n_pop: int, n_gen: int,
               mut_rate: float, seed: int = 1
               ) -> Tuple[np.ndarray, np.ndarray]:
    """简化版 NSGA-II：非支配排序 + 拥挤度 + 锦标赛选择。

    返回 (最终种群, 对应目标值)。
    """
    rng = np.random.default_rng(seed)
    lo, hi = bounds

    pop = rng.uniform(lo, hi, size=(n_pop, n_vars))
    F = np.array([obj(ind) for ind in pop])

    for gen in range(n_gen):
        # --- 锦标赛选择（先比支配层，再比拥挤度）---
        fronts = fast_non_dominated_sort(F)
        rank = np.zeros(n_pop, dtype=int)
        crowd = np.zeros(n_pop)
        for r, front in enumerate(fronts):
            for i in front:
                rank[i] = r
            cd = crowding_distance(F, front)
            for k, i in enumerate(front):
                crowd[i] = cd[k]

        def tournament() -> int:
            a, b = rng.integers(0, n_pop, 2)
            if rank[a] != rank[b]:
                return int(a if rank[a] < rank[b] else b)
            return int(a if crowd[a] > crowd[b] else b)

        # --- 模拟二进制交叉 SBX ---
        children = []
        while len(children) < n_pop:
            p1 = pop[tournament()].copy()
            p2 = pop[tournament()].copy()
            u = rng.random(n_vars)
            beta = np.where(u <= 0.5,
                            (2 * u) ** (1.0 / 6.0),
                            (1.0 / (2 * (1 - u))) ** (1.0 / 6.0))
            c1 = 0.5 * ((1 + beta) * p1 + (1 - beta) * p2)
            c2 = 0.5 * ((1 - beta) * p1 + (1 + beta) * p2)

            for c in (c1, c2):
                mask = rng.random(n_vars) < mut_rate
                # 多项式变异
                c[mask] += rng.normal(0, 0.1, mask.sum())
                children.append(np.clip(c, lo, hi))
                if len(children) >= n_pop:
                    break

        child_pop = np.array(children[:n_pop])
        child_F = np.array([obj(ind) for ind in child_pop])

        # --- 环境选择：父+子一起排序，取前 n_pop ---
        merged = np.vstack([pop, child_pop])
        merged_F = np.vstack([F, child_F])
        fronts = fast_non_dominated_sort(merged_F)

        new_idx: List[int] = []
        for front in fronts:
            if len(new_idx) + len(front) <= n_pop:
                new_idx.extend(front)
            else:
                cd = crowding_distance(merged_F, front)
                order = np.argsort(-cd)          # 拥挤度大的优先
                need = n_pop - len(new_idx)
                new_idx.extend([front[i] for i in order[:need]])
                break

        pop = merged[new_idx]
        F = merged_F[new_idx]

    return pop, F


# ============================== 4. 加权和法 ================================
def weighted_sum(obj: Callable[[np.ndarray], np.ndarray],
                 bounds: Tuple[float, float], n_vars: int,
                 n_weights: int = 40, seed: int = 3
                 ) -> Tuple[np.ndarray, np.ndarray]:
    """加权和法：把多目标压成一个标量，扫权重。

    优点：快、简单、每个权重出一个解。
    缺点：**抓不到非凸（凹陷）的前沿** —— 这是它最大的局限，
    论文里如果只用加权和，要说明这一点。
    """
    from itertools import product

    rng = np.random.default_rng(seed)
    lo, hi = bounds
    results = []

    # 两目标时的权重网格
    ws = np.linspace(0.0, 1.0, n_weights)
    for w1 in ws:
        w = np.array([w1, 1.0 - w1])

        def scalar(ind: np.ndarray) -> float:
            return float(w @ obj(ind))

        # 简单随机搜索 + 局部扰动（不想引入 scipy 依赖）
        best, best_val = None, np.inf
        for _ in range(600):
            cand = rng.uniform(lo, hi, n_vars)
            v = scalar(cand)
            if v < best_val:
                best, best_val = cand, v
        # 局部精化
        for _ in range(60):
            cand = np.clip(best + rng.normal(0, 0.05, n_vars), lo, hi)
            v = scalar(cand)
            if v < best_val:
                best, best_val = cand, v

        results.append(obj(best))

    return np.array(results)


# ============================== 5. 前沿分析 ================================
def extract_pareto(F: np.ndarray) -> np.ndarray:
    """从任意点集里筛出非支配子集。"""
    keep = []
    for i in range(F.shape[0]):
        if not any(dominates(F[j], F[i]) for j in range(F.shape[0]) if j != i):
            keep.append(i)
    return F[keep]


def knee_point(F: np.ndarray) -> int:
    """找膝点（转折点）：折中最优解。

    做法：把前沿归一化到 [0,1]，找离"理想点(0,0)"和
    "最差点(1,1)"连线**距离最大**的点 —— 那就是权衡曲线拐得最厉害的地方。
    这是向决策者推荐单一方案时最常用的依据。
    """
    if F.shape[0] == 0:
        return 0
    lo, hi = F.min(axis=0), F.max(axis=0)
    span = np.where(hi - lo > 0, hi - lo, 1.0)
    norm = (F - lo) / span

    a = np.array([0.0, 0.0])
    b = np.array([1.0, 1.0])
    ab = b - a
    dists = []
    for p in norm:
        ap = p - a
        # 点到直线 ab 的距离
        d = np.abs(ab[0] * ap[1] - ab[1] * ap[0]) / np.linalg.norm(ab)
        dists.append(d)
    return int(np.argmax(dists))


# ============================== 6. 画图 ====================================
def plot_pareto(F_ga: np.ndarray, F_ws: np.ndarray,
                out_png: Optional[str] = None) -> None:
    """帕累托前沿对比图：遗传算法 vs 加权和法。"""
    out_png = out_path(out_png, "pareto_frontier.png")
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

    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    ax.scatter(F_ga[:, 0], F_ga[:, 1], s=22, alpha=0.55, color="#4c72b0",
               label=safe("NSGA-II 非支配解"))
    if F_ws.size:
        ax.scatter(F_ws[:, 0], F_ws[:, 1], s=30, marker="s", alpha=0.75,
                   color="#27ae60", label=safe("加权和法解"))

    # 理想点与膝点
    ideal = F_ga.min(axis=0)
    ax.plot(ideal[0], ideal[1], "r*", ms=16, label=safe("理想点"))
    k = knee_point(F_ga)
    ax.plot(F_ga[k, 0], F_ga[k, 1], "o", ms=11, mfc="none", mec="#c0392b",
            mew=2.2, label=safe("膝点（推荐折中）"))

    # 前沿连线（按第一目标排序）
    order = np.argsort(F_ga[:, 0])
    ax.plot(F_ga[order, 0], F_ga[order, 1], "--", color="#4c72b0",
            alpha=0.6, lw=1.3)

    ax.set_xlabel(safe(OBJ_NAMES[0]))
    ax.set_ylabel(safe(OBJ_NAMES[1]))
    ax.set_title(safe("帕累托前沿：两目标权衡"))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_weights(pop: np.ndarray, F: np.ndarray,
                 out_png: Optional[str] = None) -> None:
    """前沿上若干代表解的决策变量构成（堆叠条形）。"""
    out_png = out_path(out_png, "pareto_weights.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    order = np.argsort(F[:, 0])
    picks = order[np.linspace(0, len(order) - 1, min(10, len(order))).astype(int)]
    W = np.array([normalize_weights(pop[i]) for i in picks])

    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    bottom = np.zeros(len(picks))
    colors = plt.cm.tab10(np.linspace(0, 1, W.shape[1]))
    for j in range(W.shape[1]):
        nm = CN_VARS[j] if j < len(CN_VARS) else f"变量{j}"
        ax.bar(range(len(picks)), W[:, j], bottom=bottom,
               color=colors[j], label=safe(nm))
        bottom += W[:, j]

    ax.set_xticks(range(len(picks)))
    ax.set_xticklabels([f"解{order[i]}" for i in picks], rotation=45, ha="right")
    ax.set_ylabel(safe("归一化权重"))
    ax.set_title(safe("前沿上不同折中方案的决策变量构成"))
    ax.legend(fontsize=8, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("多目标优化与帕累托前沿（投资组合模型，目标函数是模拟的）")
    print("=" * 66)

    print(f"\n[设置] 变量={N_VARS}  种群={N_POP}  代数={N_GEN}")
    print(f"[目标] {OBJ_NAMES}")

    # --- NSGA-II ---
    print("\n[运行] 简化版 NSGA-II ...")
    pop, F_all = nsga2_like(objectives, BOUNDS, N_VARS, N_POP, N_GEN, MUT_RATE)
    F_pareto = extract_pareto(F_all)

    print(f"  最终种群 {F_all.shape[0]} 个个体")
    print(f"  其中非支配解（帕累托前沿）{F_pareto.shape[0]} 个")

    # 前沿跨度
    print(f"\n[前沿范围]")
    print(f"  {OBJ_NAMES[0]}: [{F_pareto[:, 0].min():.5f}, "
          f"{F_pareto[:, 0].max():.5f}]")
    print(f"  {OBJ_NAMES[1]}: [{F_pareto[:, 1].min():.5f}, "
          f"{F_pareto[:, 1].max():.5f}]")

    # --- 膝点 ---
    k = knee_point(F_pareto)
    print(f"\n[膝点（推荐折中方案）]")
    print(f"  风险 = {F_pareto[k, 0]:.5f}")
    print(f"  负收益 = {F_pareto[k, 1]:.5f}")
    print(f"  即年化收益 = {-F_pareto[k, 1]:.4%}，"
          f"风险（方差）= {F_pareto[k, 0]:.5f}")

    # 膝点对应的权重
    idx_in_pop = np.argmin(np.linalg.norm(F_all - F_pareto[k], axis=1))
    w = normalize_weights(pop[idx_in_pop])
    print("  建议配置比例：")
    for j, wj in enumerate(w):
        nm = CN_VARS[j] if j < len(CN_VARS) else f"变量{j}"
        print(f"    {safe(nm):<8} {wj:6.2%}")

    # --- 加权和法对照 ---
    print("\n[对照] 加权和法扫描 ...")
    F_ws = weighted_sum(objectives, BOUNDS, N_VARS, n_weights=35)
    F_ws_pareto = extract_pareto(F_ws)
    print(f"  得到 {F_ws_pareto.shape[0]} 个非支配解")

    # 用超体积的粗代理比较两种方法的覆盖能力
    def spread(Fx: np.ndarray) -> float:
        if Fx.shape[0] < 2:
            return 0.0
        rng_ = Fx.max(axis=0) - Fx.min(axis=0)
        return float(np.prod(np.where(rng_ > 0, rng_, 1.0)))

    print(f"  前沿覆盖面积（粗略）：NSGA-II={spread(F_pareto):.3e}  "
          f"加权和={spread(F_ws_pareto):.3e}")

    print("\n[结论]")
    print("  帕累托前沿给出了风险与收益的全部最优折中，"
          "决策者可按偏好在前沿上选点；")
    print("  加权和法在非凸前沿上会漏解，所以主结果以 NSGA-II 为准。")

    plot_pareto(F_pareto, F_ws_pareto)
    plot_weights(pop, F_all)
    return 0


if __name__ == "__main__":
    sys.exit(main())
