# -*- coding: utf-8 -*-
"""蒙特卡洛模拟与置信区间 —— 代码骨架（可直接复制使用）

【解决什么问题】
  模型里有随机性、或者解析解求不出来时，用大量随机抽样估计：
  * 结果的期望与分布
  * 均值的置信区间（含 Bootstrap）
  * 某个事件发生的概率（如"库存不足的概率"）
  * 输出对输入不确定性的敏感程度

【要改哪几行】
  1. `simulate_once()` —— 你的单次随机实验，返回一个（或几个）指标
  2. `N_SIMS`          —— 模拟次数，10000 起，要精度就加到 1e6
  3. `INPUT_DIST`      —— 输入变量的分布假设
  4. `THRESHOLD`       —— 关心的事件阈值（算概率用）

【输入】随机输入的分布假设 + 单次模拟函数
【输出】指标分布、均值/中位数、置信区间、事件概率、收敛曲线

【注意】下面的数据是模拟的，替换成你的数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

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
N_SIMS = 20000          # 模拟次数
SEED = 12345            # 随机种子：固定住，结果才可复现（论文要求）
THRESHOLD = 0.0         # 关心的事件阈值（下面按需求利润 < 阈值算概率）
ALPHA = 0.05            # 置信水平 1 - ALPHA

# 输入变量的分布假设：(分布类型, 参数...)
INPUT_DIST: Dict[str, Tuple] = {
    "demand_mu": ("norm", 1000.0, 120.0),      # 需求均值，正态
    "demand_sigma": ("norm", 150.0, 20.0),     # 需求标准差，正态
    "unit_price": ("triang", 8.0, 12.0, 18.0),  # 单价，三角分布（低/众数/高）
    "unit_cost": ("norm", 6.0, 0.5),           # 单位成本，正态
    "fixed_cost": ("uniform", 800.0, 1500.0),  # 固定成本，均匀
}


# ============================== 1. 输入抽样 ================================
def draw_inputs(rng: np.random.Generator,
                spec: Dict[str, Tuple]) -> Dict[str, float]:
    """按指定分布抽一组输入参数。

    分布选择建议：
      有大量历史数据 -> 拟合实际分布
      只知道范围     -> 均匀分布 uniform(a, b)
      知道最可能值   -> 三角分布 triang(left, mode, right)
      知道均值方差   -> 正态分布 norm(mu, sigma)
    """
    out: Dict[str, float] = {}
    for name, spec_tuple in spec.items():
        kind = spec_tuple[0]
        args = spec_tuple[1:]
        if kind == "norm":
            out[name] = float(rng.normal(args[0], args[1]))
        elif kind == "uniform":
            out[name] = float(rng.uniform(args[0], args[1]))
        elif kind == "triang":
            # numpy 的 triangular(left, mode, right) 要求 left <= mode <= right。
            # 这里直接按位置形式传入，最直观也最不容易错。
            left, mode, right = args
            out[name] = float(rng.triangular(left, mode, right))
        elif kind == "lognorm":
            out[name] = float(rng.lognormal(args[0], args[1]))
        elif kind == "beta":
            out[name] = float(rng.beta(args[0], args[1]))
        else:
            raise ValueError(f"未知分布类型：{kind}")
    return out


# ============================== 2. 单次模拟 ================================
def simulate_once(inp: Dict[str, float],
                  rng: np.random.Generator) -> Dict[str, float]:
    """一次随机实验，返回若干指标。

    这里模拟一个"订货决策"问题：
      实际需求 ~ N(mu, sigma)，收入 = 单价 * min(需求, 库存)
      利润 = 收入 - 单位成本 * 库存 - 固定成本

    >>> 换成你的模型 <<<
    """
    demand = max(0.0, rng.normal(inp["demand_mu"], inp["demand_sigma"]))
    stock = 1000.0                                 # 决策变量：订多少

    served = min(demand, stock)                    # 缺货就少卖
    revenue = inp["unit_price"] * served
    cost = inp["unit_cost"] * stock + inp["fixed_cost"]

    profit = revenue - cost
    shortage = max(0.0, demand - stock)

    return {
        "profit": profit,
        "demand": demand,
        "shortage": shortage,
        "fill_rate": served / demand if demand > 0 else 1.0,
    }


# ============================== 3. 跑模拟 ==================================
def run_simulation(n: int, seed: int) -> Dict[str, np.ndarray]:
    """跑 n 次，把每个指标收集成数组。"""
    rng = np.random.default_rng(seed)
    records: List[Dict[str, float]] = []
    for _ in range(n):
        inp = draw_inputs(rng, INPUT_DIST)
        records.append(simulate_once(inp, rng))

    keys = records[0].keys()
    return {k: np.array([r[k] for r in records], dtype=float) for k in keys}


# ============================== 4. 统计推断 ================================
def describe(x: np.ndarray, alpha: float = 0.05) -> Dict[str, float]:
    """描述统计 + 正态近似置信区间。"""
    n = x.size
    mean = float(x.mean())
    sd = float(x.std(ddof=1))
    se = sd / np.sqrt(n)                    # 均值的标准误
    # 用正态分位数（大样本下 t 与正态几乎一致）
    z = _z_critical(alpha)
    return {
        "n": n,
        "mean": mean,
        "std": sd,
        "se": se,
        "median": float(np.median(x)),
        "p2.5": float(np.percentile(x, 2.5)),
        "p97.5": float(np.percentile(x, 97.5)),
        "ci_low": mean - z * se,
        "ci_high": mean + z * se,
        "min": float(x.min()),
        "max": float(x.max()),
    }


def _z_critical(alpha: float) -> float:
    """标准正态的 1 - alpha/2 分位数。

    用有理逼近（Abramowitz & Stegun 26.2.23），精度约 4.5e-4，
    比赛场景完全够用，且不需要 scipy。
    """
    p = 1.0 - alpha / 2.0
    # 先做 Acklam 风格的有理逼近
    t = np.sqrt(-2.0 * np.log(1.0 - p)) if p < 1.0 else 0.0
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    z = t - (c0 + c1 * t + c2 * t ** 2) / (1.0 + d1 * t + d2 * t ** 2
                                           + d3 * t ** 3)
    # 用正态 CDF 的级数再校正一次，提高精度
    for _ in range(3):
        err = _norm_cdf(z) - p
        z -= err / max(_norm_pdf(z), 1e-12)
    return float(z)


def _norm_pdf(z: float) -> float:
    return float(np.exp(-0.5 * z * z) / np.sqrt(2.0 * np.pi))


def _norm_cdf(z: float) -> float:
    """标准正态 CDF，用 erfc 精确计算（math 库自带，无需 scipy）。"""
    from math import erfc, sqrt
    return float(0.5 * erfc(-z / sqrt(2.0)))


def bootstrap_ci(x: np.ndarray, n_boot: int = 5000,
                 alpha: float = 0.05,
                 seed: int = 7) -> Tuple[float, float]:
    """Bootstrap 置信区间（百分位法）。

    为什么还要 Bootstrap：正态近似要求均值近似正态，
    但利润分布常常严重偏斜，这时百分位法更可信。
    """
    rng = np.random.default_rng(seed)
    n = x.size
    idx = rng.integers(0, n, size=(n_boot, n))
    means = x[idx].mean(axis=1)
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return lo, hi


def probability_below(x: np.ndarray, threshold: float) -> float:
    """P(X < threshold)，即事件发生概率。"""
    return float((x < threshold).mean())


def required_n_for_precision(std: float, target_halfwidth: float,
                             alpha: float = 0.05) -> int:
    """要让置信区间半宽小于目标值，需要多少次模拟？

    n = (z * sigma / halfwidth)² —— 论文里"模拟次数怎么定"的依据。
    """
    z = _z_critical(alpha)
    if target_halfwidth <= 0:
        return 0
    return int(np.ceil((z * std / target_halfwidth) ** 2))


# ============================== 5. 画图 ====================================
def plot_distribution(x: np.ndarray, stats: Dict[str, float],
                      boot_ci: Tuple[float, float],
                      out_png: Optional[str] = None) -> None:
    """指标分布直方图 + 置信区间标注。"""
    out_png = out_path(out_png, "monte_carlo_distribution.png")
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

    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    ax.hist(x, bins=60, color="#4c72b0", edgecolor="white", alpha=0.85,
            density=True)

    ax.axvline(stats["mean"], color="#c0392b", lw=2.0,
               label=safe(f"均值 {stats['mean']:.1f}"))
    ax.axvline(stats["p2.5"], color="gray", ls="--", lw=1.3)
    ax.axvline(stats["p97.5"], color="gray", ls="--", lw=1.3,
               label=safe("2.5% / 97.5% 分位"))
    ax.axvspan(boot_ci[0], boot_ci[1], color="#c0392b", alpha=0.15,
               label=safe(f"均值 95% CI [{boot_ci[0]:.1f}, {boot_ci[1]:.1f}]"))
    ax.axvline(THRESHOLD, color="black", ls=":", lw=1.6,
               label=safe(f"阈值 {THRESHOLD:g}"))

    ax.set_xlabel(safe("利润"))
    ax.set_ylabel(safe("概率密度"))
    ax.set_title(safe(f"蒙特卡洛模拟结果分布（{stats['n']} 次）"))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_convergence(x: np.ndarray,
                     out_png: Optional[str] = None) -> None:
    """累计均值收敛曲线 —— 证明模拟次数够了。"""
    out_png = out_path(out_png, "monte_carlo_convergence.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    # 对数均匀取点，避免 x 轴被前几千次挤满
    n = x.size
    steps = np.unique(np.round(np.logspace(1, np.log10(n), 120)).astype(int))
    steps = steps[steps <= n]
    running = np.cumsum(x)[steps - 1] / steps
    final = running[-1]

    fig, ax = plt.subplots(figsize=(9.0, 4.4))
    ax.plot(steps, running, color="#2c3e50", lw=1.7,
            label=safe("累计均值"))
    ax.axhline(final, color="#c0392b", ls="--", lw=1.4,
               label=safe(f"最终值 {final:.2f}"))
    ax.fill_between(steps, final * 0.99, final * 1.01, color="#c0392b",
                    alpha=0.12, label=safe("±1% 带"))
    ax.set_xscale("log")
    ax.set_xlabel(safe("模拟次数（对数轴）"))
    ax.set_ylabel(safe("累计均值"))
    ax.set_title(safe("蒙特卡洛收敛性检验"))
    ax.legend()
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("蒙特卡洛模拟与置信区间（数据是模拟的，替换成你的模型）")
    print("=" * 66)

    t0 = time.time()
    res = run_simulation(N_SIMS, SEED)
    elapsed = time.time() - t0

    profit = res["profit"]
    print(f"\n[模拟] {N_SIMS} 次，耗时 {elapsed:.2f} 秒，"
          f"随机种子={SEED}（固定种子保证结果可复现）")

    stats = describe(profit, ALPHA)
    print("\n[利润分布统计]")
    for key in ["mean", "std", "se", "median", "min", "max"]:
        print(f"  {key:<8}= {stats[key]:12.3f}")
    print(f"  2.5%   = {stats['p2.5']:12.3f}")
    print(f"  97.5%  = {stats['p97.5']:12.3f}")

    print(f"\n[均值 95% 置信区间]（正态近似）")
    print(f"  [{stats['ci_low']:.3f}, {stats['ci_high']:.3f}]  "
          f"半宽 = {(stats['ci_high'] - stats['ci_low']) / 2:.3f}")

    lo, hi = bootstrap_ci(profit, alpha=ALPHA)
    print(f"[均值 95% 置信区间]（Bootstrap 百分位法）")
    print(f"  [{lo:.3f}, {hi:.3f}]")

    p_bad = probability_below(profit, THRESHOLD)
    print(f"\n[事件概率] P(利润 < {THRESHOLD:g}) = {p_bad:.4f}"
          f"（{p_bad * 100:.2f}%）")
    print(f"  即约 {int(p_bad * N_SIMS)} 次模拟中亏损。")

    # 样本量建议
    need = required_n_for_precision(stats["std"], 5.0, ALPHA)
    print(f"\n[样本量建议] 若希望 95% CI 半宽 <= 5.0，"
          f"需要约 {need} 次模拟")

    # 其他指标的简述
    print("\n[其他指标摘要]")
    for key in ["demand", "shortage", "fill_rate"]:
        arr = res[key]
        print(f"  {key:<10} 均值={arr.mean():10.3f}  "
              f"标准差={arr.std(ddof=1):9.3f}  "
              f"95%区间=[{np.percentile(arr, 2.5):.3f}, "
              f"{np.percentile(arr, 97.5):.3f}]")

    plot_distribution(profit, stats, (lo, hi))
    plot_convergence(profit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
