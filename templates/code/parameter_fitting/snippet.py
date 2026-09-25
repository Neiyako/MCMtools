# -*- coding: utf-8 -*-
"""参数拟合（最小二乘 + 网格搜索局部精化）—— 代码骨架

【解决什么问题】
  模型结构定了，但参数不知道。这个骨架给两条互补的路：

  * `fit_leastsq()` —— 非线性最小二乘（Gauss-Newton / Levenberg-Marquardt），
                       有 scipy 用 scipy，没有就走手写 Gauss-Newton。
  * `grid_search()` —— 先粗网格扫一遍定位全局最优附近，
                       再局部精化。防止最小二乘掉进局部极小。

  比赛里正确做法是两个都用：网格给初值，最小二乘给精度。

【要改哪几行】
  1. `model()`      —— 你的模型函数 f(x; params)
  2. `PARAM_SPEC`   —— 参数名 + 搜索范围（网格用）
  3. `p0`           —— 最小二乘初值
  4. `build_data()` —— 换成你的实验数据

【输入】自变量 x、观测值 y（可带误差）
【输出】最优参数、拟合优度 R²、参数置信区间、拟合图与残差图

【注意】下面的数据是模拟的，替换成你的数据。
"""

from __future__ import annotations

import itertools
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
PARAM_NAMES = ["a", "b", "c"]
CN_NAMES = {"a": "幅值 a", "b": "衰减率 b", "c": "偏置 c"}

# 网格搜索范围：(起点, 终点, 份数)
PARAM_SPEC: Dict[str, Tuple[float, float, int]] = {
    "a": (0.5, 3.0, 12),
    "b": (0.1, 1.5, 12),
    "c": (-2.0, 2.0, 8),
}

p0 = [1.5, 0.6, 0.2]        # 最小二乘初值（可以先跑网格再填这里）
TRUE_PARAMS = {"a": 2.1, "b": 0.55, "c": -0.4}   # 仅用于验证：真值


# ============================== 1. 模型与数据 ==============================
def model(x: np.ndarray, p: Dict[str, float]) -> np.ndarray:
    """你的模型函数。这里用阻尼振荡：

        y = a * exp(-b*x) * cos(1.8*x) + c

    >>> 换成你的模型 <<<
    """
    return p["a"] * np.exp(-p["b"] * x) * np.cos(1.8 * x) + p["c"]


def build_data() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """生成带噪声的模拟观测数据。

    >>> 换成你的数据 <<<
        x = ...; y = ...; sigma = ...
        return x, y, sigma
    """
    rng = np.random.default_rng(314)
    x = np.linspace(0.0, 8.0, 90)
    y_true = model(x, TRUE_PARAMS)
    sigma = 0.08 + 0.02 * x / x.max()          # 误差随 x 略增
    y = y_true + rng.normal(0, sigma)
    return x, y, sigma


# ============================== 2. 目标函数 ================================
def sse(x: np.ndarray, y: np.ndarray, p: Dict[str, float],
        sigma: Optional[np.ndarray] = None) -> float:
    """残差平方和。给了 sigma 就做加权（等价于最大似然）。"""
    pred = model(x, p)
    resid = (y - pred)
    if sigma is not None:
        resid = resid / sigma
    return float((resid ** 2).sum())


def r_squared(y: np.ndarray, pred: np.ndarray) -> float:
    """决定系数 R²，衡量拟合优度。"""
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def adjusted_r_squared(y: np.ndarray, pred: np.ndarray, k: int) -> float:
    """调整 R²，惩罚参数个数。"""
    n = y.size
    r2 = r_squared(y, pred)
    if n - k - 1 <= 0:
        return np.nan
    return 1.0 - (1.0 - r2) * (n - 1) / (n - k - 1)


# ============================== 3. 网格搜索 ================================
def grid_search(x: np.ndarray, y: np.ndarray,
                sigma: Optional[np.ndarray] = None,
                spec: Optional[Dict[str, Tuple[float, float, int]]] = None,
                top_k: int = 5) -> List[Tuple[Dict[str, float], float]]:
    """在参数网格上穷举，返回最优的 top_k 组。

    为什么先网格：最小二乘对初值敏感，初值给偏了会收敛到局部极小，
    而且**拟合出来的 R² 看起来还不错** —— 这种错误最难发现。
    粗网格加局部精化能有效规避。
    """
    spec = spec or PARAM_SPEC
    names = list(spec.keys())
    axes = [np.linspace(lo, hi, n) for (lo, hi, n) in (spec[k] for k in names)]

    results: List[Tuple[Dict[str, float], float]] = []
    total = int(np.prod([len(a) for a in axes]))
    print(f"  网格规模：{total} 个组合（{' x '.join(str(len(a)) for a in axes)}）")

    for combo in itertools.product(*axes):
        p = dict(zip(names, combo))
        results.append((p, sse(x, y, p, sigma)))

    results.sort(key=lambda kv: kv[1])
    return results[:top_k]


