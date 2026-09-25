"""DIY 生图：用声明式规格拼出任意图表，不需要写代码。

设计取舍
--------
用户要"可以自行 DIY 的生图功能"。有两种做法：

1. 让用户贴 Python 代码执行 —— 灵活，但在比赛期间等于开了一个
   任意代码执行的口子，而且贴进来的代码报错时用户自己没法调。
2. 把"图长什么样"拆成几个正交的选项（图形 + 数据 + 样式），
   由这里组装成 matplotlib 调用 —— 用户点选就能出图。

选了 2。理由是这工具的使用场景：比赛期间、时间压力、用户是建模的人
不是程序员。让他们调 matplotlib 参数不如给一组调好的预设。
真要写代码的人，本来就可以直接往 templates/figures/ 加模板。

支持组合的维度：图形类型 × 多序列 × 误差棒 × 参考线 × 标注 × 配色 ×
图例/网格/对数轴。这个笛卡尔积覆盖了绝大多数"我想要的图模板里没有"的情况。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 支持的图形类型。键是面板上的值，值是中文名。
CHART_TYPES: List[Tuple[str, str]] = [
    ("line", "折线图"),
    ("line_markers", "折线 + 数据点"),
    ("scatter", "散点图"),
    ("bar", "柱状图"),
    ("barh", "条形图（横）"),
    ("bar_grouped", "分组柱状图"),
    ("bar_stacked", "堆叠柱状图"),
    ("area", "面积图"),
    ("area_stacked", "堆叠面积图"),
    ("step", "阶梯图"),
    ("stem", "火柴梗图"),
    ("pie", "饼图"),
    ("donut", "环形图"),
    ("hist", "直方图"),
    ("box", "箱线图"),
    ("violin", "小提琴图"),
    ("errorbar", "误差棒折线"),
    ("fill_between", "带误差带的折线"),
    ("heatmap", "热力图"),
    ("contour", "等高线"),
    ("surface", "三维曲面"),
    ("loglog", "双对数图"),
    ("semilogy", "半对数图（纵轴对数）"),
    ("polar", "极坐标图"),
    ("pareto", "帕累托图"),
    ("waterfall", "瀑布图"),
    ("radar", "雷达图"),
]

PALETTES: Dict[str, List[str]] = {
    "学术蓝": ["#1f4e79", "#c0504d", "#9bbb59", "#8064a2", "#4bacc6", "#f79646"],
    "灰度": ["#1a1a1a", "#5c5c5c", "#8c8c8c", "#b8b8b8", "#dcdcdc", "#f0f0f0"],
    "暖色": ["#c0392b", "#e67e22", "#f1c40f", "#d35400", "#a04000", "#7b241c"],
    "冷色": ["#1a5276", "#2e86c1", "#5dade2", "#48c9b0", "#117a65", "#0e6251"],
    "Nature": ["#0C5DA5", "#00B945", "#FF9500", "#FF2C00", "#845B97", "#474747"],
    "色盲友好": ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#F0E442", "#56B4E9"],
}

MARKERS = ["o", "s", "^", "D", "v", "P", "*", "X"]
LINESTYLES = ["-", "--", "-.", ":"]

# 分类图：它们吃"一组数值"，不吃"多列序列"
CATEGORICAL = {"bar", "barh", "bar_grouped", "bar_stacked", "pie", "donut",
               "box", "violin", "pareto", "waterfall", "hist"}
# 需要二维输入
MATRIX_TYPES = {"heatmap", "contour", "surface"}


class DIYError(ValueError):
    """规格有问题。消息是给人看的中文，会直接显示在面板上。"""


def _as_list(v: Any, what: str) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    raise DIYError(f"{what} 要写成数组，例如 [1, 2, 3]，现在收到的是 {type(v).__name__}。")


def _as_floats(v: Any, what: str) -> List[float]:
    out = []
    for i, x in enumerate(_as_list(v, what)):
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            raise DIYError(f"{what} 的第 {i + 1} 项不是数字：{x!r}")
    return out


def _matrix(v: Any, what: str) -> List[List[float]]:
    if not isinstance(v, (list, tuple)) or not v:
        raise DIYError(f"{what} 要写成二维数组，例如 [[1,2],[3,4]]。")
    if not isinstance(v[0], (list, tuple)):
        raise DIYError(f"{what} 的每一项都要是数组（二维），现在是 {type(v[0]).__name__}。")
    return [_as_floats(row, f"{what} 第 {i + 1} 行") for i, row in enumerate(v)]


def _fmt(v: float) -> str:
    if v == int(v) and abs(v) < 1e15:
        return f"{int(v):,}"
    return f"{v:,.3g}"


def render(spec: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    """按规格画一张图，返回 matplotlib Figure。

    抛出的错误都是中文，直接显示给用户 —— 这个功能的使用者
    不该为了看懂一个 KeyError 去读源码。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    spec = spec or {}
    meta = meta or {}

    chart = (spec.get("chart") or "line").strip()
    known = {k for k, _ in CHART_TYPES}
    if chart not in known:
        raise DIYError(f"不认识的图形类型「{chart}」。可选：{'、'.join(sorted(known))}")

    title = (spec.get("title") or "").strip()
    xlabel = (spec.get("xlabel") or "").strip()
    ylabel = (spec.get("ylabel") or "").strip()
    caption = (meta.get("caption") or "").strip()
    palette_name = spec.get("palette") or "学术蓝"
    colors = PALETTES.get(palette_name) or PALETTES["学术蓝"]
    width = float(spec.get("width_in") or 6.4)
    height = float(spec.get("height_in") or 4.0)
    show_grid = spec.get("grid", True)
    show_legend = spec.get("legend", True)
    logx = bool(spec.get("log_x"))
    logy = bool(spec.get("log_y"))

    # -- 数据准备 ---------------------------------------------------------
    # 两种写法都收：series 列表（多序列），或裸的 x/y。
    # 后者是大多数人第一反应会写的，不该逼他们套一层结构。
    raw_series = spec.get("series")
    if raw_series and isinstance(raw_series, list) and raw_series \
            and isinstance(raw_series[0], dict):
        series = raw_series
    else:
        x = spec.get("x")
        y = spec.get("y")
        if y is None and x is None:
            # 矩阵类和分类图各有自己的数据键（matrix / values），
            # 不该因为它们没写 y 就拒掉。所以这里不抛错，
            # 交给下面的分支去要它真正需要的东西。
            if chart in MATRIX_TYPES:
                series = []
            elif chart in CATEGORICAL:
                series = [{"name": "序列 1",
                           "y": spec.get("values") or spec.get("y"),
                           "errors": spec.get("errors")}]
            else:
                raise DIYError(
                    "没有数据。请填 y（或者用 series 给多组数据）。")
        else:
            series = [{"name": (spec.get("y_label") or "序列 1"),
                       "x": x, "y": y if y is not None else x,
                       "errors": spec.get("errors")}]

    labels = [str(s) for s in _as_list(spec.get("labels"), "labels")]

    from . import mcmplot
    try:
        mcmplot.setup()
    except Exception:  # noqa: BLE001  字体缺失不该让整个功能不可用
        pass

    fig, ax = plt.subplots(figsize=(width, height))
    safe = getattr(mcmplot, "safe", lambda s: s)

    # -- 矩阵类 -----------------------------------------------------------
    if chart in MATRIX_TYPES:
        m = _matrix(spec.get("matrix") or spec.get("z"), "matrix")
        arr = np.array(m, dtype=float)
        if chart == "surface":
            z = arr
            xv = _as_floats(spec.get("x") or list(range(z.shape[1])), "x")
            yv = _as_floats(spec.get("y") or list(range(z.shape[0])), "y")
            if len(xv) != z.shape[1] or len(yv) != z.shape[0]:
                raise DIYError(
                    f"x 有 {len(xv)} 个、y 有 {len(yv)} 个，而矩阵是 "
                    f"{z.shape[0]}×{z.shape[1]} —— 行列数必须对得上。")
            fig = plt.figure(figsize=(width, height))
            ax = fig.add_subplot(111, projection="3d")
            xx, yy = np.meshgrid(xv, yv)
            surf = ax.plot_surface(xx, yy, z, cmap="viridis", edgecolor="none")
            fig.colorbar(surf, ax=ax, shrink=0.7,
                         label=safe(spec.get("cbar_label") or "数值"))
            ax.set_xlabel(safe(xlabel or "x"))
            ax.set_ylabel(safe(ylabel or "y"))
            ax.set_zlabel(safe(spec.get("zlabel") or "z"))
        else:
            if chart == "contour":
                cs = ax.contourf(arr, cmap="viridis", levels=12)
            else:
                cs = ax.imshow(arr, cmap="viridis", aspect="auto")
            fig.colorbar(cs, ax=ax, shrink=0.85,
                         label=safe(spec.get("cbar_label") or "数值"))
            if labels and len(labels) == arr.shape[0]:
                ax.set_yticks(range(arr.shape[0]))
                ax.set_yticklabels([safe(x) for x in labels])
            cols = _as_list(spec.get("col_labels"), "col_labels")
            if cols and len(cols) == arr.shape[1]:
                ax.set_xticks(range(arr.shape[1]))
                ax.set_xticklabels([safe(str(c)) for c in cols],
                                   rotation=45, ha="right")
        _finish(fig, ax, safe, title, xlabel, ylabel, caption, show_grid, None)
        return fig

    # -- 极坐标 -----------------------------------------------------------
    if chart == "polar":
        s0 = series[0]
        theta = _as_floats(s0.get("x") or s0.get("theta"), "x")
        r = _as_floats(s0.get("y") or s0.get("r"), "y")
        if len(theta) != len(r):
            raise DIYError(f"角度有 {len(theta)} 个、半径有 {len(r)} 个，必须一样多。")
        ax.remove()
        ax = fig.add_subplot(111, projection="polar")
        ax.plot([math.radians(t) for t in theta], r, "-",
                color=colors[0], lw=1.9)
        _finish(fig, ax, safe, title, xlabel, ylabel, caption, show_grid, None)
        return fig

    # -- 雷达图 -----------------------------------------------------------
    if chart == "radar":
        axes_labels = labels or [f"指标{i + 1}" for i in
                                 range(len(_as_list(series[0].get("y"), "y")))]
        n = len(axes_labels)
        if n < 3:
            raise DIYError("雷达图至少要 3 个指标。")
        ax.remove()
        ax = fig.add_subplot(111, projection="polar")
        angles = [i / n * 2 * math.pi for i in range(n)] + [0]
        for i, s in enumerate(series):
            v = _as_floats(s.get("y"), f"第 {i + 1} 个序列")
            if len(v) != n:
                raise DIYError(
                    f"第 {i + 1} 个序列有 {len(v)} 个值，指标有 {n} 个，必须一样多。")
            # 归一化：量纲不同的指标直接画会全被最大的那个压平
            mx = max(abs(x) for x in v) or 1.0
            vv = [x / mx for x in v] + [v[0] / mx]
            ax.plot(angles, vv, "-", lw=1.9,
                    color=colors[i % len(colors)],
                    label=safe(s.get("name") or f"方案{i + 1}"))
            ax.fill(angles, vv, alpha=0.12, color=colors[i % len(colors)])
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels([safe(str(a)) for a in axes_labels])
        if show_legend and len(series) > 1:
            ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1),
                      fontsize=8)
        _finish(fig, ax, safe, title, "", "", caption, show_grid, None)
        return fig

    # -- 瀑布图 -----------------------------------------------------------
    if chart == "waterfall":
        vals = _as_floats(spec.get("values") or series[0].get("y"), "values")
        if not vals:
            raise DIYError("瀑布图需要 values：各因素的增减量。")
        names = labels or [f"因素{i + 1}" for i in range(len(vals))]
        if len(names) != len(vals):
            raise DIYError(f"names 有 {len(names)} 个、values 有 {len(vals)} 个，必须一样多。")
        base = float(spec.get("base") or 0.0)
        cum = base
        for i, v in enumerate(vals):
            c = "#2e7d32" if v >= 0 else "#c62828"
            ax.bar(i, v, bottom=cum, color=c, edgecolor="white", lw=0.8)
            ytxt = cum + v + (abs(v) * 0.03 if v >= 0 else -abs(v) * 0.08)
            ax.text(i, ytxt, ("+" if v >= 0 else "") + _fmt(v),
                    ha="center", va="bottom" if v >= 0 else "top",
                    fontsize=8, color=c)
            cum += v
        ax.bar(len(vals), cum, bottom=0, color="#1f4e79",
               edgecolor="white", lw=0.8)
        ax.set_xticks(range(len(vals) + 1))
        ax.set_xticklabels([safe(str(x)) for x in names]
                           + [safe(spec.get("total_label") or "合计")],
                           rotation=30, ha="right")
        ax.axhline(base, color="#888", lw=0.9, ls="--")
        _finish(fig, ax, safe, title, xlabel, ylabel, caption, show_grid, None)
        return fig

    # -- 分类图 -----------------------------------------------------------
    if chart in CATEGORICAL:
        if chart == "pie" or chart == "donut":
            s0 = series[0]
            vals = _as_floats(s0.get("y"), "y")
            if any(v < 0 for v in vals):
                raise DIYError("饼图不能有负值。")
            names = labels or [f"项{i + 1}" for i in range(len(vals))]
            if len(names) != len(vals):
                raise DIYError(
                    f"labels 有 {len(names)} 个、数值有 {len(vals)} 个，必须一样多。")
            wedges, texts, autot = ax.pie(
                vals, labels=[safe(str(x)) for x in names], autopct="%1.1f%%",
                colors=colors[:len(vals)], startangle=90,
                wedgeprops={"edgecolor": "white", "linewidth": 1.0})
            for t in autot:
                t.set_fontsize(8)
            if chart == "donut":
                ax.add_artist(plt.Circle((0, 0), 0.55, color="white"))
            ax.set_aspect("equal")
            _finish(fig, ax, safe, title, "", "", caption, False, None)
            return fig

        if chart == "hist":
            vals = _as_floats(spec.get("values") or series[0].get("y"), "y")
            if not vals:
                raise DIYError("直方图需要一组数值。")
            bins = int(spec.get("bins") or 10)
            ax.hist(vals, bins=bins, color=colors[0], edgecolor="white", lw=0.8)
            if spec.get("show_mean", True):
                mu = sum(vals) / len(vals)
                ax.axvline(mu, color="#c62828", ls="--", lw=1.4,
                           label=safe(f"均值 {_fmt(mu)}"))
                if show_legend:
                    ax.legend(fontsize=8)
            _finish(fig, ax, safe, title, xlabel or "取值", ylabel or "频数",
                    caption, show_grid, None)
            return fig

        if chart in ("box", "violin"):
            groups = [s for s in series if _as_list(s.get("y"), "y")]
            if not groups:
                raise DIYError("箱线图/小提琴图需要至少一组数值。")
            data = [_as_floats(s.get("y"), "y") for s in groups]
            names = labels or [str(s.get("name") or f"组{i + 1}")
                               for i, s in enumerate(groups)]
            if len(names) != len(data):
                raise DIYError(
                    f"labels 有 {len(names)} 个，数据有 {len(data)} 组，必须一样多。")
            if chart == "box":
                bp = ax.boxplot(data, patch_artist=True,
                                medianprops={"color": "#c62828", "lw": 1.6})
                for i, box in enumerate(bp["boxes"]):
                    box.set_facecolor(colors[i % len(colors)])
                    box.set_alpha(0.55)
            else:
                vp = ax.violinplot(data, showmedians=True)
                for i, b in enumerate(vp["bodies"]):
                    b.set_facecolor(colors[i % len(colors)])
                    b.set_alpha(0.6)
            ax.set_xticks(range(1, len(data) + 1))
            ax.set_xticklabels([safe(str(n)) for n in names],
                               rotation=20, ha="right")
            _finish(fig, ax, safe, title, xlabel, ylabel or "取值",
                    caption, show_grid, None)
            return fig

        if chart == "pareto":
            vals = _as_floats(spec.get("values") or series[0].get("y"), "values")
            names = labels or [f"项{i + 1}" for i in range(len(vals))]
            if len(names) != len(vals):
                raise DIYError(f"labels 有 {len(names)} 个、数值有 {len(vals)} 个，必须一样多。")
            order = sorted(range(len(vals)), key=lambda i: -vals[i])
            sv = [vals[i] for i in order]
            sn = [names[i] for i in order]
            total = sum(sv) or 1.0
            cum = []
            run = 0.0
            for v in sv:
                run += v
                cum.append(run / total * 100)
            ax.bar(range(len(sv)), sv, color=colors[0], edgecolor="white", lw=0.8)
            ax.set_xticks(range(len(sv)))
            ax.set_xticklabels([safe(str(x)) for x in sn],
                               rotation=30, ha="right")
            ax.set_ylabel(safe(ylabel or "数值"))
            ax2 = ax.twinx()
            ax2.plot(range(len(cum)), cum, "-o", color="#c62828",
                     ms=4, lw=1.6)
            ax2.set_ylabel(safe("累计占比 (%)"), color="#c62828")
            ax2.tick_params(axis="y", colors="#c62828")
            ax2.set_ylim(0, 105)
            ax2.axhline(80, color="#888", ls=":", lw=1.0)
            ax2.annotate(safe("80% 线"), xy=(0, 80), fontsize=8, color="#666",
                         va="bottom")
            _finish(fig, ax, safe, title, xlabel, ylabel, caption, show_grid, None)
            return fig

        # 单序列柱状
        s0 = series[0]
        vals = _as_floats(s0.get("y"), "y")
        names = labels or [str(i + 1) for i in range(len(vals))]
        if len(names) != len(vals):
            raise DIYError(
                f"labels 有 {len(names)} 个、数值有 {len(vals)} 个，必须一样多。"
                "柱状图每个柱子需要一个名字。")
        errs = s0.get("errors")
        pos = range(len(vals))
        horiz = chart == "barh"
        if horiz:
            ax.barh(list(pos), vals, color=colors[0], edgecolor="white",
                    lw=0.8,
                    xerr=_as_floats(errs, "errors") if errs else None,
                    capsize=3)
            ax.set_yticks(list(pos))
            ax.set_yticklabels([safe(str(x)) for x in names])
            ax.invert_yaxis()
        else:
            ax.bar(list(pos), vals, color=colors[0], edgecolor="white", lw=0.8,
                   yerr=_as_floats(errs, "errors") if errs else None,
                   capsize=3)
            ax.set_xticks(list(pos))
            ax.set_xticklabels([safe(str(x)) for x in names],
                               rotation=30, ha="right")
        if spec.get("show_values", True):
            for i, v in enumerate(vals):
                if horiz:
                    ax.text(v, i, " " + _fmt(v), va="center", fontsize=8,
                            color="#333")
                else:
                    ax.text(i, v, _fmt(v), ha="center", va="bottom", fontsize=8,
                            color="#333")
        _finish(fig, ax, safe, title, xlabel, ylabel, caption, show_grid, None)
        return fig

    # -- 多序列：分组/堆叠柱 ----------------------------------------------
    if chart in ("bar_grouped", "bar_stacked"):
        data = [_as_floats(s.get("y"), "y") for s in series]
        k = max(len(d) for d in data)
        names = labels or [f"组{i + 1}" for i in range(k)]
        if len(names) != k:
            raise DIYError(
                f"labels 有 {len(names)} 个，数据每组有 {k} 个点，必须一样多。")
        x = list(range(k))
        w = 0.8 / len(data)
        bottom = [0.0] * k
        for i, d in enumerate(data):
            if len(d) != k:
                raise DIYError(
                    f"第 {i + 1} 个序列有 {len(d)} 个点，其他序列有 {k} 个，"
                    "多序列的每列长度必须一致。")
            c = colors[i % len(colors)]
            nm = safe(series[i].get("name") or f"序列{i + 1}")
            if chart == "bar_stacked":
                ax.bar(x, d, bottom=bottom, color=c, label=nm,
                       edgecolor="white", lw=0.7)
                bottom = [b + v for b, v in zip(bottom, d)]
            else:
                ax.bar([p + i * w for p in x], d, width=w, color=c,
                       label=nm, edgecolor="white", lw=0.7)
        ax.set_xticks([p + 0.4 - w / 2 for p in x] if chart == "bar_grouped" else x)
        ax.set_xticklabels([safe(str(n)) for n in names],
                           rotation=30, ha="right")
        if show_legend:
            ax.legend(fontsize=8)
        _finish(fig, ax, safe, title, xlabel, ylabel, caption, show_grid, None)
        return fig

    # -- 其余都是"x 对 y"的曲线/散点 --------------------------------------
    for i, s in enumerate(series):
        yv = _as_floats(s.get("y"), f"第 {i + 1} 个序列的 y")
        if not yv:
            raise DIYError(f"第 {i + 1} 个序列没有数据。")
        xv = _as_floats(s.get("x"), "x") if s.get("x") is not None \
            else [float(j) for j in range(len(yv))]
        if len(xv) != len(yv):
            raise DIYError(
                f"第 {i + 1} 个序列：x 有 {len(xv)} 个点，y 有 {len(yv)} 个，"
                "必须一样多。")
        c = colors[i % len(colors)]
        nm = safe(s.get("name") or f"序列{i + 1}")
        errs = s.get("errors")
        ev = _as_floats(errs, "errors") if errs else None
        if ev and len(ev) != len(yv):
            raise DIYError(
                f"第 {i + 1} 个序列：误差有 {len(ev)} 个，数据有 {len(yv)} 个，"
                "必须一样多。")

        if chart == "line":
            ax.plot(xv, yv, "-", color=c, lw=1.9, label=nm)
        elif chart == "line_markers":
            ax.plot(xv, yv, LINESTYLES[i % len(LINESTYLES)],
                    marker=MARKERS[i % len(MARKERS)], ms=5, color=c,
                    lw=1.7, markeredgecolor="white", markeredgewidth=0.8,
                    label=nm)
        elif chart == "scatter":
            ax.scatter(xv, yv, s=34, color=c, alpha=0.8,
                       edgecolor="white", lw=0.7, label=nm, zorder=3)
        elif chart == "step":
            ax.step(xv, yv, where="mid", color=c, lw=1.8, label=nm)
        elif chart == "stem":
            ml, sl, bl = ax.stem(xv, yv, linefmt="-", markerfmt="o",
                                 basefmt=" ")
            plt.setp(sl, color=c, lw=1.6)
            plt.setp(ml, color=c, ms=5)
            plt.setp(bl, visible=False)
            ml.set_label(nm)
        elif chart == "area":
            ax.fill_between(xv, 0, yv, color=c, alpha=0.35, label=nm)
            ax.plot(xv, yv, "-", color=c, lw=1.8)
        elif chart == "area_stacked":
            # 堆叠要所有序列共用横轴，先攒起来统一画
            pass
        elif chart == "errorbar":
            if not ev:
                raise DIYError("误差棒图需要 errors：每个点的不确定度。")
            ax.errorbar(xv, yv, yerr=ev, fmt="-o", color=c, lw=1.7, ms=4.5,
                        capsize=3, label=nm)
        elif chart == "fill_between":
            if not ev:
                raise DIYError("误差带图需要 errors：每个点的不确定度。")
            lo = [a - b for a, b in zip(yv, ev)]
            hi = [a + b for a, b in zip(yv, ev)]
            ax.plot(xv, yv, "-", color=c, lw=1.9, label=nm)
            ax.fill_between(xv, lo, hi, color=c, alpha=0.22)
        elif chart == "loglog":
            ax.loglog(xv, yv, "-o", color=c, lw=1.7, ms=4, label=nm)
        elif chart == "semilogy":
            ax.semilogy(xv, yv, "-o", color=c, lw=1.7, ms=4, label=nm)
        else:
            raise DIYError(f"「{chart}」还没实现，请换一种图形。")

    if chart == "area_stacked":
        xs = [_as_floats(s.get("x"), "x") if s.get("x") is not None
              else list(range(len(_as_list(s.get("y"), "y")))) for s in series]
        ys = [_as_floats(s.get("y"), "y") for s in series]
        k = min(len(v) for v in ys)
        ax.stackplot(xs[0][:k], [v[:k] for v in ys],
                     colors=colors[:len(ys)],
                     labels=[safe(s.get("name") or f"序列{i + 1}")
                             for i, s in enumerate(series)])
        if show_legend:
            ax.legend(fontsize=8, loc="upper left")

    if logx and chart not in ("loglog", "semilogy"):
        ax.set_xscale("log")
    if logy and chart not in ("loglog", "semilogy"):
        ax.set_yscale("log")

    # 参考线。加一条"目标值"线是评审最容易看懂的表达方式之一。
    for ref in _as_list(spec.get("hlines"), "hlines"):
        try:
            ax.axhline(float(ref), color="#888", ls="--", lw=1.1)
        except (TypeError, ValueError):
            raise DIYError(f"hlines 里有个值不是数字：{ref!r}")
    for ref in _as_list(spec.get("vlines"), "vlines"):
        try:
            ax.axvline(float(ref), color="#888", ls="--", lw=1.1)
        except (TypeError, ValueError):
            raise DIYError(f"vlines 里有个值不是数字：{ref!r}")

    if show_legend and len(series) > 1:
        ax.legend(fontsize=8)
    _finish(fig, ax, safe, title, xlabel, ylabel, caption,
            show_grid, spec)
    return fig


