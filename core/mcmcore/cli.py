"""MCMtools command-line interface.

Layer 2 (Interface). Deliberately dependency-free (argparse, not click/typer) so
it works on the competition machine with no network and no extra installs.

Commands::

    mcm init <dir>
    mcm status
    mcm template list|show
    mcm math show        符号表、公式、假设\n    mcm param list       参数及其来源
    mcm exp list|show
    mcm result list
    mcm validate [--json]
    mcm paper spine
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .schemas import SectionKind, Verdict
from .compiler import PaperCompiler, find_engine
from .figures import FigureGenerator
from .runner import ExperimentRunner, stale_artifacts
from .runstore import RunStore
from .store import Store
from .templates import TEMPLATE_KINDS
from .templates import TemplateRegistry, default_registry_root
from .validate import audit_project


def _default_root(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "dir", None) or ".").resolve()


def _registry() -> TemplateRegistry:
    return TemplateRegistry(default_registry_root()).load_strict()


def _fmt_table(headers: List[str], rows: List[List[str]]) -> str:
    if not rows:
        return "  (none)"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "  " + "  ".join("-" * w for w in widths)
    body = [
        "  " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row))
        for row in rows
    ]
    return "\n".join([line, sep] + body)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    root = _default_root(args)
    store = Store.init(root, project_id=args.project_id)
    print(f"已在 {root} 新建 MCMtools 项目")
    print(f"  项目 ID : {store.layout.load_config().project_id}")
    print("  下一步  : mcm status")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = Store.open(_default_root(args))
    cfg = store.layout.load_config()
    math_content = store.math.load()
    params = store.params.load()
    exps = store.list_experiments()
    atoms = store.load_atoms()
    figs = store.list_figures()
    tabs = store.list_tables()
    paper = store.load_paper()
    reg = _registry()

    print(f"项目         : {cfg.project_id}")
    print(f"阶段         : {cfg.phase.value}    模式: {cfg.mode.value}")
    print(f"已锁定题目   : {cfg.locked_problem_id or '（无）'}")
    print()
    print(f"数学内容     : 符号 {len(math_content.symbols)} · "
          f"公式 {len(math_content.equations)} · 假设 {len(math_content.assumptions)}")
    print(f"参数         : {len(params.parameters)}"
          + (f"（{len(params.unresolved())} 个未解析）"
             if params.unresolved() else ""))
    print(f"实验         : {len(exps)}")
    print(f"结果原子     : {len(atoms)}")
    print(f"图           : {len(figs)}")
    print(f"表           : {len(tabs)}")
    print(f"章节         : 已启用 {len(paper.enabled_sections())} 个")
    print(f"模板         : 已注册 {len(reg)} 个")
    if paper.build.page_count is not None:
        remaining = paper.latex.page_limit - paper.build.page_count
        print(
            f"Pages        : {paper.build.page_count}/{paper.latex.page_limit} "
            f"({remaining} remaining)"
        )
    return 0


def cmd_template_list(args: argparse.Namespace) -> int:
    reg = _registry()
    query = getattr(args, "q", None)

    if query:
        # 模板到 70 多个后，列表本身就不够用了。搜索支持中文：
        # 用户写"分布"，映射表把它变成 histogram。
        hits = reg.suggest(query, kind=args.kind, limit=None)
        if not hits:
            print(f"没有匹配「{query}」的模板。", file=sys.stderr)
            print("试试更宽的说法，或 `mcm template list` 看全部。", file=sys.stderr)
            return 1
        print(f"\n匹配「{query}」的模板（{len(hits)}）")
        rows = [[t.template_id, reg.headline(t)[:56]] for t in hits]
        print(_fmt_table(["template_id", "用途"], rows))
        return 0

    kinds = [args.kind] if args.kind else list(TEMPLATE_KINDS)
    for kind in kinds:
        items = reg.by_kind(kind)
        print(f"\n{kind.upper()} ({len(items)})")
        # 显示用途而不是 observed_in：用户挑模板时想知道"这图干什么用"，
        # 语料出现率是佐证，放在 `template show` 里看。
        rows = [[t.template_id, reg.headline(t)[:62]] for t in items]
        print(_fmt_table(["template_id", "用途"], rows))
    print("\n提示：`mcm template list -q 关键词` 可按中文搜索；"
          "`mcm template show <id>` 看完整说明。")
    return 0


def cmd_template_show(args: argparse.Namespace) -> int:
    reg = _registry()
    t = reg.get(args.template_id)
    if t is None:
        print(f"没有这个模板：{args.template_id}", file=sys.stderr)
        candidates = [i for i in reg.ids() if args.template_id.lower() in i.lower()]
        if candidates:
            print("你是不是想找：", "、".join(candidates), file=sys.stderr)
        return 1
    print(f"{t.template_id}  (kind={t.kind}, v{t.version})")
    if t.description:
        print(f"\n{t.description}")
    if t.purpose:
        print(f"\n用途：{t.purpose}")
    if t.observed_in:
        print(f"语料观测：{t.observed_in}")
    if t.requires.required_inputs or t.requires.required_fields:
        req = t.requires.required_inputs + t.requires.required_fields
        print(f"依赖：{', '.join(req)}")
    if t.inputs:
        print("\n输入：")
        for i in t.inputs:
            opt = " (optional)" if i.optional else ""
            print(f"  - {i.name}: {i.type} [{i.role or '-'}]{opt}")
    if t.caption_template:
        print(f"\n图注模板：{t.caption_template}")
    if t.defaults:
        print("\n默认值：")
        print(json.dumps(t.defaults, indent=2, ensure_ascii=False, default=str))
    if t.evidence:
        print("\n语料证据：")
        for e in t.evidence:
            print(f"  * {e}")
    return 0


def cmd_math_show(args: argparse.Namespace) -> int:
    """看符号表、公式、假设。"""
    store = Store.open(_default_root(args))
    content = store.math.load()

    if args.json:
        print(content.model_dump_json(indent=2, by_alias=True))
        return 0

    print(f"符号表   : {len(content.symbols)} 个")
    print(f"公式     : {len(content.equations)} 个"
          f"（已编号 {len(content.numbered_equations())} 个）")
    print(f"假设     : {len(content.assumptions)} 条")

    dupes = content.duplicate_glyphs()
    if dupes:
        print(f"\n⚠ 符号重复定义：{', '.join(dupes)} —— 同一符号含义不同会让读者误解。")
    dup_eq = content.duplicate_equation_numbers()
    if dup_eq:
        print(f"⚠ 公式编号重复：{', '.join(dup_eq)} —— 编号是全文计数器，必须唯一。")

    if content.symbols:
        print("\n符号：")
        rows = [[x.glyph, x.role.value, x.meaning[:40], x.unit or "/"]
                for x in content.symbols[:20]]
        print(_fmt_table(["符号", "role", "含义", "单位"], rows))
        if len(content.symbols) > 20:
            print(f"  ...（另有 {len(content.symbols) - 20} 个）")

    if content.assumptions:
        print("\n假设：")
        for a in content.assumptions[:10]:
            label = f"[{a.label}] " if a.label else ""
            print(f"  {a.id}  {label}{a.text[:60]}")
    return 0


def cmd_param_list(args: argparse.Namespace) -> int:
    """列出参数及其来源。"""
    store = Store.open(_default_root(args))
    ps = store.params.load()
    if args.json:
        print(ps.model_dump_json(indent=2, by_alias=True))
        return 0

    if not ps.parameters:
        print("还没有登记参数。参数区在 params/parameters.yaml，可直接编辑。")
        return 0

    rows = []
    for p in ps.parameters:
        value = "-" if p.value is None else str(p.value)
        # Parameter 没有 description 字段；来源引用更能说明"这个数从哪来"。
        note = p.source_ref or (f"由 {p.fitted_by} 拟合" if p.fitted_by else "")
        rows.append([p.name, value, p.unit or "/", p.source.value, note[:30]])
    print(_fmt_table(["参数", "取值", "单位", "来源", "说明"], rows))

    unresolved = ps.unresolved()
    if unresolved:
        print(f"\n⚠ {len(unresolved)} 个参数还没确定取值："
              f"{', '.join(p.name for p in unresolved[:8])}")
    unknown = [p for p in ps.parameters if p.source.value == "unknown"]
    if unknown:
        print(f"⚠ {len(unknown)} 个参数没有标注来源："
              f"{', '.join(p.name for p in unknown[:8])}")
        print("  应标明 literature / dataset / fitted / assumed。")
    return 0


def cmd_exp_list(args: argparse.Namespace) -> int:
    store = Store.open(_default_root(args))
    rows = []
    for e in store.list_experiments():
        varied = ", ".join(v.name for v in e.varied) or "-"
        rows.append(
            [e.id, e.kind.value, e.model_id or "-", varied[:28], e.status.value,
             str(e.n_runs or "-"), str(len(e.result_atom_ids))]
        )
    print(_fmt_table(["id", "kind", "model", "varied", "status", "runs", "atoms"], rows))
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    """列出运行归档：每次运行一行，附产出文件与代码指纹。"""
    store = Store.open(_default_root(args))
    rs = RunStore(store.root)
    runs = rs.list_runs(getattr(args, "experiment_id", None))
    if not runs:
        print("还没有运行记录。在「实验」页或 `mcm exp run <EXP-ID>` 跑一次即可。")
        return 0

    if args.json:
        print(json.dumps(runs, ensure_ascii=False, indent=2, default=str))
        return 0

    rows = []
    for r in runs:
        params = ", ".join(
            f"{k}={v}" for k, v in (r.get("resolved_parameters") or {}).items()
        ) or "-"
        arts = r.get("artifacts") or []
        fp = (r.get("script") or {}).get("sha256") or ""
        rows.append([
            r["run_id"],
            r.get("status", "-"),
            params[:34],
            str(r.get("atom_count", "-")),
            f"{r.get('duration_seconds', '-')}s",
            str(len(arts)) if arts else "无产出",
            fp[:8] or "-",
        ])
    print(_fmt_table(
        ["运行号", "状态", "参数", "原子", "耗时", "产出", "代码指纹"], rows
    ))

    # 产物明细单独列，因为文件名通常很长，塞进表格会挤变形。
    for r in runs:
        for a in (r.get("artifacts") or []):
            print(f"  {r['run_id']}  {a}")

    stale = rs.staleness(store.root)
    if stale:
        print()
        print(f"注意：有 {len(stale)} 个实验的结果来自旧代码 ——")
        for item in stale:
            print(f"  {item['experiment_id']}：{item['message']}")
    return 0


def cmd_exp_show(args: argparse.Namespace) -> int:
    store = Store.open(_default_root(args))
    try:
        e = store.load_experiment(args.exp_id)
    except FileNotFoundError:
        print(f"No such experiment: {args.exp_id}", file=sys.stderr)
        return 1
    if args.json:
        print(e.model_dump_json(indent=2, by_alias=True))
        return 0
    print(f"{e.id}  ({e.kind.value}, {e.status.value})")
    print(f"  model={e.model_id or '-'}  dataset={e.dataset_id or '-'}")
    if e.motivation:
        print(f"  motivation: {e.motivation}")
    if e.varied:
        print("  Varied:")
        for v in e.varied:
            vals = v.values or (v.range or [])
            print(f"    {v.name} = {vals}{' step ' + str(v.step) if v.step else ''}")
    if e.held_fixed:
        print(f"  Held fixed: {', '.join(e.held_fixed)}")
    if e.n_runs:
        print(f"  Runs: {e.n_runs}  aggregation: {e.aggregation or '-'}")
    print(f"  Trials implied: {e.n_trials() if hasattr(e, 'n_trials') else '-'}")
    if e.failure_reason:
        print(f"  Failure/rejection reason: {e.failure_reason}")
    if e.metrics:
        print("  Metrics:")
        for m in e.metrics:
            print(f"    {m.name:12s} = {m.value}  ({m.direction.value})")
    return 0


def cmd_result_list(args: argparse.Namespace) -> int:
    store = Store.open(_default_root(args))
    atoms = store.load_atoms()
    rows = [
        [a.atom_id, a.name[:24], a.rendered()[:16], a.unit or "-",
         (a.condition or "-")[:20], a.experiment_id or "-"]
        for a in atoms
    ]
    print(_fmt_table(["atom_id", "name", "value", "unit", "condition", "experiment"], rows))
    return 0


# Warnings that --strict promotes to errors, and why each one earns it.
#
# These are not "quality" warnings -- they are cases where the document makes a
# claim the toolchain can prove is not backed by the current numbers, or where
# COMAP compliance itself is at stake. Everything else (an uncited table, an
# assumption without justification, an unused page of budget) stays a warning,
# because a gate that blocks on taste gets disabled and then blocks nothing.
STRICT_CODES = {
    "FIG_STALE",            # a figure no longer matches the results it shows
    "TAB_STALE",            # same, tabular
    "ARTIFACT_FILE_MISSING",  # the PDF would contain a placeholder box
    "NUMERIC_UNBOUND",      # prose states a number with no ResultAtom behind it
    "ARTIFACT_NOT_CITED",   # 100% of references are cited; only 37% of figures are
    "PARAMETER_NO_PROVENANCE",  # an unsourced number is an invented number
    "SYMBOL_REDEFINED",     # the same glyph means two things
}


def cmd_validate(args: argparse.Namespace) -> int:
    store = Store.open(_default_root(args))
    reg = _registry()
    report = audit_project(store, reg)

    strict_hits = []
    if args.strict:
        strict_hits = [f for f in report.warnings
                       if getattr(f, "code", "") in STRICT_CODES]

    if args.json:
        verdict = "not_ready" if (not report.ok() or strict_hits) else report.verdict().value
        print(json.dumps(
            {
                "verdict": verdict,
                "strict": bool(args.strict),
                "promoted": [getattr(f, "code", "") for f in strict_hits],
                "findings": report.as_dicts(),
            },
            indent=2, ensure_ascii=False,
        ))
        return 0 if (report.ok() and not strict_hits) else 1

    if report.errors:
        print(f"ERRORS ({len(report.errors)})")
        for f in report.errors:
            print(f"  {f}")
        print()
    if report.warnings:
        print(f"WARNINGS ({len(report.warnings)})")
        for f in report.warnings:
            print(f"  {f}")
        print()
    if args.verbose and report.infos:
        print(f"提示 ({len(report.infos)})")
        for f in report.infos:
            print(f"  {f}")
        print()
    if strict_hits:
        print(f"STRICT 拦截 ({len(strict_hits)}) —— 开启 --strict 时这些会阻止提交")
        for f in strict_hits:
            print(f"  {f}")
        print()

    print(report.summary_line())
    if args.strict and strict_hits and report.ok():
        print(
            f"  -> 请勿提交：有 {len(strict_hits)} 条阻塞性警告。"
            "去掉 --strict 可以把它们只看作警告。"
        )
    return 0 if (report.ok() and not strict_hits) else 1






def cmd_deploy(args: argparse.Namespace) -> int:
    """部署自检：确认这个目录拷到别的机器上能用。"""
    from .deploy import format_report, inspect

    rep = inspect()
    print(format_report(rep))
    return 0 if rep.ok() else 1


def cmd_report(args: argparse.Namespace) -> int:
    """生成诊断报告。

    报 bug 时最费时间的不是修，是**问清楚现场**：哪一版、什么系统、
    装了什么、模板有几个、报什么错。这份报告把这些一次性收集齐，
    并且**不包含用户的数据内容** —— 只报告结构和计数，不报告论文正文。
    """
    import platform

    from . import version_string
    from .deploy import inspect
    from .doctor import diagnose

    lines: List[str] = []
    add = lines.append

    add("=" * 66)
    add(f"MCMtools 诊断报告  {version_string()}")
    add("=" * 66)
    add("")
    add("## 运行环境")
    add(f"  版本      : {version_string()}")
    add(f"  纯版本    : {version_string(with_rev=False)}")
    add(f"  Python    : {sys.version.split()[0]}")
    add(f"  解释器    : {sys.executable}")
    add(f"  系统      : {platform.platform()}")
    add(f"  处理器    : {platform.machine()}")
    add("")

    add("## 依赖")
    d = diagnose()
    for c in d.checks:
        add(f"  {c.line()}")
    add("")

    add("## 目录完整性")
    rep = inspect()
    for f in rep.findings:
        add(f"  {f.line()}")
    add(f"  结论: {'可以部署' if rep.ok() else '有问题'}")
    add("")

    if args.project:
        add(f"## 项目：{args.project}")
        try:
            from .store import Store

            st = Store(Path(args.project).expanduser())
            paper = st.load_paper()
            add(f"  阶段      : {st.layout.load_config().phase}")
            add(f"  章节      : {len(paper.sections)}")
            add(f"  数据集    : {len(st.list_datasets())}")
            add(f"  图        : {len(st.list_figures())}")
            add(f"  表        : {len(st.list_tables())}")
            add(f"  实验      : {len(st.list_experiments())}")
            add(f"  参数      : {len(st.params.load().parameters)}")
            add(f"  结果原子  : {len(st.load_atoms())}")
            add(f"  文献      : {len(st.load_references())}")
            # 只报计数，不报内容 —— 用户的论文正文不该进 bug 报告
            add("  （只报告数量，不含正文内容）")
        except Exception as exc:  # noqa: BLE001
            add(f"  读取失败: {type(exc).__name__}: {exc}")
        add("")

    add("## 已知的坑（先自查这几条）")
    for line in [
        "--strict 只把 7 类问题升级为错误，其余仍是提示",
        "模板加载失败会让启动失败（load_strict），不会静默少一半",
        "中文字体缺失时图上会出现豆腐块，跑 mcm doctor --deploy 查",
        "没有 pdflatex 时审计和出图照常，只是不能编译 PDF",
    ]:
        add(f"  - {line}")

    text = "\n".join(lines)
    if args.out:
        Path(args.out).expanduser().write_text(text, encoding="utf-8")
        print(f"报告已写入 {args.out}")
    else:
        print(text)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check the environment, optionally installing what is missing."""
    from .doctor import diagnose, install_missing, recheck

    if getattr(args, "deploy", False):
        # `doctor --deploy` 是 `deploy` 的别名 —— 用户想的是"检查能不能用"，
        # 两个入口通向同一件事，不必让他记哪个是哪个。
        return cmd_deploy(args)

    d = diagnose()
    for c in d.checks:
        print(c.line())
    print()
    print(d.summary())

    if args.fix and (d.missing_required or d.missing_optional):
        print()
        ok, log = install_missing(d, include_optional=True, dry_run=args.dry_run)
        for line in log:
            print("  " + line)
        if not ok:
            return 1
        if not args.dry_run:
            d = recheck()
            print()
            print(d.summary())

    if not d.tex_ok():
        print()
        print("pdflatex not found: auditing works, PDF compilation does not.")
    return 0 if d.ready else 1


