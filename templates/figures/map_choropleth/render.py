"""fig.map_choropleth —— 按区域填色的地理分布图。

数据从哪来
----------
    regions         区域名序列，如 ['北京', '上海', '广东']
    values          对应数值，如 [120, 95, 310]
    colorbar_label  色标说明（可选）

诚实的限制
----------
真正的等值线地图需要**地理边界数据**（shapefile / GeoJSON），那种文件
动辄几十 MB，不适合塞进模板库，不同赛题用的行政区划也不一样。

所以这里画的是**色块地图**：每个区域一个方块，按数值深浅着色。
它表达的是"谁高谁低"，不是"谁在哪"。

这个取舍是有意的：宁可画一张诚实传达数据的图，也不要一张
因为没有边界数据而画歪的地图。论文里要用真地图，请把边界 GeoJSON
传给 `geojson` 参数 —— 那样会走真正的多边形填充路径。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import matplotlib

matplotlib.use("Agg")

# 同级模板共用绘图环境（中文字体、字号、数字格式化）。
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmplot  # noqa: E402

mcmplot.setup()
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def render(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None):
    meta = meta or {}
    regions = [str(r) for r in (data.get("regions") or [])]
    values = list(data.get("values") or [])
    if not regions:
        raise ValueError("regions 不能为空：至少要给出一个区域名。")
    if len(regions) != len(values):
        raise ValueError(
            f"regions 有 {len(regions)} 个，values 有 {len(values)} 个，数量必须一致。"
        )

    label = data.get("colorbar_label") or meta.get("y_label") or "数值"
    geojson = data.get("geojson")

    fig, ax = plt.subplots(figsize=(meta.get("width_in", 6.0), 4.6))

    if geojson:
        _draw_geojson(ax, geojson, dict(zip(regions, values)), label)
    else:
        _draw_grid(ax, regions, values, label)

    ax.axis("off")
    if meta.get("caption"):
        ax.set_title(meta["caption"].rstrip("."))
    fig.tight_layout()
    return fig


def _draw_grid(ax, regions, values, label) -> None:
    """色块网格：按数值深浅着色，把区域名写在格子里。

    网格尽量接近正方形，读起来比一条长条更自然。
    """
    n = len(regions)
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))

    v = np.array([float(x) for x in values], dtype=float)
    # 归一化到 0..1；全部相等时分母会是 0，要防一下。
    lo, hi = (v.min(), v.max()) if v.size else (0.0, 1.0)
    norm = (v - lo) / (hi - lo) if hi > lo else np.full_like(v, 0.5)

    import matplotlib.cm as cm

    for i, (name, val, t) in enumerate(zip(regions, values, norm)):
        r, c = divmod(i, cols)
        # 行号从上往下排，符合阅读习惯
        y = rows - 1 - r
        ax.add_patch(plt.Rectangle((c, y), 0.94, 0.94,
                                   facecolor=cm.Blues(0.15 + 0.75 * t),
                                   edgecolor="white", linewidth=1.5))
        ax.annotate(name, xy=(c + 0.47, y + 0.60), ha="center", va="center",
                    fontsize=8, color="#111")
        ax.annotate(mcmplot.fmt(val), xy=(c + 0.47, y + 0.32), ha="center",
                    va="center", fontsize=7.5, color="#333")

    ax.set_xlim(-0.1, cols + 0.1)
    ax.set_ylim(-0.1, rows + 0.1)
    ax.set_aspect("equal")

    # 色标：让读者知道深浅代表什么
    sm = plt.cm.ScalarMappable(cmap="Blues",
                               norm=plt.Normalize(vmin=lo, vmax=hi))
    cb = ax.figure.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label(label)


def _draw_geojson(ax, geojson, values_by_region, label) -> None:
    """有边界数据时画真正的多边形填充。"""
    import matplotlib.cm as cm
    from matplotlib.patches import Polygon

    feats = geojson.get("features", []) if isinstance(geojson, dict) else []
    if not feats:
        raise ValueError("geojson 里没有 features，无法绘制边界。")

    vals = [float(values_by_region[f.get("properties", {}).get("name", "")])
            for f in feats
            if f.get("properties", {}).get("name") in values_by_region]
    lo, hi = (min(vals), max(vals)) if vals else (0.0, 1.0)

    for f in feats:
        props = f.get("properties", {})
        name = props.get("name", "")
        val = values_by_region.get(name)
        t = 0.5 if val is None or hi <= lo else (float(val) - lo) / (hi - lo)
        geom = f.get("geometry", {})
        polys = (geom.get("coordinates") or []) if geom.get("type") == "Polygon" \
            else [p[0] for p in (geom.get("coordinates") or [])]
        for ring in polys:
            if len(ring) < 3:
                continue
            ax.add_patch(Polygon(ring, closed=True,
                                 facecolor=cm.Blues(0.15 + 0.75 * t),
                                 edgecolor="#555", linewidth=0.6))

    if vals:
        sm = plt.cm.ScalarMappable(cmap="Blues",
                                   norm=plt.Normalize(vmin=lo, vmax=hi))
        cb = ax.figure.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
        cb.set_label(label)
    ax.set_aspect("equal")