def _finish(fig, ax, safe, title, xlabel, ylabel, caption,
            show_grid, spec) -> None:
    """统一的收尾：标题、轴标签、网格、题注。"""
    if title:
        ax.set_title(safe(title), fontsize=11)
    if xlabel:
        ax.set_xlabel(safe(xlabel), fontsize=9.5)
    if ylabel:
        ax.set_ylabel(safe(ylabel), fontsize=9.5)
    if show_grid:
        ax.grid(alpha=0.28, lw=0.6)
        ax.set_axisbelow(True)
    # 题注放图下：论文里图题是排版的活，但预览时要能看见自己写了什么
    if caption:
        fig.text(0.5, 0.005, safe(caption), ha="center", va="bottom",
                 fontsize=8, color="#555", wrap=True)
    try:
        fig.tight_layout()
    except Exception:  # noqa: BLE001  极坐标/3D 有时会拒绝 tight_layout
        pass


def catalog() -> Dict[str, Any]:
    """给面板的选项清单：图形类型、配色、说明。

    前端不该硬编码这些 —— 加一种图要同时改两处，早晚不一致。
    """
    return {
        "chart_types": [{"value": k, "label": v} for k, v in CHART_TYPES],
        "palettes": [{"value": k, "colors": v} for k, v in PALETTES.items()],
        "markers": MARKERS,
    }
