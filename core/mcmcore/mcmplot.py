"""绘图的共享底座：中文字体、负号、以及"把中文安全地交给 matplotlib"。

为什么需要这个模块
------------------
matplotlib 默认字体 DejaVu Sans **不含任何汉字**。写
``ax.set_title("人数变化")`` 得到的是六个豆腐块 —— 图能生成、
不报错、看起来"成功了"，但完全没法用。这种失败比崩溃难查得多。

还有两个更细的坑：

* DejaVu Sans 没有 U+2212（真正的减号）。matplotlib 默认用它画负号，
  配上中文字体后负号会变成方块。所以要把 ``axes.unicode_minus`` 关掉，
  让它改用 ASCII 连字符。
* 中文字体普遍**没有上标 ``²``**（U+00B2）和数学符号。所以
  ``R²``、``m³`` 这类写法在中文字体下同样是豆腐块，要换成 ASCII
  （``R2``）或让 matplotlib 用数学模式（``$R^2$``）。

``safe()`` 做的就是最后这件事：把中文文本里字体画不出来的字符换掉。
调用它比让用户去看方块强。
"""

from __future__ import annotations

import re
from typing import Any, Optional

# 按优先级排列。第一个装得上的就用它。
CJK_CANDIDATES = [
    "PingFang SC", "Hiragino Sans GB", "Heiti SC", "STHeiti",
    "Songti SC", "Arial Unicode MS", "Noto Sans CJK SC",
    "Microsoft YaHei", "SimHei", "WenQuanYi Zen Hei",
    "Heiti TC", "Hiragino Sans", "Lantinghei SC",
]

_READY = False
_FONT: Optional[str] = None

# 字体画不出来的字符 -> 可画的替代写法。
# 上标下标最常踩：中文字体基本都没有 ²³ 这些。
SUBSTITUTIONS = {
    "\u00b2": "2",    # ²
    "\u00b3": "3",    # ³
    "\u00b9": "1",    # ¹
    "\u2070": "0", "\u2074": "4", "\u2075": "5", "\u2076": "6",
    "\u2077": "7", "\u2078": "8", "\u2079": "9",
    "\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3",
    "\u2084": "4", "\u2085": "5", "\u2086": "6", "\u2087": "7",
    "\u2088": "8", "\u2089": "9",
    "\u2212": "-",    # 真减号
    "\u2013": "-",    # en dash
    "\u2014": "--",   # em dash
    "\u00b7": ".",    # 间隔号
    "\u00d7": "x",    # 乘号
    "\u00f7": "/",    # 除号
    "\u2264": "<=", "\u2265": ">=", "\u2260": "!=",
    "\u2248": "~=", "\u221e": "inf",
}


def setup(force: bool = False) -> Optional[str]:
    """挑一个能画中文的字体装上。返回选中的字体名（没有则 None）。

    找不到中文字体时**不抛错**：宁可图里的中文变方块，
    也不能让整个生图功能不可用 —— 用户可能只是想画个英文图。
    """
    global _READY, _FONT
    if _READY and not force:
        return _FONT

    import matplotlib
    import matplotlib.font_manager as fm

    available = {f.name for f in fm.fontManager.ttflist}
    chosen = next((n for n in CJK_CANDIDATES if n in available), None)

    if chosen:
        # 中文字体排第一，后面兜底英文。这样数字和英文走 DejaVu，
        # 中文走中文字体，混排时都不缺字。
        matplotlib.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
        _FONT = chosen

    # 负号必须关：DejaVu Sans 没有 U+2212，中文字体也没有，
    # 开着它坐标轴上的负数就是方块。
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["figure.dpi"] = 150
    matplotlib.rcParams["savefig.bbox"] = "tight"
    _READY = True
    return _FONT


def has_cjk() -> bool:
    """当前有没有装上是中文的字体。面板用它提示用户。"""
    setup()
    return _FONT is not None


def safe(text: Any, math: bool = False) -> str:
    """把一段文本变成"字体画得出来"的样子。

    ``math=True`` 时把 ``R2`` 这类写法转成 ``$R^2$``，让 matplotlib
    用数学字体画上标 —— 中文字体没有上标字形。
    """
    if text is None:
        return ""
    s = str(text)
    for bad, good in SUBSTITUTIONS.items():
        s = s.replace(bad, good)
    if math:
        s = re.sub(r"\b([A-Za-z])(\d)\b", r"$\1^\2$", s)
    return s


def mathify(symbol: str, sub: Optional[str] = None,
            sup: Optional[str] = None) -> str:
    """拼一个数学标记，例如 mathify("R", sup="2") -> "$R^2$"。

    比手写 ``$R^2$`` 稳：手写时忘了转义下划线会直接编译失败。
    """
    body = str(symbol)
    if sub:
        body += f"_{{{sub}}}"
    if sup:
        body += f"^{{{sup}}}"
    return f"${body}$"
