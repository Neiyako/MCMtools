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


# ---------------------------------------------------------------------------
# 外观覆盖
# ---------------------------------------------------------------------------
#
# 为什么放在这里而不是改 38 个图模板
# ----------------------------------
# 生图工作台的抱怨是"灵活度不够、不好微调"：模板能画，但线宽、字号、
# 刻度范围全是模板作者定的，用户改不了，只能重新导出去 PS。
#
# 有两条路：
#   1. 给 38 个模板各自加一堆样式参数 —— 改 38 个文件，加一个模板
#      就多一处要维护，而且新模板很容易漏掉某几个旋钮；
#   2. 在**渲染收尾处**统一施加覆盖 —— 改一处，全部模板都受益。
#
# 选了 2。前提是模板都把 meta 传进来了（它们确实传了），
# 所以覆盖可以挂在调用链的最后一环上，模板本身不用知道这件事。
#
# 一个例外：**配色**没法在收尾时改。线的颜色在 plot() 那一刻就定死了，
# 事后遍历 axes 拿不到"这个元素该用什么颜色"的可靠信息。所以配色走
# `palette`（模板自己读），其他的走 apply_overrides。

# 面板上可调的旋钮。键名就是前端传进来的键名，值是 (中文名, 默认值, 类型)。
# 这份清单同时是面板的渲染依据 —— 前端不硬编码，加一个旋钮不用改两处。
OVERRIDES = [
    ("width_in",     "图宽（英寸）",     6.4,  "float"),
    ("height_in",    "图高（英寸）",     4.0,  "float"),
    # PDF 是矢量的，DPI 对它不起作用 —— 只影响导出位图（PNG/TIFF）时的
    # 清晰度。名字里写明"位图"，否则用户调了没变化会以为旋钮坏了。
    ("dpi",          "位图分辨率 DPI",    300,  "int"),
    ("line_width",   "线宽",             1.9,  "float"),
    ("marker_size",  "标记大小",         5.0,  "float"),
    ("font_size",    "字号",             10.0, "float"),
    ("title_size",   "标题字号",         11.0, "float"),
    ("label_size",   "轴标签字号",       9.5,  "float"),
    ("legend_size",  "图例字号",         8.0,  "float"),
    ("legend_loc",   "图例位置",         "best", "str"),
    ("grid_alpha",   "网格透明度",       0.28, "float"),
    ("alpha",        "图形透明度",       1.0,  "float"),
    ("xlim_min",     "横轴下限",         None, "float?"),
    ("xlim_max",     "横轴上限",         None, "float?"),
    ("ylim_min",     "纵轴下限",         None, "float?"),
    ("ylim_max",     "纵轴上限",         None, "float?"),
    ("xtick_rot",    "横轴刻度旋转",     0.0,  "float"),
]

# 面板上能选的图例位置。matplotlib 认这些字符串。
LEGEND_LOCS = ["best", "upper right", "upper left", "lower right",
               "lower left", "center right", "center left",
               "upper center", "lower center", "center", "outside right"]


def catalog() -> dict:
    """给面板的外观选项清单。前端照着渲染，不硬编码。"""
    return {
        "overrides": [
            {"key": k, "label": cn, "default": dv, "type": t}
            for k, cn, dv, t in OVERRIDES
        ],
        "legend_locs": LEGEND_LOCS,
    }