def local_refine(x: np.ndarray, y: np.ndarray,
                 p_start: Dict[str, float],
                 sigma: Optional[np.ndarray] = None,
                 shrink: float = 0.35, rounds: int = 4,
                 per_axis: int = 7) -> Tuple[Dict[str, float], float]:
    """局部精化：围绕当前最优点，逐轮缩小搜索范围再网格一遍。

    比梯度法慢但更稳，不受可导性限制，适合"模型里有 if/查表"的场合。
    """
    best_p = dict(p_start)
    best_sse = sse(x, y, best_p, sigma)
    step = {k: (PARAM_SPEC.get(k, (0, 1, 1))[1]
                - PARAM_SPEC.get(k, (0, 1, 1))[0]) * shrink
            for k in best_p}

    for r in range(rounds):
        improved = False
        for name in best_p:
            lo = best_p[name] - step[name]
            hi = best_p[name] + step[name]
            for cand in np.linspace(lo, hi, per_axis):
                trial = dict(best_p)
                trial[name] = float(cand)
                s = sse(x, y, trial, sigma)
                if s < best_sse:
                    best_sse, best_p = s, trial
                    improved = True
        step = {k: v * shrink for k, v in step.items()}
        print(f"    第 {r + 1} 轮精化：SSE = {best_sse:.6f}")
        if not improved and r >= 1:
            break

    return best_p, best_sse


# ============================== 4. 最小二乘 ================================
def fit_leastsq(x: np.ndarray, y: np.ndarray,
                p_init: List[float],
                sigma: Optional[np.ndarray] = None
                ) -> Tuple[Dict[str, float], float, np.ndarray]:
    """非线性最小二乘。

    优先用 scipy.optimize.curve_fit；没装 scipy 时用手写
    Gauss-Newton（数值差分求雅可比 + 阻尼），一样能收敛。

    返回 (最优参数, SSE, 参数协方差矩阵)。
    """
    names = PARAM_NAMES

    def f(xx, *args):
        return model(xx, dict(zip(names, args)))

    try:
        from scipy.optimize import curve_fit
        popt, pcov = curve_fit(f, x, y, p0=p_init,
                               sigma=sigma, absolute_sigma=False,
                               maxfev=20000)
        best = dict(zip(names, [float(v) for v in popt]))
        print("  [方法] scipy.optimize.curve_fit（Levenberg-Marquardt）")
        return best, sse(x, y, best, sigma), np.asarray(pcov)
    except ImportError:
        print("  [方法] 手写 Gauss-Newton（未安装 scipy）")
        return _gauss_newton(x, y, p_init, sigma, names)
    except Exception as exc:                       # noqa: BLE001
        print(f"  [方法] curve_fit 失败（{type(exc).__name__}），"
              f"退回手写 Gauss-Newton")
        return _gauss_newton(x, y, p_init, sigma, names)