def cmd_start(args: argparse.Namespace) -> int:
    """Check, serve and open the panel in one step."""
    from .launcher import launch

    return launch(
        project=Path(args.dir).expanduser().resolve() if args.dir else Path.cwd(),
        port=args.port,
        open_browser=not args.no_browser,
        auto_install=not args.no_install,
    )


def cmd_mode(args: argparse.Namespace) -> int:
    """Show or switch the run mode, with real enforcement."""
    from . import mode as mode_mod
    from .schemas import RunMode

    store = Store.open(_default_root(args))
    cfg = store.layout.load_config()

    if args.set is not None:
        target = RunMode.COMPETITION if args.set == "competition" else RunMode.DEVELOPMENT
        previous = cfg.mode
        cfg.mode = target
        store.layout.save_config(cfg)
        print(f"mode: {previous.value} -> {target.value}")
        if target == RunMode.COMPETITION:
            print("  Network access is blocked while competition mode is active.")
            print("  AI-assisted commands are refused.")
        return 0

    status = mode_mod.mode_status()
    print(f"project mode : {cfg.mode.value}")
    print(f"process mode : {status['mode']}")
    print(f"net guard    : {'installed' if status['network_guard_installed'] else 'not installed'}")
    if status["blocked_outbound"]:
        print(f"blocked      : {len(status['blocked_outbound'])} outbound attempt(s)")
        for v in status["blocked_outbound"][-5:]:
            print(f"    {v['at']}  {v['detail']}")
    return 0


