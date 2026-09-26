"""论文骨架：把模板里的空白章节填进项目，让人直接往里写。

这个模块做的是"填空题的卷子"这件事
-----------------------------------
`templates/paper/section_spine` 决定**有哪几节、什么顺序**（语料实证：
14 组两两先后关系在 152 篇里 100% 成立）。
`templates/paper/section_bodies` 决定**每节里写什么**（骨架 + 检查项）。

本模块把两者合起来，生成项目里可直接编辑的章节。

为什么不是"生成一篇论文"
------------------------
生成的正文一定是空话。这个工具的价值不在替你写，而在：
1. 节次顺序不用猜（有语料依据）
2. 每节该写什么有骨架，不会漏掉"假设要给理由"这类硬要求
3. 每节带篇幅建议 —— 72.1% 的真实论文正好 25 页，超页是硬伤
4. 带检查项，写完能自查

占位符 {{...}} 保留在正文里，审计会查出未填的占位符（SUMMARY_PLACEHOLDER）。
所以"忘了填"不会溜过去。
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .schemas import Paper, PaperSection, SectionKind
from .root import find_template_file

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


def _load_template(name: str) -> Optional[Dict[str, Any]]:
    """读 templates/paper/<name>/template.yaml。"""
    path = find_template_file("paper", name, "template.yaml")
    if path is None:
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None


# 可选的章节骨架。不同题型章节结构不一样：
#   data_driven  数据类（C 题）—— 数据描述、模型拟合、预测
#   physical     机理类（A 题）—— 守恒律、参数辨识、数值验证
#   policy       政策类（B/D 题）—— 方案设计、评价、敏感性
#   evaluation   评价类（E 题）—— 指标体系、赋权、排序
# 默认用 general（通用结构），找不到指定骨架时也回退到它。
SPINE_TEMPLATES = {
    "general": "section_spine",
    "data_driven": "spine_data_driven",
    "physical": "spine_physical",
    "policy": "spine_policy",
    "evaluation": "spine_evaluation",
}


def available_spines() -> List[str]:
    """有哪些章节骨架可用（只列真的存在模板文件的）。"""
    return [name for name, tmpl in SPINE_TEMPLATES.items()
            if find_template_file("paper", tmpl, "template.yaml") is not None]


def load_spine(kind: str = "general") -> List[Dict[str, Any]]:
    """章节顺序表（按 order 排好）。

    kind 指定用哪套骨架；不认识或模板缺失时回退到 general，
    绝不让"选的骨架不存在"变成一次崩溃。
    """
    tmpl_name = SPINE_TEMPLATES.get(kind, SPINE_TEMPLATES["general"])
    tmpl = _load_template(tmpl_name)
    if not tmpl and tmpl_name != SPINE_TEMPLATES["general"]:
        tmpl = _load_template(SPINE_TEMPLATES["general"])
    if not tmpl:
        return []
    spine = (tmpl.get("defaults") or {}).get("spine") or []
    return sorted(spine, key=lambda s: s.get("order", 0))


def load_bodies() -> Dict[str, Dict[str, Any]]:
    """章节骨架，按 kind 索引。"""
    tmpl = _load_template("section_bodies")
    if not tmpl:
        return {}
    bodies = (tmpl.get("defaults") or {}).get("bodies") or []
    return {b["kind"]: b for b in bodies if b.get("kind")}


def placeholders_in(text: str) -> List[str]:
    """正文里还没填的占位符名。"""
    return PLACEHOLDER_RE.findall(text or "")


def build_sections(spine_kind: str = "general") -> List[Section]:
    """按 spine + bodies 生成章节列表。

    spine 决定顺序和是否启用；bodies 提供正文骨架。
    spine 里有、bodies 里没有的节（如 appendix）用空正文 ——
    不编内容，留空比编一段假话好。

    spine_kind 选章节骨架（general / data_driven / physical / policy /
    evaluation）。题型不同，评审期待的结构也不同：机理题要先讲守恒律，
    评价题要先立指标体系，用同一套骨架会让论文显得答非所问。
    """
    spine = load_spine(spine_kind)
    bodies = load_bodies()
    out: List[PaperSection] = []
    self_problems: List[str] = []

    for item in spine:
        kind = item.get("kind")
        body_tmpl = bodies.get(kind, {})
        try:
            skind = SectionKind(kind)
        except ValueError:
            # 骨架里写了 SectionKind 没有的 kind。**必须出声**：
            # 静默降级成 OTHER 的后果是这一节照常显示、照常排版，
            # 但它匹配不到任何正文骨架，用户只会看到一节空的，
            # 完全不知道为什么（solution / scenario 这两个 kind
            # 并不是 SectionKind 的合法取值）。
            self_problems.append(
                f"骨架 '{spine_kind}' 的章节 kind='{kind}' 不是合法的 "
                f"SectionKind，已按 other 处理。合法取值见 schemas.SectionKind。"
            )
            skind = SectionKind.OTHER
        out.append(PaperSection(
            id=f"SEC-{item.get('order', 0):03d}",
            kind=skind,
            title=item.get("title") or kind,
            level=1,
            order=item.get("order", 0),
            enabled=bool(item.get("enabled", True)),
            # 自动生成的章节**不带正文**：符号表、参考文献、AI 报告的
            # 内容由编译器产出。带上骨架会怎样：符号表章节拿到一句
            # \input{generated/notations}，那个文件根本不会被生成，
            # 编译报 Undefined control sequence 且不产出 PDF。
            body="" if item.get("generated") else body_tmpl.get("body", ""),
            generated=bool(item.get("generated", False)),
        ))
    for msg in self_problems:
        warnings.warn(msg, stacklevel=2)
    return out


def section_budget(kind: str) -> Optional[float]:
    """某一节的建议篇幅（页）。"""
    b = load_bodies().get(kind)
    return b.get("budget_pages") if b else None


def section_checklist(kind: str) -> List[str]:
    """某一节的自查项。"""
    return list((load_bodies().get(kind) or {}).get("checklist") or [])


def scaffold(paper: Paper, fill_existing: bool = False,
             spine_kind: str = "general") -> Tuple[Paper, Dict[str, Any]]:
    """把骨架填进 Paper 记录。

    默认**不覆盖**已有正文：已经在写的章节不能被生成的内容冲掉。
    只补空章节和缺正文的章节。

    spine_kind 选用哪套题型骨架（general / data_driven / physical /
    policy / evaluation）。注意：**已经建好的论文换骨架不会删掉旧章节**
    —— 换骨架只影响"缺的章节补哪些"，想重建用 `paper spine`。
    """
    sections = build_sections(spine_kind)
    existing = {s.kind: s for s in paper.sections}

    added, filled = [], []
    for s in sections:
        prev = existing.get(s.kind)
        if prev is None:
            paper.sections.append(s)
            if not s.generated:
                added.append(s.title)
        elif prev.generated:
            # 自动生成的章节（符号表、参考文献、AI 报告）正文由编译器产出，
            # **不能**给它塞模板骨架。塞了会怎样：符号表章节拿到一句
            # \input{generated/notations}，而那个文件根本不会被生成，
            # 编译直接报 Undefined control sequence。
            # 这个坑真实踩到过，浪费了很久才定位到"骨架覆盖了生成标记"。
            continue
        elif fill_existing or not (prev.body or "").strip():
            # 只在这一节**真的有骨架**时才记一笔。
            # spine 里有、bodies 里没有的节（附录、AI 报告）本来就该是空的，
            # 把它们报成"已填入"是假消息 —— 用户会以为补了什么，其实没有。
            if (s.body or "").strip() and not (prev.body or "").strip():
                prev.body = s.body
                filled.append(prev.title)

    paper.sections.sort(key=lambda x: x.order)
    report = {
        "spine_kind": spine_kind,
        "added": added,
        "filled": filled,
        "total": len(paper.sections),
        "pending_placeholders": sum(
            len(placeholders_in(s.body)) for s in paper.sections
        ),
        "budget_pages": sum(
            section_budget(s.kind.value) or 0 for s in paper.sections if s.enabled
        ),
    }
    return paper, report


def outline(paper: Paper) -> List[Dict[str, Any]]:
    """给面板用的章节大纲：每节的篇幅建议、检查项、待填占位符。"""
    out = []
    for s in sorted(paper.sections, key=lambda x: x.order):
        kind = s.kind.value if hasattr(s.kind, "value") else str(s.kind)
        out.append({
            "id": s.id,
            "kind": kind,
            "title": s.title,
            "order": s.order,
            "enabled": s.enabled,
            "words": len((s.body or "").split()),
            "budget_pages": section_budget(kind),
            "checklist": section_checklist(kind),
            "placeholders": placeholders_in(s.body),
        })
    return out
