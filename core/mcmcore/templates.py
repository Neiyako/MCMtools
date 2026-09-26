"""Template Registry — Layer 3, reusable knowledge and code.

Templates are the third layer (Architecture §12), distinct from Core
(execution) and Interface (invocation). They encode *reusable knowledge*:
what a sensitivity sweep is, what a metric-comparison table looks like, what
the COMAP summary sheet requires.

The registry is deliberately data-first: a template is a YAML file with an
optional ``entrypoint`` script. That means a template can be inspected,
diffed, and validated without executing anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import Field

from .schemas import MCMBase

# 模板分区。加分区时要一并改 cli.py 里硬编码的那份清单，
# 否则 `mcm template list` 不会显示新分区 —— 加载正常、校验正常，
# 但用户看不到，属于"系统没坏、功能没了"的那种问题。
TEMPLATE_KINDS = ("model", "experiment", "figure", "table", "paper", "code")


class TemplateIO(MCMBase):
    """One declared input or output of a template."""

    name: str
    type: str = Field(default="any", description="scalar | array | matrix | dataframe | any")
    role: Optional[str] = None
    unit: Optional[str] = None
    optional: bool = False
    description: Optional[str] = None


class TemplateRequires(MCMBase):
    """What the caller must supply for the template to be usable."""

    model: bool = False
    dataset: bool = False
    required_inputs: List[str] = Field(default_factory=list)
    required_fields: List[str] = Field(default_factory=list)


class TemplateLoadError(RuntimeError):
    """模板加载失败。宁可启动就崩，也不要少一半模板还照常跑。"""


class Template(MCMBase):
    """A reusable, parameterised unit of knowledge or code."""

    template_id: str = Field(..., min_length=1, description="e.g. 'exp.sensitivity_oat'.")
    kind: str = Field(..., description="model | experiment | figure | table | paper.")
    version: str = "1.0.0"
    description: Optional[str] = None

    # Corpus grounding: why this template exists and how often it occurs.
    observed_in: Optional[str] = Field(
        default=None,
        description="Frequency evidence from the corpus, e.g. '~42% of modern papers'.",
    )
    evidence: List[str] = Field(
        default_factory=list, description="Corpus citations supporting this template."
    )

    requires: TemplateRequires = Field(default_factory=TemplateRequires)
    inputs: List[TemplateIO] = Field(default_factory=list)
    outputs: List[TemplateIO] = Field(default_factory=list)

    # Presentation
    purpose: Optional[str] = Field(
        default=None, description="One line: what this template is for."
    )
    # 面板是中文界面，模板用途却是英文 —— 用户在一堆英文句子里挑模板。
    # 所以中文单独放一个字段：英文的 purpose 保留给搜索和论文引用，
    # 中文的给面板显示。谁都不将就谁。
    purpose_cn: Optional[str] = Field(
        default=None, description="中文用途，供面板显示。"
    )
    caption_template: Optional[str] = None
    latex: Optional[str] = None
    defaults: Dict[str, object] = Field(default_factory=dict)

    # Figure/table specifics
    figure_type: Optional[str] = Field(
        default=None,
        description="line | scatter | bar | boxplot | heatmap | map | graph | diagram.",
    )
    reference_file: Optional[str] = Field(
        default=None,
        description="A verbatim source artifact bundled beside the template, e.g. the "
        "official COMAP .tex that the paper template was extracted from.",
    )

    # Execution (optional)
    entrypoint: Optional[str] = Field(
        default=None, description="Relative path to a script, if this template runs code."
    )
    dependencies: List[str] = Field(default_factory=list)
    backend: Optional[str] = Field(
        default=None, description="matplotlib | drawio | latex | none."
    )

    def resolve_entrypoint(self, root: Path) -> Optional[Path]:
        if not self.entrypoint:
            return None
        return Path(root) / self.entrypoint


class TemplateRegistry:
    """Loads and queries templates from a directory tree.

    Expected layout::

        templates/
          registry.yaml            (optional index)
          models/<name>/template.yaml
          experiments/<name>/template.yaml
          figures/<name>/template.yaml
          tables/<name>/template.yaml
          paper/<name>/template.yaml
    """

    def __init__(self, root: Path, extra_roots: Optional[List[Path]] = None) -> None:
        self.root = Path(root)
        # 用户自定模板库（~/.mcmtools/templates）。同一 template_id 在两处
        # 都有时**自带库胜出** —— 那是官方版本，行为可预期。
        self.extra_roots: List[Path] = [Path(p) for p in (extra_roots or [])]
        self._templates: Dict[str, Template] = {}
        self._errors: List[str] = []

    # -- loading -----------------------------------------------------------
    def load(self) -> "TemplateRegistry":
        self._templates.clear()
        self._errors.clear()
        # 自带库缺失是错误（"模板没了"必须报出来）；用户库缺失是正常的
        # （还没存过任何自定模板）。
        for i, root in enumerate([self.root, *self.extra_roots]):
            if not root.is_dir():
                if i == 0:
                    self._errors.append(
                        f"template root does not exist: {root}")
                continue
            self._load_one(root)
        return self

    def _load_one(self, root: Path) -> None:
        for path in sorted(root.rglob("template.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                tmpl = Template(**data)
            except Exception as exc:  # keep loading; report at the end
                self._errors.append(f"{path}: {type(exc).__name__}: {exc}")
                continue
            if tmpl.template_id in self._templates:
                # 自带库里的重复仍是错误；自带库和用户库撞名则以自带为准，
                # 静默跳过即可 —— 用户重新存一次同名图不该让启动失败。
                if root == self.root:
                    self._errors.append(
                        f"{path}: duplicate template_id '{tmpl.template_id}'"
                    )
                continue
            self._templates[tmpl.template_id] = tmpl

    def load_strict(self) -> "TemplateRegistry":
        """加载并**在有任何模板失败时抛错**。

        为什么需要这个：``load()`` 把失败收进 ``_errors`` 继续跑。
        给 28 个模板加一个 schema 不认识的字段时，它们被静默丢弃，
        注册表从 74 掉到 46 而没有任何异常 —— 直到有人发现
        ``get('fig.timeseries')`` 返回 None。工具库少一半模板
        却不出声，比直接报错危险得多。

        所以生产和测试都走这个方法：宁可启动就崩，也不要少东西还照常跑。
        """
        self.load()
        if self._errors:
            detail = "\n  ".join(self._errors[:5])
            more = "" if len(self._errors) <= 5 else f"\n  ...另有 {len(self._errors) - 5} 条"
            raise TemplateLoadError(
                f"{len(self._errors)} 个模板加载失败：\n  {detail}{more}"
            )
        return self

    def assert_no_errors(self) -> None:
        """有加载错误就抛。已经 load() 过的场景用它补一道检查。"""
        if self._errors:
            raise TemplateLoadError(
                f"{len(self._errors)} 个模板加载失败，第一条：{self._errors[0]}"
            )

    # -- queries -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._templates)

    def __contains__(self, template_id: object) -> bool:
        return template_id in self._templates

    def get(self, template_id: str) -> Optional[Template]:
        return self._templates.get(template_id)

    def all(self) -> List[Template]:
        return list(self._templates.values())

    def by_kind(self, kind: str) -> List[Template]:
        return [t for t in self._templates.values() if t.kind == kind]

    def ids(self, kind: Optional[str] = None) -> List[str]:
        items = self.by_kind(kind) if kind else self.all()
        return sorted(t.template_id for t in items)

    @property
    def errors(self) -> List[str]:
        return list(self._errors)

    def validate(self) -> List[str]:
        """Return a list of registry-level problems (empty means healthy)."""
        problems = list(self._errors)
        for t in self._templates.values():
            if t.kind not in TEMPLATE_KINDS:
                problems.append(
                    f"{t.template_id}: unknown kind '{t.kind}' "
                    f"(expected one of {', '.join(TEMPLATE_KINDS)})"
                )
            if t.entrypoint and not t.resolve_entrypoint(self.root).exists():  # type: ignore[union-attr]
                problems.append(
                    f"{t.template_id}: entrypoint not found: {t.entrypoint}"
                )
        return problems

    def summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for t in self._templates.values():
            counts[t.kind] = counts.get(t.kind, 0) + 1
        return counts

    # -- presentation ------------------------------------------------------
    @staticmethod
    def headline(t: "Template") -> str:
        """一句话用途。

        早期模板写 ``description``，后来加的写 ``purpose``，两个字段
        含义相同且都在 schema 里。翻遍调用点会把半个代码库搅一遍，
        而且容易漏 —— 所以在这里收口成一个访问器，谁要显示用途都走它。

        中文优先：面板是中文界面，给用户看英文句子等于没给。
        英文的 ``purpose`` 仍保留，供搜索和论文引用使用。
        """
        return (t.purpose_cn or t.purpose or t.description or "").strip()

    def describe(self, t: "Template") -> Dict[str, object]:
        """模板的展示卡片：面板和 CLI 都用它，保证两处显示一致。"""
        return {
            "template_id": t.template_id,
            "kind": t.kind,
            "headline": self.headline(t),
            "observed_in": t.observed_in or "",
            "figure_type": t.figure_type or "",
            "required": list((t.requires.required_inputs if t.requires else []) or []),
            "inputs": [
                {"name": i.name, "optional": i.optional, "type": i.type}
                for i in t.inputs
            ],
            "defaults": dict(t.defaults or {}),
        }

    # -- search ------------------------------------------------------------
    def search(self, query: str, kind: Optional[str] = None,
               limit: Optional[int] = None) -> List["Template"]:
        """按关键词找模板。

        模板一多，"我知道有这么个图但想不起叫什么"就是最常发生的事。
        这里让用户用**自己的话**搜：可以搜 "敏感性"、"sensitivity"、
        "参数扫描"，都能命中同一个模板。

        匹配按权重排序，权重高的排前面：

            4  模板 id 完全相等
            3  id 或 purpose 里出现
            2  输入名、图注模板、用途说明里出现
            1  evidence / observed_in 里出现

        这样搜 "roc" 时，id 叫 roc_curve 的模板一定排在
        "某篇论文的 evidence 里提了一句 ROC" 的模板前面。
        """
        q = (query or "").strip().lower()
        if not q:
            return []

        # 多词按"全部命中"处理，词的顺序不重要
        terms = [w for w in q.replace(",", " ").split() if w]

        scored: List[tuple] = []
        for t in self._templates.values():
            if kind and t.kind != kind:
                continue

            tid = t.template_id.lower()
            purpose = self.headline(t).lower()
            inputs = " ".join(
                f"{i.name} {i.role or ''} {i.description or ''}"
                for i in t.inputs
            ).lower()
            caption = (t.caption_template or "").lower()
            ground = " ".join(
                [t.observed_in or ""] + list(t.evidence or [])
            ).lower()

            score = 0
            hit_all = True
            for term in terms:
                if term == tid or tid.endswith("." + term):
                    score += 4
                elif term in tid or term in purpose:
                    score += 3
                elif term in inputs or term in caption:
                    score += 2
                elif term in ground:
                    score += 1
                else:
                    hit_all = False
                    break
            if hit_all and score > 0:
                # 同分时按 id 排序，保证结果稳定可复现
                scored.append((-score, t.template_id, t))

        scored.sort(key=lambda x: (x[0], x[1]))
        found = [t for _, _, t in scored]
        return found[:limit] if limit else found

    def suggest(self, need: str, kind: Optional[str] = None,
                limit: int = 3) -> List["Template"]:
        """给一句中文需求，猜该用哪个模板。

        和 search 的区别：search 是精确找，suggest 是"我不知道要什么，
        你看着办"。所以这里额外做中文关键词到英文模板词的映射 ——
        用户写"画个热力图"时，模板里一个中文字都没有。
        """
        # 中文需求 → 模板词汇。左边是用户会写的，右边是模板里真实存在的词。
        CN2EN = {
            "热力": "heatmap", "热图": "heatmap", "相关": "correlation",
            "相关矩阵": "correlation", "散点": "scatter", "分布": "histogram",
            "直方": "histogram", "密度": "histogram", "箱线": "box",
            "小提琴": "violin", "折线": "timeseries", "趋势": "timeseries",
            "时间": "timeseries", "时序": "timeseries", "柱状": "bar",
            "条形": "bar", "排序": "ranked", "雷达": "radar",
            "网络": "network", "图结构": "network", "流程": "flowchart",
            "结构": "structure", "桑基": "sankey", "流向": "sankey",
            "甘特": "gantt", "调度": "gantt", "排班": "gantt",
            "帕累托": "pareto", "前沿": "pareto", "权衡": "pareto",
            "曲面": "surface", "三维": "surface", "3d": "surface",
            "瀑布": "waterfall", "贡献": "waterfall", "分解": "waterfall",
            "残差": "residual", "拟合": "pred_vs_actual", "预测": "pred_vs_actual",
            "roc": "roc", "混淆": "confusion", "分类": "roc",
            "误差": "errorbar", "置信": "errorbar", "收敛": "convergence",
            "迭代": "convergence", "累积": "cumulative", "生存": "survival",
            "堆叠": "stacked", "面积": "stacked", "地图": "map",
            "地理": "map", "相图": "phase", "相空间": "phase",
            "qq": "qq", "正态": "qq", "敏感性": "sensitivity",
            "扫描": "sensitivity", "对比": "comparison", "评价": "radar",
            "蒙特卡洛": "errorbar", "交叉验证": "errorbar",
        }
        extra = [en for cn, en in CN2EN.items() if cn in (need or "").lower()]
        # 中文词没有英文对应时，原词也拿去搜一次，至少能命中 purpose
        query = " ".join([need or ""] + extra).strip()
        hits = self.search(query, kind=kind, limit=None)
        if not hits and extra:
            for en in extra:
                hits = self.search(en, kind=kind, limit=None)
                if hits:
                    break
        return hits[:limit]


def default_registry_root() -> Path:
    """Locate the bundled templates/ directory.

    路径解析统一走 ``root.py``。原来这里是"从本文件往上找第一个叫
    templates 的目录"—— 会被任何同名文件夹骗到（项目目录里恰好有个
    ``templates/`` 就命中那里，模板少一半而服务照常启动、照常响应）。
    """
    from .root import templates_root

    return templates_root()


def registry_roots() -> List[Path]:
    """模板库的全部根目录：自带的在前，用户自定的在后。"""
    from .root import template_roots

    return template_roots()


def load_registry(strict: bool = True) -> "TemplateRegistry":
    """加载全部模板根。生产和测试都该走这里，而不是手搓 Registry。"""
    reg = TemplateRegistry(default_registry_root(),
                           extra_roots=registry_roots()[1:])
    return reg.load_strict() if strict else reg.load()
