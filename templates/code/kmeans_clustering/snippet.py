# -*- coding: utf-8 -*-
"""聚类分析 K-means（含肘部法选 K、轮廓系数）—— 代码骨架

【解决什么问题】
  没有标签的数据怎么分组？K-means 是最常用的答案。
  但它有一个致命前提：**K 必须你自己定**。本骨架把"选 K"也做掉：

  * 肘部法（Elbow）：看组内平方和 SSE 随 K 的下降拐点
  * 轮廓系数（Silhouette）：衡量"组内紧密、组间分离"的程度，越高越好
  * Gap 思想简版：与随机数据的 SSE 对照

【要改哪几行】
  1. `build_data()`  —— 换成你的数据
  2. `K_RANGE`       —— 候选 K 的范围
  3. `FEATURES`      —— 参与聚类的特征列
  4. `STANDARDIZE`   —— 是否标准化（量纲差很多时必须 True）

【输入】数值矩阵（样本 × 特征）
【输出】各 K 的评估指标、最优 K 的聚类结果、聚类图

【注意】下面的数据是模拟的，替换成你的数据。
"""

from __future__ import annotations

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
FEATURES = ["annual_spend", "visit_freq", "avg_order"]
CN_NAMES = {
    "annual_spend": "年消费额",
    "visit_freq": "到访频次",
    "avg_order": "客单价",
}
K_RANGE = range(2, 9)      # 候选 K
STANDARDIZE = True         # 量纲差异大时必须标准化
SEED = 2024
N_INIT = 12                # K-means 重启次数（取 SSE 最小的那次）


# ============================== 1. 数据 ====================================
def build_data() -> np.ndarray:
    """构造三簇的模拟客户数据。

    >>> 换成你的数据 <<<
        df = pd.read_csv("your_data.csv")
        X = df[FEATURES].values.astype(float)
    """
    rng = np.random.default_rng(SEED)
    c1 = rng.normal([3000, 4, 120], [600, 1.0, 25], (80, 3))
    c2 = rng.normal([12000, 12, 350], [2000, 3.0, 60], (70, 3))
    c3 = rng.normal([6000, 20, 90], [1200, 4.0, 20], (60, 3))
    return np.vstack([c1, c2, c3])


