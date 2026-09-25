"""fig.flowchart —— 算法 / 方法流程框图。

数据从哪来
----------
    nodes   [{'id': 'n1', 'label': '读入数据', 'kind': 'input'}, ...]
    edges   [['n1', 'n2'], ['n2', 'n3', '不满足时'], ...]

`kind` 决定配色（input / process / decision / output），
`label` 是框里显示的文字。edges 的第三项是可选的边标签，
用来标"是/否"这类分支条件。

输出是 .drawio 文件，**可以打开继续编辑** —— 流程图一定会在答辩前改，
能改比好看重要。见 mcmdrawio.py 的说明。
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmdrawio  # noqa: E402


def build(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> str:
    """只生成 XML 字符串（供测试和预览用）。"""
    nodes = list(data.get("nodes") or [])
    if not nodes:
        raise ValueError("缺少必填输入 nodes：流程至少要有一个步骤。")
    return mcmdrawio.build_xml(
        nodes,
        list(data.get("edges") or []),
        title=(meta or {}).get("caption", "") or "流程图",
        direction=(meta or {}).get("direction", "TB"),
    )


def render_to_file(
    data: Dict[str, Any],
    out_dir: str,
    name: str = "flowchart",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """写出 .drawio，并尽量导出 PDF。"""
    xml = build(data, meta)
    os.makedirs(out_dir, exist_ok=True)
    drawio_path = os.path.join(out_dir, f"{name}.drawio")
    with open(drawio_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    pdf = mcmdrawio.export_pdf(__import__("pathlib").Path(drawio_path))
    return {"drawio": drawio_path, "pdf": str(pdf) if pdf else None}
