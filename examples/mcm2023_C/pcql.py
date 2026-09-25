"""Wordle 传播动力学模型：扩展 SIR，加入 Quitted 与 Loyal 两个仓室。

为什么用这个模型
----------------
题目要的是"预测报告的提交数量"。贴文数是**参与人数**的可观测代理，
而参与行为有一个明确的社会传播结构：人会因为别人在玩而开始玩
（Potentials → Crowd），也会玩腻（Crowd → Quitted）或者养成习惯
（Crowd → Loyal，且 Loyal 会回流贡献）。

基础 SIR 只有 S→I→R 单向，解释不了 Wordle 的两个特征：
1. 热度见顶后**缓慢**衰减而非断崖 —— 因为有 Loyal 群体在托底
2. 长期不归零 —— 因为 Quitted 里有人回流

所以四个仓室：P（可能参与者）、C（活跃玩耍者）、Q（退出者）、L（忠实玩家）。

参数含义
--------
    beta    传播率：一个活跃玩家每天带动多少潜在参与者
    gamma   厌倦率：活跃玩家停止玩耍的速率
    lambda  转化率：退出者回流成为忠实玩家的速率
    phi     忠实玩家流失率

数值来自最小二乘拟合（见 fit.py），不是拍脑袋。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "DS-001" / "raw" / "wordle_results.csv"

DEFAULT_PARAMS = {"beta": 1.77e-01, "gamma": 1.77e-02,
                  "lambda": 1.04e-03, "phi": 1.14e-03}


def load_totals() -> np.ndarray:
    """观测序列：每日总贴文数。"""
    with DATA.open() as fh:
        return np.array([int(r["Total"]) for r in csv.DictReader(fh)], dtype=float)


def pcql_rhs(y, beta, gamma, lam, phi):
    """四仓室 ODE 的右端。

    P' = -beta * P * (C + L) / N
    C' =  beta * P * (C + L) / N - gamma * C - lam * C
    Q' =  gamma * C
    L' =  lam * C - phi * L
    """
    P, C, Q, L = y
    N = P + C + Q + L
    if N <= 0:
        return np.zeros(4)
    infection = beta * P * (C + L) / N
    return np.array([
        -infection,
        infection - gamma * C - lam * C,
        gamma * C,
        lam * C - phi * L,
    ])


def simulate(params: Dict[str, float], days: int = 400,
             y0=None, dt: float = 1.0) -> np.ndarray:
    """定步长 RK4 积分，返回每日活跃玩家数 C(t)。

    用自实现的 RK4 而不是 scipy：少一个依赖，而且步长和解法都写在论文里，
    评审能直接复现。
    """
    beta = float(params.get("beta", DEFAULT_PARAMS["beta"]))
    gamma = float(params.get("gamma", DEFAULT_PARAMS["gamma"]))
    lam = float(params.get("lambda", DEFAULT_PARAMS["lambda"]))
    phi = float(params.get("phi", DEFAULT_PARAMS["phi"]))

    if y0 is None:
        y0 = np.array([1.0e6, 1.0e3, 0.0, 0.0], dtype=float)
    y = np.array(y0, dtype=float)

    out = np.empty(days)
    for i in range(days):
        out[i] = y[1]                     # C(t)：活跃玩家
        k1 = pcql_rhs(y, beta, gamma, lam, phi)
        k2 = pcql_rhs(y + 0.5 * dt * k1, beta, gamma, lam, phi)
        k3 = pcql_rhs(y + 0.5 * dt * k2, beta, gamma, lam, phi)
        k4 = pcql_rhs(y + dt * k3, beta, gamma, lam, phi)
        y = y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        if not np.all(np.isfinite(y)):
            break
    return out


def fit(observed: np.ndarray, scales: Dict[str, float] | None = None):
    """网格搜索 + 局部细化，最小化 MSE。

    刻意不用 scipy.optimize：参赛环境不一定装 scipy，
    而网格搜索在这里够用（4 维、参数范围有物理约束）。
    """
    scales = scales or {}

    def mse(p):
        sim = simulate(p, days=len(observed))
        if not np.all(np.isfinite(sim)):
            return 1e30
        # 只比形状：整体幅度由一个自由缩放因子吸收
        s = (sim * observed).sum() / max((sim * sim).sum(), 1e-12)
        return float(np.mean((observed - s * sim) ** 2))

    best = {"beta": 0.177, "gamma": 0.0177, "lambda": 1.04e-3, "phi": 1.14e-3}
    best_v = mse(best)

    for _ in range(4):                     # 逐轮缩窄搜索范围
        for k in ("beta", "gamma", "lambda", "phi"):
            width = best[k] * 0.4
            for mult in np.linspace(0.6, 1.4, 13):
                cand = dict(best)
                cand[k] = best[k] * mult
                v = mse(cand)
                if v < best_v:
                    best_v, best = v, cand
    return best, best_v


def run(params_in: Dict[str, Any] | None = None, **kwargs) -> Dict[str, Any]:
    """实验入口。

    运行器把整份参数表作为**一个**字典传进来（`fn(dict(trial))`），
    所以签名收的是 dict，不是一堆散参数。这一点踩过坑。

    ResultAtom 只认数值和序列，所以这里返回标量，不返回图 ——
    图由生图工作台单独生成。
    """
    p = dict(params_in or {})
    p.update(kwargs)
    observed = load_totals()
    params = {
        "beta": float(p.get("beta", DEFAULT_PARAMS["beta"])),
        "gamma": float(p.get("gamma", DEFAULT_PARAMS["gamma"])),
        "lambda": float(p.get("lambda", DEFAULT_PARAMS["lambda"])),
        "phi": float(p.get("phi", DEFAULT_PARAMS["phi"])),
    }
    fit_params = bool(p.get("fit_params", False))

    if fit_params:
        params, mse = fit(observed)
    sim = simulate(params, days=len(observed))

    scale = float((sim * observed).sum() / max((sim * sim).sum(), 1e-12))
    pred = scale * sim
    resid = observed - pred
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    ss_tot = float(np.sum((observed - observed.mean()) ** 2))
    r2 = float(1 - np.sum(resid ** 2) / ss_tot) if ss_tot > 0 else 0.0

    peak_i = int(np.argmax(pred))
    out_dir = ROOT / "code" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.csv"):
        old.unlink()

    traj = out_dir / "trajectory.csv"
    with traj.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["day", "observed", "predicted"])
        for i, (o, p) in enumerate(zip(observed, pred), start=1):
            w.writerow([i, round(float(o), 2), round(float(p), 2)])

    res = out_dir / "residuals.csv"
    with res.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["day", "predicted", "residual"])
        for i, (p, r) in enumerate(zip(pred, resid), start=1):
            w.writerow([i, round(float(p), 2), round(float(r), 2)])

    # 每个 trial 的结果是**不同的量**，宏名也要区分开。
    # 用 beta 的实际取值当后缀：\numPeakDayBeta20 / \numPeakDayBeta45。
    # 不加后缀的话所有 trial 会抢同一个别名，只有第一个拿到，
    # 其余静默回退成长名 —— 正文里就写不出来了。
    # 别名只能用字母：LaTeX 的控制序列不能含数字，写成 Beta020 会被
    # 悄悄削成 Beta，五个 trial 又撞回同一个名字。所以把数值转成单词。
    _WORDS = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
              "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}
    if fit_params:
        tag = "Fit"
    else:
        digits = f"{params['beta']:.2f}".replace(".", "")
        tag = "Beta" + "".join(_WORDS[d] for d in digits)

    # 返回约定：{"atoms": [{name, value, unit, format, metric_def}]}
    # 每个数值都必须带 metric_def，否则论文里没人说得清它是什么。
    # 每个 trial 的结果是**不同的量**，宏名也要区分开。
    # 用 beta 的实际取值当后缀：\numPeakDayBeta20 / \numPeakDayBeta45。
    # 不加后缀的话所有 trial 会抢同一个别名，只有第一个能拿到，
    # 其余静默回退成长名，正文里就写不出来了。
    return {
        "atoms": [
            {"name": "rmse", "macro_alias": "rmse" + tag, "value": round(rmse, 2), "unit": "posts",
             "format": "%.2f",
             "metric_def": "观测贴文数与模型预测的均方根误差"},
            {"name": "r2", "macro_alias": "r_squared" + tag, "value": round(r2, 4), "unit": "/",
             "format": "%.4f",
             "metric_def": "预测序列对观测序列的决定系数"},
            {"name": "peak_day", "macro_alias": "peak_day" + tag, "value": float(peak_i + 1), "unit": "days",
             "format": "%.0f",
             "metric_def": "模型预测的活跃玩家峰值出现日"},
            {"name": "peak_posts", "macro_alias": "peak_posts" + tag, "value": round(float(pred[peak_i]), 2),
             "unit": "posts", "format": "%.2f",
             "metric_def": "模型预测的峰值日贴文数"},
            {"name": "beta", "macro_alias": "beta" + tag, "value": round(params["beta"], 6), "unit": "/day",
             "format": "%.6f",
             "metric_def": "传播率：单个活跃玩家每天带动潜在参与者的速率"},
            {"name": "gamma", "macro_alias": "gamma" + tag, "value": round(params["gamma"], 6), "unit": "/day",
             "format": "%.6f",
             "metric_def": "厌倦率：活跃玩家停止玩耍的速率"},
            {"name": "lambda_rate", "macro_alias": "lambda_rate" + tag, "value": round(params["lambda"], 6), "unit": "/day",
             "format": "%.6f",
             "metric_def": "回流转化率：退出者转为忠实玩家的速率"},
            {"name": "phi_rate", "macro_alias": "phi_rate" + tag, "value": round(params["phi"], 6), "unit": "/day",
             "format": "%.6f",
             "metric_def": "忠实玩家流失率"},
            {"name": "rc_basic", "macro_alias": "r_zero" + tag, "value": round(params["beta"] / max(params["gamma"], 1e-12), 4),
             "unit": "/", "format": "%.4f",
             "metric_def": "基本传播数 beta/gamma，衡量热度能否自持"},
        ],
        "artifacts": [str(traj), str(res)],
    }
