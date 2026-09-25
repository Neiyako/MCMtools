"""The Overview payload: one derived answer to "what state is this project in?"

This is Core, not API. The CLI, the API and any future UI all read the SAME
computed picture, because a UI that computes its own counts will eventually
disagree with the auditor -- and the auditor is the one that decides whether the
paper is submittable.

The central idea is the **blocker**: a thing that is currently wrong and has a
concrete next action. The corpus justifies treating failures as first-class
(83% of winning papers discuss weaknesses; the best document rejected methods),
so a failed experiment is surfaced as content, not hidden as an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schemas import ArtifactStatus, ExperimentStatus, Severity
from .store import Store


# --------------------------------------------------------------------------
# Blocker
# --------------------------------------------------------------------------


@dataclass
class Blocker:
    """Something wrong, with the action that resolves it.

    A blocker without an ``action`` is a complaint. Every constructor below
    supplies one, because the whole point of the panel is to say what to do
    next, not merely that something is broken.
    """

    code: str
    severity: str  # "error" | "warning"
    message: str
    action: str
    target: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "action": self.action,
            "target": self.target,
        }


# --------------------------------------------------------------------------
# Phase
# --------------------------------------------------------------------------


def current_phase(store: Store) -> str:
    """The project's phase, used to drive which navigation is visible.

    Mirrors ProjectConfig.phase: problem_selection -> problem_locked -> build
    -> finalize. Falls back to inspecting the project when unset, so a
    hand-edited project.yaml still yields a sensible answer.
    """
    try:
        cfg = store.layout.load_config()
    except FileNotFoundError:
        return "problem_selection"

    phase = getattr(cfg, "phase", None)
    if phase:
        return phase.value if hasattr(phase, "value") else str(phase)
    # No explicit phase: infer it from the lock state.
    if getattr(cfg, "locked_problem_id", None):
        return "build"
    return "problem_selection"


# --------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------


@dataclass
class Overview:
    """Everything the Overview screen renders, computed from the store."""

    phase: str = "problem_selection"
    problem: Dict[str, Any] = field(default_factory=dict)
    counts: Dict[str, Any] = field(default_factory=dict)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    blockers: List[Blocker] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "problem": self.problem,
            "counts": self.counts,
            "steps": self.steps,
            "blockers": [b.to_dict() for b in self.blockers],
        }

    @property
    def errors(self) -> List[Blocker]:
        return [b for b in self.blockers if b.severity == "error"]

    @property
    def warnings(self) -> List[Blocker]:
        return [b for b in self.blockers if b.severity == "warning"]


def build_overview(store: Store, report: Any = None) -> Overview:
    """Compute the Overview payload.

    ``report`` is an optional pre-computed AuditReport; when omitted the audit
    is run here. Passing it in lets a caller avoid auditing twice.
    """
    from .runner import stale_artifacts

    ov = Overview(phase=current_phase(store))

    # -- problem -----------------------------------------------------------
    try:
        cfg = store.layout.load_config()
        ov.problem = {
            "id": getattr(cfg, "locked_problem_id", None),
            "team_number": getattr(cfg, "team_control_number", None),
            "mode": getattr(getattr(cfg, "mode", None), "value", None),
            "locked": cfg.is_locked(),
        }
    except FileNotFoundError:
        ov.problem = {"locked": False}

    # -- counts ------------------------------------------------------------
    math_content = store.math.load()
    params = store.params.load()
    experiments = store.list_experiments()
    runs = store.load_runs()
    atoms = store.load_atoms()
    figures = store.list_figures()
    tables = store.list_tables()
    datasets = store.list_datasets()
    try:
        paper = store.load_paper()
        sections = paper.sections
    except Exception:
        paper, sections = None, []

    stale_figs, stale_tabs = stale_artifacts(store)
    failed_exps = [e for e in experiments if e.status == ExperimentStatus.FAILED]
    running_exps = [e for e in experiments if e.status == ExperimentStatus.RUNNING]
    done_exps = [e for e in experiments if e.status == ExperimentStatus.COMPLETED]

    pages, budget = _page_state(store, paper)

    ov.counts = {
        "problems": 1 if ov.problem.get("locked") else 0,
        "datasets": len(datasets),
        "symbols": len(math_content.symbols),
        "equations": len(math_content.equations),
        "assumptions": len(math_content.assumptions),
        "params": len(params.parameters),
        "params_unresolved": len(params.unresolved()),
        "experiments": {
            "total": len(experiments),
            "done": len(done_exps),
            "running": len(running_exps),
            "failed": len(failed_exps),
        },
        "runs": len(runs),
        "result_atoms": len(atoms),
        "figures": len(figures),
        "tables": len(tables),
        "stale_artifacts": len(stale_figs) + len(stale_tabs),
        "sections": len([s for s in sections if getattr(s, "enabled", True)]),
        "pages": pages,
        "page_budget": budget,
        "page_remaining": (budget - pages) if (pages is not None and budget) else None,
    }

    # -- steps (the state machine rendered as a checklist) -----------------
    ov.steps = _steps(store, ov, stale_figs, stale_tabs, failed_exps)

    # -- blockers ----------------------------------------------------------
    ov.blockers = _blockers(store, ov, report, stale_figs, stale_tabs, failed_exps)

    return ov


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------


def _page_state(store: Store, paper) -> tuple:
    """(pages, budget) from the last measured build, or (None, budget)."""
    budget = getattr(getattr(paper, "latex", None), "page_limit", None) or 25
    build = getattr(paper, "build_state", None) if paper else None
    pages = getattr(build, "last_page_count", None) if build else None
    if pages is None:
        # Fall back to an actual PDF on disk if one exists.
        pdf = store.root / "build" / "main.pdf"
        if pdf.exists():
            try:
                from .compiler import count_pdf_pages

                pages = count_pdf_pages(pdf)
            except Exception:
                pages = None
    return pages, budget


def _steps(store, ov: Overview, stale_figs, stale_tabs, failed_exps) -> List[Dict]:
    c = ov.counts
    locked = bool(ov.problem.get("locked"))
    pages = c.get("pages")
    budget = c.get("page_budget") or 25

    return [
        _step("problem", "已锁定题目", "done" if locked else "todo",
              detail=(ov.problem.get("id") or "") if locked else "尚未选题"),
        _step("data", "数据", _tick(c["datasets"]),
              detail=f"{c['datasets']} 个数据集"),
        _step("math", "数学内容", _tick(c["symbols"]),
              detail=(f"{c['symbols']} 个符号 · {c['equations']} 个公式"
                      f" · {c['assumptions']} 条假设")),
        _step("params", "参数", _tick(c["params"], partial=bool(c["params_unresolved"])),
              detail=(f"{c['params']} 个参数"
                      + (f" · {c['params_unresolved']} 个未解析"
                         if c["params_unresolved"] else ""))),
        _step("experiments", "实验",
              _tick(c["experiments"]["total"], partial=bool(
                  c["experiments"]["running"] or c["experiments"]["failed"])),
              detail=(f"完成 {c['experiments']['done']}"
                      f" · 运行中 {c['experiments']['running']}"
                      f" · 失败 {c['experiments']['failed']}")),
        _step("results", "结果与图表",
              _tick(c["figures"] + c["tables"], partial=bool(stale_figs or stale_tabs)),
              detail=(f"{c['figures']} 张图 · {c['tables']} 个表"
                      + (f" · {len(stale_figs) + len(stale_tabs)} 个已过期"
                         if stale_figs or stale_tabs else "")),
              ),
        _step("paper", "论文",
              "todo" if not c["sections"] else (
                  "done" if pages is not None else "partial"),
              detail=(f"{c['sections']} 个章节"
                      + (f" · {pages}/{budget} 页" if pages is not None else ""))),
        _step("audit", "审计",
              "todo" if not c["result_atoms"] else "partial",
              detail="见审计发现"),
    ]


def _step(key: str, label: str, status: str, detail: str = "") -> Dict[str, Any]:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _tick(n: int, partial: bool = False) -> str:
    if n == 0:
        return "todo"
    return "partial" if partial else "done"


def _blockers(
    store: Store, ov: Overview, report, stale_figs, stale_tabs, failed_exps
) -> List[Blocker]:
    out: List[Blocker] = []

    # -- stale artifacts: the headline blocker ----------------------------
    for f in stale_figs:
        out.append(Blocker(
            code="FIG_STALE", severity="error",
            message=f"图 {f.id} 已过期（stale）：它绑定的结果数字变了。",
            action="按当前结果重新生成。",
            target=f.id,
        ))
    for t in stale_tabs:
        out.append(Blocker(
            code="TAB_STALE", severity="error",
            message=f"表 {t.id} 已过期（stale）：它绑定的结果数字变了。",
            action="按当前结果重新生成。",
            target=t.id,
        ))

    # -- failed experiments: surfaced, not hidden --------------------------
    for e in failed_exps:
        out.append(Blocker(
            code="EXP_FAILED", severity="warning",
            message=f"实验 {e.id} 运行失败：{e.failure_reason or '没有记录原因'}",
            action="查看运行日志，然后修复它，或者把它作为「被否方案」写进论文。",
            target=e.id,
        ))

    # -- page budget --------------------------------------------------------
    pages = ov.counts.get("pages")
    budget = ov.counts.get("page_budget") or 25
    if pages is not None and pages > budget:
        out.append(Blocker(
            code="PAGE_OVERRUN", severity="error",
            message=f"PDF 共 {pages} 页，超出上限 {budget} 页。",
            action="删减内容，或者移到附录。",
            target="PAPER-001",
        ))

    # -- audit findings -----------------------------------------------------
    if report is not None:
        for f in getattr(report, "findings", []):
            if getattr(f, "suppressed", False):
                continue
            sev = getattr(getattr(f, "severity", None), "value", "info")
            if sev not in ("error", "warning"):
                continue
            out.append(Blocker(
                code=getattr(f, "code", "FINDING"),
                severity=sev,
                message=getattr(f, "message", ""),
                action=_action_for(getattr(f, "code", "")),
                target=getattr(f, "target", None),
            ))

    # Errors first, then warnings; stable within a severity.
    out.sort(key=lambda b: 0 if b.severity == "error" else 1)
    return out


_ACTIONS = {
    "AI_USE_UNDISCLOSED": "加一个启用的「Report on Use of AI」章节（不计入页数上限）。",
    "AI_DISCLOSURE_WITHOUT_USE": "删掉这个章节，或者补上实际用过的 AI 工具记录。",
    "SUMMARY_PLACEHOLDER": "把摘要页的占位内容写成正文。",
    "PAGE_OVERRUN": "删减内容，或者移到附录。",
    "NUMERIC_UNBOUND": "把这个数字绑定到 ResultAtom，或者用 \\lit{...} 标记为例外。",
    "ARTIFACT_NOT_CITED": "在正文里引用它，或者删掉它。",
    "ARTIFACT_FILE_MISSING": "生成这个图表文件。",
    "SENSITIVITY_WITHOUT_INVARIANT": "声明哪些参数保持固定不变。",
    "DUPLICATE_EQUATION_NUMBER": "重新编号公式。",
    "DANGLING_REFERENCE": "修正或删除这个引用。",
    "SYMBOL_REDEFINED": "改掉其中一个符号名，或者用 `redefines` 说明它们的关系。",
    "PARAMETER_NO_PROVENANCE": "标明这个数值的来源（literature / fitted / assumed）。",
    "NO_VALIDATION": "补一个验证实验。",
    "LITERATURE_REVIEW_HEADING": "删掉它：415 篇论文里 0 篇使用这个标题。",
}


def _action_for(code: str) -> str:
    return _ACTIONS.get(code, "检查这条发现，修正它指向的根本问题。")
