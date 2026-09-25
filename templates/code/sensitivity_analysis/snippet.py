# -*- coding: utf-8 -*-
"""单因子与双因子敏感性分析 —— 代码骨架（可直接复制使用）

【解决什么问题】
  模型跑出结果之后，评委必问："参数不准会怎样？"
  敏感性分析就是回答这个。本骨架给三种做法：

  * `oat_sweep()`      单因子扫描（OAT, One-At-a-Time）：
                       每次只动一个参数，其余固定在基准值。
  * `two_way_sweep()`  双因子扫描：两个参数同时变，看交互作用，
                       结果画成热力图，是论文里的标准配图。
  * `sobol_like()`     方差分解（Sobol 一阶指数的近似）：
                       给出"哪个参数贡献了多少输出不确定性"。

【要改哪几行】
  1. `model()`     —— 你的模型，输入参数字典，输出一个标量指标
  2. `BASE`        —— 基准参数值
  3. `SWEEP_SPEC`  —— 每个参数的扫描范围与步数
  4. `OUTPUT_KEY`  —— 关注的输出指标名

【输入】模型函数 + 参数范围
【输出】敏感度排序、弹性系数、单因子曲线、双因子热力图

【注意】下面的模型是模拟的，替换成你的模型。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

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
BASE: Dict[str, float] = {
    "price": 12.0,        # 单价
    "cost": 7.0,          # 单位成本
    "demand": 1000.0,     # 需求量
    "elasticity": 1.4,    # 价格弹性
    "fixed": 900.0,       # 固定成本
}

CN_NAMES = {
    "price": "单价",
    "cost": "单位成本",
    "demand": "基准需求",
    "elasticity": "价格弹性",
    "fixed": "固定成本",
}

# 每个参数的扫描范围（相对基准值的比例）与步数
SWEEP_SPEC: Dict[str, Tuple[float, float, int]] = {
    "price": (0.6, 1.4, 25),
    "cost": (0.6, 1.4, 25),
    "demand": (0.6, 1.4, 25),
    "elasticity": (0.7, 1.3, 25),
    "fixed": (0.5, 1.5, 25),
}

TWO_WAY_PAIR = ("price", "demand")     # 画热力图的两个参数
OUTPUT_KEY = "profit"                  # 关注的输出


# ============================== 1. 模型 ====================================
def model(p: Dict[str, float]) -> float:
    """你的模型：参数 -> 一个标量指标。

    这里用一个带价格弹性的利润模型：
        需求 = demand * (price / base_price)^(-elasticity)
        利润 = (price - cost) * 需求 - fixed

    >>> 换成你的模型 <<<
    """
    base_price = BASE["price"]
    d = p["demand"] * (p["price"] / base_price) ** (-p["elasticity"])
    d = max(d, 0.0)
    return float((p["price"] - p["cost"]) * d - p["fixed"])


# ============================== 2. 单因子扫描 ==============================
def oat_sweep(base: Dict[str, float],
              spec: Optional[Dict[str, Tuple[float, float, int]]] = None
              ) -> Dict[str, Dict[str, np.ndarray]]:
    """单因子（OAT）扫描。

    每个参数在自己的范围内变化，其余固定在基准值。
    返回 {参数名: {"values": 参数取值, "outputs": 对应输出}}
    """
    spec = spec or SWEEP_SPEC
    base_out = model(base)
    results: Dict[str, Dict[str, np.ndarray]] = {}

    for name, (lo_rel, hi_rel, n) in spec.items():
        vals = np.linspace(base[name] * lo_rel, base[name] * hi_rel, n)
        outs = np.array([model({**base, name: float(v)}) for v in vals])
        results[name] = {"values": vals, "outputs": outs}

    print(f"[单因子扫描] 基准输出 {OUTPUT_KEY} = {base_out:.3f}")
    return results


def compute_sensitivity(sweep: Dict[str, Dict[str, np.ndarray]],
                        base: Dict[str, float]) -> "object":
    """算每个参数的敏感度指标。

    两个常用度量：
    * 弹性系数 E = (dY/Y) / (dX/X)：参数变化 1% 时输出变化百分之几。
      用基准点附近的中心差分算，E > 1 说明输出对该参数特别敏感。
    * 极差比 = (输出最大值 - 最小值) / 基准输出：
      该参数在给定范围内变动时，输出最多能变多少。
    """
    base_out = model(base)
    rows = []

    for name, d in sweep.items():
        vals, outs = d["values"], d["outputs"]

        # 中心差分求弹性（在基准点附近）
        i_mid = int(np.argmin(np.abs(vals - base[name])))
        i_lo = max(i_mid - 1, 0)
        i_hi = min(i_mid + 1, len(vals) - 1)
        dy = outs[i_hi] - outs[i_lo]
        dx = vals[i_hi] - vals[i_lo]
        # E = (dY/dX) * (X/Y)
        elast = (dy / dx) * (base[name] / base_out) if dx != 0 and base_out != 0 else np.nan

        rng_out = float(outs.max() - outs.min())
        rows.append({
            "参数": name,
            "中文名": CN_NAMES.get(name, name),
            "基准值": base[name],
            "弹性系数": elast,
            "输出最小值": float(outs.min()),
            "输出最大值": float(outs.max()),
            "极差": rng_out,
            "极差比%": rng_out / abs(base_out) * 100 if base_out else np.nan,
        })

    try:
        import pandas as pd
        table = pd.DataFrame(rows)
        # 按弹性绝对值排序，最敏感的排最前
        table["绝对弹性"] = table["弹性系数"].abs()
        table = table.sort_values("绝对弹性", ascending=False)
        return table.drop(columns=["绝对弹性"]).reset_index(drop=True)
    except ImportError:
        rows.sort(key=lambda r: -abs(r["弹性系数"]))
        return rows


# ============================== 3. 双因子扫描 ==============================
def two_way_sweep(base: Dict[str, float], p1: str, p2: str,
                  spec: Optional[Dict[str, Tuple[float, float, int]]] = None,
                  n: int = 40
                  ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """两个参数同时变化，返回网格。

    为什么要双因子：单因子扫描会**漏掉交互作用**。
    两个参数各自单独变时影响都不大，一起变却可能让结果翻倍。
    """
    spec = spec or SWEEP_SPEC
    lo1, hi1 = base[p1] * spec[p1][0], base[p1] * spec[p1][1]
    lo2, hi2 = base[p2] * spec[p2][0], base[p2] * spec[p2][1]

    v1 = np.linspace(lo1, hi1, n)
    v2 = np.linspace(lo2, hi2, n)
    Z = np.zeros((n, n))

    for i, a in enumerate(v1):
        for j, b in enumerate(v2):
            Z[j, i] = model({**base, p1: float(a), p2: float(b)})

    return v1, v2, Z


def interaction_index(base: Dict[str, float], p1: str, p2: str,
                      delta: float = 0.15) -> float:
    """交互作用指数。

    定义：II = [f(x+dx, y+dy) - f(x+dx, y) - f(x, y+dy) + f(x, y)]
               / |f(x, y)|

    等于 0 说明两参数互不影响（可分离）；绝对值越大交互越强。
    """
    x0, y0 = base[p1], base[p2]
    f00 = model({**base, p1: x0, p2: y0})
    f10 = model({**base, p1: x0 * (1 + delta), p2: y0})
    f01 = model({**base, p1: x0, p2: y0 * (1 + delta)})
    f11 = model({**base, p1: x0 * (1 + delta), p2: y0 * (1 + delta)})
    if f00 == 0:
        return np.nan
    return float((f11 - f10 - f01 + f00) / abs(f00))


# ============================== 4. 方差分解 ================================
def sobol_like(base: Dict[str, float],
               n_samples: int = 4000,
               seed: int = 5) -> "object":
    """Sobol 一阶敏感性指数的近似估计。

    做法（Saltelli 简化版）：
      A、B 是两个独立采样矩阵，AB_i 是把 A 的第 i 列换成 B 的第 i 列。
      一阶指数 S_i ≈ 由「换掉第 i 个参数带来的输出方差」占「总方差」的比例。

    比起 OAT，它能公平地给出"谁贡献了最多的输出不确定性"，
    而且不依赖模型可导。
    """
    rng = np.random.default_rng(seed)
    names = list(base.keys())
    k = len(names)

    # 在基准值 ±30% 内均匀采样
    lo = np.array([base[n] * 0.7 for n in names])
    hi = np.array([base[n] * 1.3 for n in names])

    A = rng.uniform(lo, hi, size=(n_samples, k))
    B = rng.uniform(lo, hi, size=(n_samples, k))

    def evaluate(M: np.ndarray) -> np.ndarray:
        return np.array([model(dict(zip(names, row))) for row in M])

    yA = evaluate(A)
    yB = evaluate(B)
    var_total = float(np.var(np.concatenate([yA, yB])))
    if var_total <= 0:
        return []

    rows = []
    for i, name in enumerate(names):
        AB = A.copy()
        AB[:, i] = B[:, i]
        yAB = evaluate(AB)
        # Saltelli 2010 的一阶指数估计式
        s_i = float(np.mean(yB * (yAB - yA)) / var_total)
        rows.append({
            "参数": name,
            "中文名": CN_NAMES.get(name, name),
            "一阶指数": s_i,
            "贡献占比%": s_i * 100,
        })

    try:
        import pandas as pd
        table = pd.DataFrame(rows).sort_values("一阶指数", ascending=False)
        return table.reset_index(drop=True)
    except ImportError:
        rows.sort(key=lambda r: -r["一阶指数"])
        return rows


# ============================== 5. 画图 ====================================
def plot_oat(sweep: Dict[str, Dict[str, np.ndarray]],
             base: Dict[str, float],
             out_png: Optional[str] = None) -> None:
    """单因子敏感度曲线（蜘蛛图）。"""
    out_png = out_path(out_png, "sensitivity_oat.png")
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

    n = len(sweep)
    ncol = 3
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.0 * ncol, 3.3 * nrow))
    axes = np.atleast_1d(axes).ravel()

    base_out = model(base)
    for ax, (name, d) in zip(axes, sweep.items()):
        rel = d["values"] / base[name]          # 显示相对基准的倍数
        ax.plot(rel, d["outputs"], lw=1.9, color="#4c72b0")
        ax.axvline(1.0, color="gray", ls=":", lw=1.1)
        ax.axhline(base_out, color="gray", ls=":", lw=1.1)
        ax.plot([1.0], [base_out], "ro", ms=6)
        ax.set_title(safe(f"{CN_NAMES.get(name, name)}"))
        ax.set_xlabel(safe("相对基准倍数"))
        ax.set_ylabel(safe(OUTPUT_KEY))
        ax.grid(alpha=0.3)

    for ax in axes[n:]:
        ax.axis("off")

    fig.suptitle(safe("单因子敏感性分析（红点 = 基准情形）"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_heatmap(v1: np.ndarray, v2: np.ndarray, Z: np.ndarray,
                 p1: str, p2: str,
                 out_png: Optional[str] = None) -> None:
    """双因子热力图 + 等高线，论文标准配图。"""
    out_png = out_path(out_png, "sensitivity_heatmap.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    fig, ax = plt.subplots(figsize=(7.4, 5.8))
    cf = ax.contourf(v1, v2, Z, levels=24, cmap="viridis")
    cs = ax.contour(v1, v2, Z, levels=10, colors="white",
                    linewidths=0.7, alpha=0.7)
    ax.clabel(cs, inline=True, fontsize=7, fmt="%.0f")

    ax.set_xlabel(safe(CN_NAMES.get(p1, p1)))
    ax.set_ylabel(safe(CN_NAMES.get(p2, p2)))
    ax.set_title(safe(f"双因子敏感性：{CN_NAMES.get(p1, p1)} 与 "
                      f"{CN_NAMES.get(p2, p2)} 对 {OUTPUT_KEY} 的影响"))
    fig.colorbar(cf, ax=ax, label=safe(OUTPUT_KEY))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


def plot_tornado(rows: List[Dict[str, object]],
                 out_png: Optional[str] = None) -> None:
    """龙卷风图：按极差排序的横向条形，一眼看出谁最关键。"""
    out_png = out_path(out_png, "sensitivity_tornado.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    base_out = float(rows[0]["基准输出"]) if "基准输出" in rows[0] else 0.0
    labels = [str(r["中文名"]) for r in rows]
    lows = [float(r["输出最小值"]) - base_out for r in rows]
    highs = [float(r["输出最大值"]) - base_out for r in rows]

    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(8.0, 0.62 * len(rows) + 1.8))
    ax.barh(y, highs, color="#c0392b", alpha=0.8, label=safe("参数增大方向"))
    ax.barh(y, lows, color="#4c72b0", alpha=0.8, label=safe("参数减小方向"))
    ax.set_yticks(y)
    ax.set_yticklabels([safe(l) for l in labels])
    ax.axvline(0, color="black", lw=1.2)
    ax.set_xlabel(safe(f"{OUTPUT_KEY} 相对基准的变化量"))
    ax.set_title(safe("龙卷风图：参数影响力排序"))
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("单因子与双因子敏感性分析（模型是模拟的，替换成你的模型）")
    print("=" * 66)

    base_out = model(BASE)
    print(f"\n[基准情形] {OUTPUT_KEY} = {base_out:.3f}")
    print(f"[参数基准值] {BASE}")

    # --- 单因子 ---
    sweep = oat_sweep(BASE)
    table = compute_sensitivity(sweep, BASE)

    print("\n[单因子敏感度排序]（按弹性绝对值）")
    try:
        print(table.to_string(index=False))
    except AttributeError:
        for r in table:
            print(r)

    # --- 结论 ---
    print("\n[结论]")
    try:
        top = table.iloc[0]
        print(f"  最敏感参数：{safe(top['中文名'])}"
              f"（弹性 {top['弹性系数']:.4f}）")
        for _, r in table.iterrows():
            e = r["弹性系数"]
            level = ("极敏感" if abs(e) > 1.0 else
                     "敏感" if abs(e) > 0.5 else
                     "一般" if abs(e) > 0.2 else "不敏感")
            print(f"    {safe(r['中文名']):<8} 弹性={e:+8.4f}  "
                  f"极差比={r['极差比%']:7.2f}%  -> {safe(level)}")
    except AttributeError:
        pass

    # 弹性符号的解读
    print("\n[解读] 弹性为负说明该参数增大时输出下降，"
          "这类参数是「反向杠杆」，定价/成本决策时要特别注意。")

    # --- 双因子 ---
    p1, p2 = TWO_WAY_PAIR
    print(f"\n[双因子扫描] {safe(CN_NAMES[p1])} × {safe(CN_NAMES[p2])}")
    v1, v2, Z = two_way_sweep(BASE, p1, p2, n=40)
    print(f"  网格 {Z.shape}，{OUTPUT_KEY} 范围 "
          f"[{Z.min():.2f}, {Z.max():.2f}]")
    iz, ix = np.unravel_index(int(np.argmax(Z)), Z.shape)
    print(f"  最优点：{safe(CN_NAMES[p1])}={v1[ix]:.3f}, "
          f"{safe(CN_NAMES[p2])}={v2[iz]:.3f} -> {Z[iz, ix]:.3f}")

    ii = interaction_index(BASE, p1, p2)
    print(f"  交互作用指数 = {ii:.6f}")
    print("  " + ("两参数存在明显交互，必须联合调优。"
                  if abs(ii) > 0.01 else
                  "交互作用很弱，可分别优化。"))

    # --- 方差分解 ---
    print("\n[方差分解] Sobol 一阶指数（谁贡献了最多的输出不确定性）")
    sobol = sobol_like(BASE, n_samples=1500, seed=5)
    try:
        print(sobol.to_string(index=False))
    except AttributeError:
        for r in sobol:
            print(r)

    # 画图（龙卷风图需要基准输出，补进去）
    rows_for_tornado = []
    try:
        for _, r in table.iterrows():
            r = dict(r)
            r["基准输出"] = base_out
            rows_for_tornado.append(r)
    except AttributeError:
        for r in table:
            r["基准输出"] = base_out
            rows_for_tornado.append(r)

    plot_oat(sweep, BASE)
    plot_heatmap(v1, v2, Z, p1, p2)
    plot_tornado(rows_for_tornado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
