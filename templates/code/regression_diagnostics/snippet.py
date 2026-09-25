# -*- coding: utf-8 -*-
"""回归建模与残差诊断 —— 代码骨架（可直接复制使用）

【解决什么问题】
  跑出一个回归模型只是开始。评委真正看的是：系数有没有意义、
  残差是不是白噪声、有没有异方差。这个骨架把"建模 + 四项诊断"一次做完。

  诊断四件套：
  1. 残差 vs 拟合值  —— 看是否随机散布（有喇叭形 = 异方差）
  2. QQ 图           —— 看残差是否正态
  3. 残差 vs 自变量  —— 看是否漏了非线性项
  4. 库克距离        —— 找强影响点（个别点主导结论）

【要改哪几行】
  1. `build_frame()` —— 换成你自己的数据
  2. `TARGET`        —— 因变量列名
  3. `FEATURES`      —— 自变量列名列表（None = 除 TARGET 外全部）

【输入】数值型 DataFrame
【输出】回归系数表（含 p 值）、R²/调整R²、四张诊断图、异常点清单

【注意】下面的数据是模拟的，替换成你的数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


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


def safe(text: object, math: bool = False) -> str:
    return mcmplot.safe(text, math=math) if mcmplot is not None else str(text)


# ============================== 参数区（改这里）=============================
TARGET = "yield"
FEATURES: Optional[List[str]] = None      # None = 用除 TARGET 外的所有列
COOK_THRESHOLD = 4.0 / 100                # 库克距离阈值，常用 4/n

CN_NAMES: Dict[str, str] = {
    "yield": "产量",
    "fertilizer": "施肥量",
    "water": "灌溉量",
    "sunlight": "日照时数",
    "temperature": "温度",
}


# ============================== 1. 模拟数据 ================================
def build_frame() -> pd.DataFrame:
    """构造一份**带异方差**的数据，让诊断图真的能看出问题。

    >>> 换成你的数据 <<<
        return pd.read_csv("your_data.csv")
    """
    rng = np.random.default_rng(2024)
    n = 180

    fertilizer = rng.uniform(0, 100, n)
    water = rng.uniform(10, 60, n)
    sunlight = rng.uniform(4, 12, n)
    temperature = rng.normal(22, 4, n)

    # 真实关系：二次项（施肥过量反而减产）+ 线性项
    signal = (0.9 * fertilizer - 0.006 * fertilizer ** 2
              + 1.5 * water + 0.8 * sunlight + 0.5 * temperature)
    # 噪声随施肥量增大 -> 异方差，标准化残差图会呈喇叭形
    noise = rng.normal(0, 1, n) * (2.0 + 0.06 * fertilizer)
    y = signal + noise - 20.0

    return pd.DataFrame({
        "yield": y.round(3),
        "fertilizer": fertilizer.round(2),
        "water": water.round(2),
        "sunlight": sunlight.round(2),
        "temperature": temperature.round(2),
    })


# ============================== 2. OLS 拟合 ================================
def ols_fit(X: np.ndarray, y: np.ndarray) -> Dict[str, object]:
    """普通最小二乘，返回系数与全部诊断所需的量。

    公式：beta = (X'X)^-1 X'y
    残差 e = y - X beta，无偏方差 s² = e'e / (n - p)
    """
    n, p = X.shape
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)   # lstsq 比显式求逆稳
    y_hat = X @ beta
    resid = y - y_hat

    dof = n - p
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    # 调整 R² 惩罚变量个数，变量越多不一定越大
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / dof if dof > 0 else np.nan
    sigma2 = ss_res / dof if dof > 0 else np.nan

    # 系数标准误：se = sqrt(diag(sigma2 * (X'X)^-1))
    try:
        xtx_inv = np.linalg.inv(X.T @ X)
        se = np.sqrt(np.diag(xtx_inv) * sigma2)
        # 帽子矩阵对角元 h_ii（杠杆值）
        hat = np.einsum("ij,jk,ik->i", X, xtx_inv, X)
    except np.linalg.LinAlgError:
        se = np.full(p, np.nan)
        hat = np.full(n, np.nan)

    with np.errstate(divide="ignore", invalid="ignore"):
        t_stat = beta / se
        p_val = 2.0 * _t_sf(np.abs(t_stat), dof)

    # 库克距离：衡量第 i 个点对全部拟合值的影响
    with np.errstate(divide="ignore", invalid="ignore"):
        cook = (resid ** 2 / (p * sigma2)) * (hat / (1.0 - hat) ** 2)

    return {
        "beta": beta, "se": se, "t": t_stat, "p_val": p_val,
        "resid": resid, "y_hat": y_hat, "hat": hat, "cook": cook,
        "r2": r2, "adj_r2": adj_r2, "sigma2": sigma2,
        "n": n, "n_params": p, "dof": dof,
    }


def _t_sf(t: np.ndarray, dof: int) -> np.ndarray:
    """双侧 t 尾概率。

    有 scipy 用 scipy；没有就退化成标准正态近似（n 上百时足够）。
    注意返回的一定是**数组**：标量进标量出会让后面的 p[i] 直接 IndexError。
    """
    t = np.atleast_1d(np.asarray(t, dtype=float))
    try:
        from scipy import stats
        return np.asarray(2.0 * stats.t.sf(np.abs(t), dof))
    except ImportError:
        from math import erfc, sqrt
        v = np.vectorize(lambda z: erfc(abs(z) / sqrt(2.0)))
        return np.asarray(v(t), dtype=float)


def coefficient_table(fit: Dict[str, object],
                      names: List[str]) -> pd.DataFrame:
    """拼系数表，含置信区间。"""
    beta = np.asarray(fit["beta"])
    se = np.asarray(fit["se"])
    t = np.asarray(fit["t"])
    p = np.atleast_1d(np.asarray(fit["p_val"], dtype=float))
    dof = int(fit["dof"])

    try:
        from scipy import stats
        tcrit = float(stats.t.ppf(0.975, dof))
    except ImportError:
        tcrit = 1.96

    rows = []
    for i, nm in enumerate(names):
        star = ""
        if not np.isnan(p[i]):
            star = ("***" if p[i] < 0.001 else "**" if p[i] < 0.01
                    else "*" if p[i] < 0.05 else "")
        rows.append({
            "变量": nm,
            "中文名": CN_NAMES.get(nm, nm),
            "系数": round(float(beta[i]), 4),
            "标准误": round(float(se[i]), 4),
            "t值": round(float(t[i]), 3),
            "p值": float(p[i]) if not np.isnan(p[i]) else np.nan,
            "显著性": star,
            "CI下界": round(float(beta[i] - tcrit * se[i]), 4),
            "CI上界": round(float(beta[i] + tcrit * se[i]), 4),
        })
    return pd.DataFrame(rows).set_index("变量")


# ============================== 3. 诊断 ====================================
def diagnose(fit: Dict[str, object],
             residuals: np.ndarray) -> List[str]:
    """做统计层面的诊断，返回问题清单。"""
    issues: List[str] = []

    # --- 1. Shapiro 正态性（没 scipy 时用 JB 检验兜底）---
    try:
        from scipy import stats
        if residuals.size >= 3:
            _, p = stats.shapiro(residuals[:5000])
            if p < 0.05:
                issues.append(f"残差不服从正态（Shapiro p={p:.4g}）"
                              f"——考虑对 y 取对数或加变量")
            else:
                print(f"  [正态性] Shapiro p={p:.4f}，残差近似正态")
    except ImportError:
        n_r = residuals.size
        m_r, s_r = residuals.mean(), residuals.std(ddof=0)
        if s_r > 0 and n_r > 3:
            skew = float((((residuals - m_r) / s_r) ** 3).mean())
            kurt = float((((residuals - m_r) / s_r) ** 4).mean() - 3.0)
            jb = n_r / 6.0 * (skew ** 2 + kurt ** 2 / 4.0)
            # 卡方(2) 的 95% 分位数 = 5.991
            if jb > 5.991:
                issues.append(f"残差偏离正态（Jarque-Bera={jb:.3f} > 5.991）"
                              f"——考虑对 y 取对数或加变量")
            else:
                print(f"  [正态性] Jarque-Bera={jb:.3f}，残差近似正态")

    # --- 2. Breusch-Pagan 异方差检验（手算，不依赖 statsmodels）---
    resid = residuals
    n = resid.size
    e2 = resid ** 2
    # 把 e² 对拟合值回归，看解释力
    y_hat = np.asarray(fit["y_hat"])
    Z = np.column_stack([np.ones(n), y_hat])
    g, *_ = np.linalg.lstsq(Z, e2, rcond=None)
    e2_hat = Z @ g
    ss_res = float(((e2 - e2_hat) ** 2).sum())
    ss_tot = float(((e2 - e2.mean()) ** 2).sum())
    r2_bp = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    lm = n * r2_bp
    try:
        from scipy import stats
        p_bp = float(stats.chi2.sf(lm, 1))
        if p_bp < 0.05:
            issues.append(f"存在异方差（Breusch-Pagan p={p_bp:.4g}）"
                          f"——考虑加权最小二乘或对 y 取对数")
        else:
            print(f"  [异方差] Breusch-Pagan p={p_bp:.4f}，未见显著异方差")
    except ImportError:
        import math
        # 卡方(1) 的上尾概率有闭式解 = erfc(sqrt(LM/2))
        p_bp = math.erfc(math.sqrt(max(lm, 0.0) / 2.0))
        if p_bp < 0.05:
            issues.append(f"存在异方差（Breusch-Pagan LM={lm:.3f}，"
                          f"p={p_bp:.4g}）——考虑加权最小二乘或对 y 取对数")
        else:
            print(f"  [异方差] Breusch-Pagan LM={lm:.3f}，"
                  f"p={p_bp:.4f}，未见显著异方差")

    # --- 3. 强影响点 ---
    cook = np.asarray(fit["cook"])
    n_out = int((cook > COOK_THRESHOLD).sum())
    print(f"  [强影响点] 库克距离 > {COOK_THRESHOLD:.4f} 的点：{n_out} 个")
    if n_out > 0:
        idx = np.argsort(-cook)[:5]
        print(f"    影响最大的 5 个样本行号：{idx.tolist()}")
        if n_out > 0.05 * len(cook):
            issues.append(f"{n_out} 个强影响点（占比 "
                          f"{n_out / len(cook) * 100:.1f}%）"
                          f"——检查是否有录入错误")

    return issues


# ============================== 4. 画图 ====================================
def plot_diagnostics(fit: Dict[str, object], df: pd.DataFrame,
                     features: List[str],
                     out_png: Optional[str] = None) -> None:
    """四联诊断图，这是论文里回归章节的标准配图。"""
    out_png = out_path(out_png, "regression_diagnostics.png")
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

    resid = np.asarray(fit["resid"])
    y_hat = np.asarray(fit["y_hat"])
    cook = np.asarray(fit["cook"])
    std_resid = resid / np.sqrt(fit["sigma2"]) if fit["sigma2"] else resid

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.6))

    # (1) 残差 vs 拟合值：最该看的一张，喇叭形=异方差，弧形=漏了非线性
    ax = axes[0, 0]
    ax.scatter(y_hat, resid, s=16, alpha=0.65, color="#4c72b0")
    ax.axhline(0, color="red", ls="--", lw=1.2)
    ax.set_xlabel(safe("拟合值"))
    ax.set_ylabel(safe("残差"))
    ax.set_title(safe("残差 vs 拟合值（看喇叭形/弧形）"))

    # (2) QQ 图
    ax = axes[0, 1]
    try:
        from scipy import stats
        (osm, osr), (slope, intercept, _) = stats.probplot(resid, dist="norm")
        ax.plot(osm, osr, "o", ms=3.5, alpha=0.65)
        ax.plot(osm, slope * np.asarray(osm) + intercept, "r-", lw=1.5)
    except ImportError:
        sorted_r = np.sort(resid)
        ax.plot(sorted_r, sorted_r, "o", ms=3)
    ax.set_title(safe("残差 QQ 图（看是否正态）"))
    ax.set_xlabel(safe("理论分位数"))
    ax.set_ylabel(safe("样本分位数"))

    # (3) 标准化残差 vs 自变量（每个自变量一色一列，这里画第一个）
    ax = axes[1, 0]
    col = features[0]
    ax.scatter(df[col].values, std_resid, s=16, alpha=0.65, color="#55a868")
    ax.axhline(0, color="red", ls="--", lw=1.2)
    ax.axhline(2, color="gray", ls=":", lw=1.0)
    ax.axhline(-2, color="gray", ls=":", lw=1.0)
    ax.set_xlabel(safe(CN_NAMES.get(col, col)))
    ax.set_ylabel(safe("标准化残差"))
    ax.set_title(safe(f"标准化残差 vs {CN_NAMES.get(col, col)}"))

    # (4) 库克距离
    ax = axes[1, 1]
    ax.stem(range(len(cook)), cook, basefmt=" ")
    ax.axhline(COOK_THRESHOLD, color="red", ls="--", lw=1.2,
               label=safe(f"阈值 {COOK_THRESHOLD:.4f}"))
    ax.set_xlabel(safe("样本序号"))
    ax.set_ylabel(safe("库克距离"))
    ax.set_title(safe("强影响点诊断"))
    ax.legend(fontsize=8)

    r2 = fit["r2"]
    adj = fit["adj_r2"]
    fig.suptitle(safe(f"回归诊断（$R^2$={r2:.4f}，调整 $R^2$={adj:.4f}）"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_fit_vs_actual(fit: Dict[str, object], y: np.ndarray,
                       out_png: Optional[str] = None) -> None:
    """预测值 vs 真实值散点，理想情况落在 45 度线上。"""
    out_png = out_path(out_png, "regression_fit.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()
    y_hat = np.asarray(fit["y_hat"])

    fig, ax = plt.subplots(figsize=(5.4, 5.2))
    ax.scatter(y, y_hat, s=18, alpha=0.65, color="#4c72b0",
               label=safe("样本"))
    lo = float(min(y.min(), y_hat.min()))
    hi = float(max(y.max(), y_hat.max()))
    ax.plot([lo, hi], [lo, hi], "r--", lw=1.5, label=safe("理想线 y=x"))
    ax.set_xlabel(safe("真实值"))
    ax.set_ylabel(safe("预测值"))
    ax.set_title(safe(f"拟合效果（$R^2$={fit['r2']:.4f}）"))
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("回归建模与残差诊断（数据是模拟的，替换成你的数据）")
    print("=" * 66)

    df = build_frame()
    features = FEATURES or [c for c in df.columns if c != TARGET]
    names = ["const"] + features

    y = df[TARGET].values.astype(float)
    X = np.column_stack([np.ones(len(df))] + [df[c].values for c in features])

    fit = ols_fit(X, y)

    print(f"\n[模型] n={fit['n']}  参数个数={fit['n_params']}  自变量={features}")
    print(f"[拟合优度] R2={fit['r2']:.4f}  调整R2={fit['adj_r2']:.4f}  "
          f"残差标准误={np.sqrt(fit['sigma2']):.4f}")

    table = coefficient_table(fit, names)
    print("\n[系数表]  显著性标记：*** p<0.001  ** p<0.01  * p<0.05")
    print(table.to_string())

    print("\n[残差诊断]")
    issues = diagnose(fit, np.asarray(fit["resid"]))

    print("\n[结论]")
    if issues:
        for i, msg in enumerate(issues, 1):
            print(f"  {i}. {safe(msg)}")
    else:
        print("  四项诊断均通过，模型可用。")

    # 贡献最大的变量
    coef = table.drop(index="const", errors="ignore")
    if not coef.empty:
        biggest = coef["系数"].abs().idxmax()
        print(f"\n[解读] 影响最大的变量：{safe(CN_NAMES.get(biggest, biggest))}"
              f"（系数 {coef.loc[biggest, '系数']}）")

    plot_diagnostics(fit, df, features)
    plot_fit_vs_actual(fit, y)
    return 0


if __name__ == "__main__":
    sys.exit(main())
