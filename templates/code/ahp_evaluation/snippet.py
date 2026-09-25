# -*- coding: utf-8 -*-
"""层次分析法 AHP（含一致性检验）—— 代码骨架（可直接复制使用）

【解决什么问题】
  指标权重靠专家判断给出，主观性怎么约束？AHP 的做法是：
  让专家做**两两比较**（比直接给权重容易得多），再从判断矩阵
  反解出权重，并用一致性比率 CR 检验判断是否自相矛盾。

  关键判据：
    CR = CI / RI < 0.1  才算通过一致性检验，否则要重新调整判断矩阵。

【要改哪几行】
  1. `PAIRWISE`  —— 你的判断矩阵（Saaty 1-9 标度）
  2. `CN_NAMES`  —— 指标中文名
  3. `SCHEME_SCORES` —— 各方案在每个指标上的得分（用于最终合成）

【输入】判断矩阵（正互反）+ 方案得分
【输出】权重向量、一致性检验、方案总排序、权重图

【注意】下面的判断矩阵是模拟的，替换成你的专家判断。
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
CRITERIA = ["economic", "technical", "environmental", "social"]
CN_NAMES: Dict[str, str] = {
    "economic": "经济效益",
    "technical": "技术可行性",
    "environmental": "环境影响",
    "social": "社会效益",
}

# Saaty 1-9 标度判断矩阵（正互反：a_ij = 1 / a_ji，对角线为 1）
# a_ij 表示"第 i 个指标比第 j 个重要多少倍"
PAIRWISE = np.array([
    [1.0, 2.0, 4.0, 3.0],
    [1 / 2, 1.0, 3.0, 2.0],
    [1 / 4, 1 / 3, 1.0, 1 / 2],
    [1 / 3, 1 / 2, 2.0, 1.0],
])

SCHEMES = ["方案甲", "方案乙", "方案丙"]

# 每个方案在各指标上的得分（0-100）
SCHEME_SCORES = np.array([
    [85.0, 70.0, 60.0, 75.0],
    [70.0, 90.0, 75.0, 65.0],
    [78.0, 65.0, 88.0, 82.0],
])


# ============================== 1. 判断矩阵检查 ============================
def check_reciprocal(A: np.ndarray, tol: float = 1e-6) -> bool:
    """检查正互反性：a_ij > 0 且 a_ij * a_ji = 1。

    判断矩阵写错（比如只填了上三角、下三角忘了取倒数）是常见错误，
    AHP 的结果会全错但一点都不报错，所以必须先检查。
    """
    if np.any(A <= 0):
        print("  [错误] 判断矩阵存在非正元素")
        return False
    prod = A * A.T
    ok = np.allclose(prod, np.ones_like(A), atol=tol)
    if not ok:
        bad = np.argwhere(~np.isclose(prod, 1.0, atol=tol))
        print(f"  [错误] 不满足互反性，位置（行,列）：{bad[:, 0].tolist()}, "
              f"{bad[:, 1].tolist()}")
        print("         请确认 a_ij 与 a_ji 互为倒数")
    else:
        print("  [检查] 正互反性通过")
    return ok


# ============================== 2. 权重求解 ================================
def ahp_weights(A: np.ndarray) -> Tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """三种方法求权重，互相印证。

    返回 (特征值法权重, lambda_max, 算术平均权重, 几何平均权重)。

    1. 特征值法（主）：最大特征值对应的特征向量，归一化后即权重。
    2. 算术平均法：每列归一化后按行平均。
    3. 几何平均法：每行求几何平均后归一化。

    比赛里推荐报告特征值法的结果，另两个作为校验。
    """
    n = A.shape[0]

    # --- 方法1：特征值法 ---
    eigvals, eigvecs = np.linalg.eig(A)
    k = int(np.argmax(eigvals.real))
    lam_max = float(eigvals.real[k])
    v = np.abs(eigvecs[:, k].real)
    w_eig = v / v.sum()

    # --- 方法2：算术平均法 ---
    col_norm = A / A.sum(axis=0, keepdims=True)
    w_arith = col_norm.mean(axis=1)

    # --- 方法3：几何平均法 ---
    geo = np.prod(A, axis=1) ** (1.0 / n)
    w_geo = geo / geo.sum()

    return w_eig, lam_max, w_arith, w_geo  # type: ignore[return-value]


# ============================== 3. 一致性检验 ==============================
# Saaty 随机一致性指标 RI（n = 1..15）
RI_TABLE = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24,
    7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49, 11: 1.51, 12: 1.54,
    13: 1.56, 14: 1.58, 15: 1.59,
}


def consistency_check(A: np.ndarray,
                      lam_max: float) -> Tuple[float, float, float, bool]:
    """一致性检验。

    CI = (lambda_max - n) / (n - 1)
    CR = CI / RI

    CR < 0.1 通过。n <= 2 时矩阵必然一致，无需检验。
    """
    n = A.shape[0]
    if n <= 2:
        return 0.0, 0.0, 0.0, True

    ci = (lam_max - n) / (n - 1)
    ri = RI_TABLE.get(n, 1.59)
    cr = ci / ri if ri > 0 else 0.0
    return ci, ri, cr, cr < 0.1


# ============================== 4. 方案合成 ================================
def synthesize(weights: np.ndarray,
               scores: np.ndarray,
               normalize: bool = True) -> np.ndarray:
    """方案总分 = 得分矩阵 × 权重。

    normalize=True 时先把各指标得分极差标准化到 [0,1]，
    避免某个指标数值大就主导总分（量纲问题）。
    """
    S = scores.astype(float)
    if normalize:
        lo, hi = S.min(axis=0), S.max(axis=0)
        span = np.where(hi - lo < 1e-12, 1.0, hi - lo)
        S = (S - lo) / span
    return S @ weights


# ============================== 5. 灵敏度 ==================================
def weight_sensitivity(A: np.ndarray, scores: np.ndarray,
                       delta: float = 0.1, n_trials: int = 400,
                       seed: int = 12) -> Dict[str, object]:
    """权重扰动下排名的稳定性。"""
    rng = np.random.default_rng(seed)
    w0, _, _, _ = ahp_weights(A)
    base_order = list(np.argsort(-synthesize(w0, scores)))
    base_winner = base_order[0]

    wins = 0
    for _ in range(n_trials):
        noise = rng.uniform(1 - delta, 1 + delta, w0.size)
        w = w0 * noise
        w = w / w.sum()
        order = list(np.argsort(-synthesize(w, scores)))
        if order[0] == base_winner:
            wins += 1

    return {"冠军保持率": wins / n_trials, "base_winner": base_winner}


# ============================== 6. 画图 ====================================
def plot_weights(weights_list: Dict[str, np.ndarray],
                 out_png: Optional[str] = None) -> None:
    """三种算法求得的权重对比。"""
    out_png = out_path(out_png, "ahp_weights.png")
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

    labels = [CN_NAMES.get(k, k) for k in CRITERIA]
    x = np.arange(len(labels))
    width = 0.26

    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    for i, (method, w) in enumerate(weights_list.items()):
        ax.bar(x + (i - 1) * width, w, width, label=safe(method))
        for xi, wi in zip(x + (i - 1) * width, w):
            ax.text(xi, wi, f"{wi:.3f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels([safe(l) for l in labels])
    ax.set_ylabel(safe("权重"))
    ax.set_title(safe("AHP 三种算法权重对比（应基本一致）"))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_ranking(total: np.ndarray, out_png: Optional[str] = None) -> None:
    """方案总排序。"""
    out_png = out_path(out_png, "ahp_ranking.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    order = np.argsort(-total)
    labels = [SCHEMES[i] if i < len(SCHEMES) else f"方案{i}" for i in order]
    vals = total[order]
    colors = ["#c0392b" if k == 0 else "#4c72b0" for k in range(len(vals))]

    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.bar([safe(l) for l in labels], vals, color=colors)
    for xi, v in enumerate(vals):
        ax.text(xi, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel(safe("综合得分"))
    ax.set_title(safe("AHP 方案总排序（红 = 最优）"))
    ax.set_ylim(0, max(vals) * 1.18)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("层次分析法 AHP（判断矩阵是模拟的，替换成你的专家判断）")
    print("=" * 66)

    n = len(CRITERIA)
    print(f"\n[判断矩阵] {n}×{n}")
    print("  " + "".join(f"{CN_NAMES.get(c, c):>12}" for c in CRITERIA))
    for i, row in enumerate(PAIRWISE):
        print(f"  {CN_NAMES.get(CRITERIA[i], CRITERIA[i]):<10}"
              + "".join(f"{v:12.4f}" for v in row))

    if not check_reciprocal(PAIRWISE):
        print("\n判断矩阵不合法，请修正后重跑。")
        return 1

    w_eig, lam_max, w_arith, w_geo = ahp_weights(PAIRWISE)

    print(f"\n[权重结果]")
    print(f"  {'指标':<12}{'特征值法':>12}{'算术平均':>12}{'几何平均':>12}")
    for j, c in enumerate(CRITERIA):
        print(f"  {CN_NAMES.get(c, c):<12}{w_eig[j]:12.4f}"
              f"{w_arith[j]:12.4f}{w_geo[j]:12.4f}")
    print(f"  {'合计':<12}{w_eig.sum():12.4f}"
          f"{w_arith.sum():12.4f}{w_geo.sum():12.4f}")

    # 三种方法的最大偏差
    max_dev = max(float(np.abs(w_eig - w_arith).max()),
                  float(np.abs(w_eig - w_geo).max()))
    print(f"  三法最大偏差 = {max_dev:.4f}"
          + ("（一致，结果可信）" if max_dev < 0.05 else "（偏差偏大，检查矩阵）"))

    # --- 一致性检验 ---
    ci, ri, cr, ok = consistency_check(PAIRWISE, lam_max)
    print(f"\n[一致性检验]")
    print(f"  最大特征值 lambda_max = {lam_max:.6f}")
    print(f"  一致性指标 CI = (lambda_max - n)/(n-1) = {ci:.6f}")
    print(f"  随机一致性指标 RI = {ri:.4f}  (n={n})")
    print(f"  一致性比率 CR = CI/RI = {cr:.6f}")
    if ok:
        print(f"  CR = {cr:.4f} < 0.1，通过一致性检验，权重可用。")
    else:
        print(f"  CR = {cr:.4f} >= 0.1，**未通过**！判断矩阵存在逻辑矛盾，")
        print("  请重新检查两两比较，例如「A比B重要、B比C重要、但C比A重要」"
              "这类循环矛盾。")

    # --- 方案合成 ---
    total = synthesize(w_eig, SCHEME_SCORES)
    print(f"\n[方案得分矩阵]")
    print("  " + "".join(f"{CN_NAMES.get(c, c):>12}" for c in CRITERIA))
    for i, row in enumerate(SCHEME_SCORES):
        label = SCHEMES[i] if i < len(SCHEMES) else f"方案{i}"
        print(f"  {safe(label):<8}" + "".join(f"{v:12.2f}" for v in row))

    print(f"\n[方案总排序]")
    order = np.argsort(-total)
    for rk, i in enumerate(order, 1):
        label = SCHEMES[i] if i < len(SCHEMES) else f"方案{i}"
        print(f"  第{rk}名  {safe(label):<8} 总分 = {total[i]:.4f}")

    winner = SCHEMES[order[0]] if order[0] < len(SCHEMES) else "方案0"
    print(f"\n[结论] 推荐方案：{safe(winner)}")

    sens = weight_sensitivity(PAIRWISE, SCHEME_SCORES)
    print(f"[稳健性] 权重 ±10% 扰动下冠军保持率 = "
          f"{float(sens['冠军保持率']):.1%}")

    plot_weights({"特征值法": w_eig, "算术平均": w_arith, "几何平均": w_geo})
    plot_ranking(total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
