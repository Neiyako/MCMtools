# -*- coding: utf-8 -*-
"""排队论指标计算 —— 代码骨架（可直接复制使用）

【解决什么问题】
  服务系统里"该开几个窗口/几台机器"这类问题。给定到达率与服务率，
  算出：平均等待时间、排队长度、系统利用率、顾客等待概率。
  这是优化服务台数量、评估拥堵的标准工具。

  本骨架覆盖三种最常见的模型（Kendall 记号）：
    * M/M/1      单服务台
    * M/M/c      多服务台（c 个并行窗口）
    * M/M/c/K    多服务台 + 系统容量上限 K（超过就拒绝，算阻塞率）
  以及 Little 公式校验和仿真对照。

【要改哪几行】
  1. `LAMBDA_`   —— 到达率（单位时间到达人数）
  2. `MU_`       —— 单台服务率（单位时间服务人数）
  3. `C_SERVERS` —— 服务台数量
  4. `CAPACITY`  —— 系统容量上限（None 表示无限）

【输入】到达率、服务率、服务台数
【输出】各排队指标、最优服务台数建议、仿真验证、指标图

【注意】下面的参数是模拟的，替换成你的数据。
"""

from __future__ import annotations

import math
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
    """把输出文件名解析到 OUTDIR 下，并确保该目录存在。"""
    OUTDIR.mkdir(parents=True, exist_ok=True)
    return str(OUTDIR / (name or default))


def safe(text: object) -> str:
    return mcmplot.safe(text) if mcmplot is not None else str(text)


# ============================== 参数区（改这里）=============================
LAMBDA_ = 18.0        # 到达率：每小时到达 18 人
MU_ = 5.0             # 单台服务率：每小时服务 5 人（平均服务 12 分钟）
C_SERVERS = 4         # 服务台数量
CAPACITY = None       # 系统容量上限（含正在服务的），None = 无限

SERVICE_COST_PER_SERVER = 60.0   # 每台每小时成本
WAIT_COST_PER_CUSTOMER = 25.0    # 每位顾客等待每小时的机会成本


# ============================== 1. M/M/1 ==================================
def mm1(lam: float, mu: float) -> Dict[str, float]:
    """M/M/1：单服务台、泊松到达、指数服务时间、无限容量。

    核心公式（令 rho = lam/mu）：
      L  = rho / (1 - rho)          系统内平均人数
      Lq = rho^2 / (1 - rho)        队列中平均等待人数
      W  = 1 / (mu - lam)           平均逗留时间
      Wq = rho / (mu - lam)         平均等待时间

    前提 rho < 1，否则队列无限增长（系统不稳定）。
    """
    rho = lam / mu
    if rho >= 1:
        return {"稳定": 0.0, "rho": rho}

    L = rho / (1 - rho)
    Lq = rho ** 2 / (1 - rho)
    W = 1.0 / (mu - lam)
    Wq = rho / (mu - lam)
    return {
        "稳定": 1.0, "rho": rho,
        "L": L, "Lq": Lq, "W": W, "Wq": Wq,
        "P0": 1 - rho,
        "P_wait": rho,                # 到达即需等待的概率
        "Lq_formula_check": L - rho,
    }


# ============================== 2. M/M/c ==================================
def erlang_c(lam: float, mu: float, c: int) -> float:
    """Erlang-C 公式：到达时需要等待的概率 P(等待)。

    这是多服务台排队论的核心量，其余指标都由它推出。
        a = lam / mu               （ offered load，单位 Erlang）
        rho = a / c                （每台利用率）
        P_wait = [a^c/(c!(1-rho)) * P0]，P0 为系统空闲概率
    """
    a = lam / mu
    rho = a / c
    if rho >= 1:
        return 1.0

    # P0 的分母：sum_{n=0}^{c-1} a^n/n! + a^c/(c!(1-rho))
    s = sum(a ** n / math.factorial(n) for n in range(c))
    s += a ** c / (math.factorial(c) * (1 - rho))
    p0 = 1.0 / s

    p_wait = (a ** c / (math.factorial(c) * (1 - rho))) * p0
    return float(min(max(p_wait, 0.0), 1.0))


