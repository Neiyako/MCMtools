# -*- coding: utf-8 -*-
"""数据清洗与缺失值处理 —— 代码骨架（可直接复制使用）

【解决什么问题】
  拿到原始数据后的第一道工序：找出缺失、重复、异常值并合理填补，
  把"脏表"变成可以喂给模型的干净矩阵。

【要改哪几行】
  1. `build_raw_frame()`  —— 换成你自己的数据，例如
         df = pd.read_csv("your_data.csv")
  2. `MISSING_STRATEGY`   —— 每个数值列选 drop / mean / median / ffill
  3. `OUTLIER_Z`          —— 判定异常值的 |z| 阈值，默认 3.0

【输入】一个含缺失值 / 重复行 / 异常值的 pandas DataFrame
【输出】清洗后的 DataFrame、一张缺失值分布图、一份清洗日志

【注意】下面的数据是模拟的，替换成你的数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# mcmplot 引导：向上找到项目的 core/ 目录，装上中文字体。
# 复制到别处时如果报 ImportError，把 core/ 一起拷过去或改 project_root。
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
except ImportError:                                    # 脱离项目单跑时的兜底
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
MISSING_STRATEGY: Dict[str, str] = {
    "gdp": "median",        # drop | mean | median | ffill
    "population": "ffill",
    "rainfall": "mean",
    "score": "drop",
}
OUTLIER_Z = 3.0             # |z| 超过它就记为异常值
WINSORIZE = True            # True=截断到边界；False=置为 NaN 后按策略填补


# ============================== 1. 模拟数据 ================================
def build_raw_frame() -> pd.DataFrame:
    """构造一份"脏"数据：有缺失、有重复、有极端值。

    >>> 换成你的数据 <<<
        df = pd.read_csv("your_data.csv")
        return df
    """
    rng = np.random.default_rng(42)
    n = 200
    df = pd.DataFrame({
        "city": [f"城市{i % 10}" for i in range(n)],
        "year": rng.integers(2005, 2025, n),
        "gdp": rng.normal(5000, 900, n).round(1),
        "population": rng.normal(800, 120, n).round(1),
        "rainfall": rng.gamma(2.0, 40.0, n).round(1),
        "score": rng.normal(75, 8, n).round(2),
    })

    # 人为制造缺失：不同列缺失比例不同，模拟真实数据的"有的列缺得多"
    for col, frac in [("gdp", 0.08), ("population", 0.15),
                      ("rainfall", 0.05), ("score", 0.20)]:
        idx = rng.choice(n, int(n * frac), replace=False)
        df.loc[idx, col] = np.nan

    # 人为制造极端值：单位填错（万 vs 元）造成的量级错误
    df.loc[3, "gdp"] = 98000.0
    df.loc[17, "rainfall"] = 1500.0

    # 人为制造重复行
    df = pd.concat([df, df.iloc[[0, 1, 2]]], ignore_index=True)
    return df


# ============================== 2. 清洗 ====================================
def report_missing(df: pd.DataFrame, title: str) -> pd.DataFrame:
    """打印缺失情况，返回一张缺失率表。"""
    n_missing = df.isna().sum()
    rate = (n_missing / len(df) * 100).round(2)
    table = pd.DataFrame({"缺失数": n_missing, "缺失率%": rate})
    table = table[table["缺失数"] > 0].sort_values("缺失率%", ascending=False)

    print(f"\n[{title}] 形状={df.shape}")
    if table.empty:
        print("  没有缺失值。")
    else:
        print(table.to_string())
    return table


def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """按整行去重；报告删掉了几行。"""
    before = len(df)
    out = df.drop_duplicates().reset_index(drop=True)
    print(f"\n[去重] {before} -> {len(out)} 行，删除 {before - len(out)} 行重复记录")
    return out


def fill_missing(df: pd.DataFrame,
                 strategy: Dict[str, str]) -> pd.DataFrame:
    """按列策略填补缺失值。

    为什么不用一个统一的 fillna(0)：均值/中位数保分布，ffill 保时间连续，
    置 0 会把"没测到"变成"真的是 0"，是最常见的建模事故。
    """
    out = df.copy()
    for col, how in strategy.items():
        if col not in out.columns:
            print(f"  [跳过] 列 {col} 不在数据里")
            continue
        n_before = int(out[col].isna().sum())
        if n_before == 0:
            continue

        if how == "drop":
            out = out.dropna(subset=[col]).reset_index(drop=True)
            print(f"  [drop] {col}: 删除 {n_before} 行")
        elif how == "mean":
            out[col] = out[col].fillna(out[col].mean())
            print(f"  [mean] {col}: 填补 {n_before} 个，均值={out[col].mean():.2f}")
        elif how == "median":
            out[col] = out[col].fillna(out[col].median())
            print(f"  [median] {col}: 填补 {n_before} 个，中位数={out[col].median():.2f}")
        elif how == "ffill":
            # 时间序列用前向填充更合理：不引入未来信息
            out[col] = out[col].ffill().bfill()
            print(f"  [ffill] {col}: 填补 {n_before} 个")
        else:
            raise ValueError(f"未知的缺失值策略：{how}")
    return out


def handle_outliers(df: pd.DataFrame, cols: List[str],
                    z_threshold: float,
                    winsorize: bool = True) -> pd.DataFrame:
    """用 z 分数找异常值并处理。

    z = (x - 均值) / 标准差。|z| > 3 在正态假设下约占 0.27%。
    注意：均值和标准差本身会被极端值拉偏，样本很小时改用中位数 + MAD 更稳。
    """
    out = df.copy()
    print("\n[异常值] z 分数法，阈值 |z| > {}".format(z_threshold))
    for col in cols:
        if col not in out.columns:
            continue
        s = out[col]
        mu, sigma = s.mean(), s.std()
        if sigma == 0 or np.isnan(sigma):
            print(f"  {col}: 标准差为 0，跳过")
            continue

        z = (s - mu) / sigma
        mask = z.abs() > z_threshold
        n_out = int(mask.sum())
        if n_out == 0:
            print(f"  {col}: 无异常值")
            continue

        lo, hi = mu - z_threshold * sigma, mu + z_threshold * sigma
        if winsorize:
            out[col] = s.clip(lo, hi)       # 截断：保留样本量，只压住极端值
            action = f"截断到 [{lo:.1f}, {hi:.1f}]"
        else:
            out.loc[mask, col] = np.nan    # 置空，留给后续填补
            action = "置为缺失"
        print(f"  {col}: {n_out} 个异常值 -> {action}")
    return out


# ============================== 3. 画图 ====================================
def plot_missing_matrix(raw: pd.DataFrame, cleaned: pd.DataFrame,
                        out_png: Optional[str] = None) -> None:
    """画清洗前后的缺失情况对比图。"""
    out_png = out_path(out_png, "missing_before_after.png")
    if mcmplot is None:
        print("\n[跳过画图] 没找到 mcmplot 模块")
        return

    try:
        import matplotlib
        matplotlib.use("Agg")          # 无显示环境也能出图
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[跳过画图] 没装 matplotlib")
        return

    mcmplot.setup()                    # 必须先 setup，否则中文是豆腐块

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    for ax, df, title in [(axes[0], raw, "清洗前"),
                          (axes[1], cleaned, "清洗后")]:
        cols = list(df.columns)
        miss = df.isna().sum().values
        colors = ["#c0392b" if m > 0 else "#27ae60" for m in miss]
        ax.bar(range(len(cols)), miss, color=colors)
        ax.set_xticks(range(len(cols)))
        # 中文标签必须过 safe()
        ax.set_xticklabels([safe(c) for c in cols], rotation=30, ha="right")
        ax.set_ylabel(safe("缺失值个数"))
        ax.set_title(safe(f"{title}（共 {len(df)} 行）"))

    fig.suptitle(safe("缺失值清洗前后对比"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_distributions(df: pd.DataFrame, cols: List[str],
                       out_png: Optional[str] = None) -> None:
    """画清洗后各数值列的分布，确认填补没有制造畸形峰。"""
    out_png = out_path(out_png, "cleaned_distributions.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return

    fig, axes = plt.subplots(1, len(cols), figsize=(3.2 * len(cols), 3.4))
    axes = np.atleast_1d(axes)
    for ax, col in zip(axes, cols):
        ax.hist(df[col].dropna(), bins=20, color="#4c72b0", edgecolor="white")
        ax.set_title(safe(col))
        ax.set_ylabel(safe("频数"))
    fig.suptitle(safe("清洗后各变量分布"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("数据清洗与缺失值处理（数据是模拟的，替换成你的数据）")
    print("=" * 66)

    raw = build_raw_frame()
    report_missing(raw, "原始数据")

    df = drop_duplicates(raw)
    df = fill_missing(df, MISSING_STRATEGY)

    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    df = handle_outliers(df, num_cols, OUTLIER_Z, WINSORIZE)

    report_missing(df, "清洗后数据")

    print("\n[描述统计]")
    print(df[num_cols].describe().round(2).to_string())

    print(f"\n[类型检查] 数值列 {len(num_cols)} 个：{num_cols}")
    print(f"[结果] 清洗完成，最终形状 {df.shape}")

    plot_missing_matrix(raw, df)
    plot_distributions(df, ["gdp", "rainfall", "score"])

    csv_out = out_path("cleaned_data.csv")
    df.to_csv(csv_out, index=False, encoding="utf-8-sig")
    print(f"[落盘] 已保存 {csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