def _num(meta: dict, key: str):
    """取一个数值型覆盖。取不到或不是数字就返回 None（= 不覆盖）。"""
    v = meta.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def apply_overrides(fig, meta: Optional[dict] = None):
    """把面板传来的外观覆盖施加到一张已经画好的图上。

    刻意**不抛异常**：一个旋钮填错了不该让整张图出不来 ——
    那比"无视这一个旋钮"糟得多。所以取不到值就跳过，
    其余的照常生效。

    返回 fig，方便链式调用。
    """
    meta = meta or {}
    if not meta:
        return fig

    # -- 画布 ------------------------------------------------------------
    # 宽高**各自独立**生效。原来要求两个都给才调整，于是只填高度
    # 完全没有反应 —— 用户看到的就是"这个旋钮是坏的"。
    # 没给的那一边保持模板自己的尺寸。
    w = _num(meta, "width_in")
    h = _num(meta, "height_in")
    if w or h:
        try:
            cur_w, cur_h = fig.get_size_inches()
            fig.set_size_inches(w if (w and w > 0) else cur_w,
                                h if (h and h > 0) else cur_h)
        except Exception:  # noqa: BLE001
            pass
    dpi = _num(meta, "dpi")
    if dpi and dpi > 0:
        fig.set_dpi(dpi)

    lw = _num(meta, "line_width")
    ms = _num(meta, "marker_size")
    alpha = _num(meta, "alpha")
    legend_loc = str(meta.get("legend_loc") or "").strip()
    if legend_loc == "outside right":
        legend_loc = "center left"
    legend_size = _num(meta, "legend_size")
    grid_alpha = _num(meta, "grid_alpha")

    axes = list(getattr(fig, "axes", []) or [])

    for ax in axes:
        # -- 线宽 / 标记 / 透明度 ---------------------------------------
        for ln in ax.get_lines():
            try:
                if lw:
                    ln.set_linewidth(lw)
                if ms and ln.get_marker() not in (None, "", "None"):
                    ln.set_markersize(ms)
                if alpha:
                    ln.set_alpha(alpha)
            except Exception:  # noqa: BLE001
                pass

        for coll in list(ax.collections):
            try:
                if alpha:
                    coll.set_alpha(alpha)
                # 散点的点大小是面积，不是直径 —— 直接当成 ms 会大得离谱。
                if ms and hasattr(coll, "set_sizes"):
                    coll.set_sizes([ms ** 2])
            except Exception:  # noqa: BLE001
                pass

        # -- 字号 --------------------------------------------------------
        fs = _num(meta, "font_size")
        ts = _num(meta, "title_size") or fs
        ls = _num(meta, "label_size") or fs
        if ts:
            try:
                ax.title.set_fontsize(ts)
            except Exception:  # noqa: BLE001
                pass
        if fs:
            for lbl in (ax.get_xticklabels() + ax.get_yticklabels()):
                try:
                    lbl.set_fontsize(fs)
                except Exception:  # noqa: BLE001
                    pass
        if ls:
            try:
                ax.xaxis.label.set_fontsize(ls)
                ax.yaxis.label.set_fontsize(ls)
            except Exception:  # noqa: BLE001
                pass

        # 颜色条也是 axes 之一，它的刻度不该被当成主图的刻度调 ——
        # 但字号统一改是合理的，所以上面照常处理。
        if legend_size:
            leg = ax.get_legend()
            if leg is not None:
                try:
                    for txt in leg.get_texts():
                        txt.set_fontsize(legend_size)
                except Exception:  # noqa: BLE001
                    pass
        if legend_loc and ax.get_legend() is not None:
            try:
                ax.legend(loc=legend_loc, fontsize=legend_size or None)
            except Exception:  # noqa: BLE001
                pass

        # -- 网格 --------------------------------------------------------
        if grid_alpha is not None and ax.get_xgridlines():
            try:
                ax.grid(alpha=max(0.0, min(1.0, grid_alpha)))
            except Exception:  # noqa: BLE001
                pass

        # -- 坐标范围 ----------------------------------------------------
        # 直方图等类别轴设 xlim 会把柱子切掉，所以只在用户明确给了值时设。
        xlo, xhi = _num(meta, "xlim_min"), _num(meta, "xlim_max")
        ylo, yhi = _num(meta, "ylim_min"), _num(meta, "ylim_max")
        try:
            if xlo is not None or xhi is not None:
                cur = ax.get_xlim()
                ax.set_xlim(xlo if xlo is not None else cur[0],
                            xhi if xhi is not None else cur[1])
            if ylo is not None or yhi is not None:
                cur = ax.get_ylim()
                ax.set_ylim(ylo if ylo is not None else cur[0],
                            yhi if yhi is not None else cur[1])
        except Exception:  # noqa: BLE001
            pass

        # -- 刻度旋转 ----------------------------------------------------
        rot = _num(meta, "xtick_rot")
        if rot:
            try:
                for lbl in ax.get_xticklabels():
                    lbl.set_rotation(rot)
                    lbl.set_ha("right" if rot else "center")
            except Exception:  # noqa: BLE001
                pass

    # 题注字号跟着字号走，不然大图上那行小字会显得是另一个来源
    fs = _num(meta, "font_size")
    if fs:
        for txt in fig.texts:
            try:
                txt.set_fontsize(max(6.0, fs * 0.8))
            except Exception:  # noqa: BLE001
                pass

    return fig


def clean_overrides(meta: Optional[dict]) -> dict:
    """把外观覆盖从 meta 里挑出来，免得混进别的用途。

    模板读 meta 时会顺带看到这些键，多数模板用 ``meta.get("x_label")``
    这种显式取值，多出来的键不会造成影响。但 ``width_in`` 是个例外 ——
    模板**真的**会读它来决定 figsize，所以那个键必须留着。
    """
    if not meta:
        return {}
    keys = {k for k, _, _, _ in OVERRIDES}
    return {k: v for k, v in meta.items() if k in keys}

