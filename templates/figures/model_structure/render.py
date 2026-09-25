"""fig.model_structure —— 模型结构图 / 技术路线 mindmap。

数据从哪来
----------
    models  [{'id': 'm1', 'label': '数据清洗'}, ...]   各模块
    flows   [['m1', 'm2', '输入'], ...]                模块之间的流向

这是 O 奖论文几乎必有的一张图（"mindmap" / "framework"）：
在读者看公式之前，先用一张图说明整体思路。

输出是 .drawio 文件，可继续编辑。见 mcmdrawio.py。
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mcmdrawio  # noqa: E402


def build(data: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> str:
    models = list(data.get("models") or [])
    if not models:
        raise ValueError("缺少必填输入 models：技术路线图至少要有一个模块。")
    # 没写 kind 时默认按 process 上色；路线图里模块是主体。
    nodes = [
        {"id": m.get("id") or m.get("name"), "label": m.get("label") or m.get("name"),
         "kind": m.get("kind") or "model"}
        for m in models
    ]
    return mcmdrawio.build_xml(
        nodes,
        list(data.get("flows") or []),
        title=(meta or {}).get("caption", "") or "技术路线图",
        direction=(meta or {}).get("direction", "TB"),
    )


def render_to_file(
    data: Dict[str, Any],
    out_dir: str,
    name: str = "model_structure",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    xml = build(data, meta)
    os.makedirs(out_dir, exist_ok=True)
    import pathlib
    drawio_path = os.path.join(out_dir, f"{name}.drawio")
    with open(drawio_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    pdf = mcmdrawio.export_pdf(pathlib.Path(drawio_path))
    return {"drawio": drawio_path, "pdf": str(pdf) if pdf else None}