def mmc(lam: float, mu: float, c: int) -> Dict[str, float]:
    """M/M/c：c 个并行服务台，无限容量。

    关键结论：**合并服务台能显著减少等待**。
    同样的总服务能力，4 个窗口各管一队 比 4 个独立单队快得多
    （因为不会出现"这边排队那边空闲"）。
    """
    a = lam / mu
    rho = a / c
    if rho >= 1:
        return {"稳定": 0.0, "rho": rho}

    p_wait = erlang_c(lam, mu, c)
    Wq = p_wait / (c * mu - lam)
    W = Wq + 1.0 / mu
    Lq = lam * Wq
    L = lam * W

    # 系统空闲概率
    s = sum(a ** n / math.factorial(n) for n in range(c))
    s += a ** c / (math.factorial(c) * (1 - rho))
    p0 = 1.0 / s

    return {
        "稳定": 1.0, "rho": rho, "L": L, "Lq": Lq, "W": W, "Wq": Wq,
        "P0": p0, "P_wait": p_wait, "a": a,
    }


# ============================== 3. M/M/c/K ================================
def mmc_k(lam: float, mu: float, c: int, K: int) -> Dict[str, float]:
    """M/M/c/K：加系统容量上限 K（K >= c）。

    超过 K 人的到达会被**拒绝**（比如停车场满了、呼叫中心占线）。
    这时新增两个关键指标：
      * P_block 阻塞率（到达被拒的概率）
      * 实际有效到达率 = lam * (1 - P_block)，比标称到达率低
    """
    if K < c:
        raise ValueError("系统容量 K 必须 >= 服务台数 c")

    a = lam / mu
    # 稳态概率 p_n = p0 * a^n / n!      (n <= c)
    #             = p0 * a^n / (c! c^(n-c))  (c < n <= K)
    terms = []
    for n in range(K + 1):
        if n <= c:
            terms.append(a ** n / math.factorial(n))
        else:
            terms.append(a ** n / (math.factorial(c) * c ** (n - c)))
    terms = np.array(terms, dtype=float)
    total = terms.sum()
    if total <= 0 or not np.isfinite(total):
        return {"稳定": 0.0, "rho": 1.0}
    p = terms / total
    p0 = float(p[0])

    p_block = float(p[K])                       # 系统满 -> 新到者被拒
    lam_eff = lam * (1 - p_block)               # 有效到达率

    # 平均队长（不含被拒者）
    n_arr = np.arange(K + 1)
    L = float((n_arr * p).sum())
    # 平均排队人数 = 系统内 - 正在服务的平均台数
    busy = sum(min(n, c) * p[n] for n in range(K + 1))
    Lq = L - float(busy)

    # Little 公式：用有效到达率
    W = L / lam_eff if lam_eff > 0 else float("nan")
    Wq = Lq / lam_eff if lam_eff > 0 else float("nan")

    return {
        "稳定": 1.0, "rho": lam_eff / (c * mu), "L": L, "Lq": Lq,
        "W": W, "Wq": Wq, "P0": p0, "P_wait": float(p[c:].sum()),
        "P_block": p_block, "lam_eff": lam_eff, "a": a,
    }


