"""Validation and audit — the integrity engine.

This is where the tool earns its keep. Each check exists because the corpus
showed the corresponding defect is real and costly. Crucially, the checks are
calibrated so that a *winning* paper would pass: uncited figures are a warning
(63% of Outstanding figures are uncited), not an error.

Severity policy:
  ERROR   - the artifact is internally inconsistent; it cannot be trusted.
  WARNING - a real defect class that most published papers also have.
  INFO    - a notice worth surfacing, not a defect.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Set

from .schemas import (
    AIToolEntry,
    Experiment,
    ExperimentKind,
    ExperimentStatus,
    Figure,
    Paper,
    ProjectConfig,
    ResultAtom,
    SectionKind,
    Severity,
    Table,
    ValidationKind,
    Verdict,
)
from .store import Store
from .templates import TemplateRegistry

# Verbatim near-universal disclaimer from the corpus. Injected when a model's
# notation table is declared non-exhaustive, which is the correct default.
NOTATION_DISCLAIMER = (
    "There are some variables that are not listed here and will be discussed "
    "in detail in each section."
)

# Section kinds whose content is generated from records rather than authored.
AUTO_GENERATED = {
    SectionKind.NOTATIONS,
    SectionKind.REFERENCES,
    SectionKind.REPORT_ON_AI,
}


class Finding:
    """One audit finding."""

    __slots__ = ("severity", "code", "message", "subject")

    def __init__(
        self, severity: Severity, code: str, message: str, subject: Optional[str] = None
    ) -> None:
        self.severity = severity
        self.code = code
        self.message = message
        self.subject = subject

    def __repr__(self) -> str:  # pragma: no cover - display helper
        tag = self.severity.value.upper()
        where = f" [{self.subject}]" if self.subject else ""
        return f"{tag} {self.code}{where}: {self.message}"

    def as_dict(self) -> Dict[str, str]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "subject": self.subject or "",
            "message": self.message,
        }


class AuditReport:
    """Aggregated findings with a readiness verdict."""

    def __init__(self, findings: Optional[List[Finding]] = None) -> None:
        self.findings: List[Finding] = list(findings or [])

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def error(self, code: str, message: str, subject: Optional[str] = None) -> None:
        self.add(Finding(Severity.ERROR, code, message, subject))

    def warn(self, code: str, message: str, subject: Optional[str] = None) -> None:
        self.add(Finding(Severity.WARNING, code, message, subject))

    def info(self, code: str, message: str, subject: Optional[str] = None) -> None:
        self.add(Finding(Severity.INFO, code, message, subject))

    def of(self, severity: Severity) -> List[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def errors(self) -> List[Finding]:
        return self.of(Severity.ERROR)

    @property
    def warnings(self) -> List[Finding]:
        return self.of(Severity.WARNING)

    @property
    def infos(self) -> List[Finding]:
        return self.of(Severity.INFO)

    def ok(self) -> bool:
        return not self.errors

    def verdict(self) -> Verdict:
        if self.errors:
            return Verdict.NOT_READY
        if self.warnings:
            return Verdict.READY_FOR_HUMAN_REVIEW
        return Verdict.READY

    def summary_line(self) -> str:
        return (
            f"{len(self.errors)} 个错误，{len(self.warnings)} 个警告，"
            f"{len(self.infos)} 条提示  ->  {_VERDICT_ZH.get(self.verdict().value, self.verdict().value)}"
        )

    def as_dicts(self) -> List[Dict[str, str]]:
        return [f.as_dict() for f in self.findings]


# 结论的中文说法。枚举值本身是对外契约（API 里照原样返回），
# 所以这里只做显示层的映射，不改枚举。
_VERDICT_ZH = {
    "ready_for_human_review": "可以交给人审阅",
    "not_ready": "尚未就绪",
    "blocked": "存在阻塞问题",
}


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


def check_math(
    math, parameters: Sequence[Parameter], report: AuditReport
) -> None:
    """数学内容与参数的不变量。

    这块原来挂在 `Model` 下面按模型逐个检查。拆掉模型层之后改成
    **项目级**检查 —— 这更贴近事实：一篇论文只有一套符号表和
    一套公式编号，跨模型的符号冲突本质上是全文符号冲突。
    """
    # 1. 符号表非穷尽声明。语料里近乎通用，缺了就补，不报错。
    if not math.notation_table.exhaustive and not math.notation_table.disclaimer:
        math.notation_table.disclaimer = NOTATION_DISCLAIMER
        report.info(
            "NOTATION_DISCLAIMER_ADDED",
            "已自动加入标准的「符号表非穷尽」免责声明"
            "（语料惯例：符号表从来不是符号的权威定义）。",
            math.notation_table.id if hasattr(math.notation_table, "id") else None,
        )

    # 2. 符号重复定义。同一个符号两次含义不同 = 读者会被误导。
    by_glyph: Dict[str, List[Any]] = {}
    for sym in math.symbols:
        by_glyph.setdefault(sym.glyph, []).append(sym)
    for glyph, group in sorted(by_glyph.items()):
        if len(group) < 2:
            continue
        meanings = {g.meaning.strip().lower() for g in group}
        ids = ", ".join(g.id for g in group)
        if len(meanings) > 1:
            report.error(
                "SYMBOL_REDEFINED",
                f"符号 '{glyph}' 被定义了 {len(group)} 次且含义不同"
                f"（{ids}）。同一个符号在一篇论文里只能有一个含义；"
                f"若确为复用，请用 redefines 指明关系。",
                group[0].id,
            )
        else:
            report.warn(
                "SYMBOL_DUPLICATE",
                f"符号 '{glyph}' 重复出现在符号表里 {len(group)} 次（{ids}），"
                "含义相同，应当合并。",
                group[0].id,
            )

    # 3. 符号 role 全未标注。
    if math.symbols and all(s.role.value == "unknown" for s in math.symbols):
        report.info(
            "SYMBOL_ROLES_UNSET",
            f"全部 {len(math.symbols)} 个符号的 role 都是 'unknown'。"
            "这与多数论文一致，但标注出 state/decision/parameter 之后，"
            "符号表和参数表才能自动生成。",
            math.symbols[0].id,
        )

    # 4. 公式编号重复。编号是全文计数器，必须唯一。
    numbers = [e.number for e in math.equations if e.number and e.is_numbered]
    for n in sorted({x for x in numbers if numbers.count(x) > 1}):
        report.error(
            "EQUATION_NUMBER_DUPLICATE",
            f"公式编号 ({n}) 重复使用。公式编号是全文统一的计数器，必须唯一。",
            None,
        )

    # 5. 有目标函数就应有约束；优化类内容缺约束是常见硬伤。
    if math.objective and math.objective.expressions and not math.constraints:
        report.warn(
            "OPTIMIZATION_NO_CONSTRAINTS",
            "已记录目标函数，但没有记录任何约束条件。",
            None,
        )

    # 6. 参数要有来源。105/237 篇现代论文会列表说明来源。
    unprovenanced = [p for p in parameters if p.source.value == "unknown"]
    if unprovenanced:
        names = ", ".join(p.name for p in unprovenanced[:5])
        more = "" if len(unprovenanced) <= 5 else f"（另有 {len(unprovenanced) - 5} 个）"
        report.warn(
            "PARAMETER_NO_PROVENANCE",
            f"{len(unprovenanced)} 个参数没有标注来源：{names}{more}。"
            "应标明 literature / dataset / fitted / assumed。",
            unprovenanced[0].id,
        )

    # 7. 声明过的符号是否真的在正文里出现过（避免符号表比正文还长）。
    if math.symbols:
        unused = [s for s in math.symbols if s.role.value == "unknown"]
        if len(unused) == len(math.symbols) and len(math.symbols) > 12:
            report.info(
                "NOTATION_LARGER_THAN_BODY",
                f"符号表有 {len(math.symbols)} 个符号且都没有标注用途，"
                "容易与正文脱节。",
                math.symbols[0].id,
            )


def check_experiment(
    exp: Experiment,
    atom_ids: Set[str],
    report: AuditReport,
) -> None:
    """Experiment protocol invariants."""

    for rid in exp.result_atom_ids:
        if rid not in atom_ids:
            report.error(
                "DANGLING_RESULT_ATOM",
                f"result_atom_ids 引用了不存在的结果原子 '{rid}'。",
                exp.id,
            )

    # The signature of a real sensitivity experiment: one varied axis plus a
    # declared invariant. Without the invariant the result is not interpretable.
    if exp.kind == ExperimentKind.SENSITIVITY_OAT:
        if len(exp.varied) != 1:
            report.warn(
                "OAT_VARIED_AXIS_COUNT",
                f"kind 是 'sensitivity_oat'，但有 {len(exp.varied)} 个参数在变动。"
                "多参数同时扫描请用 'sensitivity_grid'。",
                exp.id,
            )
        if not exp.held_fixed:
            report.error(
                "OAT_NO_INVARIANT",
                "单因子轮换（OAT）必须声明哪些参数保持固定不变。"
                "这是判断一次敏感性分析是否真实做过的最可靠特征"
                "（「我们只改变该参数，其余参数保持默认值」）。",
                exp.id,
            )

    # Multi-run experiments must declare how runs were aggregated.
    if exp.n_runs and exp.n_runs > 1 and not exp.aggregation:
        report.warn(
            "MULTIRUN_NO_AGGREGATION",
            f"n_runs={exp.n_runs}，但没有声明聚合方式。"
            "论文必须说明多次重复是怎么合并的（如「均值与标准差」）。",
            exp.id,
        )

    # A failed/rejected experiment must say why: that reason is the argument.
    if exp.status in (ExperimentStatus.FAILED, ExperimentStatus.REJECTED):
        if not exp.failure_reason:
            report.warn(
                "FAILED_WITHOUT_REASON",
                f"status 是 '{exp.status.value}'，但 failure_reason 是空的。"
                "写出失败原因，才能让「被否方案」成为站得住脚的论证。",
                exp.id,
            )

    # Uncertainty claims need a magnitude to be meaningful.
    for m in exp.metrics:
        if m.dispersion is not None and m.dispersion_kind.value == "none":
            report.warn(
                "DISPERSION_WITHOUT_KIND",
                f"指标 '{m.name}' 有离散度数值，但没有指定 dispersion_kind"
                "（std / confidence_interval / iqr 含义不同）。",
                exp.id,
            )

    if not exp.random_seed and exp.kind in (
        ExperimentKind.MONTE_CARLO,
        ExperimentKind.ROBUSTNESS_NOISE,
    ):
        report.info(
            "NO_SEED",
            "没有记录随机种子。已发表论文中只有约 5% 会写，"
            "所以这条只是提示 —— 但记录它不花任何代价。",
            exp.id,
        )


def check_result_atom(atom: ResultAtom, report: AuditReport) -> None:
    """A number is meaningless without its condition and unit."""
    if atom.condition is None and not atom.unit:
        report.warn(
            "ATOM_NO_CONDITION_OR_UNIT",
            f"结果原子 '{atom.atom_id}' 既没有条件也没有单位。"
            "一个数字至少要有其一才能被解释。",
            atom.atom_id,
        )
    if atom.numeric() is None:
        report.error(
            "ATOM_NON_NUMERIC_NO_FORMAT",
            f"结果原子 '{atom.atom_id}' 不是数值；它的值必须能通过格式串渲染。",
            atom.atom_id,
        )


def collect_body_text(paper: Paper) -> str:
    """把论文全文拼成一段，用来找图表引用。"""
    parts = []
    if paper.summary and paper.summary.body:
        parts.append(paper.summary.body)
    for sec in paper.ordered_sections():
        if sec.enabled and sec.body:
            parts.append(sec.body)
    return "\n".join(parts)


def mark_citations(
    paper: Paper, figures: List[Figure], tables: List[Table], report: AuditReport
) -> None:
    """扫描正文中的 \ref{...}，回填每个图表的 referenced_in。

    引用形式有两种：`\ref{fig:fit}`（靠 label）和最直接的
    `\includegraphics{figures/FIG-002.pdf}`（靠文件名）。两种都认，
    因为作者可能用其中任何一种。
    """
    body = collect_body_text(paper)
    if not body:
        return

    refs = set(re.findall(r"\\ref\{([^}]+)\}", body))
    refs |= set(re.findall(r"\\eqref\{([^}]+)\}", body))
    graphics = set(re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", body))

    for art in list(figures) + list(tables):
        found: List[str] = []
        label = getattr(art, "label", None)
        if label and label in refs:
            found.append(f"\\ref{{{label}}}")
        # 文件名匹配：figures/FIG-002.pdf 里含 FIG-002
        for g in graphics:
            if art.id in g:
                found.append(g)
                break
        art.referenced_in = found


def check_artifact(
    art: object, atom_ids: Set[str], report: AuditReport
) -> None:
    """Figures and tables must bind to real atoms, and citation is a warning."""
    label = getattr(art, "id", "?")
    bounds: List[str] = []

    if isinstance(art, Figure):
        # 只有**标量原子绑定**需要指向真实原子。
        # 序列绑定指向的是运行产物里的一列，字面绑定指向人写的结构内容
        # （流程图节点）—— 这两类本来就没有对应的 ResultAtom，
        # 把它们当悬空绑定报错会逼用户去伪造原子。
        bounds = [
            b.atom_id for b in art.bindings
            if not b.is_series() and not b.is_literal()
        ]
    elif isinstance(art, Table):
        bounds = art.bound_atom_ids()

    for aid in bounds:
        if aid not in atom_ids:
            report.error(
                "DANGLING_ARTIFACT_BINDING",
                f"绑定了不存在的结果原子 '{aid}'。"
                "图表只能绑定由实验产出的原子。",
                label,
            )

    # Staleness: the artifact no longer matches the results it displays. The
    # compiler emits this too, but the auditor is what the submission gate
    # trusts, so it must detect staleness independently rather than relying on
    # a build having been run.
    if getattr(art, "status", None) is not None:
        status = getattr(art.status, "value", art.status)
        if status == "stale":
            report.warn(
                "FIG_STALE" if isinstance(art, Figure) else "TAB_STALE",
                "这张图生成之后，它绑定的结果数字变了 —— "
                "文档里现在显示的是实验已经不再产生的结果。请重新生成。",
                label,
            )

    # 序列绑定和字面绑定同样是"绑定"，只是绑的不是标量原子。
    # 只看 bounds 会把所有曲线图都误报成"没有绑定"，这里要一起看。
    has_any_binding = bool(getattr(art, "bindings", [])) or bool(bounds)
    if not has_any_binding:
        report.warn(
            "ARTIFACT_UNBOUND",
            "图表没有绑定任何结果原子。没有绑定，数字变化时它就无法被重新生成。",
            label,
        )

    referenced_in = getattr(art, "referenced_in", [])
    if not referenced_in:
        report.warn(
            "ARTIFACT_NOT_CITED",
            "正文里从来没有引用过它。已发表论文中只有 37% 的图和 33% 的表"
            "被交叉引用，所以这是警告而非错误 —— 但引用它能提升论文质量。",
            label,
        )


def check_artifact_files(
    store_root, figures, report: AuditReport
) -> None:
    """A figure whose bound file is absent renders as a placeholder box."""
    from pathlib import Path

    for fig in figures:
        if not fig.file:
            report.warn(
                "ARTIFACT_NO_FILE",
                "图还没有生成文件；构建时会在 PDF 里留下一个可见的占位框。"
                "请先运行图表生成器。",
                fig.id,
            )
            continue
        if not (Path(store_root) / fig.file).exists():
            report.warn(
                "ARTIFACT_FILE_MISSING",
                f"图文件 '{fig.file}' 不存在；构建时会在 PDF 里留下一个可见的占位框。",
                fig.id,
            )


def check_paper(
    paper: Paper,
    atom_ids: Set[str],
    figure_ids: Set[str],
    table_ids: Set[str],
    report: AuditReport,
    competition_mode: bool = False,
) -> None:
    """Paper-level structure, page budget, and COMAP compliance."""

    # 1. Summary sheet placeholders are errors: they must never ship.
    if paper.summary.is_placeholder():
        report.error(
            "SUMMARY_PLACEHOLDER",
            "摘要页仍然是占位内容 "
            f"（题目 '{paper.summary.problem_letter}'，队伍号 "
            f"'{paper.summary.team_control_number}'）。提交前必须写成真实内容。",
            paper.paper_id,
        )

    # 2. Page budget. 72.1% of 2022-2025 papers are exactly 25 pages.
    if paper.build.page_count is not None:
        limit = paper.latex.page_limit
        if paper.build.page_count > limit:
            report.error(
                "PAGE_LIMIT_EXCEEDED",
                f"PDF 共 {paper.build.page_count} 页，超出 {limit} 页上限。"
                "超出的部分必须移到附录。",
                paper.paper_id,
            )
        elif paper.build.page_count == limit:
            report.info(
                "PAGE_LIMIT_EXACT",
                f"PDF 正好 {limit} 页，与近年 72.1% 的 Outstanding 论文一致。",
                paper.paper_id,
            )
        elif paper.build.page_count < limit - 3:
            report.warn(
                "PAGE_BUDGET_UNDERUSED",
                f"PDF 只有 {paper.build.page_count} 页，还有 {limit - paper.build.page_count} 页预算没有用。",
                paper.paper_id,
            )

    # 3. Section structure. Order is templated; membership is free.
    kinds = [s.kind for s in paper.enabled_sections()]
    if SectionKind.INTRODUCTION not in kinds:
        report.error(
            "MISSING_INTRODUCTION",
            "缺少引言章节。87.5% 的论文都有引言。",
            paper.paper_id,
        )
    if SectionKind.REFERENCES not in kinds:
        report.error(
            "MISSING_REFERENCES",
            "缺少参考文献章节。92.0% 的论文都有参考文献。",
            paper.paper_id,
        )

    # The one relation that must hold: Introduction precedes References.
    order_by_kind: Dict[SectionKind, int] = {}
    for s in paper.enabled_sections():
        order_by_kind.setdefault(s.kind, s.order)
    if SectionKind.INTRODUCTION in order_by_kind and SectionKind.REFERENCES in order_by_kind:
        if order_by_kind[SectionKind.REFERENCES] < order_by_kind[SectionKind.INTRODUCTION]:
            report.error(
                "SECTION_ORDER_VIOLATION",
                "参考文献排在引言前面。语料中有 14 组顺序关系是 100% 成立的，"
                "这就是其中一组。",
                paper.paper_id,
            )

    # Literature Review must never be templated: it appears in 0 of 415 papers.
    for s in paper.sections:
        if "literature review" in s.title.strip().lower():
            report.warn(
                "LITERATURE_REVIEW_SECTION",
                f"章节 '{s.title}' 是「文献综述」。"
                "这个标题在 415 篇语料论文里出现 0 次，应当并入引言。",
                s.id,
            )

    # 5. Content sections should not be empty.
    for s in paper.enabled_sections():
        if s.kind in AUTO_GENERATED:
            continue
        if not s.body or not s.body.strip():
            report.warn(
                "SECTION_EMPTY",
                f"章节 '{s.title}' 没有正文。",
                s.id,
            )

    # 6b. Unbound numeric literals in prose.
    #     A number typed by hand cannot be kept in sync with its source, which is
    #     how 69% of papers end up repeating a precise number internally.
    try:
        from .compiler.numbers import check_section_body
    except ImportError:  # pragma: no cover - compiler always present in-tree
        check_section_body = None
    if check_section_body is not None:
        for s in paper.enabled_sections():
            if s.generated or not s.body:
                continue
            for code, msg in check_section_body(s.id, s.body):
                report.warn(code, msg, s.id)

    # 7. COMAP AI compliance. This is a real, checkable requirement.
    if paper.ai_usage.requires_disclosure():
        has_section = any(
            s.kind == SectionKind.REPORT_ON_AI and s.enabled for s in paper.sections
        )
        if not has_section:
            report.error(
                "AI_USE_UNDISCLOSED",
                "记录了 AI 使用，但没有启用「Report on Use of AI」章节。"
                "COMAP 允许使用 AI，但要求在解答之后用一个"
                "不计入页数上限的章节披露。",
                paper.paper_id,
            )
        comp = paper.ai_usage.competition_use()
        if comp and competition_mode:
            report.warn(
                "AI_USED_DURING_COMPETITION",
                f"竞赛阶段记录了 {len(comp)} 条 AI 使用。"
                "本工具的设计前提是竞赛期离线操作；"
                "如果确实发生了，必须完整披露。",
                paper.paper_id,
            )


def check_result_reuse(atoms: Sequence[ResultAtom], report: AuditReport) -> None:
    """Duplicate values are the signature of an un-single-sourced number.

    69% of papers repeat a precise number internally; this check makes the
    repetition visible so it can be replaced by an atom reference.
    """
    by_value: Dict[str, List[str]] = {}
    for a in atoms:
        n = a.numeric()
        if n is None:
            continue
        key = f"{n:.6g}"
        by_value.setdefault(key, []).append(a.atom_id)
    for value, ids in sorted(by_value.items()):
        if len(ids) > 1:
            report.info(
                "POSSIBLE_DUPLICATE_VALUE",
                f"数值 {value} 出现在 {len(ids)} 个结果原子里：{', '.join(ids)}。"
                "如果它们其实是同一个量，应当合并为一个原子。",
                value,
            )


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def audit_project(
    store: Store,
    registry: Optional[TemplateRegistry] = None,
    check_templates: bool = True,
) -> AuditReport:
    """Run every check over a project on disk."""
    report = AuditReport()

    math_content = store.math.load()
    params = store.params.load().parameters
    experiments = store.list_experiments()
    atoms = store.load_atoms()
    figures = store.list_figures()
    tables = store.list_tables()
    paper = store.load_paper()

    atom_ids = {a.atom_id for a in atoms}
    figure_ids = {f.id for f in figures}
    table_ids = {t.id for t in tables}

    if not atoms:
        report.warn("NO_RESULTS", "项目里还没有结果原子。")

    # 数学内容与参数统一在项目级检查（不再按模型逐个检查）。
    check_math(math_content, params, report)
    for e in experiments:
        check_experiment(e, atom_ids, report)
    for a in atoms:
        check_result_atom(a, report)
    # 先扫正文里的 \ref{}，把"这张图在正文哪里被引用过"填进去。
    # 不扫的话 referenced_in 永远是空的，ARTIFACT_NOT_CITED 就必然对
    # **每一张图**报警 —— 一条永远无法消除的警告等于没有警告。
    mark_citations(paper, figures, tables, report)

    for f in figures:
        check_artifact(f, atom_ids, report)
    check_artifact_files(store.root, figures, report)
    for t in tables:
        check_artifact(t, atom_ids, report)

    cfg = store.layout.load_config()
    check_paper(
        paper,
        atom_ids,
        figure_ids,
        table_ids,
        report,
        competition_mode=cfg.mode.value == "competition",
    )
    check_result_reuse(atoms, report)

    # Validate that every experiment/artifact template referenced actually exists.
    if check_templates and registry is not None:
        for tpl_err in registry.validate():
            report.error("TEMPLATE_INVALID", tpl_err)
        for e in experiments:
            tid = getattr(e, "template_id", None)
            if tid and tid not in registry:
                report.warn(
                    "UNKNOWN_TEMPLATE",
                    f"实验引用了模板 '{tid}'，但模板注册表里没有它。",
                    e.id,
                )

    return report