def _gauss_newton(x: np.ndarray, y: np.ndarray,
                  p_init: List[float],
                  sigma: Optional[np.ndarray],
                  names: List[str],
                  max_iter: int = 120) -> Tuple[Dict[str, float], float, np.ndarray]:
    """手写 Gauss-Newton，带简单阻尼。

    每步：J = d r / d p（中心差分）
          delta = (J'J + lam*I)^-1 J'r
          p <- p + delta
    lam 是阻尼项，防止 J'J 奇异导致解跳飞。
    """
    p = np.array(p_init, dtype=float)
    k = p.size
    lam = 1e-6
    w = 1.0 / sigma if sigma is not None else None

    def residuals(pp: np.ndarray) -> np.ndarray:
        r = y - model(x, dict(zip(names, pp)))
        return r * w if w is not None else r

    r = residuals(p)
    cost = float((r ** 2).sum())

    for _ in range(max_iter):
        # 数值差分雅可比 J[i, j] = d r_i / d p_j
        J = np.zeros((x.size, k))
        for j in range(k):
            dp = max(1e-7, abs(p[j]) * 1e-6)
            pp = p.copy()
            pp[j] += dp
            pm = p.copy()
            pm[j] -= dp
            J[:, j] = (residuals(pp) - residuals(pm)) / (2.0 * dp)

        JtJ = J.T @ J
        Jtr = J.T @ r
        # 注意负号：最小二乘要**下降**，delta = -(J'J)^-1 J'r。
        # 漏掉负号会每步都让代价变大，阻尼逻辑随后一路拒绝，
        # 函数最后把初值原样返回 —— 看起来"收敛了"，其实一步没动。
        try:
            delta = -np.linalg.solve(JtJ + lam * np.eye(k), Jtr)
        except np.linalg.LinAlgError:
            delta = -np.linalg.lstsq(JtJ + lam * np.eye(k), Jtr,
                                     rcond=None)[0]

        p_new = p + delta
        r_new = residuals(p_new)
        cost_new = float((r_new ** 2).sum())

        if cost_new < cost:                 # 接受，减小阻尼
            p, r, cost = p_new, r_new, cost_new
            lam = max(lam * 0.5, 1e-12)
            if np.linalg.norm(delta) < 1e-10:
                break
        else:                               # 拒绝，加大阻尼再试
            lam *= 8.0
            if lam > 1e12:
                break

    # 协方差 ≈ (J'J)^-1 * s²，用于估参数标准误
    try:
        JtJ = J.T @ J
        dof = max(x.size - k, 1)
        s2 = cost / dof
        cov = np.linalg.inv(JtJ + 1e-12 * np.eye(k)) * s2
    except (np.linalg.LinAlgError, NameError):
        cov = np.full((k, k), np.nan)

    return dict(zip(names, [float(v) for v in p])), float(cost), cov


def bootstrap_ci(x: np.ndarray, y: np.ndarray, p_best: Dict[str, float],
                 sigma: Optional[np.ndarray] = None,
                 n_boot: int = 120,
                 alpha: float = 0.05) -> Dict[str, Tuple[float, float]]:
    """用残差自助法（bootstrap）估参数的 95% 置信区间。

    做法：从残差里重抽样，造出新的 y，再重新拟合。
    比解析式协方差更稳健，也对非正态残差更宽容。
    """
    rng = np.random.default_rng(99)
    names = list(p_best.keys())
    pred = model(x, p_best)
    resid = y - pred
    samples = {n: [] for n in names}

    for _ in range(n_boot):
        y_sim = pred + rng.choice(resid, size=resid.size, replace=True)
        try:
            p_b, _, _ = fit_leastsq_quiet(x, y_sim, [p_best[n] for n in names],
                                          sigma)
            for n in names:
                samples[n].append(p_b[n])
        except Exception:                       # noqa: BLE001
            continue

    out = {}
    lo_q, hi_q = 100 * alpha / 2, 100 * (1 - alpha / 2)
    for n in names:
        arr = np.asarray(samples[n], dtype=float)
        if arr.size >= 10:
            out[n] = (float(np.percentile(arr, lo_q)),
                      float(np.percentile(arr, hi_q)))
    return out


def fit_leastsq_quiet(x, y, p_init, sigma):
    """静默版最小二乘，避免 bootstrap 里刷屏。"""
    names = PARAM_NAMES

    def f(xx, *args):
        return model(xx, dict(zip(names, args)))

    try:
        from scipy.optimize import curve_fit
        popt, pcov = curve_fit(f, x, y, p0=p_init, sigma=sigma,
                               absolute_sigma=False, maxfev=20000)
        return dict(zip(names, [float(v) for v in popt])), 0.0, np.asarray(pcov)
    except ImportError:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            return _gauss_newton(x, y, p_init, sigma, names)


