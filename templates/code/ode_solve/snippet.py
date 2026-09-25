# -*- coding: utf-8 -*-
"""常微分方程组求解（RK4 手写 + scipy solve_ivp）—— 代码骨架

【解决什么问题】
  把"状态量随时间连续演化"的模型写成 dy/dt = f(t, y) 后求解。
  比赛里 90% 的动力学题（传染病、种群、药物代谢、热传导）都是这个形状。

  骨架给两条路：
  * `rk4_solve()`      —— 手写四阶龙格-库塔，无依赖，可控步长
  * `solve_ivp_solve()` —— 有 scipy 时用它，自适应步长更省事
  两者结果会互相对照，这也是论文里验证数值解可信度的标准做法。

【要改哪几行】
  1. `params`      —— 模型参数（增长率、传染率……）
  2. `derivs()`    —— 你的方程组，改这一个函数就够
  3. `y0`          —— 初值
  4. `T_END`, `DT` —— 模拟时长与步长

【输入】方程组、初值、参数
【输出】时间序列解、结尾状态、相图与演化图、守恒量检查

【注意】下面的模型是模拟的（SIR 传染病模型），替换成你的方程。
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
params: Dict[str, float] = {
    "beta": 0.42,      # 传染率
    "gamma": 0.14,     # 康复率（1/gamma = 平均病程）
    "mu": 0.01,        # 自然出生/死亡率
}

y0 = [0.99, 0.01, 0.0]          # [S 易感, I 感染, R 康复]，占比之和为 1
T_END = 160.0                   # 模拟天数
DT = 0.1                        # 步长

STATE_NAMES = ["易感者 S", "感染者 I", "康复者 R"]


# ============================== 1. 方程组 ==================================
def derivs(t: float, y: np.ndarray,
           p: Dict[str, float]) -> np.ndarray:
    """核心：写你的 dy/dt。

    SIR 模型：
        dS/dt = -beta * S * I + mu * (1 - S)
        dI/dt =  beta * S * I - gamma * I - mu * I
        dR/dt =  gamma * I - mu * R

    >>> 换成你的方程 <<<
    返回值和 y 长度必须一致。
    """
    S, I, R = y
    beta, gamma, mu = p["beta"], p["gamma"], p["mu"]

    dS = -beta * S * I + mu * (1.0 - S)
    dI = beta * S * I - gamma * I - mu * I
    dR = gamma * I - mu * R
    return np.array([dS, dI, dR])


# ============================== 2. RK4 ====================================
def rk4_solve(f: Callable[[float, np.ndarray], np.ndarray],
              y_init: List[float],
              t_end: float, dt: float) -> Tuple[np.ndarray, np.ndarray]:
    """经典四阶龙格-库塔。

    为什么用 RK4 而不是欧拉：欧拉是一阶，步长稍大就发散；
    RK4 是四阶，同样步长下误差小几个数量级，且实现只要几行。

    每一步：k1 = f(t, y)
            k2 = f(t+dt/2, y + dt/2 * k1)
            k3 = f(t+dt/2, y + dt/2 * k2)
            k4 = f(t+dt,   y + dt   * k3)
            y_{n+1} = y_n + dt/6 * (k1 + 2k2 + 2k3 + k4)
    """
    y = np.asarray(y_init, dtype=float)
    n_steps = int(round(t_end / dt))
    ts = np.linspace(0.0, n_steps * dt, n_steps + 1)
    ys = np.zeros((n_steps + 1, y.size))
    ys[0] = y

    for i in range(n_steps):
        t = ts[i]
        k1 = f(t, y)
        k2 = f(t + dt / 2.0, y + dt / 2.0 * k1)
        k3 = f(t + dt / 2.0, y + dt / 2.0 * k2)
        k4 = f(t + dt, y + dt * k3)
        y = y + dt / 6.0 * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        ys[i + 1] = y

    return ts, ys


def solve_ivp_solve(f: Callable[[float, np.ndarray], np.ndarray],
                    y_init: List[float],
                    t_end: float) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """有 scipy 时用 solve_ivp（RK45 自适应步长）。没有就返回 None。"""
    try:
        from scipy.integrate import solve_ivp
    except ImportError:
        return None

    sol = solve_ivp(f, (0.0, t_end), np.asarray(y_init, dtype=float),
                    method="RK45", rtol=1e-8, atol=1e-10, dense_output=True)
    if not sol.success:
        print(f"  [警告] solve_ivp 未收敛：{sol.message}")
        return None
    return sol.t, sol.y.T


# ============================== 3. 分析 ====================================
def peak_infection(ts: np.ndarray, ys: np.ndarray,
                   idx: int = 1) -> Tuple[float, float]:
    """找峰值和峰值时刻 —— 传染病题里最关键的结论。"""
    i_max = int(np.argmax(ys[:, idx]))
    return float(ts[i_max]), float(ys[i_max, idx])


def basic_reproduction_number(p: Dict[str, float]) -> float:
    """R0 = beta / (gamma + mu)。R0 > 1 才会爆发。"""
    return p["beta"] / (p["gamma"] + p["mu"])


def conservation_error(ts: np.ndarray, ys: np.ndarray,
                       target: float = 1.0) -> float:
    """检查守恒量（S+I+R 应恒为 1）的最大偏离。

    数值解必须满足模型的守恒律，否则说明步长太大或方程写错了。
    这是自检数值解可信度最省事的办法。
    """
    total = ys.sum(axis=1)
    return float(np.max(np.abs(total - target)))


# ============================== 4. 画图 ====================================
def plot_evolution(ts: np.ndarray, ys: np.ndarray,
                   out_png: Optional[str] = None) -> None:
    """各状态量随时间演化 + 峰值标注。"""
    out_png = out_path(out_png, "ode_evolution.png")
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

    colors = ["#4c72b0", "#c0392b", "#27ae60"]
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    for j in range(ys.shape[1]):
        nm = STATE_NAMES[j] if j < len(STATE_NAMES) else f"状态{j}"
        ax.plot(ts, ys[:, j], lw=1.9, color=colors[j % len(colors)],
                label=safe(nm))

    t_pk, v_pk = peak_infection(ts, ys)
    ax.plot([t_pk], [v_pk], "k*", ms=12, zorder=5)
    ax.annotate(safe(f"峰值 {v_pk:.1%} @ t={t_pk:.0f}"),
                xy=(t_pk, v_pk), xytext=(t_pk + 8, v_pk + 0.12),
                arrowprops=dict(arrowstyle="->", color="black"), fontsize=9)

    ax.set_xlabel(safe("时间（天）"))
    ax.set_ylabel(safe("占比"))
    ax.set_title(safe("SIR 模型状态演化"))
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_phase(ys: np.ndarray, out_png: Optional[str] = None) -> None:
    """相图（S-I 平面），看轨线走向。"""
    out_png = out_path(out_png, "ode_phase.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    ax.plot(ys[:, 0], ys[:, 1], color="#8e44ad", lw=1.7)
    ax.plot(ys[0, 0], ys[0, 1], "go", ms=8, label=safe("起点"))
    ax.plot(ys[-1, 0], ys[-1, 1], "rs", ms=8, label=safe("终点"))
    ax.set_xlabel(safe(STATE_NAMES[0]))
    ax.set_ylabel(safe(STATE_NAMES[1]))
    ax.set_title(safe("相图（S-I 平面）"))
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("常微分方程组求解（SIR 模型，数据是模拟的，替换成你的方程）")
    print("=" * 66)

    f = lambda t, y: derivs(t, y, params)      # noqa: E731

    # --- RK4 ---
    ts, ys = rk4_solve(f, y0, T_END, DT)
    print(f"\n[RK4] 步数={ts.size - 1}  步长={DT}  终端时刻={ts[-1]:.1f}")

    # --- 与 scipy 对照 ---
    ref = solve_ivp_solve(f, y0, T_END)
    if ref is not None:
        t_ref, y_ref = ref
        y_at_ref = np.array([np.interp(t_ref, ts, ys[:, j])
                             for j in range(ys.shape[1])]).T
        max_diff = float(np.max(np.abs(y_ref - y_at_ref)))
        print(f"[对照] scipy solve_ivp 最大偏差 = {max_diff:.3e}")
        if max_diff < 1e-3:
            print("  两条路径一致，数值解可信。")
        else:
            print("  偏差偏大，建议减小步长 DT。")
    else:
        print("[对照] 未安装 scipy，跳过 solve_ivp 对照")

    # --- 守恒检查 ---
    err = conservation_error(ts, ys)
    print(f"\n[守恒检查] S+I+R 与 1 的最大偏离 = {err:.3e}")
    print("  通过" if err < 1e-6 else "  未通过（步长可能太大）")

    # --- 关键指标 ---
    R0 = basic_reproduction_number(params)
    t_pk, v_pk = peak_infection(ts, ys)
    print(f"\n[关键指标]")
    print(f"  基本再生数 R0 = beta/(gamma+mu) = {R0:.4f}")
    print(f"  R0 {'> 1，疫情会扩散' if R0 > 1 else '<= 1，疫情会自然消退'}")
    print(f"  感染峰值 = {v_pk:.4%}  出现在 t = {t_pk:.1f}")
    print(f"  最终状态：S={ys[-1, 0]:.4f}  I={ys[-1, 1]:.4f}  R={ys[-1, 2]:.4f}")

    # --- 打印采样轨迹 ---
    print("\n[轨迹抽样] 每 20 步取一个点")
    print(f"  {'t':>7} {'S':>10} {'I':>10} {'R':>10}")
    for i in range(0, ts.size, max(1, ts.size // 10)):
        print(f"  {ts[i]:7.1f} {ys[i, 0]:10.5f} {ys[i, 1]:10.5f} "
              f"{ys[i, 2]:10.5f}")

    plot_evolution(ts, ys)
    plot_phase(ys)
    return 0


if __name__ == "__main__":
    sys.exit(main())
