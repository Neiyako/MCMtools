# -*- coding: utf-8 -*-
"""相关性分析与多重共线性诊断（VIF）—— 代码骨架（可直接复制使用）

【解决什么问题】
  回归之前必须先看两件事：
  1. 哪些变量和因变量相关（筛特征）；
  2. 自变量之间是否高度相关（多重共线性会把系数符号搞反）。

  VIF（方差膨胀因子）= 1 / (1 - R²_j)，其中 R²_j 是第 j 个自变量
  被其余自变量回归出来的决定系数。经验阈值：VIF > 10 说明共线性严重。

【要改哪几行】
  1. `build_frame()`  —— 换成你自己的数据
  2. `TARGET`         —— 因变量列名
  3. `VIF_THRESHOLD`  —— 共线性阈值，默认 10.0

【输入】一个数值型 DataFrame（含因变量）
【输出】相关系数矩阵、VIF 表、热力图与剔除建议

【注意】下面的数据是模拟的，替换成你的数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

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


def safe(text: object) -> str:
    return mcmplot.safe(text) if mcmplot is not None else str(text)


# ============================== 参数区（改这里）=============================
TARGET = "price"
VIF_THRESHOLD = 10.0        # 论文里普遍采用 10；严格一点可用 5
CORR_METHOD = "pearson"     # pearson | spearman（非正态用 spearman）

CN_NAMES: Dict[str, str] = {
    "price": "房价",
    "area": "面积",
    "rooms": "房间数",
    "age": "房龄",
    "floor_area": "建筑面积",
    "dist_center": "距市中心",
}


# ============================== 1. 模拟数据 ================================
def build_frame() -> pd.DataFrame:
    """构造一份带**故意共线性**的数据。

    floor_area 和 area 几乎同义（相关系数约 0.97），
    这正是 VIF 要抓出来的东西。

    >>> 换成你的数据 <<<
        return pd.read_csv("your_data.csv")
    """
    rng = np.random.default_rng(11)
    n = 260

    area = rng.normal(95, 22, n)
    rooms = np.round(area / 30 + rng.normal(0, 0.4, n)).clip(1, 6)
    age = rng.integers(0, 40, n).astype(float)
    dist_center = np.abs(rng.normal(9, 5, n)) + 0.5

    # 建筑面积 ≈ 面积 * 1.18 —— 制造强共线性
    floor_area = area * 1.18 + rng.normal(0, 2.0, n)

    price = (area * 0.85 + rooms * 3.0 - age * 0.35
             - dist_center * 1.6 + rng.normal(0, 6.0, n) + 30.0)

    return pd.DataFrame({
        "price": price.round(2),
        "area": area.round(2),
        "rooms": rooms,
        "age": age,
        "floor_area": floor_area.round(2),
        "dist_center": dist_center.round(2),
    })


# ============================== 2. 相关系数 ================================
def correlation_table(df: pd.DataFrame,
                      method: str = "pearson") -> pd.DataFrame:
    """算相关系数矩阵。

    注意：Pearson 只度量**线性**相关。两个变量可能是完美的 U 形关系而
    Pearson 系数为 0。所以除了系数，也要看散点图。
    """
    return df.corr(method=method).round(3)


def correlation_with_target(df: pd.DataFrame, target: str,
                            method: str = "pearson") -> pd.DataFrame:
    """算各自变量与因变量的相关性，并按绝对值排序。"""
    corr = df.corr(method=method)[target].drop(target)
    out = pd.DataFrame({
        "相关系数": corr.round(4),
        "绝对值": corr.abs().round(4),
    }).sort_values("绝对值", ascending=False)
    return out


def significance_vs_target(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """对每个自变量做显著性检验，给出 p 值。

    Pearson 用 t 检验，Spearman 用近似 t 检验。p 小才说明相关性可信。
    """
    rows = []
    for col in df.columns:
        if col == target:
            continue
        x, y = df[col].values, df[target].values
        mask = ~(np.isnan(x) | np.isnan(y))
        x, y = x[mask], y[mask]
        n = x.size

        r = float(np.corrcoef(x, y)[0, 1]) if n > 2 else np.nan
        if n > 2 and abs(r) < 1.0:
            # t = r * sqrt((n-2) / (1-r^2))，自由度 n-2
            t_stat = r * np.sqrt((n - 2) / (1 - r ** 2))
            p = float(_t_sf_two_sided(t_stat, n - 2))
        else:
            t_stat, p = np.nan, np.nan

        rows.append({
            "变量": col,
            "中文名": CN_NAMES.get(col, col),
            "r": round(r, 4) if not np.isnan(r) else np.nan,
            "t": round(t_stat, 3) if not np.isnan(t_stat) else np.nan,
            "p值": round(p, 5) if not np.isnan(p) else np.nan,
            "显著": ("是" if (not np.isnan(p) and p < 0.05) else "否"),
        })
    return pd.DataFrame(rows).set_index("变量")


def _t_sf_two_sided(t: float, df: int) -> float:
    """双侧 t 分布尾概率。有 scipy 就用 scipy，没有再退化成正态近似。"""
    try:
        from scipy import stats
        return 2.0 * float(stats.t.sf(abs(t), df))
    except ImportError:
        # 正态近似，n 较大时够用
        from math import erfc, sqrt
        return float(erfc(abs(t) / sqrt(2.0)))


# ============================== 3. VIF =====================================
def compute_vif(df: pd.DataFrame,
                features: List[str]) -> pd.DataFrame:
    """逐个算 VIF。

    做法：把第 j 个特征当因变量，其余特征当自变量做回归，
    取 R²，则 VIF_j = 1 / (1 - R²_j)。
    用最小二乘闭式解，避免依赖 statsmodels。
    """
    rows = []
    for j, col in enumerate(features):
        others = [c for c in features if c != col]
        if not others:
            rows.append({"变量": col, "R2": 0.0, "VIF": 1.0})
            continue

        X = df[others].values.astype(float)
        y = df[col].values.astype(float)

        # 加截距列
        Xd = np.column_stack([np.ones(len(X)), X])
        # 最小二乘：beta = (X'X)^-1 X'y，用 lstsq 更稳（避免奇异矩阵报错）
        beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
        y_hat = Xd @ beta

        ss_res = float(((y - y_hat) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        r2 = min(max(r2, 0.0), 1.0 - 1e-12)      # 防止除零

        vif = 1.0 / (1.0 - r2)
        rows.append({
            "变量": col,
            "中文名": CN_NAMES.get(col, col),
            "R2": round(r2, 4),
            "VIF": round(vif, 3),
        })

    out = pd.DataFrame(rows).sort_values("VIF", ascending=False)
    return out.reset_index(drop=True)


def vif_verdict(vif_table: pd.DataFrame,
                threshold: float) -> Tuple[List[str], List[str]]:
    """按阈值给出保留 / 剔除建议。"""
    keep = vif_table.loc[vif_table["VIF"] <= threshold, "变量"].tolist()
    drop = vif_table.loc[vif_table["VIF"] > threshold, "变量"].tolist()
    return keep, drop


# ============================== 4. 画图 ====================================
def plot_correlation_heatmap(df: pd.DataFrame,
                             out_png: Optional[str] = None) -> None:
    """画相关矩阵热力图，中文标签过 safe()。"""
    out_png = out_path(out_png, "correlation_heatmap.png")
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

    corr = df.corr()
    labels = [CN_NAMES.get(c, c) for c in corr.columns]

    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels([safe(l) for l in labels], rotation=40, ha="right")
    ax.set_yticklabels([safe(l) for l in labels])

    # 每个格子写上数值
    for i in range(len(labels)):
        for j in range(len(labels)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=8, color="white" if abs(v) > 0.6 else "black")

    ax.set_title(safe("变量相关系数矩阵"))
    fig.colorbar(im, ax=ax, shrink=0.85, label=safe("相关系数"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_vif_bars(vif_table: pd.DataFrame, threshold: float,
                  out_png: Optional[str] = None) -> None:
    """画 VIF 条形图，超阈值的标红。"""
    out_png = out_path(out_png, "vif_bars.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    labels = [CN_NAMES.get(v, v) for v in vif_table["变量"]]
    vals = vif_table["VIF"].values
    colors = ["#c0392b" if v > threshold else "#4c72b0" for v in vals]

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.barh([safe(l) for l in labels], vals, color=colors)
    ax.axvline(threshold, color="black", ls="--", lw=1.2,
               label=safe(f"阈值 VIF={threshold:g}"))
    ax.set_xlabel(safe("方差膨胀因子 VIF"))
    ax.set_title(safe("多重共线性诊断（红色为超阈值）"))
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("相关性分析与多重共线性 VIF（数据是模拟的，替换成你的数据）")
    print("=" * 66)

    df = build_frame()
    print(f"\n[数据] 形状={df.shape}  列={list(df.columns)}")

    # --- 相关系数矩阵 ---
    corr = correlation_table(df, CORR_METHOD)
    print(f"\n[相关系数矩阵]（{CORR_METHOD}）")
    print(corr.to_string())

    # --- 找出强相关对 ---
    print("\n[强相关变量对] |r| > 0.8")
    cols = list(corr.columns)
    found = False
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if abs(r) > 0.8:
                found = True
                a, b = CN_NAMES.get(cols[i], cols[i]), CN_NAMES.get(cols[j], cols[j])
                print(f"  {safe(a)} ~ {safe(b)}: r = {r:.3f}")
    if not found:
        print("  没有")

    # --- 与因变量的相关性 ---
    print(f"\n[各自变量与「{safe(CN_NAMES.get(TARGET, TARGET))}」的相关性]")
    print(correlation_with_target(df, TARGET, CORR_METHOD).to_string())
    print(f"\n[显著性检验 vs {safe(CN_NAMES.get(TARGET, TARGET))}]")
    print(significance_vs_target(df, TARGET).to_string())

    # --- VIF ---
    features = [c for c in df.columns if c != TARGET]
    vif_table = compute_vif(df, features)
    print(f"\n[VIF 诊断]  阈值 = {VIF_THRESHOLD}")
    print(vif_table.to_string(index=False))

    keep, drop = vif_verdict(vif_table, VIF_THRESHOLD)
    print("\n[结论]")
    print(f"  建议保留：{keep}")
    if drop:
        print(f"  建议剔除（VIF 超阈值）：{drop}")
        print("  处理方式：删掉其中一个、做主成分分析、或改用岭回归/套索。")
    else:
        print("  未发现严重共线性，可直接进入回归建模。")

    plot_correlation_heatmap(df)
    plot_vif_bars(vif_table, VIF_THRESHOLD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