# ============================== 5. 画图 ====================================
def plot_fit(x: np.ndarray, y: np.ndarray, p_best: Dict[str, float],
             sigma: Optional[np.ndarray], r2: float,
             out_png: Optional[str] = None) -> None:
    """拟合曲线 + 数据点 + 残差子图。"""
    out_png = out_path(out_png, "parameter_fit.png")
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

    xs = np.linspace(x.min(), x.max(), 400)
    ys = model(xs, p_best)
    pred = model(x, p_best)

    fig, axes = plt.subplots(2, 1, figsize=(9.0, 6.4),
                             gridspec_kw={"height_ratios": [3, 1.2]})

    ax = axes[0]
    if sigma is not None:
        ax.errorbar(x, y, yerr=1.96 * sigma, fmt="o", ms=4, alpha=0.6,
                    color="#4c72b0", label=safe("观测值 ± 95%"))
    else:
        ax.plot(x, y, "o", ms=4, alpha=0.6, color="#4c72b0",
                label=safe("观测值"))
    ax.plot(xs, ys, "-", lw=2.2, color="#c0392b", label=safe("拟合曲线"))
    ax.set_ylabel(safe("y"))
    ax.set_title(safe(f"参数拟合结果（$R^2$={r2:.4f}）"))
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.stem(x, y - pred, basefmt=" ")
    ax.axhline(0, color="red", ls="--", lw=1.1)
    ax.set_xlabel(safe("x"))
    ax.set_ylabel(safe("残差"))
    ax.set_title(safe("残差分布（应无系统结构）"))
    ax.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("参数拟合：网格搜索 + 最小二乘（数据是模拟的，替换成你的数据）")
    print("=" * 66)

    x, y, sigma = build_data()
    print(f"\n[数据] {x.size} 个点，x 范围 [{x.min():.2f}, {x.max():.2f}]")
    print(f"[真值] {TRUE_PARAMS}（真实问题里当然不知道，这里只为验证方法）")

    # --- 第一步：粗网格定位 ---
    print("\n[第一步] 粗网格搜索")
    top = grid_search(x, y, sigma, PARAM_SPEC, top_k=3)
    for i, (p, s) in enumerate(top, 1):
        desc = "  ".join(f"{k}={v:.4f}" for k, v in p.items())
        print(f"  第{i}名 SSE={s:.5f}  {desc}")

    best_grid, sse_grid = top[0]

    # --- 第二步：局部精化 ---
    print("\n[第二步] 局部精化")
    refined, sse_refined = local_refine(x, y, best_grid, sigma)
    desc = "  ".join(f"{k}={v:.5f}" for k, v in refined.items())
    print(f"  精化后 SSE={sse_refined:.6f}  {desc}")

    # --- 第三步：最小二乘 ---
    print("\n[第三步] 非线性最小二乘")
    p_ls, sse_ls, cov = fit_leastsq(
        x, y, [refined[n] for n in PARAM_NAMES], sigma)
    desc = "  ".join(f"{k}={v:.5f}" for k, v in p_ls.items())
    print(f"  SSE={sse_ls:.6f}  {desc}")

    # --- 选最好的 ---
    candidates = [(sse_grid, best_grid, "网格"),
                  (sse_refined, refined, "网格+精化"),
                  (sse_ls, p_ls, "最小二乘")]
    candidates.sort(key=lambda t: t[0])
    best_sse, p_best, method = candidates[0]

    pred = model(x, p_best)
    r2 = r_squared(y, pred)
    adj_r2 = adjusted_r_squared(y, pred, len(PARAM_NAMES))

    print(f"\n[最优结果] 来自「{safe(method)}」")
    print(f"  {'参数':<10}{'估计值':>12}{'真值':>10}{'相对误差':>12}")
    for n in PARAM_NAMES:
        est, tru = p_best[n], TRUE_PARAMS.get(n, np.nan)
        rel = abs(est - tru) / abs(tru) * 100 if tru else np.nan
        print(f"  {CN_NAMES.get(n, n):<10}{est:12.5f}{tru:10.3f}{rel:11.2f}%")

    print(f"\n[拟合优度] R2={r2:.6f}  调整R2={adj_r2:.6f}  "
          f"RMSE={np.sqrt(best_sse / x.size):.5f}")

    # --- 参数标准误 ---
    if cov is not None and not np.all(np.isnan(cov)):
        se = np.sqrt(np.diag(cov))
        print("\n[参数标准误]（来自协方差矩阵对角元）")
        for n, s in zip(PARAM_NAMES, se):
            if not np.isnan(s):
                print(f"  {CN_NAMES.get(n, n):<10} SE = {s:.6f}  "
                      f"（估计值 ± {1.96 * s:.5f}）")

    # --- Bootstrap 置信区间 ---
    print("\n[Bootstrap 95% 置信区间]")
    ci = bootstrap_ci(x, y, p_best, sigma, n_boot=100)
    for n in PARAM_NAMES:
        if n in ci:
            print(f"  {CN_NAMES.get(n, n):<10} [{ci[n][0]:.5f}, {ci[n][1]:.5f}]")

    plot_fit(x, y, p_best, sigma, r2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
