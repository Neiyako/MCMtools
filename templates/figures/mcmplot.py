"""所有图模板共用的绘图环境设置。

为什么必须有这个模块
--------------------
matplotlib 默认字体是 DejaVu Sans，**不含中文字形**。用中文当坐标轴
标签时不会报错，只会在图上印出一排空心方框 —— 图照常生成、照常导出、
照常插进论文，等你发现时已经排版完了。这个坑真实踩到过。

所以字体设置放在这里统一做，并在找不到中文字体时**明确警告**，
而不是静默画出一堆方框。

模板作者只需要：

    from mcmplot import setup, fmt, save_pdf
    setup()
"""

from __future__ import annotations

import warnings
from typing import Any, List, Optional

# 中文字体候选：按优先级排。macOS / Windows / Linux 各覆盖一遍，
# 找不到第一个就往下试。
CJK_FONTS: List[str] = [
    "PingFang SC",        # macOS 默认
    "Hiragino Sans GB",   # macOS
    "Heiti SC",           # macOS
    "STHeiti",            # macOS
    "SimHei",             # Windows 默认黑体
    "Microsoft YaHei",    # Windows
    "Noto Sans CJK SC",   # Linux
    "Source Han Sans SC", # Linux
    "WenQuanYi Zen Hei",  # Linux
    "Arial Unicode MS",   # 兜底
]

_configured = False


def setup(verbose: bool = False) -> Optional[str]:
    """配置 matplotlib 以正确显示中文和负号。返回选中的中文字体名。"""
    global _configured
    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((f for f in CJK_FONTS if f in available), None)

    if chosen:
        plt.rcParams["font.sans-serif"] = [chosen] + plt.rcParams.get(
            "font.sans-serif", []
        )
    else:
        # 找不到就直说。静默画方框比报错糟糕得多。
        warnings.warn(
            "没有找到中文字体，图上的中文会显示成方框。"
            f"请安装以下任一字体：{', '.join(CJK_FONTS[:4])}",
            RuntimeWarning,
            stacklevel=2,
        )
    # 负号默认用 U+2212，很多中文字体没有这个字形，会显示成方框。
    plt.rcParams["axes.unicode_minus"] = False
    # 论文图偏小，字号统一调一档，保证缩到 0.8\linewidth 后还看得清。
    plt.rcParams.update({
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 110,
    })
    if verbose:
        print(f"绘图字体：{chosen or '（未找到中文字体）'}")
    _configured = True
    return chosen


def fmt(v: Any) -> str:
    """数字格式化：极小或极大的值用科学计数法，否则 4 位有效数字。

    图上的数字要能一眼读完，所以不做无意义的精度展示 ——
    0.0010400000001 不如 1.040e-03。精确值由 ResultAtom 负责，
    图只需要传达量级。
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != 0 and (abs(f) < 1e-3 or abs(f) >= 1e5):
        return f"{f:.2e}"
    return f"{f:.4g}"


def save_pdf(fig, path: str, dpi: int = 300) -> str:
    """存成矢量 PDF —— 论文里插图必须是矢量，位图放大会糊。

    dpi 只影响 PDF 里嵌的位图元素（如散点密度图），矢量部分不受影响。
    """
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    return path


# 中文字体里缺失、但科研图常用的字符 -> ASCII 安全替代。
# 这些字符画出来是空心方框，而且**不报错**，等排完版才发现。
# 上标 2 是最容易踩的：R² 几乎每篇建模论文都有。
GLYPH_FALLBACKS = {
    "\u00b2": "^2",   # ²  R²
    "\u00b3": "^3",   # ³
    "\u00b9": "^1",   # ¹
    "\u207b": "^-",  # ⁻  上标负号
    "\u2212": "-",    # −  数学减号（U+2212，不是 ASCII 连字符）
    "\u2013": "-",    # –  en dash
    "\u2014": "--",   # —  em dash
}


def safe(text: Any) -> str:
    """把中文字体画不出来的字符换成 ASCII 等价写法。

    为什么不留着原字符：macOS/Windows/Linux 上能显示这些符号的字体
    都不一样，而论文要跨平台编译。换成 ASCII 是唯一稳的做法 ——
    R^2 和 R² 在读者眼里没区别，但前者一定画得出来。
    """
    out = str(text)
    for bad, good in GLYPH_FALLBACKS.items():
        out = out.replace(bad, good)
    return out


def close(fig) -> None:
    """用完立刻释放 figure。

    pyplot 会保留每个创建过的 figure，直到显式关闭。批量出图时
    （比如一次生成 50 张）内存会一直涨，最后 matplotlib 自己发
    "More than 20 figures have been opened" 警告。渲染函数不负责
    关闭 —— 关掉之后调用方就没法 savefig 了，所以由调用方在存完之后调这个。
    """
    import matplotlib.pyplot as plt

    plt.close(fig)


def spread_labels(fig, anns, gap: float = 1.0, rounds: int = 14) -> int:
    """把互相压住的标注推开，返回还剩下几处重叠。

    为什么需要：雷达图上"分数接近"不等于"屏幕位置接近"。两个指标
    取值相近时顶点挨着；多个系列的对应顶点可能**完全重合** ——
    三个数值标注可能落在同一个像素上，只剩最上面那个能读。

    做法：画完量 bbox，两两比对，把重叠的按序号绕扇形散开。

    踩过的坑：**不能按"相对圆心的方向"推**。三个标注重合时方向
    完全相同，它们会一起移动、永远保持重叠 —— 我第一版就是这么写的，
    结果把标注推到了画布外 400 点。所以这里按序号给不同方向。

    用 `ann.xyann`（不是 `xytext`）读写偏移，单位是 offset points。
    """
    import math

    for rnd in range(rounds):
        fig.canvas.draw()
        ren = fig.canvas.get_renderer()
        boxes = []
        for a in anns:
            try:
                bb = a.get_window_extent(renderer=ren)
            except Exception:          # pragma: no cover - 极端情况
                bb = None
            if bb is not None and bb.width > 0 and bb.height > 0:
                boxes.append((a, bb))

        clashing = set()
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                _a1, b1 = boxes[i]
                _a2, b2 = boxes[j]
                if (min(b1.x1, b2.x1) - max(b1.x0, b2.x0) > gap
                        and min(b1.y1, b2.y1) - max(b1.y0, b2.y0) > gap):
                    clashing.add(i)
                    clashing.add(j)
        if not clashing:
            break

        order = sorted(clashing)
        span = 140.0 if len(order) > 1 else 0.0
        for k, idx in enumerate(order):
            a = boxes[idx][0]
            ang = math.radians(-span / 2 + span * k / max(1, len(order) - 1))
            dx, dy = a.xyann
            a.xyann = (dx + 11 * math.cos(ang), dy + 11 * math.sin(ang))
    return len(clashing)
