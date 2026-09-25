"""fig.timeseries —— 时间演化曲线。

为什么这是最该有的模板
----------------------
语料里 41.3% 的 Outstanding 论文都有时间演化图，是**出现率最高**的一类。
早先的模板库里一个都没有 —— 结果就是每篇论文的时间序列图都得手画，
而手画的图不绑原子，论文里的数字和代码就断了联系。

数据从哪来
----------
data 的键：
    t         横轴，通常是日期或时间步
    y         主序列（模型输出）
    observed  观测序列（可选）—— 有它就画成对照，这是论文最需要的形态
    series    分组名（可选）—— 多组时画多条线
    events    事件位置列表（可选）—— 竖虚线标出"第几天发生了什么事"

meta 里可能有：caption / x_label / y_label / width_in
"""

from __future__ import annotations

from typing import Any, Dict

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402


def render(data: Dict[str, Any], meta: Dict[str, Any] | None = None):
    meta = meta or {}
    y = list(data.get("y") or [])
    if not y:
        # 空图看起来像"跑成功了但没结果"，比直接报错难查得多。
        raise ValueError("缺少必填输入 y：请提供要画成曲线的数值序列。")

    t = list(data.get("t") or range(len(y)))
    if len(t) != len(y):
        raise ValueError(
            f"t 有 {len(t)} 个点，y 有 {len(y)} 个点，数量必须一致。"
        )

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.6), 3.9))

    observed = data.get("observed")
    series = data.get("series")

    if series:
        # 多组：按组名切段画线。组名顺序按首次出现，不排序 ——
        # 用户给的顺序往往就是他想让读者看到的顺序。
        groups: Dict[str, list] = {}
        for i, name in enumerate(series):
            groups.setdefault(str(name), []).append(i)
        for name, idx in groups.items():
            ax.plot([t[i] for i in idx], [y[i] for i in idx],
                    "-", lw=1.8, label=mcmplot.safe(name))
        ax.legend(frameon=False, fontsize=9)
    else:
        ax.plot(t, y, "-", lw=1.9, color="#1f4e79",
                label=mcmplot.safe(meta.get("y_label", "")) or "模型")

    # 观测序列画成散点叠在上面：实线是模型，点是被拟合的现实。
    # 用点不用线，是因为评审看的就是"模型有没有抓住数据的形状"。
    if observed:
        observed = list(observed)
        if len(observed) != len(t):
            raise ValueError(
                f"observed 有 {len(observed)} 个点，t 有 {len(t)} 个点，"
                "数量必须一致。"
            )
        ax.plot(t, observed, "o", ms=2.6, color="#c0392b", alpha=0.65,
                label="观测", markevery=max(1, len(t) // 120))
        if not series:
            ax.legend(frameon=False, fontsize=9)

    for ev in (data.get("events") or []):
        ax.axvline(ev, ls=":", lw=1.1, color="#777777")
        ax.annotate(mcmplot.safe(str(ev)), xy=(ev, 0.97),
                    xycoords=("data", "axes fraction"),
                    xytext=(3, 0), textcoords="offset points",
                    fontsize=8, color="#555555", va="top", rotation=90)

    ax.set_xlabel(mcmplot.safe(meta.get("x_label", "时间")))
    ax.set_ylabel(mcmplot.safe(meta.get("y_label", "数值")))
    if meta.get("caption"):
        ax.set_title(mcmplot.safe(meta["caption"].rstrip(".")))
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