def standardize_data(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Z-score 标准化。

    为什么必须做：年消费额是几千、到访频次是个位数，
    直接算欧氏距离的话，消费额会完全主导距离，其他特征等于不存在。
    """
    mu = X.mean(axis=0)
    sd = X.std(axis=0, ddof=0)
    sd = np.where(sd < 1e-12, 1.0, sd)
    return (X - mu) / sd, mu, sd


# ============================== 2. K-means =================================
def kmeans(X: np.ndarray, k: int, n_init: int = 10,
           max_iter: int = 300,
           seed: int = 0) -> Tuple[np.ndarray, np.ndarray, float]:
    """K-means（Lloyd 算法）。

    返回 (簇中心, 每个样本的标签, 组内平方和 SSE)。

    为什么要 n_init 次重启：K-means 对初始中心敏感，
    随机初始化可能收敛到很差的局部最优。
    跑多次取 SSE 最小的那一次是标准做法。
    """
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    best_labels = None
    best_centers = None
    best_sse = np.inf

    for _ in range(n_init):
        # k-means++ 初始化：第一个随机，后续按距离平方概率选，分散得多
        idx = [int(rng.integers(n))]
        for _ in range(1, k):
            d2 = np.min(
                np.linalg.norm(X[:, None, :] - X[idx][None, :, :], axis=2) ** 2,
                axis=1)
            total = d2.sum()
            probs = d2 / total if total > 0 else np.full(n, 1.0 / n)
            idx.append(int(rng.choice(n, p=probs)))
        centers = X[idx].copy()

        labels = np.zeros(n, dtype=int)
        for _ in range(max_iter):
            # --- 分配步：每个样本归到最近的簇 ---
            dists = np.linalg.norm(X[:, None, :] - centers[None, :, :], axis=2)
            new_labels = np.argmin(dists, axis=1)

            # --- 更新步：簇中心取均值 ---
            new_centers = centers.copy()
            for j in range(k):
                members = X[new_labels == j]
                if members.size > 0:
                    new_centers[j] = members.mean(axis=0)

            if np.array_equal(new_labels, labels) and \
                    np.allclose(new_centers, centers):
                labels = new_labels
                centers = new_centers
                break
            labels, centers = new_labels, new_centers

        sse = float(((X - centers[labels]) ** 2).sum())
        if sse < best_sse:
            best_sse, best_labels, best_centers = sse, labels, centers

    return best_centers, best_labels, best_sse  # type: ignore[return-value]


def elbow_curve(X: np.ndarray, k_range) -> Dict[int, float]:
    """肘部法：算每个 K 的 SSE。

    SSE 一定随 K 增大而减小（K=N 时 SSE=0），
    所以要找的是"下降速度突然变缓"的拐点，而不是最小的 SSE。
    """
    out = {}
    for k in k_range:
        if k >= X.shape[0]:
            continue
        _, _, sse = kmeans(X, k, n_init=N_INIT, seed=SEED)
        out[k] = sse
    return out


def silhouette_score(X: np.ndarray, labels: np.ndarray,
                     sample_size: int = 600,
                     seed: int = 1) -> float:
    """轮廓系数（-1 到 1，越大越好）。

    对每个样本 i：
      a_i = 它到同簇其他点的平均距离（越小说明簇内越紧）
      b_i = 它到最近的其他簇的平均距离（越大说明簇间越开）
      s_i = (b_i - a_i) / max(a_i, b_i)

    样本多时随机抽样，避免 O(n²) 爆炸。
    """
    n = X.shape[0]
    k = len(np.unique(labels))
    if k < 2 or n < 3:
        return -1.0

    rng = np.random.default_rng(seed)
    idx = (rng.choice(n, sample_size, replace=False)
           if n > sample_size else np.arange(n))

    # 一次性算好两两距离矩阵（抽样后规模可控）
    sub = X[idx]
    D = np.linalg.norm(sub[:, None, :] - X[None, :, :], axis=2)
    sub_labels = labels[idx]

    scores = []
    for i in range(len(idx)):
        same = labels == sub_labels[i]
        same[i] = False
        if not same.any():
            continue
        a_i = D[i, same].mean()

        b_i = np.inf
        for j in np.unique(labels):
            if j == sub_labels[i]:
                continue
            other = labels == j
            if other.any():
                b_i = min(b_i, D[i, other].mean())
        if not np.isfinite(b_i):
            continue

        denom = max(a_i, b_i)
        if denom > 0:
            scores.append((b_i - a_i) / denom)

    return float(np.mean(scores)) if scores else -1.0


def suggest_k(elbow: Dict[int, float],
              silhouettes: Dict[int, float]) -> int:
    """综合肘部法和轮廓系数推荐 K。

    两个指标常常不一致：肘部法偏保守，轮廓系数偏爱分离好的。
    这里以轮廓系数为主、肘部法为辅，并把选择理由打印出来。
    """
    if not silhouettes:
        return min(elbow) if elbow else 2

    best_sil = max(silhouettes, key=lambda k: silhouettes[k])

    # 肘部法：找 SSE 降幅明显变缓的那个 K
    ks = sorted(elbow)
    elbow_k = ks[0]
    if len(ks) >= 3:
        drops = [elbow[ks[i]] - elbow[ks[i + 1]] for i in range(len(ks) - 1)]
        for i in range(1, len(drops)):
            if drops[i] < 0.35 * drops[0]:
                elbow_k = ks[i]
                break

    print(f"\n  [肘部法] 建议 K = {elbow_k}")
    print(f"  [轮廓系数] 建议 K = {best_sil}"
          f"（轮廓系数 {silhouettes[best_sil]:.4f}）")

    # 若一致直接采用；不一致时优先轮廓系数（它是直接的聚类质量度量）
    if best_sil == elbow_k:
        print("  两个准则一致，采用该 K。")
        return best_sil

    print("  两个准则不一致：肘部法看「边际收益」，轮廓系数看「分离质量」。")
    print("  比赛里建议取轮廓系数最优的 K，并在论文中说明理由。")
    return best_sil


# ============================== 3. 画图 ====================================
def plot_selection(elbow: Dict[int, float],
                   silhouettes: Dict[int, float],
                   chosen: int,
                   out_png: Optional[str] = None) -> None:
    """肘部图 + 轮廓系数图，双轴并排。"""
    out_png = out_path(out_png, "kmeans_selection.png")
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

    ks = sorted(elbow)
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))

    axes[0].plot(ks, [elbow[k] for k in ks], "o-", color="#4c72b0", lw=1.9)
    axes[0].axvline(chosen, color="#c0392b", ls="--", lw=1.4,
                    label=safe(f"选定 K={chosen}"))
    axes[0].set_xlabel(safe("聚类数 K"))
    axes[0].set_ylabel(safe("组内平方和 SSE"))
    axes[0].set_title(safe("肘部法（找拐点）"))
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)

    ks2 = sorted(silhouettes)
    vals = [silhouettes[k] for k in ks2]
    colors = ["#c0392b" if k == chosen else "#55a868" for k in ks2]
    axes[1].bar(ks2, vals, color=colors)
    axes[1].axhline(max(vals), color="gray", ls=":", lw=1.1)
    axes[1].set_xlabel(safe("聚类数 K"))
    axes[1].set_ylabel(safe("轮廓系数"))
    axes[1].set_title(safe("轮廓系数（越高越好）"))
    axes[1].grid(alpha=0.3, axis="y")

    fig.suptitle(safe("聚类数选择"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_clusters(X: np.ndarray, labels: np.ndarray,
                  centers: np.ndarray,
                  out_png: Optional[str] = None) -> None:
    """聚类结果散点图（取前两个特征）。"""
    out_png = out_path(out_png, "kmeans_clusters.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    # 多于两维时，用前两个主成分方向投影（简化 PCA）
    if X.shape[1] > 2:
        Xc = X - X.mean(axis=0)
        U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
        P = Xc @ Vt[:2].T
        C = (centers - X.mean(axis=0)) @ Vt[:2].T
        xlab, ylab = "主成分1", "主成分2"
    else:
        P, C = X, centers
        xlab = CN_NAMES.get(FEATURES[0], FEATURES[0])
        ylab = CN_NAMES.get(FEATURES[1], FEATURES[1])

    fig, ax = plt.subplots(figsize=(7.6, 6.0))
    colors = plt.cm.tab10(np.linspace(0, 1, len(np.unique(labels))))
    for j in np.unique(labels):
        m = labels == j
        ax.scatter(P[m, 0], P[m, 1], s=26, alpha=0.65, color=colors[j],
                   label=safe(f"簇 {j}（{int(m.sum())} 个）"))
    ax.scatter(C[:, 0], C[:, 1], s=260, marker="X", color="black",
               edgecolors="white", linewidths=1.6, zorder=5,
               label=safe("簇中心"))
    ax.set_xlabel(safe(xlab))
    ax.set_ylabel(safe(ylab))
    ax.set_title(safe(f"K-means 聚类结果（K={len(np.unique(labels))}）"))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("K-means 聚类分析（数据是模拟的，替换成你的数据）")
    print("=" * 66)

    X_raw = build_data()
    print(f"\n[数据] {X_raw.shape[0]} 个样本 × {X_raw.shape[1]} 个特征")
    print(f"[特征] {FEATURES}")
    print(f"[标准化] {'是' if STANDARDIZE else '否'}")

    if STANDARDIZE:
        X, mu, sd = standardize_data(X_raw)
        print(f"  原始均值 {np.round(mu, 2).tolist()}")
        print(f"  原始标准差 {np.round(sd, 2).tolist()}")
    else:
        X = X_raw

    # --- 选 K ---
    print("\n[第一步] 肘部法计算 SSE")
    elbow = elbow_curve(X, K_RANGE)
    for k in sorted(elbow):
        print(f"  K={k}: SSE = {elbow[k]:9.3f}")

    print("\n[第二步] 轮廓系数")
    silhouettes: Dict[int, float] = {}
    for k in sorted(elbow):
        _, labels_k, _ = kmeans(X, k, n_init=N_INIT, seed=SEED)
        s = silhouette_score(X, labels_k)
        silhouettes[k] = s
        print(f"  K={k}: 轮廓系数 = {s:.4f}")

    print("\n[第三步] 综合判定")
    best_k = suggest_k(elbow, silhouettes)

    # --- 用最优 K 聚类 ---
    centers, labels, sse = kmeans(X, best_k, n_init=N_INIT, seed=SEED)
    print(f"\n[最终聚类] K = {best_k}")
    print(f"  组内平方和 SSE = {sse:.4f}")
    print(f"  轮廓系数 = {silhouette_score(X, labels):.4f}")

    # 各簇规模
    print(f"\n[各簇规模与中心]")
    print(f"  {'簇':<6}{'样本数':>8}{'占比':>9}")
    for j in range(best_k):
        m = labels == j
        print(f"  {j:<6}{int(m.sum()):>8}{m.mean():>9.2%}")

    # 还原到原始量纲的中心
    print(f"\n[各簇中心（原始量纲）]")
    hdr = "  " + "".join(f"{CN_NAMES.get(f, f):>14}" for f in FEATURES)
    print(hdr)
    for j in range(best_k):
        c = centers[j] * sd + mu if STANDARDIZE else centers[j]
        print(f"  {f'簇{j}':<6}" + "".join(f"{v:14.2f}" for v in c))

    # 给每簇一个业务解读
    print(f"\n[各簇特征解读]")
    for j in range(best_k):
        c = centers[j] * sd + mu if STANDARDIZE else centers[j]
        desc = "，".join(
            f"{CN_NAMES.get(f, f)}={'高' if c[i] > mu[i] else '低'}"
            for i, f in enumerate(FEATURES))
        print(f"  簇{j}（{int((labels == j).sum())} 个）：{safe(desc)}")

    plot_selection(elbow, silhouettes, best_k)
    plot_clusters(X, labels, centers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