# ============================== 4. 仿真验证 ================================
def simulate_queue(lam: float, mu: float, c: int,
                   K: Optional[int] = None,
                   n_customers: int = 40000,
                   seed: int = 7) -> Dict[str, float]:
    """离散事件仿真，用来验证解析公式。

    比赛里非常推荐做这一步：解析解基于"泊松到达+指数服务"的强假设，
    仿真能在假设不成立时给出更可信的数字，两者对照也是加分项。
    """
    rng = np.random.default_rng(seed)
    servers_free_at = np.zeros(c)        # 每台服务台空闲的时刻
    arrival_t = 0.0
    wait_times = []
    in_system = []
    rejected = 0

    for _ in range(n_customers):
        arrival_t += rng.exponential(1.0 / lam)

        # 当前系统内人数（还在被服务或排队）
        occupied = int((servers_free_at > arrival_t).sum())
        queued = int((servers_free_at > arrival_t).sum())
        # 更准确：统计"此刻尚未完成服务"的顾客数
        in_service_end = servers_free_at[servers_free_at > arrival_t]
        n_now = in_service_end.size
        if K is not None and n_now >= K:
            rejected += 1
            continue

        # 找最早空闲的服务台
        j = int(np.argmin(servers_free_at))
        start = max(arrival_t, servers_free_at[j])
        wait = start - arrival_t
        service = rng.exponential(1.0 / mu)
        servers_free_at[j] = start + service

        wait_times.append(wait)
        in_system.append(wait + service)

    wait_arr = np.array(wait_times)
    sys_arr = np.array(in_system)
    total_time = servers_free_at.max() - 0.0
    lam_eff = len(wait_arr) / total_time if total_time > 0 else lam

    return {
        "Wq_sim": float(wait_arr.mean()) if wait_arr.size else float("nan"),
        "W_sim": float(sys_arr.mean()) if sys_arr.size else float("nan"),
        "Lq_sim": float(wait_arr.mean() * lam_eff),
        "L_sim": float(sys_arr.mean() * lam_eff),
        "P_wait_sim": float((wait_arr > 1e-9).mean()) if wait_arr.size else 0.0,
        "P_block_sim": rejected / n_customers,
        "利用率_sim": float(min(lam_eff / (c * mu), 1.0)),
        "样本数": float(len(wait_arr)),
    }


# ============================== 5. 成本优化 ================================
def cost_analysis(lam: float, mu: float,
                  c_max: int = 12) -> List[Dict[str, float]]:
    """扫服务台数量，算总成本 = 服务台成本 + 顾客等待成本。

    这是排队论在比赛里最常见的落点：
    不是"指标是多少"，而是"开几个窗口总成本最低"。
    """
    rows = []
    for c in range(1, c_max + 1):
        if lam / (c * mu) >= 1:
            rows.append({"c": c, "稳定": 0.0})
            continue
        r = mmc(lam, mu, c)
        server_cost = c * SERVICE_COST_PER_SERVER
        wait_cost = lam * r["Wq"] * WAIT_COST_PER_CUSTOMER
        rows.append({
            "c": c, "稳定": 1.0,
            "rho": r["rho"], "Wq": r["Wq"], "Lq": r["Lq"],
            "P_wait": r["P_wait"],
            "服务台成本": server_cost,
            "等待成本": wait_cost,
            "总成本": server_cost + wait_cost,
        })
    return rows


