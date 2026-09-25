# -*- coding: utf-8 -*-
"""元胞自动机 / 网格仿真 —— 代码骨架（可直接复制使用）

【解决什么问题】
  空间上的扩散与传播：森林火灾蔓延、传染病空间扩散、城市扩张、
  交通流、舆情传播。共同点是"每个格子的下一状态只取决于它和邻居的当前状态"。

  本骨架实现一个通用的二维元胞自动机 + 森林火灾案例：
    * 每个格子状态：空地 / 树木 / 燃烧中
    * 邻居规则（Moore 8 邻域）：燃烧的格子把邻居的树点燃；
      树有一定概率自然引燃，燃烧若干步后变成空地

【要改哪几行】
  1. `next_state()` —— 你的演化规则，改这一个函数就够
  2. `GRID_SIZE`    —— 网格边长
  3. `P_GROW`, `P_IGNITE`, `BURN_STEPS` —— 生长率 / 引燃率 / 燃烧持续步数
  4. `N_STEPS`      —— 演化步数

【输入】初始网格 + 演化规则
【输出】各步网格快照、统计曲线（树木覆盖率等）、演化过程图

【注意】下面的数据和参数是模拟的，替换成你的规则。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

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
GRID_SIZE = 100          # 网格边长（100x100）
N_STEPS = 60             # 演化步数
P_GROW = 0.02            # 空地长出新树的概率
P_IGNITE = 0.0006        # 树被雷击自然引燃的概率
BURN_STEPS = 4           # 燃烧持续多少步后变成空地
INIT_TREE_DENSITY = 0.7  # 初始树木覆盖率
SEED = 2025

# 状态编码
EMPTY, TREE, BURNING = 0, 1, 2
STATE_NAMES = {EMPTY: "空地", TREE: "树木", BURNING: "燃烧"}


# ============================== 1. 初始化 ==================================
def init_grid(n: int, density: float,
              seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """初始网格：随机撒树；aget 记录每个格子已经烧了几步。

    >>> 换成你的初始条件 <<<
    """
    rng = np.random.default_rng(seed)
    grid = np.where(rng.random((n, n)) < density, TREE, EMPTY).astype(np.int8)
    age = np.zeros((n, n), dtype=np.int16)
    return grid, age


# ============================== 2. 演化规则 ================================
def count_burning_neighbors(grid: np.ndarray) -> np.ndarray:
    """统计每个格子的 Moore 8 邻域里有多少个正在燃烧。

    用 np.roll 做环形移位，等价于周期性边界（左右上下相连）。
    比双重循环快几十倍，是大网格仿真的关键技巧。
    """
    counts = np.zeros(grid.shape, dtype=np.int16)
    burning = (grid == BURNING).astype(np.int16)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            counts += np.roll(np.roll(burning, dx, axis=0), dy, axis=1)
    return counts


def next_state(grid: np.ndarray, age: np.ndarray,
               rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    """核心：写你的演化规则。

    规则：
      1. 燃烧中的格子：age+1；烧够 BURN_STEPS 步后变成空地
      2. 树：若邻域有燃烧的格子，则被点燃；否则以 P_IGNITE 概率自燃
      3. 空地：以 P_GROW 概率长出新树

    >>> 换成你的规则 <<<
    """
    n = grid.shape[0]
    new_grid = grid.copy()
    new_age = age.copy()

    burning_nb = count_burning_neighbors(grid)

    # --- 1. 燃烧 -> 空地 ---
    burning_mask = (grid == BURNING)
    new_age[burning_mask] = age[burning_mask] + 1
    burned_out = burning_mask & (new_age >= BURN_STEPS)
    new_grid[burned_out] = EMPTY
    new_age[burned_out] = 0

    # --- 2. 树 -> 燃烧 ---
    tree_mask = (grid == TREE)
    # 邻域有火：必定被点燃（这一步可以改成按概率，更像真实情形）
    caught = tree_mask & (burning_nb > 0)
    # 自然引燃
    spontaneous = tree_mask & (rng.random((n, n)) < P_IGNITE) & (~caught)
    new_grid[caught | spontaneous] = BURNING
    new_age[caught | spontaneous] = 0

    # --- 3. 空地 -> 树 ---
    empty_mask = (grid == EMPTY) & (~burned_out)
    grow = empty_mask & (rng.random((n, n)) < P_GROW)
    new_grid[grow] = TREE

    return new_grid, new_age


# ============================== 3. 统计 ====================================
def grid_stats(grid: np.ndarray) -> dict:
    """统计各状态占比。"""
    total = grid.size
    return {
        "空地": float((grid == EMPTY).sum()) / total,
        "树木": float((grid == TREE).sum()) / total,
        "燃烧": float((grid == BURNING).sum()) / total,
    }


def run_simulation(n: int, steps: int, seed: int
                   ) -> Tuple[List[np.ndarray], List[dict]]:
    """跑完整仿真，返回快照列表与逐步统计。"""
    rng = np.random.default_rng(seed)
    grid, age = init_grid(n, INIT_TREE_DENSITY, seed)

    snapshots = [grid.copy()]
    stats = [grid_stats(grid)]

    for _ in range(steps):
        grid, age = next_state(grid, age, rng)
        snapshots.append(grid.copy())
        stats.append(grid_stats(grid))

    return snapshots, stats


# ============================== 4. 画图 ====================================
def plot_snapshots(snapshots: List[np.ndarray],
                   indices: Optional[List[int]] = None,
                   out_png: Optional[str] = None) -> None:
    """演化快照：挑若干步画成子图。"""
    out_png = out_path(out_png, "ca_snapshots.png")
    if mcmplot is None:
        print("\n[跳过画图] 没找到 mcmplot 模块")
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap
    except ImportError:
        return

    mcmplot.setup()

    if indices is None:
        last = len(snapshots) - 1
        indices = sorted(set([0, last // 4, last // 2, 3 * last // 4, last]))

    # 空地=浅黄, 树=绿, 火=红
    cmap = ListedColormap(["#f0e6c8", "#2e7d32", "#d32f2f"])

    fig, axes = plt.subplots(1, len(indices), figsize=(3.1 * len(indices), 3.5))
    axes = np.atleast_1d(axes)
    for ax, k in zip(axes, indices):
        ax.imshow(snapshots[k], cmap=cmap, vmin=0, vmax=2,
                  interpolation="nearest")
        ax.set_title(safe(f"第 {k} 步"))
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(safe("元胞自动机演化快照（黄=空地 绿=树木 红=燃烧）"))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"\n[出图] 已保存 {out_png}")


def plot_stats(stats: List[dict], out_png: Optional[str] = None) -> None:
    """各状态占比随时间变化。"""
    out_png = out_path(out_png, "ca_stats.png")
    if mcmplot is None:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    mcmplot.setup()

    t = np.arange(len(stats))
    fig, ax = plt.subplots(figsize=(9.0, 4.4))
    colors = {"空地": "#c9a227", "树木": "#2e7d32", "燃烧": "#d32f2f"}
    for key in ["空地", "树木", "燃烧"]:
        y = np.array([s[key] for s in stats])
        ax.plot(t, y, lw=1.8, color=colors[key], label=safe(key))
    ax.set_xlabel(safe("演化步数"))
    ax.set_ylabel(safe("面积占比"))
    ax.set_title(safe("元胞自动机状态演化"))
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"[出图] 已保存 {out_png}")


# ============================== 主流程 ====================================
def main() -> int:
    print("=" * 66)
    print("元胞自动机 / 网格仿真（森林火灾模型，参数是模拟的）")
    print("=" * 66)

    print(f"\n[设置] 网格 {GRID_SIZE}×{GRID_SIZE}  步数={N_STEPS}")
    print(f"[参数] 生长率={P_GROW}  引燃率={P_IGNITE}  "
          f"燃烧持续={BURN_STEPS} 步  初始树木密度={INIT_TREE_DENSITY}")

    snapshots, stats = run_simulation(GRID_SIZE, N_STEPS, SEED)

    print(f"\n[初始状态]")
    for k, v in stats[0].items():
        print(f"  {safe(k):<6} {v:7.4%}")

    print(f"\n[演化过程] 每 10 步抽样")
    print(f"  {'步数':>6}{'空地':>10}{'树木':>10}{'燃烧':>10}")
    for i in range(0, len(stats), 10):
        s = stats[i]
        print(f"  {i:6d}{s['空地']:10.4f}{s['树木']:10.4f}{s['燃烧']:10.4f}")

    # --- 关键统计 ---
    tree_series = np.array([s["树木"] for s in stats])
    burn_series = np.array([s["燃烧"] for s in stats])

    print(f"\n[统计结论]")
    print(f"  树木覆盖率：初始 {tree_series[0]:.2%} -> "
          f"末态 {tree_series[-1]:.2%}")
    print(f"  最低 {tree_series.min():.2%}（第 {int(tree_series.argmin())} 步）")
    print(f"  燃烧峰值 {burn_series.max():.2%}"
          f"（第 {int(burn_series.argmax())} 步）")

    # 火灾是否发生过
    n_fires = int((burn_series > 0).sum())
    print(f"  有明火的步数：{n_fires} / {len(stats)}")

    # 稳态判断：后半段波动很小就认为达到稳态
    tail = tree_series[len(tree_series) // 2:]
    if tail.std() < 0.02:
        print(f"  后半段树木覆盖率标准差 {tail.std():.4f}，系统已达稳态。")
    else:
        print(f"  后半段树木覆盖率标准差 {tail.std():.4f}，"
              f"系统仍在波动（火烧周期）。")

    # 简单的敏感度提示
    print(f"\n[拓展提示] 把 P_GROW 调大，火灾会更频繁；"
          f"把 BURN_STEPS 调小，火烧得快、破坏反而小。")

    plot_snapshots(snapshots)
    plot_stats(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
