# -*- coding: utf-8 -*-
"""描述性统计与分布检验 —— 代码骨架（可直接复制使用）

【解决什么问题】
  建模前先回答三个问题：数据长什么样（中心/离散/偏度峰度）、
  是否符合正态（决定后面用 t 检验还是秩检验）、有没有偏态需要变换。

【要改哪几行】
  1. `build_sample()`  —— 换成你自己的数据，例如
         data = pd.read_csv("your_data.csv")["your_column"].values
  2. `ALPHA`           —— 显著性水平，默认 0.05
  3. `GROUPS`          —— 分组名，画图例用

【输入】一维数值数组（或若干组）
【输出】描述统计表、正态性检验结论、QQ 图与直方图

【注意】下面的数据是模拟的，替换成你的数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional

import numpy as np


# --------------------------------------------------------------------------
# mcmplot 引导：向上找到项目的 core/ 目录，装上中文字体。
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
    """中文文本过一遍 mcmplot.safe()，把字体画不出的字符换掉。"""
    return mcmplot.safe(text) if mcmplot is not None else str(text)


# ============================== 参数区（改这里）=============================
ALPHA = 0.05                # 显著性水平
GROUPS: Dict[str, str] = {  # 变量名 -> 中文显示名
    "score": "成绩",
    "income": "收入",
}


# ============================== 1. 模拟数据 ================================
def build_sample() -> Dict[str, np.ndarray]:
    """构造两组数据：一组近正态（成绩），一组明显右偏（收入）。

    >>> 换成你的数据 <<<
    """
    rng = np.random.default_rng(7)
    return {
        "score": rng.normal(75.0, 9.0, 300),              # 近正态
        "income": rng.lognormal(mean=2.2, sigma=0.55, size=300) * 1e4,  # 右偏
    }


# ============================== 2. 描述统计 ================================
def describe(x: np.ndarray, name: str) -> Dict[str, float]:
    """算一组描述统计量。

    偏度 skewness：0 对称；>0 右偏（长尾在右）。
    峰度 kurtosis：这里给的是**超额峰度**（正态为 0），pandas 默认口径。
    """
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    q1, q3 = np.percentile(x, [25, 75])
    return {
        "变量": name,
        "样本量": int(x.size),
        "均值": float(np.mean(x)),
        "标准差": float(np.std(x, ddof=1)),
        "最小值": float(np.min(x)),
        "Q1": float(q1),
        "中位数": float(np.median(x)),
        "Q3": float(q3),
        "最大值": float(np.max(x)),
        "偏度": float(_skew(x)),
        "超额峰度": float(_kurtosis(x)),
    }


def _skew(x: np.ndarray) -> float:
    """样本偏度（Fisher-Pearson 标准化矩）。手算避免依赖 scipy。"""
    n = x.size
    m = x.mean()
    s = x.std(ddof=0)
    if s == 0:
        return 0.0
    return float((((x - m) / s) ** 3).sum() * n / ((n - 1) * (n - 2)))


def _kurtosis(x: np.ndarray) -> float:
    """样本超额峰度。正态分布下约等于 0。"""
    n = x.size
    m = x.mean()
    s = x.std(ddof=0)
    if s == 0:
        return 0.0
    g2 = float((((x - m) / s) ** 4).mean() - 3.0)
    return g2 * (n - 1) / ((n - 2) * (n - 3)) if n > 3 else g2


# ============================== 3. 分布检验 ================================
def normality_tests(x: np.ndarray) -> Dict[str, object]:
    """做三个正态性检验：Shapiro-Wilk、D'Agostino、Jarque-Bera。

    为什么做三个：单一检验会骗人。Shapiro 对样本量 > 5000 过于敏感，
    JB 依赖偏度峰度（大样本才稳）。三个结论一致才敢下判断。
    """
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    res: Dict[str, object] = {"n": int(x.size)}

    try:
        from scipy import stats
    except ImportError:
        # 没有 scipy 时用偏度/峰度自算 Jarque-Bera，结论依然可用。
        # 卡方(2) 的 95% / 99% 分位数分别是 5.991 / 9.210。
        if x.size >= 8:
            n = x.size
            s = x.std(ddof=0)
            skew = _skew(x)
            kurt = _kurtosis(x)
            jb = n / 6.0 * (skew ** 2 + kurt ** 2 / 4.0)
            # 卡方(2) 上尾概率闭式解 = exp(-JB/2)
            p = float(np.exp(-jb / 2.0))
            res["jarque_bera"] = {"stat": float(jb), "p": p}
            res["note"] = "未安装 scipy，仅用自算 Jarque-Bera 检验"
        else:
            res["note"] = "未安装 scipy，且样本量不足以做 JB 检验"
        return res

    # Shapiro-Wilk：小样本（n < 5000）最有力
    if 3 <= x.size <= 5000:
        stat, p = stats.shapiro(x)
        res["shapiro"] = {"stat": float(stat), "p": float(p)}
    else:
        res["shapiro"] = None        # 样本太大，该检验不适用

    # D'Agostino-Pearson：基于偏度峰度，n >= 8
    if x.size >= 8:
        stat, p = stats.normaltest(x)
        res["dagostino"] = {"stat": float(stat), "p": float(p)}

    # Jarque-Bera：大样本常用
    if x.size >= 8:
        stat, p = stats.jarque_bera(x)
        res["jarque_bera"] = {"stat": float(stat), "p": float(p)}

    return res


def print_normality(name: str, res: Dict[str, object]) -> bool:
    """打印检验结果，返回"是否认为服从正态"。"""
    print(f"\n  [{safe(name)}] 正态性检验（α = {ALPHA}）")
    note = res.get("note")
    if note:
        print(f"    提示：{safe(note)}")
    votes = []
    for key, label in [("shapiro", "Shapiro-Wilk"),
                       ("dagostino", "D'Agostino"),
                       ("jarque_bera", "Jarque-Bera")]:
        r = res.get(key)
        if r is None:
            # 只有"样本量不适用"和"根本没跑"两种可能，说清楚是哪一种
            print(f"    {label:<14} 未进行（样本量不适用或缺 scipy）")
            continue
        ok = r["p"] > ALPHA
        votes.append(ok)
        verdict = "不拒绝正态" if ok else "拒绝正态"
        print(f"    {label:<14} 统计量={r['stat']:8.4f}  p={r['p']:.4g}  -> {safe(verdict)}")

    is_normal = bool(votes) and all(votes)
    conclusion = "认为近似正态" if is_normal else "认为非正态（建议用秩检验/变换）"
    print(f"    综合结论：{safe(conclusion)}")
    return is_normal


# ============================== 4. 画图 ====================================
def plot_diagnostics(data: Dict[str, np.ndarray],
                     out_png: Optional[str] = None) -> None:
    """画直方图 + QQ 图，一眼看出偏态和尾部行为。"""
    out_png = out_path(out_png, "descriptive_qq.png")
    if mcmplot is None:
        print("\n[跳过画图] 没找到 mcmplot 模块")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[跳过画图] 没装 matplotlib")
        return

    mcmplot.setup()          # 必须先 setup，否则中文变豆腐块

    keys = list(data.keys())
    fig, axes = plt.subplots(2, len(keys), figsize=(5.0 * len(keys), 7.0))
    axes = np.atleast_2d(axes)

    for j, key in enumerate(keys):
        x = data[key]
        label = GROUPS.get(key, key)

        # 上排：直方图 + 正态密度参考线
        ax = axes[0, j]
        ax.hist(x, bins=30, density=True, color="#4c72b0",
                edgecolor="white", alpha=0.85)
        xs = np.linspace(x.min(), x.max(), 200)
        mu, sd = x.mean(), x.std(ddof=1)
        pdf = np.exp(-0.5 * ((xs - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi))
        ax.plot(xs, pdf, "r--", lw=1.8, label=safe("正态参考"))
        ax.set_title(safe(f"{label}的分布（偏度={_skew(x):.2f}）"))
        ax.set_ylabel(safe("概率密度"))
        ax.legend(fontsize=8)

        # 下排：QQ 图
        ax = axes[1, j]
        try:
            from scipy import stats
            (osm, osr), (slope, intercept, _) = stats.probplot(x, dist="norm")
            ax.plot(osm, osr, "o", ms=3, alpha=0.6, label=safe("样本分位数"))
            ax.plot(osm, slope * np.asarray(osm) + intercept, "r-", lw=1.5,
                    label=safe("正态参考线"))
        except ImportError:
            ax.text(0.5, 0.5, safe("需要 scipy 才能画 QQ 图"),
                    ha="center", va="center", transform=ax.transAxes)
        ax.set_title(safe(f"{label}的 QQ 图"))
        ax.set_xlabel(safe("理论分位数"))
        ax.set_ylabel(safe("样本分位数"))
        ax.legend(fontsize=8)

    fig.suptitle(safe("分布诊断：直方图与 QQ 图"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("描述性统计与分布检验（数据是模拟的，替换成你的数据）")
    print("=" * 66)

    data = build_sample()

    # --- 描述统计表 ---
    rows = [describe(v, GROUPS.get(k, k)) for k, v in data.items()]
    try:
        import pandas as pd
        table = pd.DataFrame(rows).set_index("变量")
        print("\n[描述统计]")
        print(table.round(3).to_string())
    except ImportError:
        for r in rows:
            print(r)

    # --- 正态性检验 ---
    print("\n[正态性检验]")
    verdicts = {}
    for key, arr in data.items():
        label = GROUPS.get(key, key)
        verdicts[key] = print_normality(label, normality_tests(arr))

    # --- 给出后续建模建议 ---
    print("\n[建模建议]")
    for key, ok in verdicts.items():
        label = GROUPS.get(key, key)
        if ok:
            print(f"  {safe(label)}：可用参数方法（t 检验、Pearson 相关、线性回归）")
        else:
            print(f"  {safe(label)}：建议取对数或改用秩方法"
                  f"（Mann-Whitney、Spearman）")

    # 右偏数据取对数后的效果
    if "income" in data:
        raw_skew = _skew(data["income"])
        log_skew = _skew(np.log(data["income"]))
        print(f"\n[变换效果] 收入：原始偏度={raw_skew:.2f} -> "
              f"取对数后偏度={log_skew:.2f}")

    plot_diagnostics(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