# ============================== 6. 画图 ====================================
def plot_metrics(out_png: Optional[str] = None) -> None:
    """指标随服务台数量变化的曲线。"""
    out_png = out_path(out_png, "queueing_metrics.png")
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

    rows = [r for r in cost_analysis(LAMBDA_, MU_, 12) if r.get("稳定")]
    cs = [r["c"] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(14.0, 4.2))

    axes[0].plot(cs, [r["Wq"] for r in rows], "o-", color="#4c72b0", lw=1.9)
    axes[0].set_xlabel(safe("服务台数量 c"))
    axes[0].set_ylabel(safe("平均等待时间 Wq（小时）"))
    axes[0].set_title(safe("等待时间随服务台数下降"))
    axes[0].grid(alpha=0.3)

    axes[1].plot(cs, [r["rho"] for r in rows], "s-", color="#dd8452", lw=1.9)
    axes[1].axhline(0.85, color="red", ls="--", lw=1.2,
                    label=safe("经验上限 0.85"))
    axes[1].set_xlabel(safe("服务台数量 c"))
    axes[1].set_ylabel(safe("利用率 rho"))
    axes[1].set_title(safe("利用率（过高则拥堵）"))
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    axes[2].plot(cs, [r["总成本"] for r in rows], "^-", color="#c0392b",
                 lw=2.0, label=safe("总成本"))
    axes[2].plot(cs, [r["服务台成本"] for r in rows], "--", color="#4c72b0",
                 lw=1.3, label=safe("服务台成本"))
    axes[2].plot(cs, [r["等待成本"] for r in rows], "--", color="#55a868",
                 lw=1.3, label=safe("等待成本"))
    best = min(rows, key=lambda r: r["总成本"])
    axes[2].axvline(best["c"], color="black", ls=":", lw=1.5,
                    label=safe(f"最优 c={best['c']}"))
    axes[2].set_xlabel(safe("服务台数量 c"))
    axes[2].set_ylabel(safe("每小时成本"))
    axes[2].set_title(safe("成本权衡"))
    axes[2].legend(fontsize=8)
    axes[2].grid(alpha=0.3)

    fig.suptitle(safe(f"排队系统分析（到达率={LAMBDA_:g}/小时，"
                      f"单台服务率={MU_:g}/小时）"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("排队论指标计算（参数是模拟的，替换成你的数据）")
    print("=" * 66)

    lam, mu, c = LAMBDA_, MU_, C_SERVERS
    a = lam / mu
    print(f"\n[参数] 到达率 lambda={lam:g}/小时  单台服务率 mu={mu:g}/小时")
    print(f"       服务台数 c={c}  系统容量 K={CAPACITY}")
    print(f"       总服务能力 = {c * mu:g}/小时  "
          f"（到达负荷 a = lambda/mu = {a:.2f} Erlang）")
    print(f"       利用率 rho = a/c = {a / c:.4f}")

    if a / c >= 1:
        print("\n[警告] 利用率 >= 1，系统不稳定，队列会无限增长！")
        print("       请增加服务台或提高服务率。")

    # --- M/M/1 对照 ---
    print("\n" + "-" * 66)
    print("[M/M/1] 单服务台模型（对照用）")
    r1 = mm1(lam, mu)
    if r1.get("稳定"):
        print(f"  利用率 rho = {r1['rho']:.4f}")
        print(f"  平均队长 L  = {r1['L']:.4f} 人")
        print(f"  平均排队 Lq = {r1['Lq']:.4f} 人")
        print(f"  逗留时间 W  = {r1['W']:.4f} 小时 = {r1['W'] * 60:.2f} 分钟")
        print(f"  等待时间 Wq = {r1['Wq']:.4f} 小时 = {r1['Wq'] * 60:.2f} 分钟")
        print(f"  需等待概率  = {r1['P_wait']:.4f}")
    else:
        print(f"  不稳定（rho={r1['rho']:.2f} >= 1），单台扛不住。")

    # --- M/M/c 主模型 ---
    print("\n" + "-" * 66)
    print(f"[M/M/c] {c} 个并行服务台")
    rc = mmc(lam, mu, c)
    if rc.get("稳定"):
        print(f"  利用率 rho      = {rc['rho']:.4f}")
        print(f"  系统空闲概率 P0 = {rc['P0']:.4f}")
        print(f"  平均队长 L      = {rc['L']:.4f} 人")
        print(f"  平均排队 Lq     = {rc['Lq']:.4f} 人")
        print(f"  逗留时间 W      = {rc['W']:.4f} 小时 = {rc['W'] * 60:.2f} 分钟")
        print(f"  等待时间 Wq     = {rc['Wq']:.4f} 小时 = {rc['Wq'] * 60:.2f} 分钟")
        print(f"  需等待概率      = {rc['P_wait']:.4f}")

        # Little 公式自检：L = lambda * W
        lhs = rc["L"]
        rhs = lam * rc["W"]
        print(f"\n  [Little 公式校验] L = {lhs:.4f}  "
              f"lambda*W = {rhs:.4f}  "
              f"-> {'通过' if abs(lhs - rhs) < 1e-6 else '不通过'}")
    else:
        print(f"  不稳定（rho={rc['rho']:.4f} >= 1）")

    # --- 与单台合并对比 ---
    if r1.get("稳定") and rc.get("稳定"):
        print(f"\n  [合并服务台的效果]")
        print(f"    单台 1 个窗口（M/M/1）：Wq = {r1['Wq'] * 60:.2f} 分钟")
        print(f"    {c} 个窗口各管一队     ：Wq = "
              f"{mm1(lam / c, mu)['Wq'] * 60:.2f} 分钟")
        print(f"    {c} 个窗口统一排队（M/M/c）：Wq = {rc['Wq'] * 60:.2f} 分钟")
        print(f"    => 统一排队比各自排队快很多，这就是排队论的经典结论。")

    # --- M/M/c/K ---
    if CAPACITY is not None:
        print("\n" + "-" * 66)
        print(f"[M/M/c/K] 容量上限 K = {CAPACITY}")
        rk = mmc_k(lam, mu, c, CAPACITY)
        print(f"  阻塞率 P_block = {rk['P_block']:.4f}"
              f"（{rk['P_block'] * 100:.2f}% 的顾客被拒）")
        print(f"  有效到达率 = {rk['lam_eff']:.4f}/小时"
              f"（标称 {lam:g}）")
        print(f"  平均队长 L = {rk['L']:.4f}  排队 Lq = {rk['Lq']:.4f}")
        print(f"  等待时间 Wq = {rk['Wq'] * 60:.2f} 分钟")

    # --- 仿真验证 ---
    print("\n" + "-" * 66)
    print("[仿真验证] 离散事件仿真 40000 位顾客")
    sim = simulate_queue(lam, mu, c, CAPACITY, n_customers=40000)
    print(f"  {'指标':<14}{'解析解':>12}{'仿真值':>12}{'误差':>10}")
    pairs = [("Wq(小时)", rc.get("Wq"), sim["Wq_sim"]),
             ("W(小时)", rc.get("W"), sim["W_sim"]),
             ("Lq", rc.get("Lq"), sim["Lq_sim"]),
             ("P(等待)", rc.get("P_wait"), sim["P_wait_sim"])]
    for name, theory, simv in pairs:
        if theory is None or simv is None or not np.isfinite(simv):
            continue
        err = abs(theory - simv) / theory * 100 if theory else 0.0
        print(f"  {name:<14}{theory:12.4f}{simv:12.4f}{err:9.2f}%")
    print("  [说明] 误差在几个百分点内说明公式与仿真一致，模型可信。")

    # --- 成本优化 ---
    print("\n" + "-" * 66)
    print("[成本优化] 扫服务台数量，找总成本最低")
    rows = cost_analysis(lam, mu, 12)
    print(f"  {'c':>3}{'利用率':>10}{'Wq(分)':>10}{'服务台成本':>12}"
          f"{'等待成本':>12}{'总成本':>12}")
    for r in rows:
        if not r.get("稳定"):
            print(f"  {r['c']:>3}{'不稳定':>10}")
            continue
        print(f"  {r['c']:>3}{r['rho']:10.4f}{r['Wq'] * 60:10.2f}"
              f"{r['服务台成本']:12.2f}{r['等待成本']:12.2f}"
              f"{r['总成本']:12.2f}")

    stable = [r for r in rows if r.get("稳定")]
    if stable:
        best = min(stable, key=lambda r: r["总成本"])
        print(f"\n[结论] 最优服务台数 c = {best['c']}")
        print(f"  此时利用率 {best['rho']:.4f}，"
              f"平均等待 {best['Wq'] * 60:.2f} 分钟，"
              f"每小时总成本 {best['总成本']:.2f}")

        # 服务水平视角
        for target in (5.0, 10.0):
            ok = [r for r in stable if r["Wq"] * 60 <= target]
            if ok:
                c_need = min(r["c"] for r in ok)
                print(f"  若要求平均等待 <= {target:.0f} 分钟，"
                      f"至少需要 c = {c_need} 个服务台")

    plot_metrics()
    return 0


if __name__ == "__main__":
    sys.exit(main())
