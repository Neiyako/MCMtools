"""图里不能有文字互相压住。

为什么要自动查：文字重叠靠肉眼看单张图很容易漏，尤其是"数值标注
落在同一个像素上"这种 —— 图能生成、不报错、打开看也不觉得异常，
就是有三行数字叠在一起只剩一行能读。

这一组测试把"量 bbox 找重叠"固化成规则，以后改模板不会悄悄退化。
"""

from __future__ import annotations

import importlib.util
import itertools
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from mcmcore.sampledata import sample_for
from mcmcore.templates import TemplateRegistry, default_registry_root

FIG_DIR = Path(__file__).resolve().parents[2] / "templates" / "figures"


def _load(render_path: Path):
    spec = importlib.util.spec_from_file_location(
        "r_" + render_path.parent.name, render_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _drawn_texts(fig) -> List[Tuple[Any, Any]]:
    """只收集真正会被画出来的文字。

    `axis("off")` 的轴不画刻度 —— 那些标签 get_visible() 仍是 True，
    但图上没有。把它们算进来会产生假阳性（network_graph 就是这样）。
    """
    out = []
    for ax in fig.get_axes():
        if not ax.get_visible():
            continue
        if not getattr(ax, "axison", True):
            for t in ax.texts:
                if t.get_text().strip():
                    out.append((ax, t))
            if ax.get_title().strip():
                out.append((ax, ax.title))
            continue
        for t in ax.texts:
            if t.get_visible() and t.get_text().strip():
                out.append((ax, t))
        for t in (ax.title, ax.xaxis.label, ax.yaxis.label):
            if t.get_visible() and t.get_text().strip():
                out.append((ax, t))
        for axis in (ax.xaxis, ax.yaxis):
            for t in axis.get_ticklabels():
                if t.get_visible() and t.get_text().strip():
                    out.append((ax, t))
        leg = ax.get_legend()
        if leg and leg.get_visible():
            for t in leg.get_texts():
                if t.get_visible() and t.get_text().strip():
                    out.append((ax, t))
    for t in fig.texts:
        if t.get_visible() and t.get_text().strip():
            out.append((None, t))
    return out


def _overlaps(fig, pad: float = 1.0) -> List[str]:
    """返回重叠描述。阈值 15%：擦边不算，真压住才算。"""
    fig.canvas.draw()
    ren = fig.canvas.get_renderer()
    boxes = []
    for _ax, t in _drawn_texts(fig):
        try:
            bb = t.get_window_extent(renderer=ren)
        except Exception:                      # pragma: no cover
            continue
        if bb.width > 0 and bb.height > 0:
            boxes.append((t.get_text()[:30], bb))

    hits = []
    for (n1, b1), (n2, b2) in itertools.combinations(boxes, 2):
        # 同一串文字、垂直完全对齐 = 同一个元素（twin 轴两侧各有一份），
        # 不是重叠
        if n1 == n2 and abs(b1.y0 - b2.y0) < 1.5:
            continue
        ox = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
        oy = min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
        if ox > pad and oy > pad:
            small = min(b1.width * b1.height, b2.width * b2.height)
            ratio = (ox * oy / small) if small else 0
            if ratio > 0.15:
                hits.append(f"「{n1}」×「{n2}」 {ratio * 100:.0f}%")
    return hits


def _figure_templates():
    reg = TemplateRegistry(default_registry_root()).load()
    out = []
    for t in reg.by_kind("figure"):
        name = t.template_id.split(".", 1)[1]
        rp = FIG_DIR / name / "render.py"
        # 只测 matplotlib 渲染的；flowchart / model_structure 走 drawio，
        # 入口是 build()，不是 render()
        if not rp.is_file():
            continue
        if not hasattr(_load(rp), "render"):
            continue
        out.append(t)
    return out


@pytest.mark.parametrize(
    "template", _figure_templates(), ids=lambda t: t.template_id)
def test_no_text_overlap(template) -> None:
    name = template.template_id.split(".", 1)[1]
    mod = _load(FIG_DIR / name / "render.py")
    fig = mod.render(sample_for(template), {"caption": "示例标题"})
    try:
        hits = _overlaps(fig)
    finally:
        plt.close(fig)
    assert not hits, (
        f"{template.template_id} 有 {len(hits)} 处文字重叠：\n  "
        + "\n  ".join(hits))


class TestDetector:
    """检测器本身要能认出重叠，否则上面全是假绿。"""

    def test_detects_deliberate_overlap(self) -> None:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "AAAA")
        ax.text(0.5, 0.5, "BBBB")
        fig.canvas.draw()
        assert _overlaps(fig), "故意重叠却没检测出来"
        plt.close(fig)

    def test_accepts_separated_text(self) -> None:
        fig, ax = plt.subplots()
        ax.text(0.1, 0.1, "AAAA")
        ax.text(0.8, 0.8, "BBBB")
        fig.canvas.draw()
        assert _overlaps(fig) == []
        plt.close(fig)

    def test_ignores_invisible_axis_ticks(self) -> None:
        """axis("off") 的刻度不算 —— 图上根本不画。"""
        fig, ax = plt.subplots()
        for i in range(3):
            ax.text(0.2 + i * 0.3, 0.5, f"n{i}")
        ax.axis("off")
        fig.canvas.draw()
        assert _overlaps(fig) == []
        plt.close(fig)