def cmd_exp_run(args: argparse.Namespace) -> int:
    """Execute an experiment protocol and record its results."""
    store = Store.open(_default_root(args))
    runner = ExperimentRunner(store, seed=args.seed)
    outcome = runner.run(args.exp_id, dry_run=args.dry_run)

    for line in outcome.messages:
        print(line)

    if not outcome.ok:
        print(f"\nFAILED: {outcome.error}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"\n{len(outcome.messages) - 1} trial(s); nothing executed.")
        return 0

    print()
    print(outcome.summary())
    if outcome.stale and outcome.stale.stale_figures:
        print(f"  stale figures: {', '.join(outcome.stale.stale_figures)}")
    if outcome.stale and outcome.stale.stale_tables:
        print(f"  stale tables : {', '.join(outcome.stale.stale_tables)}")
    if outcome.changed:
        print(f"  changed atoms: {', '.join(outcome.changed)}")
    return 0


def cmd_exp_trials(args: argparse.Namespace) -> int:
    """Show the concrete trials a protocol expands to, without executing."""
    from .runner import condition_string, expand_trials

    store = Store.open(_default_root(args))
    exp = store.load_experiment(args.exp_id)
    trials = expand_trials(exp, store.params.load().parameters)
    names = [v.name for v in exp.varied]
    print(f"{exp.id}  ({exp.kind.value})")
    print(f"  {len(trials)} trial(s)")
    if exp.held_fixed:
        print(f"  held fixed: {', '.join(exp.held_fixed)}")
    print()
    for i, t in enumerate(trials, start=1):
        print(f"  {i:3d}. {condition_string(t, names, exp.held_fixed)}")
    return 0


def cmd_result_show(args: argparse.Namespace) -> int:
    """Show one atom in full, including its condition and renderings."""
    store = Store.open(_default_root(args))
    for a in store.load_atoms():
        if a.atom_id == args.atom_id:
            if args.json:
                print(a.model_dump_json(indent=2, by_alias=True))
                return 0
            print(f"{a.atom_id}")
            print(f"  name      : {a.name}")
            print(f"  value     : {a.rendered()}  {a.unit or ''}")
            print(f"  format    : {a.format}")
            print(f"  condition : {a.condition or '-'}")
            if a.metric_def:
                print(f"  definition: {a.metric_def}")
            if a.renderings:
                print(f"  renderings: {a.renderings}")
            print(f"  run       : {a.run_id or '-'}")
            print(f"  experiment: {a.experiment_id or '-'}")
            return 0
    print(f"No such atom: {args.atom_id}", file=sys.stderr)
    return 1


def cmd_artifact_stale(args: argparse.Namespace) -> int:
    """List artifacts invalidated by a result change."""
    store = Store.open(_default_root(args))
    figs, tabs = stale_artifacts(store)
    if not figs and not tabs:
        print("No stale artifacts.")
        return 0
    for f in figs:
        print(f"  STALE figure {f.id}  bound to {[b.atom_id for b in f.bindings]}")
    for t in tabs:
        print(f"  STALE table  {t.id}  bound to {t.bound_atom_ids()}")
    print(f"\n{len(figs) + len(tabs)} stale artifact(s).")
    return 0



def cmd_artifact_regenerate(args: argparse.Namespace) -> int:
    """Regenerate stale figures from their current atom values."""
    store = Store.open(_default_root(args))
    gen = FigureGenerator(store)
    ids = args.ids or None
    done = gen.regenerate(figure_ids=ids, only_stale=not args.all)

    if done:
        print(f"Regenerated {len(done)} figure(s): {', '.join(done)}")
    else:
        print("Nothing to regenerate.")
    for w in gen.warnings:
        print(f"  WARNING: {w}")

    figs, tabs = stale_artifacts(store)
    if figs or tabs:
        print(f"\nStill stale: {len(figs) + len(tabs)}")
        return 1
    return 0


def cmd_artifact_list(args: argparse.Namespace) -> int:
    """List every artifact with its status and bindings."""
    store = Store.open(_default_root(args))
    atoms = {a.atom_id for a in store.load_atoms()}
    rows = []
    for f in store.list_figures():
        n = len(f.bindings)
        rows.append([f.id, "figure", f.status.value, f.template_id, str(n), f.file or "-"])
    for t in store.list_tables():
        b = t.bound_atom_ids()
        rows.append([t.id, "table", t.status.value, t.template_id, str(len(b)), t.file or "-"])
    print(_fmt_table(["id", "kind", "status", "template", "bound", "file"], rows))
    return 0




def cmd_serve(args: argparse.Namespace) -> int:
    """Run the local API server."""
    try:
        from .api import serve
    except ImportError:
        print(
            "The API layer needs FastAPI and uvicorn:\n"
            "  python3 -m pip install --user fastapi uvicorn",
            file=sys.stderr,
        )
        return 1

    root = _default_root(args)
    if not (root / "project.yaml").exists():
        print(f"not an MCMtools project: {root}", file=sys.stderr)
        return 1

    print(f"MCMtools API on http://{args.host}:{args.port}")
    print(f"  project: {root}")
    print(f"  docs:    http://{args.host}:{args.port}/docs")
    try:
        serve(root, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    """Print the Overview payload: phase, counts, steps, blockers."""
    from .state import build_overview

    store = Store.open(_default_root(args))
    ov = build_overview(store)

    if args.json:
        import json

        print(json.dumps(ov.to_dict(), indent=2, default=str))
        return 0

    prob = ov.problem
    title = prob.get("id") or "no problem locked"
    team = f" · Team {prob['team_number']}" if prob.get("team_number") else ""
    print(f"{ov.phase.upper()} · {title}{team}")
    print("-" * 58)
    mark = {"done": "\u2713", "partial": "\u25d0", "todo": "\u25cb"}
    for st in ov.steps:
        print(f"  {mark.get(st['status'], '?')} {st['label']:<20s} {st['detail']}")
    print("-" * 58)
    if ov.blockers:
        print(f"{len(ov.errors)} 个错误，{len(ov.warnings)} 个警告")
        for b in ov.blockers[:10]:
            sym = "\u2717" if b.severity == "error" else "\u26a0"
            print(f"  {sym} {b.code}: {b.message}")
            print(f"      -> {b.action}")
    else:
        print("没有待处理问题。")
    return 0


def cmd_paper_build(args: argparse.Namespace) -> int:
    """Compile the paper to PDF and report the page budget."""
    store = Store.open(_default_root(args))
    compiler = PaperCompiler(store, engine=args.engine)
    result = compiler.build(clean=not args.no_clean)

    for line in result.messages:
        print(line)

    if result.warnings:
        print()
        for w in result.warnings:
            print(f"  WARNING: {w}")
    if result.findings:
        print()
        for f in result.findings:
            print(f"  {f['severity'].upper()} {f['code']}: {f['message']}")

    if not result.ok:
        if result.log_tail:
            print()
            print("--- LaTeX log tail ---")
            print(result.log_tail)
        print()
        print("BUILD FAILED")
        return 1

    print()
    print(f"PDF: {result.pdf_path} - {result.page_count} pages")
    if result.pages_remaining is not None and result.pages_remaining < 0:
        print(
            f"OVER BUDGET by {-result.pages_remaining} page(s). "
            "Move content to the appendix."
        )
        return 1
    return 0


def cmd_paper_engine(args: argparse.Namespace) -> int:
    """Report which TeX engines are available."""
    for name in ("pdflatex", "xelatex", "latexmk"):
        path = find_engine(name)
        print(f"  {name:10s} {'OK  ' + path if path else 'NOT FOUND'}")
    return 0


def cmd_paper_scaffold(args: argparse.Namespace) -> int:
    """按模板把填空骨架补进论文。

    和 `paper spine` 的区别：spine 只管**有哪几节、什么顺序**（会清空重建），
    scaffold 还会给空章节填上写作骨架，而且**绝不覆盖已经写好的正文**。
    日常用的是 scaffold；spine 是搭空架子用的。
    """
    from . import paperkit

    store = Store.open(_default_root(args))
    paper = store.load_paper()
    before = len(paper.sections)
    paper, report = paperkit.scaffold(
        paper, fill_existing=args.force,
        spine_kind=getattr(args, "spine", "general"),
    )
    store.save_paper(paper)
    if report.get("spine_kind") and report["spine_kind"] != "general":
        print(f"使用题型骨架：{report['spine_kind']}")

    if report["added"]:
        print(f"新增章节 {len(report['added'])} 节：")
        for title in report["added"]:
            print(f"  + {title}")
    if report["filled"]:
        print(f"填入骨架 {len(report['filled'])} 节：")
        for title in report["filled"]:
            print(f"  ~ {title}")
    if not report["added"] and not report["filled"]:
        print(f"无需改动（{before} 节都已有内容）。")

    print()
    print(f"共 {report['total']} 节 · 待填占位符 {report['pending_placeholders']} 个 "
          f"· 建议篇幅 {report['budget_pages']:.1f} 页")
    if report["pending_placeholders"]:
        print("占位符是 {{...}} 形式，填完审计就不会再报 SUMMARY_PLACEHOLDER。")
    print()
    print("各节篇幅建议：")
    for row in paperkit.outline(paper):
        if not row["enabled"]:
            continue
        budget = f"{row['budget_pages']:.1f} 页" if row["budget_pages"] else "  —  "
        pend = f"{len(row['placeholders'])} 个待填" if row["placeholders"] else ""
        print(f"  {row['title']:34} {budget:>6}  {row['words']:>5} 词  {pend}")
    return 0


def cmd_paper_spine(args: argparse.Namespace) -> int:
    """Materialise the section spine from the paper.section_spine template."""
    from .schemas import PaperSection

    store = Store.open(_default_root(args))
    reg = _registry()
    t = reg.get("paper.section_spine")
    if t is None:
        print("paper.section_spine template is missing", file=sys.stderr)
        return 1

    paper = store.load_paper()
    if paper.sections and not args.force:
        print(
            f"Paper already has {len(paper.sections)} section(s). "
            "Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    paper.sections = []
    for i, entry in enumerate(t.defaults.get("spine", [])):
        paper.sections.append(
            PaperSection(
                id=f"SEC-{entry['order']:03d}",
                kind=SectionKind(entry["kind"]),
                title=entry["title"],
                order=entry["order"],
                enabled=bool(entry.get("enabled", True)),
                generated=bool(entry.get("generated", False)),
            )
        )
    store.save_paper(paper)
    print(f"Wrote {len(paper.sections)} sections from the spine template:")
    for s in paper.ordered_sections():
        flag = "" if s.enabled else "  (disabled)"
        auto = "  [auto]" if s.generated else ""
        print(f"  {s.order:3d}  {s.kind.value:22s} {s.title}{auto}{flag}")
    return 0


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcm",
        description="MCMtools —— 本地、可复现、可审计的数学建模竞赛工具链。",
    )
    p.add_argument("--dir", default=".", help="项目目录（默认：当前目录）。")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="新建项目。")
    sp.add_argument("--project-id", default="mcm-project")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("status", help="查看项目状态摘要。")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("template", help="查看模板注册表。")
    tsub = sp.add_subparsers(dest="template_command", required=True)
    tl = tsub.add_parser("list", help="List templates.")
    tl.add_argument("--kind", choices=list(TEMPLATE_KINDS))
    tl.add_argument("-q", "--query", dest="q", default=None,
                    help="按关键词搜索（支持中文，如 -q 分布）。")
    tl.set_defaults(func=cmd_template_list)
    ts = tsub.add_parser("show", help="Show one template in full.")
    ts.add_argument("template_id")
    ts.set_defaults(func=cmd_template_show)

    sp = sub.add_parser("math", help="查看符号表、公式、假设。")
    ms = sp.add_subparsers(dest="math_command", required=True)
    msh = ms.add_parser("show")
    msh.add_argument("--json", action="store_true")
    msh.set_defaults(func=cmd_math_show)

    sp = sub.add_parser("param", help="查看参数及其来源。")
    psub = sp.add_subparsers(dest="param_command", required=True)
    pl = psub.add_parser("list")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_param_list)

    sp = sub.add_parser("exp", help="查看实验。")
    esub = sp.add_subparsers(dest="exp_command", required=True)
    el = esub.add_parser("list")
    el.set_defaults(func=cmd_exp_list)
    rn = esub.add_parser("runs", help="查看运行归档。")
    rn.add_argument("experiment_id", nargs="?")
    rn.add_argument("--json", action="store_true")
    rn.set_defaults(func=cmd_runs)
    es = esub.add_parser("show")
    es.add_argument("exp_id")
    es.add_argument("--json", action="store_true")
    es.set_defaults(func=cmd_exp_show)

    er = esub.add_parser("run", help="Execute an experiment protocol.")
    er.add_argument("exp_id")
    er.add_argument("--dry-run", action="store_true",
                    help="Show the expanded trials without executing.")
    er.add_argument("--seed", type=int, default=None)
    er.set_defaults(func=cmd_exp_run)

    et = esub.add_parser("trials", help="Show the trials a protocol expands to.")
    et.add_argument("exp_id")
    et.set_defaults(func=cmd_exp_trials)

    sp = sub.add_parser("result", help="查看结果原子。")
    rsub = sp.add_subparsers(dest="result_command", required=True)
    rl = rsub.add_parser("list")
    rl.set_defaults(func=cmd_result_list)

    rs = rsub.add_parser("show", help="Show one result atom in full.")
    rs.add_argument("atom_id")
    rs.add_argument("--json", action="store_true")
    rs.set_defaults(func=cmd_result_show)

    st = sub.add_parser("start", help="一步完成：检查环境、启动服务、打开面板。")
    st.add_argument("--port", type=int, default=None)
    st.add_argument("--no-browser", action="store_true")
    st.add_argument("--no-install", action="store_true",
                    help="只报告缺失依赖，不安装。")
    st.set_defaults(func=cmd_start)

    dr = sub.add_parser("doctor", help="检查运行环境。")
    dr.add_argument("--deploy", action="store_true",
                    help="检查这个目录能不能直接拷给别人用（部署自检）。")
    dr.set_defaults(func=cmd_doctor)

    dp = sub.add_parser("deploy", help="部署自检：确认目录可以直接使用。")
    dp.set_defaults(func=cmd_deploy)

    rp = sub.add_parser("report", help="生成一份诊断报告（报 bug 时附上）。")
    rp.add_argument("--out", default=None, help="写到文件，默认打印到屏幕。")
    rp.add_argument("--project", default=None, help="一并报告某个项目的状态。")
    rp.set_defaults(func=cmd_report)
    dr.add_argument("--fix", action="store_true", help="Install what is missing.")
    dr.add_argument("--dry-run", action="store_true",
                    help="配合 --fix：只打印命令，不实际执行。")
    dr.set_defaults(func=cmd_doctor)

    md = sub.add_parser("mode", help="查看或切换运行模式。")
    md.add_argument("--set", choices=["development", "competition"], default=None)
    md.set_defaults(func=cmd_mode)

    sv = sub.add_parser("serve", help="启动本地 API 服务。")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8420)
    sv.set_defaults(func=cmd_serve)

    ovp = sub.add_parser("overview", help="显示项目状态与待处理问题。")
    ovp.add_argument("--json", action="store_true")
    ovp.set_defaults(func=cmd_overview)

    sp = sub.add_parser("artifact", help="查看生成的图表。")
    asub = sp.add_subparsers(dest="artifact_command", required=True)
    ast = asub.add_parser("stale", help="List artifacts invalidated by a result change.")
    ast.set_defaults(func=cmd_artifact_stale)

    al = asub.add_parser("list", help="List artifacts with status and bindings.")
    al.set_defaults(func=cmd_artifact_list)

    ar = asub.add_parser("regenerate", help="Regenerate stale figures from current atoms.")
    ar.add_argument("ids", nargs="*", help="Specific figure ids (default: all stale).")
    ar.add_argument("--all", action="store_true", help="Regenerate every figure.")
    ar.set_defaults(func=cmd_artifact_regenerate)

    sp = sub.add_parser("validate", help="审计项目。")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("-v", "--verbose", action="store_true", help="连提示级发现一起显示。")
    sp.add_argument(
        "--strict", action="store_true",
        help="Treat submission-blocking warnings (stale artifacts, uncited "
             "figures, unbound numbers) as errors. Use as a pre-submission gate.",
    )
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("paper", help="论文相关操作。")
    psub = sp.add_subparsers(dest="paper_command", required=True)
    ps = psub.add_parser("spine", help="Write the section spine.")
    ps.add_argument("--force", action="store_true")
    ps.set_defaults(func=cmd_paper_spine)

    psc = psub.add_parser("scaffold", help="补填空骨架（不覆盖已写正文）。")
    psc.add_argument("--spine", default="general",
                     choices=["general", "data_driven", "physical",
                              "policy", "evaluation"],
                     help="题型骨架：general 通用 / data_driven 数据类 / "
                          "physical 机理类 / policy 政策类 / evaluation 评价类。")
    psc.add_argument("--force", action="store_true",
                     help="连已有正文也一起重置（默认不动）。")
    psc.set_defaults(func=cmd_paper_scaffold)

    pb = psub.add_parser("build", help="Compile the paper to PDF.")
    pb.add_argument("--engine", default="pdflatex",
                    choices=["pdflatex", "xelatex", "latexmk"])
    pb.add_argument("--no-clean", action="store_true",
                    help="Keep the existing build directory instead of wiping it.")
    pb.set_defaults(func=cmd_paper_build)

    pe = psub.add_parser("engine", help="Show available TeX engines.")
    pe.set_defaults(func=cmd_paper_engine)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    # 放在 parse_args 之前拦截：--version 不该要求一个合法子命令
    if argv is None:
        argv = sys.argv[1:]
    if "--version" in argv or "-V" in argv:
        from . import version_string
        print(f"MCMtools {version_string()}")
        return 0
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
