# -*- coding: utf-8 -*-
"""熵权法 / TOPSIS 综合评价 —— 代码骨架（可直接复制使用）

【解决什么问题】
  给多个方案在多个指标上打分排序。难点在于"指标权重怎么定"——
  主观赋权（如 AHP）容易被质疑，熵权法是**客观赋权**：
  某指标在各方案间差异越大，说明它携带的信息越多，权重就该越大。

  流程：原始矩阵 -> 正向化 -> 标准化 -> 熵权 -> TOPSIS 贴近度排序

【要改哪几行】
  1. `build_matrix()` —— 换成你的评价矩阵（每行一个方案，每列一个指标）
  2. `INDICATORS`     —— 每个指标的**方向**（越大越好 / 越小越好）
  3. `CN_NAMES`       —— 方案名与指标中文名

【输入】方案 × 指标的原始矩阵
【输出】熵权、加权标准化矩阵、TOPSIS 得分与排名、灵敏度检验

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
SCHEMES = ["方案A", "方案B", "方案C", "方案D", "方案E"]

# 指标名 -> 中文名
CN_NAMES: Dict[str, str] = {
    "benefit": "经济效益",
    "cost": "建设成本",
    "risk": "风险水平",
    "env": "环境影响",
    "social": "社会效益",
}

# 指标方向：True = 越大越好（正向），False = 越小越好（负向）
INDICATORS: Dict[str, bool] = {
    "benefit": True,
    "cost": False,
    "risk": False,
    "env": False,
    "social": True,
}


# ============================== 1. 数据 ====================================
def build_matrix() -> np.ndarray:
    """构造评价矩阵：每行一个方案，每列一个指标。

    >>> 换成你的数据 <<<
        df = pd.read_csv("your_data.csv")
        M = df[["benefit","cost",...]].values.astype(float)
    """
    rng = np.random.default_rng(88)
    n_scheme = len(SCHEMES)
    n_ind = len(INDICATORS)
    base = np.array([[80, 60, 30, 40, 70],
                     [65, 45, 55, 30, 60],
                     [90, 80, 20, 65, 85],
                     [70, 50, 45, 35, 55],
                     [85, 70, 25, 55, 75]], dtype=float)
    assert base.shape == (n_scheme, n_ind)
    return base + rng.normal(0, 2.0, base.shape)


# ============================== 2. 正向化与标准化 ==========================
def normalize_direction(M: np.ndarray,
                        directions: List[bool]) -> np.ndarray:
    """把所有指标统一成"越大越好"。

    负向指标（成本、风险）用极差法翻转：x' = max - x。
    这样后续熵权和 TOPSIS 都只需处理"越大越好"一种情形。
    """
    out = M.astype(float).copy()
    for j, is_positive in enumerate(directions):
        if not is_positive:
            col = out[:, j]
            out[:, j] = col.max() - col
    return out


def standardize(M: np.ndarray) -> np.ndarray:
    """极差标准化到 [0, 1]，消除量纲。

    加一个极小量避免除零（某一指标所有方案取值相同的情形）。
    """
    lo = M.min(axis=0)
    hi = M.max(axis=0)
    span = hi - lo
    span = np.where(span < 1e-12, 1.0, span)
    return (M - lo) / span


def entropy_weights(P: np.ndarray,
                    eps: float = 1e-12) -> Tuple[np.ndarray, np.ndarray]:
    """熵权法求权重。

    步骤：
      1. 计算第 j 个指标下第 i 个方案的比重 p_ij = x_ij / sum_i x_ij
      2. 信息熵 e_j = -k * sum_i p_ij * ln(p_ij)，其中 k = 1/ln(n)
      3. 差异系数 d_j = 1 - e_j （熵越小说明差异越大、信息越多）
      4. 权重 w_j = d_j / sum_j d_j

    注意：标准化后可能出现 0，ln(0) 无定义，所以加 eps 并重新归一化。
    """
    n, m = P.shape
    # 保证非负且每列有正数
    P = np.clip(P, 0.0, None)
    col_sum = P.sum(axis=0)
    col_sum = np.where(col_sum < eps, 1.0, col_sum)
    p = P / col_sum
    p = np.where(p < eps, eps, p)          # 避免 ln(0)

    k = 1.0 / np.log(n) if n > 1 else 1.0
    e = -k * (p * np.log(p)).sum(axis=0)   # 信息熵，0 <= e <= 1
    d = 1.0 - e                            # 差异系数
    d = np.clip(d, 0.0, None)
    if d.sum() < eps:
        w = np.full(m, 1.0 / m)            # 所有指标都没差异 -> 等权
    else:
        w = d / d.sum()
    return w, e


# ============================== 3. TOPSIS ==================================
def topsis(P: np.ndarray, w: np.ndarray
           ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """TOPSIS：逼近理想解的排序法。

    1. 加权标准化矩阵 V = P * w
    2. 正理想解 V+ = 每列最大值；负理想解 V- = 每列最小值
    3. 到两者的欧氏距离 D+、D-
    4. 贴近度 C = D- / (D+ + D-)，C 越大越优（0~1）
    """
    V = P * w
    v_plus = V.max(axis=0)
    v_minus = V.min(axis=0)

    d_plus = np.sqrt(((V - v_plus) ** 2).sum(axis=1))
    d_minus = np.sqrt(((V - v_minus) ** 2).sum(axis=1))

    denom = d_plus + d_minus
    denom = np.where(denom < 1e-12, 1.0, denom)
    closeness = d_minus / denom
    return closeness, d_plus, d_minus, V


def rank_schemes(scores: np.ndarray,
                 names: Optional[List[str]] = None) -> List[Tuple[str, float, int]]:
    """按贴近度降序排名，返回 (名称, 得分, 名次)。"""
    names = names or [f"方案{i + 1}" for i in range(scores.size)]
    order = np.argsort(-scores)
    out = []
    for rank, idx in enumerate(order, 1):
        out.append((names[idx], float(scores[idx]), rank))
    return out


# ============================== 4. 稳健性检验 ==============================
def weight_sensitivity(P: np.ndarray, w: np.ndarray,
                       delta: float = 0.2,
                       n_trials: int = 300,
                       seed: int = 4) -> Dict[str, float]:
    """权重扰动检验：熵权是基于数据的，数据一变权重就变。

    这里对每个权重加乘性随机扰动再归一化，看排名稳不稳。
    如果扰动后冠军频繁易主，结论就不够稳健，论文里必须说明。
    """
    rng = np.random.default_rng(seed)
    base_rank = rank_schemes(topsis(P, w)[0])
    base_winner = base_rank[0][0]

    same_winner = 0
    rank_orders: Dict[str, List[int]] = {}

    for _ in range(n_trials):
        noise = rng.uniform(1.0 - delta, 1.0 + delta, w.size)
        w_try = w * noise
        w_try = w_try / w_try.sum()
        r = rank_schemes(topsis(P, w_try)[0])
        if r[0][0] == base_winner:
            same_winner += 1
        for name, _, rk in r:
            rank_orders.setdefault(name, []).append(rk)

    result = {"冠军保持率": same_winner / n_trials}
    for name, rks in rank_orders.items():
        result[f"{name}_平均名次"] = float(np.mean(rks))
    return result


# ============================== 5. 画图 ====================================
def plot_weights(w: np.ndarray, e: np.ndarray,
                 out_png: Optional[str] = None) -> None:
    """权重与信息熵对比图。"""
    out_png = out_path(out_png, "entropy_weights.png")
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

    labels = [CN_NAMES.get(k, k) for k in INDICATORS.keys()]
    x = np.arange(len(labels))

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    axes[0].bar(x, w, color="#4c72b0")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([safe(l) for l in labels], rotation=25, ha="right")
    axes[0].set_ylabel(safe("权重"))
    axes[0].set_title(safe("熵权法权重分配"))
    for xi, wi in zip(x, w):
        axes[0].text(xi, wi, f"{wi:.3f}", ha="center", va="bottom", fontsize=8)

    axes[1].bar(x, e, color="#dd8452")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([safe(l) for l in labels], rotation=25, ha="right")
    axes[1].set_ylabel(safe("信息熵"))
    axes[1].set_title(safe("各指标信息熵（越小信息量越大）"))

    fig.suptitle(safe("熵权法：权重由数据差异决定"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_ranking(scores: np.ndarray, out_png: Optional[str] = None) -> None:
    """TOPSIS 贴近度排名条形图。"""
    out_png = out_path(out_png, "topsis_ranking.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    order = np.argsort(-scores)
    labels = [SCHEMES[i] if i < len(SCHEMES) else f"方案{i}" for i in order]
    vals = scores[order]
    colors = ["#c0392b" if k == 0 else "#4c72b0" for k in range(len(vals))]

    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    ax.bar([safe(l) for l in labels], vals, color=colors)
    for xi, v in enumerate(vals):
        ax.text(xi, v, f"{v:.4f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel(safe("TOPSIS 贴近度"))
    ax.set_title(safe("综合评价排序（红 = 最优方案）"))
    ax.set_ylim(0, max(vals) * 1.15)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("熵权法 + TOPSIS 综合评价（数据是模拟的，替换成你的数据）")
    print("=" * 66)

    M = build_matrix()
    names = list(INDICATORS.keys())
    directions = list(INDICATORS.values())

    print(f"\n[原始矩阵] {M.shape[0]} 个方案 × {M.shape[1]} 个指标")
    hdr = "  " + "".join(f"{CN_NAMES.get(n, n):>10}" for n in names)
    print(hdr)
    for i, row in enumerate(M):
        label = SCHEMES[i] if i < len(SCHEMES) else f"方案{i}"
        print(f"  {safe(label):<8}" + "".join(f"{v:10.2f}" for v in row))
    print("  指标方向：" + "，".join(
        f"{CN_NAMES.get(n, n)}={'越大越好' if d else '越小越好'}"
        for n, d in zip(names, directions)))

    # --- 正向化 + 标准化 ---
    M_pos = normalize_direction(M, directions)
    P = standardize(M_pos)

    # --- 熵权 ---
    w, e = entropy_weights(P)
    print("\n[熵权结果]")
    print(f"  {'指标':<10}{'信息熵':>10}{'差异系数':>12}{'权重':>10}")
    for j, n in enumerate(names):
        print(f"  {CN_NAMES.get(n, n):<10}{e[j]:10.4f}{1 - e[j]:12.4f}{w[j]:10.4f}")
    print(f"  权重合计 = {w.sum():.6f}")

    top_ind = names[int(np.argmax(w))]
    print(f"  [解读] 权重最大的是「{safe(CN_NAMES.get(top_ind, top_ind))}」，"
          f"说明该指标在各方案间差异最大、区分度最高。")

    # --- TOPSIS ---
    closeness, d_plus, d_minus, V = topsis(P, w)
    print("\n[TOPSIS 评价结果]")
    print(f"  {'方案':<8}{'D+':>10}{'D-':>10}{'贴近度':>12}{'名次':>6}")
    ranking = rank_schemes(closeness, SCHEMES)
    for name, score, rk in ranking:
        i = SCHEMES.index(name) if name in SCHEMES else 0
        print(f"  {safe(name):<8}{d_plus[i]:10.4f}{d_minus[i]:10.4f}"
              f"{score:12.4f}{rk:6d}")

    print(f"\n[结论] 最优方案 = {safe(ranking[0][0])}"
          f"（贴近度 {ranking[0][1]:.4f}）")
    print(f"       最劣方案 = {safe(ranking[-1][0])}"
          f"（贴近度 {ranking[-1][1]:.4f}）")

    # --- 稳健性 ---
    print("\n[稳健性检验] 权重加 ±20% 随机扰动，重复 300 次")
    sens = weight_sensitivity(P, w, delta=0.2, n_trials=300)
    print(f"  冠军保持率 = {sens['冠军保持率']:.1%}")
    if sens["冠军保持率"] > 0.9:
        print("  结论稳健：最优方案对权重扰动不敏感。")
    else:
        print("  结论不够稳健：排名受权重影响较大，论文中需要讨论。")
    print("  各方案平均名次：")
    for name in SCHEMES:
        key = f"{name}_平均名次"
        if key in sens:
            print(f"    {safe(name):<8} {sens[key]:.3f}")

    plot_weights(w, e)
    plot_ranking(closeness)
    return 0


if __name__ == "__main__":
    sys.exit(main())
