#!/usr/bin/env python3
"""A REAL experiment: the PCQL model from 2023 MCM Problem C (paper 2307166).

This is not a stub. It integrates the paper's actual ODE system with the
paper's actual fitted parameters, and it performs the paper's actual
sensitivity sweep over the participation factor beta.

The paper states its protocol verbatim:
    "In each parameter analysis, we only varied that parameter while keeping
     the other parameters at their default values."

The function receives ONE resolved parameter set (the runner handles the sweep)
and returns typed atoms. It never writes a number into prose: the runner stamps
each atom with the condition it was computed under.

Usage (the runner calls this; you do not):
    mcm exp run EXP-001 --dir <project>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# The paper's fitted parameters (2023 C/2307166, p.13)
#   beta = 1.77e-01  gamma = 1.77e-02  lambda = 1.04e-03  phi = 1.14e-03
# ---------------------------------------------------------------------------
DEFAULTS = {
    "beta": 1.77e-01,
    "gamma": 1.77e-02,
    "lambda": 1.04e-03,
    "phi": 1.14e-03,
    "N": 300_000.0,      # initial potential population
    "C0": 1_000.0,       # initial crowd
    "L0": 0.0,           # initial loyal
    "days": 120,
    "dt": 0.05,
}


def pcql_derivs(state, p):
    """The PCQL system, exactly as printed in the paper (equations 1-4).

        dP/dt = -beta * P * (C+L) / N
        dC/dt =  beta * P * (C+L) / N - gamma*C - lambda*C
        dQ/dt =  gamma * C
        dL/dt =  lambda * C - phi * L
    """
    P, C, Q, L = state
    infection = p["beta"] * P * (C + L) / p["N"]
    dP = -infection
    dC = infection - p["gamma"] * C - p["lambda"] * C
    dQ = p["gamma"] * C
    dL = p["lambda"] * C - p["phi"] * L
    return (dP, dC, dQ, dL)


def integrate(p):
    """RK4 integration of the PCQL system.

    RK4 rather than Euler: with beta ~ 0.18 and dt = 0.05 the Euler solution
    visibly undershoots the peak, which would corrupt the sensitivity result.
    """
    steps = int(p["days"] / p["dt"])
    state = (p["N"] - p["C0"], p["C0"], 0.0, p["L0"])
    peak_C = state[1]
    peak_day = 0.0
    traj = []

    for i in range(steps):
        t = i * p["dt"]
        k1 = pcql_derivs(state, p)
        s2 = tuple(state[j] + 0.5 * p["dt"] * k1[j] for j in range(4))
        k2 = pcql_derivs(s2, p)
        s3 = tuple(state[j] + 0.5 * p["dt"] * k2[j] for j in range(4))
        k3 = pcql_derivs(s3, p)
        s4 = tuple(state[j] + p["dt"] * k3[j] for j in range(4))
        k4 = pcql_derivs(s4, p)
        state = tuple(
            state[j] + (p["dt"] / 6.0) * (k1[j] + 2 * k2[j] + 2 * k3[j] + k4[j])
            for j in range(4)
        )
        C = state[1]
        if C > peak_C:
            peak_C = C
            peak_day = t
        traj.append((t, state[0], C, state[2], state[3]))

    return state, peak_C, peak_day, traj


def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """One trial. `params` is the resolved parameter set for this trial."""
    p = dict(DEFAULTS)
    p.update({k: v for k, v in params.items() if v is not None})

    final, peak_C, peak_day, traj = integrate(p)

    # Reported quantities. Each becomes a ResultAtom with its condition.
    atoms: List[Dict[str, Any]] = [
        {
            "name": "peak_active",
            "value": round(peak_C, 2),
            "unit": "players",
            "format": "%.2f",
            "metric_def": "maximum of the Crowd compartment C(t)",
        },
        {
            "name": "peak_day",
            "value": round(peak_day, 2),
            "unit": "days",
            "format": "%.2f",
            "metric_def": "time at which C(t) is maximal",
        },
        {
            "name": "final_active",
            "value": round(final[1], 2),
            "unit": "players",
            "format": "%.2f",
            "metric_def": "C(t) at the end of the horizon",
        },
        {
            "name": "final_loyal",
            "value": round(final[3], 2),
            "unit": "players",
            "format": "%.2f",
            "metric_def": "L(t) at the end of the horizon",
        },
        {
            "name": "final_quitted",
            "value": round(final[2], 2),
            "unit": "players",
            "format": "%.2f",
            "metric_def": "Q(t) at the end of the horizon",
        },
    ]

    # 把轨迹写到脚本自己的 output/ 下，文件名带上参数，避免不同试验互相覆盖。
    tag = "_".join(f"{k}{v}" for k, v in sorted(p.items()))
    out_dir = Path(__file__).resolve().parent / "output"
    if out_dir.is_dir():
        # 清空暂存区：所有试验共用这个目录，不清的话这次运行会把上一次
        # 试验留下的文件也报告成自己的产物。真正的归档在 runs/ 下，
        # 由 runner 负责，所以这里删掉是安全的。
        for old_file in out_dir.iterdir():
            if old_file.is_file():
                old_file.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    traj_path = out_dir / f"trajectory_{tag}.csv"
    with open(traj_path, "w", encoding="utf-8") as fh:
        fh.write("day,susceptible,crowd,quitted,loyal\n")
        for t, S, C, Q, L in traj:
            fh.write(f"{t:.4f},{S:.6f},{C:.6f},{Q:.6f},{L:.6f}\n")

    return {
        "atoms": atoms,
        "metrics": [
            {
                "name": "peak_active",
                "value": round(peak_C, 2),
                "unit": "players",
                "direction": "neutral",
            }
        ],
        # 完整轨迹落盘成一个产物文件：图可以绑定它，不必重跑积分。
        # 脚本只负责"写文件 + 报告路径"，存到哪个归档目录由 runner 决定
        # （见 core/mcmcore/runstore.py）—— 归档策略不该写进建模脚本。
        "artifacts": [str(traj_path)],
        "_trajectory": traj,
    }
