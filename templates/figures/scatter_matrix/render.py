"""fig.scatter_matrix —— 两两配对的散点矩阵（相关性总览）。

数据从哪来
----------
data 是一个 dict，键是模板声明的输入名：

    frame       变量数据，必填。支持三种形状：
                  1) dict：{"变量名": [数值, ...], ...}
                  2) 二维数组（list of lists）：每列是一个变量
                  3) pandas DataFrame（会在内部转成上面两种之一）
    variables   变量名列表（可选）。frame 是纯二维数组时用它给列命名；
                也可以用它从 frame 里挑出要画的子集并控制先后顺序。

画什么
------
n 个变量画成 n×n 的子图阵列：对角线画变量自身的直方图（看分布），
右上三角画两两散点并在标题里给出 Pearson 相关系数，左下三角留白，
避免同一组关系画两遍。为了不让图变成一片糊，最多取 6 个变量 —— 再多
就在返回前明确报错，而不是偷偷截断。

样本长度不一致的学生常犯错误在这里会被拦下来：任何一个变量与第一个
变量的长度对不上，直接抛 ValueError 说清楚是哪个变量差了多少个点。

统一约定（所有图模板都遵守）
    render(data, meta) -> matplotlib Figure
    meta 里可能有：caption / title / width_in
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
# 没有这一步，中文标签会被画成一排空心方框，而且不报错。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# 一次最多画几个变量。6 个已经是 6×6=36 个子图，再多单张子图就看不见了。
_MAX_VARIABLES = 6
_MIN_VARIABLES = 2


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}

    frame = data.get("frame")
    if frame is None:
        raise ValueError("缺少必填输入 frame：请提供 dict、二维数组或 DataFrame。")

    names, columns = _to_columns(frame, data.get("variables"))

    n = len(names)
    if n < _MIN_VARIABLES:
        raise ValueError(
            f"散点矩阵至少需要 {_MIN_VARIABLES} 个变量，当前只有 {n} 个：{names}。"
        )
    if n > _MAX_VARIABLES:
        raise ValueError(
            f"散点矩阵最多支持 {_MAX_VARIABLES} 个变量，当前有 {n} 个：{names}。"
            "请先用 variables 指定要画的子集，或先做一轮特征筛选。"
        )

    arrays = [_as_float_list(columns[i], names[i]) for i in range(n)]
    _check_lengths(names, arrays)

    width = float(meta.get("width_in", 6.0))
    # 每个子图约 1.5 英寸见方，变量多了整张图同步变大
    side = max(4.5, width * n / 3.2)
    fig, axes = plt.subplots(n, n, figsize=(side, side))

    # n=2 时 subplots 仍然返回二维数组，这里统一成 [[ax, ...], ...]
    if n == 1:
        axes = np.array([[axes]])
    axes = np.asarray(axes).reshape(n, n)

    primary = "#1f4e79"
    for i in range(n):
        for j in range(n):
            ax = axes[i, j]
            yi = arrays[i]
            xj = arrays[j]

            if i == j:
                # 对角线：看单变量分布
                ax.hist([v for v in yi if np.isfinite(v)], bins=12,
                        color=primary, alpha=0.75)
                ax.set_yticks([])
                ax.grid(alpha=0.25, axis="y")
            elif j > i:
                # 右上三角：散点 + 相关系数
                ax.scatter(xj, yi, s=12, color=primary, alpha=0.7,
                           edgecolors="none")
                r = _pearson(xj, yi)
                ax.annotate(f"r = {_fmt(r)}", xy=(0.04, 0.92),
                            xycoords="axes fraction", fontsize=7,
                            color="#b03030", va="top")
                ax.grid(alpha=0.25)
            else:
                # 左下三角留白，同一组关系不重复画
                ax.axis("off")
                continue

            if i == n - 1:
                ax.set_xlabel(names[j], fontsize=9)
            else:
                ax.set_xticklabels([])
            if j == 0:
                ax.set_ylabel(names[i], fontsize=9)
            else:
                ax.set_yticklabels([])
            ax.tick_params(labelsize=7)

    if meta.get("caption"):
        fig.suptitle(meta["caption"].rstrip("."), fontsize=10)
    fig.tight_layout()
    return fig


def _to_columns(frame: Any, variables: Any):
    """把各种形状的 frame 整理成 (变量名列表, 变量值列表)。"""
    if hasattr(frame, "columns") and hasattr(frame, "__getitem__"):
        # pandas DataFrame（这里不 import pandas，避免多一个硬依赖）
        all_names = [str(c) for c in frame.columns]
        selected = _select(all_names, variables)
        cols = [list(frame[c]) for c in selected]
        return selected, cols

    if isinstance(frame, dict):
        all_names = list(frame.keys())
        selected = _select(all_names, variables)
        cols = [list(_as_sequence(frame[k], str(k))) for k in selected]
        return selected, cols

    if isinstance(frame, (list, tuple)):
        rows = list(frame)
        if not rows:
            raise ValueError("frame 是空的：请提供至少两个变量的数据。")
        if all(isinstance(r, (list, tuple)) for r in rows):
            n_cols = len(rows[0])
            # 行数远大于列数时，几乎肯定是"每行一个样本"的矩阵
            if len(rows) >= n_cols:
                cols = [[row[c] for row in rows] for c in range(n_cols)]
            else:
                cols = [list(r) for r in rows]
            all_names = [str(i + 1) for i in range(len(cols))]
        else:
            cols = [[v] for v in rows]
            all_names = [str(i + 1) for i in range(len(cols))]
        # 纯数组没有列名，variables 在这里是"给列起名"的，不是"挑选列"。
        # 名字数量对得上就直接采用，对不上才按名字去挑（并在此报错）。
        if variables and len(list(variables)) == len(cols):
            all_names = [str(v) for v in variables]
            return list(all_names), cols
        selected = _select(all_names, variables)
        idx = [all_names.index(s) for s in selected]
        return selected, [cols[i] for i in idx]

    raise ValueError(
        f"frame 的类型是 {type(frame).__name__}，无法识别。"
        "请提供 dict、二维数组（list of lists）或 pandas DataFrame。"
    )


def _select(all_names: List[str], variables: Any) -> List[str]:
    """按 variables 选出要画的变量名，保持调用方给的顺序。"""
    if not variables:
        return list(all_names)
    wanted = [str(v) for v in variables]
    missing = [v for v in wanted if v not in all_names]
    if missing:
        raise ValueError(
            f"variables 里的 {missing} 在 frame 中不存在，可用的变量名是 {all_names}。"
        )
    return wanted


def _as_sequence(values: Any, name: str) -> List[Any]:
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        raise ValueError(f"变量 {name} 不是序列（当前是 {type(values).__name__}）。")
    return list(values)


def _as_float_list(values: List[Any], name: str) -> List[float]:
    out: List[float] = []
    for v in values:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            raise ValueError(f"变量 {name} 里含有非数值元素 {v!r}，无法画散点矩阵。")
    return out


def _check_lengths(names: List[str], arrays: List[List[float]]) -> None:
    base = len(arrays[0])
    for name, arr in zip(names[1:], arrays[1:]):
        if len(arr) != base:
            raise ValueError(
                f"变量 {names[0]} 有 {base} 个观测，变量 {name} 有 {len(arr)} 个，"
                "数量必须一致（散点矩阵是同一个样本集上的配对关系）。"
            )


def _pearson(x: List[float], y: List[float]) -> float:
    a = np.asarray(x, dtype=float)
    b = np.asarray(y, dtype=float)
    if a.size < 2:
        return float("nan")
    if np.std(a) == 0 or np.std(b) == 0:
        # 常数变量没有相关性可言，返回 nan 让标注显示 nan 而不是崩掉
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _fmt(v: Any) -> str:
    """数字格式化：太小或太大的值用科学计数法，否则保留 4 位有效数字。

    统一走 mcmplot.fmt，保证全库图上的数字长得一样。
    """
    return mcmplot.fmt(v)
