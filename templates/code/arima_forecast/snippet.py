# -*- coding: utf-8 -*-
"""时间序列分解与预测（趋势 + 季节 + ARIMA 风格自回归）—— 代码骨架

【解决什么问题】
  给一条按时间排列的序列，拆出「趋势」「季节」「残差」三部分，
  再往前预测若干期，并给出预测区间。

  本骨架只依赖 numpy 手写：
  * 分解：移动平均提趋势，按季节位置平均提季节项
  * 预测：先消除趋势与季节，对残差做自回归（AR），再叠回去
  这样在没有 statsmodels 的机器上（比赛环境常有）也能跑。
  如果装了 statsmodels，`arima_forecast()` 会自动改用它。

【要改哪几行】
  1. `build_series()`  —— 换成你自己的数据
  2. `PERIOD`          —— 季节周期（月度=12，季度=4，周=7）
  3. `FORECAST_H`      —— 预测多少期
  4. `AR_ORDER`        —— 自回归阶数，默认 2

【输入】等间隔的一维时间序列
【输出】分解结果、预测值 + 95% 区间、分解图与预测图

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
    """把输出文件名解析到 OUTDIR 下，并确保该目录存在。

    name 为 None 时用 default。函数签名里 out_png 默认是 None，
    走的就是这条路径，最终落到临时目录，不会污染模板库。
    """
    OUTDIR.mkdir(parents=True, exist_ok=True)
    return str(OUTDIR / (name or default))


def safe(text: object) -> str:
    return mcmplot.safe(text) if mcmplot is not None else str(text)


# ============================== 参数区（改这里）=============================
PERIOD = 12          # 季节周期：月度数据用 12
FORECAST_H = 12      # 预测未来 12 期
AR_ORDER = 2         # 自回归阶数


# ============================== 1. 模拟数据 ================================
def build_series() -> Tuple[np.ndarray, np.ndarray]:
    """构造一条"上升趋势 + 年度周期 + 噪声"的月度序列。

    >>> 换成你的数据 <<<
        t = np.arange(len(your_values))
        return t, np.asarray(your_values, dtype=float)
    """
    rng = np.random.default_rng(2025)
    n = 120                                  # 10 年月度数据
    t = np.arange(n)
    trend = 100.0 + 1.6 * t                  # 线性上升
    season = 18.0 * np.sin(2 * np.pi * t / 12) + 7.0 * np.cos(4 * np.pi * t / 12)
    noise = rng.normal(0, 5.0, n)
    y = trend + season + noise
    return t.astype(float), y


# ============================== 2. 分解 ====================================
def moving_average(y: np.ndarray, window: int) -> np.ndarray:
    """居中移动平均，用来提取趋势。两端用 NaN 补齐。"""
    n = y.size
    out = np.full(n, np.nan)
    half = window // 2
    for i in range(half, n - half):
        out[i] = y[i - half:i + half + 1].mean()
    return out


def decompose(y: np.ndarray,
              period: int) -> Dict[str, np.ndarray]:
    """经典加法分解：y = 趋势 + 季节 + 残差。

    步骤：
      1. 用长度 = period 的居中移动平均得到趋势（偶数周期需再 2 期平均）
      2. 去趋势后按"周期内位置"求平均，得到季节项
      3. 季节项中心化（均值归零），剩下的就是残差
    """
    n = y.size
    trend = moving_average(y, period)

    # 偶数周期要再对相邻两期平均一次，否则趋势与季节位置错位半期
    if period % 2 == 0:
        t2 = np.full(n, np.nan)
        for i in range(n - 1):
            if not np.isnan(trend[i]) and not np.isnan(trend[i + 1]):
                t2[i] = (trend[i] + trend[i + 1]) / 2.0
        trend = t2

    detrended = y - trend

    # 每个季节位置的平均偏离
    seasonal_idx = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(detrended[i]):
            seasonal_idx[i] = detrended[i]

    seasonal_pattern = np.zeros(period)
    for k in range(period):
        pos = np.arange(k, n, period)
        vals = seasonal_idx[pos]
        vals = vals[~np.isnan(vals)]
        seasonal_pattern[k] = vals.mean() if vals.size else 0.0

    # 中心化：加法模型要求季节项之和为 0，否则会污染趋势
    seasonal_pattern -= seasonal_pattern.mean()

    seasonal = np.array([seasonal_pattern[i % period] for i in range(n)])
    resid = y - trend - seasonal

    return {
        "trend": trend,
        "seasonal": seasonal,
        "resid": resid,
        "seasonal_pattern": seasonal_pattern,
    }


def seasonal_strength(dec: Dict[str, np.ndarray]) -> float:
    """季节强度 = max(0, 1 - Var(残差)/Var(残差+季节))。

    接近 1 说明季节项很重要；接近 0 说明这条序列没什么季节性。
    """
    resid = dec["resid"]
    seas = dec["seasonal"]
    r = resid[~np.isnan(resid)]
    both = (resid + seas)[~np.isnan(resid)]
    var_r, var_b = float(np.var(r)), float(np.var(both))
    if var_b <= 0:
        return 0.0
    return max(0.0, 1.0 - var_r / var_b)


# ============================== 3. 预测 ====================================
def ar_fit_predict(x: np.ndarray, order: int,
                   h: int) -> Tuple[np.ndarray, np.ndarray]:
    """对零均值序列做 AR(order) 拟合并多步预测。

    用 Yule-Walker 方程解系数：R a = r，其中 R 是自相关矩阵。
    多步预测时把上一步的预测值当观测继续喂回去。

    返回 (预测值, 残差标准差)。
    """
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    n = x.size
    if n <= order + 1:
        return np.zeros(h), float(np.std(x)) if n else 0.0

    # 自相关
    acov = np.array([float((x[:n - k] * x[k:]).sum()) / n
                     for k in range(order + 1)])
    if acov[0] <= 0:
        return np.zeros(h), 0.0

    R = np.array([[acov[abs(i - j)] for j in range(order)]
                  for i in range(order)])
    r = acov[1:order + 1]
    try:
        coef = np.linalg.solve(R, r)
    except np.linalg.LinAlgError:
        coef = np.linalg.lstsq(R, r, rcond=None)[0]

    # 用系数回算拟合值，得到残差标准差
    fitted = np.array([float(np.dot(coef, x[i - 1::-1][:order])) if i >= order
                       else np.nan for i in range(n)])
    resid = x[order:] - fitted[order:]
    sigma = float(np.std(resid, ddof=1)) if resid.size > 1 else 0.0

    # 多步递推预测
    hist = list(x)
    preds = []
    for _ in range(h):
        val = float(np.dot(coef, np.array(hist[::-1][:order])))
        preds.append(val)
        hist.append(val)

    return np.array(preds), sigma


def forecast(y: np.ndarray, dec: Dict[str, np.ndarray],
             period: int, h: int, order: int) -> Dict[str, np.ndarray]:
    """把趋势外推 + 季节项 + AR 残差预测叠起来。

    趋势用末尾若干期的平均斜率线性外推 —— 简单，但对比赛数据够用，
    而且比拟合一条全局直线更贴近近期走势。
    """
    n = y.size
    trend = dec["trend"]
    valid = trend[~np.isnan(trend)]

    # 末尾 1/4 数据的平均一阶差分作为斜率
    tail = valid[-max(period, len(valid) // 4):]
    slope = float(np.mean(np.diff(tail))) if tail.size > 1 else 0.0

    last_trend = float(valid[-1]) if valid.size else float(y[-1])
    trend_fc = last_trend + slope * np.arange(1, h + 1)

    # 季节项按位置循环
    pattern = dec["seasonal_pattern"]
    seasonal_fc = np.array([pattern[(n + i) % period] for i in range(h)])

    # 残差用 AR 外推
    resid = dec["resid"]
    resid_valid = resid[~np.isnan(resid)]
    ar_fc, sigma = ar_fit_predict(resid_valid, order, h)

    point = trend_fc + seasonal_fc + ar_fc

    # 预测区间：不确定性随步长累加（随机游走式扩散）
    steps = np.arange(1, h + 1)
    band = 1.96 * sigma * np.sqrt(steps)
    return {
        "point": point,
        "lower": point - band,
        "upper": point + band,
        "sigma": np.full(h, sigma),
    }


def try_statsmodels_arima(y: np.ndarray, h: int) -> Optional[Dict[str, np.ndarray]]:
    """如果装了 statsmodels，就用真正的 ARIMA，结果更权威。

    没装就返回 None，由调用方走手写 AR 路径。
    """
    try:
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError:
        return None

    try:
        model = ARIMA(y, order=(1, 1, 1)).fit()
        fc = model.get_forecast(steps=h)
        mean = np.asarray(fc.predicted_mean, dtype=float)
        ci = np.asarray(fc.conf_int(), dtype=float)
        print("  [方法] 使用 statsmodels ARIMA(1,1,1)")
        return {"point": mean, "lower": ci[:, 0], "upper": ci[:, 1]}
    except Exception as exc:                      # noqa: BLE001
        print(f"  [方法] statsmodels 拟合失败（{type(exc).__name__}），"
              f"改用手写 AR")
        return None


# ============================== 4. 精度评估 ================================
def backtest(y: np.ndarray, period: int, h: int,
             order: int) -> Dict[str, float]:
    """留出最后 h 期做回测，算 MAE / RMSE / MAPE。

    不评估精度的预测等于没做预测 —— 论文里必须给出误差指标。
    """
    n = y.size
    if n <= h + 2 * period:
        return {}
    train, test = y[:-h], y[-h:]

    dec = decompose(train, period)
    fc = forecast(train, dec, period, h, order)
    pred = fc["point"]

    err = test - pred
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    with np.errstate(divide="ignore", invalid="ignore"):
        mape = float(np.mean(np.abs(err / test)) * 100)

    return {"MAE": mae, "RMSE": rmse, "MAPE": mape}


# ============================== 5. 画图 ====================================
def plot_decomposition(t: np.ndarray, y: np.ndarray,
                       dec: Dict[str, np.ndarray],
                       out_png: Optional[str] = None) -> None:
    """四联分解图：原始、趋势、季节、残差。"""
    out_png = out_path(out_png, "timeseries_decomposition.png")
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

    fig, axes = plt.subplots(4, 1, figsize=(9.5, 8.5), sharex=True)
    panels = [(y, "原始序列", "#2c3e50"),
              (dec["trend"], "趋势项", "#c0392b"),
              (dec["seasonal"], "季节项", "#27ae60"),
              (dec["resid"], "残差项", "#8e44ad")]
    for ax, (series, title, color) in zip(axes, panels):
        ax.plot(t, series, color=color, lw=1.4)
        ax.set_ylabel(safe(title))
        ax.grid(alpha=0.3)
    axes[0].set_title(safe("时间序列加法分解"))
    axes[-1].set_xlabel(safe("时间序号"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_forecast(t: np.ndarray, y: np.ndarray,
                  fc: Dict[str, np.ndarray],
                  out_png: Optional[str] = None) -> None:
    """历史 + 预测 + 置信带。论文里最常出现的一张时序图。"""
    out_png = out_path(out_png, "timeseries_forecast.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    h = fc["point"].size
    t_fc = np.arange(t[-1] + 1, t[-1] + 1 + h)

    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    ax.plot(t, y, color="#2c3e50", lw=1.6, label=safe("历史观测"))
    ax.plot(t_fc, fc["point"], color="#c0392b", lw=1.8, marker="o",
            ms=3.5, label=safe("预测值"))
    ax.fill_between(t_fc, fc["lower"], fc["upper"], color="#c0392b",
                    alpha=0.18, label=safe("95% 预测区间"))
    ax.axvline(t[-1], color="gray", ls=":", lw=1.2)
    ax.set_xlabel(safe("时间序号"))
    ax.set_ylabel(safe("数值"))
    ax.set_title(safe(f"未来 {h} 期预测"))
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("时间序列分解与预测（数据是模拟的，替换成你的数据）")
    print("=" * 66)

    t, y = build_series()
    print(f"\n[数据] 长度={y.size}  季节周期={PERIOD}  "
          f"均值={y.mean():.2f}  标准差={y.std():.2f}")

    dec = decompose(y, PERIOD)
    strength = seasonal_strength(dec)
    print(f"\n[分解] 季节强度 = {strength:.4f}")
    if strength > 0.6:
        print("  季节性很强，建模时必须包含季节项。")
    elif strength > 0.3:
        print("  存在中等季节性。")
    else:
        print("  季节性很弱，可直接用趋势 + 自回归。")

    print(f"\n[季节模式] 各期相对偏离（周期={PERIOD}）")
    for k, v in enumerate(dec["seasonal_pattern"]):
        bar = "#" * int(abs(v) * 2)
        print(f"  第{k + 1:2d}期: {v:+7.3f}  {bar}")

    # --- 回测精度 ---
    metrics = backtest(y, PERIOD, FORECAST_H, AR_ORDER)
    if metrics:
        print(f"\n[回测精度] 留出最后 {FORECAST_H} 期")
        print(f"  MAE  = {metrics['MAE']:.4f}")
        print(f"  RMSE = {metrics['RMSE']:.4f}")
        print(f"  MAPE = {metrics['MAPE']:.2f}%")

    # --- 预测 ---
    print(f"\n[预测] 未来 {FORECAST_H} 期")
    result = try_statsmodels_arima(y, FORECAST_H)
    if result is None:
        print(f"  [方法] 手写 AR({AR_ORDER}) + 趋势外推 + 季节项"
              f"（未安装 statsmodels）")
        result = forecast(y, dec, PERIOD, FORECAST_H, AR_ORDER)

    for i in range(FORECAST_H):
        print(f"  第{t[-1] + i + 1:4.0f}期: "
              f"{result['point'][i]:9.3f}  "
              f"[{result['lower'][i]:9.3f}, {result['upper'][i]:9.3f}]")

    plot_decomposition(t, y, dec)
    plot_forecast(t, y, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
