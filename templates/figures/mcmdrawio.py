"""drawio 图模板共用的生成器。

为什么用 drawio 而不是 matplotlib
---------------------------------
流程图和技术路线图**必须能改**。比赛期间你一定会在答辩前调整措辞、
加一个方框、挪一下箭头 —— 如果生成的是位图或写死的 PDF，就只能重画。
drawio 文件可以在 app.diagrams.net（或桌面版）里直接打开编辑，
改完再导出 PDF 插进论文。

生成的 .drawio 是纯 XML，不依赖任何第三方库：少一个依赖就少一个
"装不上"的风险。

输出两个文件
------------
    <名字>.drawio    可编辑源文件（进版本库）
    <名字>.pdf      论文里插的图（需要 drawio CLI，没有就跳过）

关于 PDF
--------
导出 PDF 需要本机装了 drawio 命令行版。没装也能用 —— .drawio 文件
一样能打开、编辑、手动导出。这里不假装成功，导不出来就明确说。
"""

from __future__ import annotations

import html
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 节点配色：按类别区分，让读者一眼看出哪类是哪类。
PALETTE = {
    "input":     ("#dae8fc", "#6c8ebf"),
    "process":   ("#d5e8d4", "#82b366"),
    "decision":  ("#ffe6cc", "#d79b00"),
    "output":    ("#f8cecc", "#b85450"),
    "model":     ("#e1d5e7", "#9673a6"),
    "data":      ("#fff2cc", "#d6b656"),
}
DEFAULT_COLOR = ("#f5f5f5", "#666666")

# 版面参数（像素）
NODE_W, NODE_H = 160, 60
GAP_X, GAP_Y = 60, 80


def classify(node: Dict[str, Any]) -> Tuple[str, str]:
    """决定节点的填充色和描边色。"""
    kind = str(node.get("kind") or node.get("type") or "").lower()
    for key, colors in PALETTE.items():
        if key in kind:
            return colors
    return DEFAULT_COLOR


def layout(nodes: List[Dict[str, Any]], direction: str = "TB"):
    """把节点排成网格，返回 {节点 id: (x, y)}。

    为什么要自己排版：drawio 的自动布局在**没有图形界面**时用不了，
    而生成的图总得有初始位置。网格布局对流程图足够用，而且位置确定 ——
    同一份输入每次生成的位置一样，不会在 diff 里看到满屏位移。
    """
    if not nodes:
        return {}
    cols = max(1, min(4, len(nodes) if len(nodes) <= 4 else 4))
    pos: Dict[str, Tuple[int, int]] = {}
    for i, node in enumerate(nodes):
        nid = str(node.get("id") or node.get("name") or f"n{i}")
        r, c = divmod(i, cols)
        if direction == "LR":
            pos[nid] = (r * (NODE_W + GAP_X), c * (NODE_H + GAP_Y))
        else:
            pos[nid] = (c * (NODE_W + GAP_X), r * (NODE_H + GAP_Y))
    return pos


def build_xml(
    nodes: List[Dict[str, Any]],
    edges: List[Any],
    *,
    title: str = "",
    direction: str = "TB",
    page_w: int = 850,
    page_h: int = 1100,
) -> str:
    """生成 drawio 的 XML。"""
    pos = layout(nodes, direction)
    cells: List[str] = []

    for i, node in enumerate(nodes):
        nid = str(node.get("id") or node.get("name") or f"n{i}")
        label = str(node.get("label") or node.get("name") or nid)
        fill, stroke = classify(node)
        x, y = pos.get(nid, (0, 0))
        shape = "rhombus" if "decision" in str(node.get("kind", "")).lower() else \
                "ellipse" if "input" in str(node.get("kind", "")).lower() else \
                "rounded=1"
        cells.append(
            f'        <mxCell id="{html.escape(nid)}" value="{html.escape(label)}" '
            f'style="{shape};whiteSpace=wrap;html=1;fillColor={fill};'
            f'strokeColor={stroke};fontSize=12;" vertex="1" parent="1">\n'
            f'          <mxGeometry x="{x}" y="{y}" width="{NODE_W}" '
            f'height="{NODE_H}" as="geometry"/>\n'
            f'        </mxCell>'
        )

    for j, edge in enumerate(edges):
        if isinstance(edge, dict):
            src = str(edge.get("from") or edge.get("source") or "")
            dst = str(edge.get("to") or edge.get("target") or "")
            label = str(edge.get("label") or "")
        else:
            seq = list(edge)
            src = str(seq[0]) if len(seq) > 0 else ""
            dst = str(seq[1]) if len(seq) > 1 else ""
            label = str(seq[2]) if len(seq) > 2 else ""
        # 指向不存在的节点会让 drawio 里出现悬空箭头
        ids = {str(n.get("id") or n.get("name")) for n in nodes}
        if src not in ids or dst not in ids:
            continue
        cells.append(
            f'        <mxCell id="e{j}" value="{html.escape(label)}" '
            f'style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;'
            f'endArrow=block;strokeColor=#666666;" edge="1" parent="1" '
            f'source="{html.escape(src)}" target="{html.escape(dst)}">\n'
            f'          <mxGeometry relative="1" as="geometry"/>\n'
            f'        </mxCell>'
        )

    return (
        '<mxfile host="MCMtools" type="device">\n'
        f'  <diagram name="{html.escape(title or "diagram")}" id="d1">\n'
        f'    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" '
        f'page="1" pageWidth="{page_w}" pageHeight="{page_h}">\n'
        '      <root>\n'
        '        <mxCell id="0"/>\n'
        '        <mxCell id="1" parent="0"/>\n'
        + "\n".join(cells) + "\n"
        '      </root>\n'
        '    </mxGraphModel>\n'
        '  </diagram>\n'
        '</mxfile>\n'
    )


def export_pdf(drawio_file: Path, out_pdf: Optional[Path] = None) -> Optional[Path]:
    """用 drawio 命令行导出 PDF。没装就返回 None。

    不假装成功：导不出来时明确返回 None，调用方据此告诉用户
    "源文件在这里，你自己打开导出"。
    """
    exe = shutil.which("drawio") or (
        "/Applications/draw.io.app/Contents/MacOS/draw.io"
        if Path("/Applications/draw.io.app").exists() else None
    )
    if not exe:
        return None
    out_pdf = out_pdf or drawio_file.with_suffix(".pdf")
    try:
        subprocess.run(
            [exe, "--export", "--format", "pdf", "--output", str(out_pdf),
             str(drawio_file)],
            check=True, capture_output=True, timeout=120,
        )
        return out_pdf if out_pdf.is_file() else None
    except Exception:
        return None
