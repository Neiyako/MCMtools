"""Phase 3: the experiment runner — where results actually come from.

Phases 1 and 2 defined and consumed the result model; nothing produced it. This
module closes the loop:

    Experiment protocol  ->  execute  ->  Run record + ResultAtom records
                                     ->  mark dependent artifacts STALE

Three design rules, each grounded in a defect the corpus shows:

1. **A value is meaningless without its condition.** Every atom carries the
   resolved parameter set it was computed under. `P=0.02%@2030` and `P=8.25%@2039`
   are different results, not the same result twice.

2. **Runs are recorded even when they fail.** The best paper documents two
   rejected methods (KKT: "250 variables ... we have to give up"; plain PSO:
   "takes a very long time to converge"). A failed run keeps its stderr and its
   status so that argument stays reconstructable.

3. **Staleness is computed, not asserted.** An atom's *identity* is its
   (name, condition, value) triple. Re-running with identical inputs must NOT
   mark anything stale, or the warning becomes noise and gets ignored.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .runstore import RunStore, script_fingerprint
from .schemas import (
    ArtifactStatus,
    Experiment,
    ExperimentKind,
    ExperimentStatus,
    Figure,
    ResultAtom,
    Run,
    RunStatus,
    Table,
)
from .store import Store


# --------------------------------------------------------------------------
# Atom identity / change detection
# --------------------------------------------------------------------------


def atom_fingerprint(atom: ResultAtom) -> str:
    """A stable hash of everything that changes what the paper would print.

    Deliberately excludes ``run_id`` and ``experiment_id``: rerunning the same
    protocol must produce the same fingerprint, otherwise every rerun would
    falsely invalidate every bound artifact.
    """
    payload = {
        "name": atom.name,
        "value": atom.value,
        "unit": atom.unit,
        "format": atom.format,
        "condition": atom.condition,
        "renderings": dict(sorted(atom.renderings.items())),
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:16]


def changed_atoms(
    before: Sequence[ResultAtom], after: Sequence[ResultAtom]
) -> List[str]:
    """Atom ids whose printable content changed (added, removed, or altered)."""
    old = {a.atom_id: atom_fingerprint(a) for a in before}
    new = {a.atom_id: atom_fingerprint(a) for a in after}
    changed: List[str] = []
    for atom_id, fp in new.items():
        if old.get(atom_id) != fp:
            changed.append(atom_id)
    for atom_id in old:
        if atom_id not in new:
            changed.append(atom_id)
    return sorted(changed)


# --------------------------------------------------------------------------
# Staleness
# --------------------------------------------------------------------------


@dataclass
class StaleReport:
    """Which artifacts a set of changed atoms invalidates."""

    changed: List[str] = field(default_factory=list)
    stale_figures: List[str] = field(default_factory=list)
    stale_tables: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.stale_figures) + len(self.stale_tables)

    def summary(self) -> str:
        if not self.changed:
            return "no results changed; nothing is stale"
        if not self.total:
            return f"{len(self.changed)} result(s) changed; no bound artifacts"
        return (
            f"{len(self.changed)} result(s) changed -> "
            f"{len(self.stale_figures)} figure(s) and "
            f"{len(self.stale_tables)} table(s) marked stale"
        )


def mark_stale(store: Store, changed: Sequence[str]) -> StaleReport:
    """Mark every artifact bound to a changed atom as STALE and persist it."""
    report = StaleReport(changed=list(changed))
    if not changed:
        return report
    ids = set(changed)

    for fig in store.list_figures():
        if fig.is_stale_if(list(ids)):
            if fig.status != ArtifactStatus.STALE:
                fig.status = ArtifactStatus.STALE
                store.save_figure(fig)
            report.stale_figures.append(fig.id)

    for tab in store.list_tables():
        if ids & set(tab.bound_atom_ids()):
            if tab.status != ArtifactStatus.STALE:
                tab.status = ArtifactStatus.STALE
                store.save_table(tab)
            report.stale_tables.append(tab.id)

    return report


def stale_artifacts(store: Store) -> Tuple[List[Figure], List[Table]]:
    """Currently-stale artifacts, for a build gate or a UI badge."""
    figs = [f for f in store.list_figures() if f.status == ArtifactStatus.STALE]
    tabs = [t for t in store.list_tables() if t.status == ArtifactStatus.STALE]
    return figs, tabs


def clear_stale(store: Store, artifact_ids: Optional[Sequence[str]] = None) -> int:
    """Mark artifacts GENERATED after successful regeneration."""
    want = set(artifact_ids) if artifact_ids else None
    n = 0
    for fig in store.list_figures():
        if fig.status == ArtifactStatus.STALE and (want is None or fig.id in want):
            fig.status = ArtifactStatus.GENERATED
            fig.generated_at = _now()
            store.save_figure(fig)
            n += 1
    for tab in store.list_tables():
        if tab.status == ArtifactStatus.STALE and (want is None or tab.id in want):
            tab.status = ArtifactStatus.GENERATED
            tab.generated_at = _now()
            store.save_table(tab)
            n += 1
    return n


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Protocol expansion
# --------------------------------------------------------------------------


def resolve_held_values(
    experiment: Experiment, params: Sequence[Parameter]
) -> Dict[str, Any]:
    """查出协议里"固定不变"的那些参数的实际值。

    ``held_fixed: [gamma, lambda, phi]`` 是一串**名字**。不解出值的话，
    "保持不变"就只是一句无法核对的话，这次试验也就无法复现。

    值从项目级的参数区读（params/parameters.yaml）。这比原来从
    "所属模型"里读更贴近事实：参数是项目级的，不属于某个模型。
    """
    by_name = {p.name: p for p in params}
    out: Dict[str, Any] = {}
    for name in experiment.held_fixed:
        param = by_name.get(name)
        out[name] = param.value if param is not None else None
    return out


def expand_trials(
    experiment: Experiment, params: Optional[Sequence[Parameter]] = None
) -> List[Dict[str, Any]]:
    """Expand the declared protocol into concrete parameter sets.

    A protocol is a *declaration*: `beta in {0.10, 0.177, 0.25}` with
    `gamma, lambda, phi` held fixed at their fitted values. This turns that into
    the actual list of runs the executor must perform.

    Corpus grounding: "In each parameter analysis, we only varied that parameter
    while keeping the other parameters at their default values."
    """
    axes: List[Tuple[str, List[Any]]] = []
    for v in experiment.varied:
        if v.values:
            axes.append((v.name, list(v.values)))
        elif v.range and v.step and v.step > 0:
            lo, hi = float(v.range[0]), float(v.range[1])
            step = float(v.step)
            n = int(round((hi - lo) / step))
            axes.append((v.name, [lo + i * step for i in range(n + 1)]))
        elif v.range:
            axes.append((v.name, [float(v.range[0]), float(v.range[1])]))
        else:
            axes.append((v.name, [None]))

    fixed = (
        resolve_held_values(experiment, params)
        if params
        else {name: None for name in experiment.held_fixed}
    )

    trials: List[Dict[str, Any]] = []
    if not axes:
        trials.append(dict(fixed))
        return trials

    # Cartesian product, but keep the invariant explicit in every trial so the
    # condition string names what was held.
    def rec(i: int, acc: Dict[str, Any]) -> None:
        if i == len(axes):
            trials.append(dict(acc))
            return
        name, values = axes[i]
        for val in values:
            acc[name] = val
            rec(i + 1, acc)
        acc.pop(name, None)

    rec(0, dict(fixed))

    # The OAT invariant means one axis at a time; a grid sweep is a different kind.
    if (
        experiment.kind == ExperimentKind.SENSITIVITY_OAT
        and len(axes) > 1
    ):
        # Flatten to one-axis-at-a-time, holding the others at their first value.
        flat: List[Dict[str, Any]] = []
        base = {name: values[0] for name, values in axes}
        for name, values in axes:
            for val in values:
                trial = dict(base)
                trial[name] = val
                flat.append(trial)
        return flat

    return trials


def condition_string(
    trial: Dict[str, Any],
    varied_names: Sequence[str],
    held_names: Sequence[str],
) -> str:
    """Render a trial's parameter set as a compact, human-readable condition."""
    parts = [
        f"{k}={_fmt(trial.get(k))}" for k in varied_names if trial.get(k) is not None
    ]
    for k in held_names:
        v = trial.get(k)
        if v is not None:
            parts.append(f"{k}={_fmt(v)}(fixed)")
    return ", ".join(parts) if parts else "default"


def _fmt(value: Any) -> str:
    """Format a parameter for a condition string.

    The cutoff is 1e-2, not 1e-3, because fitted rate constants in these models
    are routinely ~1e-3 (lambda=1.04e-03, phi=1.14e-03). Plain decimals there
    are unreadable -- 0.00104 has three leading zeros that hide the significant
    digits -- whereas 1.04e-03 states them directly. Mid-range values like
    1.77e-02 stay decimal because 0.0177 reads better than 1.77e-02.
    """
    if isinstance(value, float) and value != 0:
        if abs(value) < 1e-2 or abs(value) >= 1e5:
            return f"{value:.2e}"
        return f"{value:g}"
    return str(value)


# --------------------------------------------------------------------------
# Executor protocol
# --------------------------------------------------------------------------


@dataclass
class TrialOutcome:
    """What a user-supplied experiment function returns for one trial."""

    atoms: List[Dict[str, Any]] = field(default_factory=list)
    metrics: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None


# A user function takes the resolved parameter dict and returns atoms.
ExperimentFn = Callable[[Dict[str, Any]], Any]


def _next_seq(runstore: RunStore, experiment_id: str) -> int:
    """本实验已用的最大序号。新的运行从它之后接着排。"""
    nxt = runstore.next_run_id(experiment_id)   # 形如 RUN-001-004
    tail = nxt.rsplit("-", 1)[-1]
    return (int(tail) - 1) if tail.isdigit() else 0


def _load_function(entrypoint: str, root: Path) -> ExperimentFn:
    """Import ``path.py:function`` relative to the project root."""
    spec_path, _, func_name = entrypoint.partition(":")
    path = (root / spec_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"experiment script not found: {path}")
    mod_name = f"mcm_exp_{hashlib.md5(str(path).encode()).hexdigest()[:8]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    fn = getattr(module, func_name or "run", None)
    if fn is None or not callable(fn):
        raise AttributeError(
            f"{path} has no callable '{func_name or 'run'}'"
        )
    return fn


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


@dataclass
class RunOutcome:
    """Result of running one Experiment."""

    experiment_id: str
    ok: bool = False
    runs: List[Run] = field(default_factory=list)
    atoms: List[ResultAtom] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    stale: Optional[StaleReport] = None
    messages: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def summary(self) -> str:
        if not self.ok:
            return f"experiment {self.experiment_id} FAILED: {self.error or 'see run log'}"
        line = (
            f"experiment {self.experiment_id}: {len(self.runs)} run(s), "
            f"{len(self.atoms)} result atom(s)"
        )
        if self.stale is not None:
            line += "\n  " + self.stale.summary()
        return line


class ExperimentRunner:
    """Executes an Experiment protocol and records what happened."""

    def __init__(self, store: Store, seed: Optional[int] = None) -> None:
        self.store = store
        self.seed = seed

    def run(self, experiment_id: str, dry_run: bool = False) -> RunOutcome:
        exp = self.store.load_experiment(experiment_id)
        outcome = RunOutcome(experiment_id=experiment_id)

        # In competition mode the network guard is active for the duration of
        # the run, so a library that phones home is caught here rather than
        # silently succeeding.
        from . import mode as mode_mod

        cfg_mode = getattr(self.store.layout.load_config(), "mode", None)
        in_competition = (
            getattr(cfg_mode, "value", cfg_mode) == "competition"
        )
        if in_competition and not mode_mod.network_guard_installed():
            mode_mod.install_network_guard()
            mode_mod.set_mode(mode_mod.RunMode.COMPETITION)
            outcome.messages.append(
                "competition mode: network access blocked for this run"
            )

        trials = expand_trials(exp, self.store.params.load().parameters)
        outcome.messages.append(f"protocol expands to {len(trials)} trial(s)")

        if dry_run:
            for i, t in enumerate(trials, start=1):
                cond = condition_string(
                    t,
                    [v.name for v in exp.varied],
                    exp.held_fixed,
                )
                outcome.messages.append(f"  trial {i}: {cond}")
            outcome.ok = True
            return outcome

        entrypoint = getattr(exp, "entrypoint", None)
        if not entrypoint:
            outcome.error = (
                "no entrypoint declared. Set `entrypoint: experiments/<exp>/run.py:run` "
                "on the Experiment record, or use --dry-run to inspect the protocol."
            )
            return outcome

        try:
            fn = _load_function(entrypoint, self.store.root)
        except (FileNotFoundError, ImportError, AttributeError) as exc:
            outcome.error = str(exc)
            return outcome

        before = self.store.load_atoms()
        atoms: List[ResultAtom] = []
        runs: List[Run] = []
        varied_names = [v.name for v in exp.varied]
        any_failure = False

        runstore = RunStore(self.store.root)
        entrypoint_rel = entrypoint.split(":")[0]
        fingerprint = script_fingerprint(self.store.root, entrypoint_rel)

        # 运行号在实验内**全局递增**，与 trial 序号无关。
        # 早先用 f"RUN-{exp}-{i:03d}"，重跑实验时编号会重复，新一轮产物
        # 直接倒进旧文件夹里（实测：跑三轮后每个文件夹里堆了 3 份产物）。
        # 归档要可信，编号就必须只增不复用。
        base_seq = _next_seq(runstore, experiment_id)

        for i, trial in enumerate(trials, start=1):
            run_id = f"RUN-{experiment_id.split('-')[-1]}-{base_seq + i:03d}"
            started = time.time()
            cond = condition_string(trial, varied_names, exp.held_fixed)
            status = RunStatus.SUCCESS
            error_text: Optional[str] = None
            produced: List[Dict[str, Any]] = []
            metrics: List[Dict[str, Any]] = []
            artifacts: List[str] = []

            # 运行前先建目录并写下已知信息：脚本崩溃也不会丢"这里跑过"这件事。
            runstore.begin(
                experiment_id, run_id,
                parameters={k: v for k, v in trial.items() if v is not None},
                script=fingerprint,
                trial_index=i,
                condition=cond,
                random_seed=self.seed,
            )

            built: List[ResultAtom] = []
            try:
                raw = fn(dict(trial))
                produced, metrics, artifacts = _normalise_outcome(raw)
                # Build atoms INSIDE the guard: a malformed atom spec is a
                # failure of that trial, not a crash of the whole experiment.
                built = [
                    _make_atom(spec, run_id, experiment_id, cond, i)
                    for spec in produced
                ]
            except Exception as exc:  # a failed run is data, not a crash
                status = RunStatus.FAILED
                error_text = f"{type(exc).__name__}: {exc}"
                any_failure = True
                built = []
                outcome.messages.append(f"  run {i} failed: {error_text}")
                self._write_traceback(experiment_id, run_id, traceback.format_exc())

            duration = time.time() - started

            # 把脚本产出的文件收进本次运行的文件夹，并记录实际落盘路径。
            saved = runstore.collect_artifacts(
                experiment_id, run_id, artifacts, self.store.root
            )
            runstore.finish(
                experiment_id, run_id,
                status=status.value,
                duration_seconds=round(duration, 4),
                exit_code=0 if status == RunStatus.SUCCESS else 1,
                artifact_paths=saved,
                atom_count=len(built),
                stderr=error_text or "",
            )

            runs.append(
                Run(
                    run_id=run_id,
                    experiment_id=experiment_id,
                    resolved_parameters={k: v for k, v in trial.items() if v is not None},
                    random_seed=self.seed,
                    started_at=datetime.fromtimestamp(started, timezone.utc),
                    duration_seconds=round(duration, 4),
                    exit_code=0 if status == RunStatus.SUCCESS else 1,
                    status=status,
                    software=f"Python {sys.version.split()[0]}",
                    artifact_paths=saved,
                    stderr_tail=error_text,
                )
            )

            atoms.extend(built)

        # -- persist --------------------------------------------------------
        self.store.save_runs(runs)
        self.store.append_atoms(atoms)

        # -- staleness ------------------------------------------------------
        after = self.store.load_atoms()
        outcome.changed = changed_atoms(before, after)
        outcome.stale = mark_stale(self.store, outcome.changed)

        # -- update the experiment record -----------------------------------
        exp.status = (
            ExperimentStatus.COMPLETED
            if not any_failure
            else ExperimentStatus.FAILED
        )
        exp.result_atom_ids = [a.atom_id for a in atoms]
        exp.run_ids = [r.run_id for r in runs]
        for m in _collect_metrics(atoms, exp):
            if m.name not in {x.name for x in exp.metrics}:
                exp.metrics.append(m)
        if any_failure and not exp.failure_reason:
            exp.failure_reason = "At least one trial failed; see the run stderr."
        self.store.save_experiment(exp)

        outcome.runs = runs
        outcome.atoms = atoms
        outcome.ok = True
        return outcome

    def _write_traceback(self, exp_id: str, run_id: str, text: str) -> None:
        path = self.store.root / "results" / "logs" / f"{run_id}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _normalise_outcome(raw: Any) -> Tuple[List[Dict], List[Dict], List[str]]:
    """Accept the several shapes a user function may reasonably return."""
    if raw is None:
        return [], [], []
    if isinstance(raw, dict):
        return (
            list(raw.get("atoms", [])),
            list(raw.get("metrics", [])),
            list(raw.get("artifacts", [])),
        )
    if isinstance(raw, list):
        return list(raw), [], []
    raise TypeError(
        "an experiment function must return a dict with 'atoms', a list of "
        f"atom dicts, or None; got {type(raw).__name__}"
    )


def _make_atom(
    spec: Dict[str, Any],
    run_id: str,
    experiment_id: str,
    condition: str,
    trial_index: int = 1,
) -> ResultAtom:
    """Build a ResultAtom from a user-supplied dict, filling in provenance."""
    if "name" not in spec:
        raise ValueError(f"atom spec missing 'name': {spec!r}")
    if "value" not in spec:
        raise ValueError(f"atom spec missing 'value': {spec!r}")
    atom_id = spec.get("atom_id") or _auto_atom_id(
        spec["name"], trial_index, experiment_id
    )
    from . import mode as mode_mod

    return ResultAtom(
        atom_id=atom_id,
        run_id=run_id,
        experiment_id=experiment_id,
        name=str(spec["name"]),
        value=spec["value"],
        unit=spec.get("unit"),
        format=spec.get("format", "%.4g"),
        condition=spec.get("condition", condition),
        metric_def=spec.get("metric_def"),
        # 短宏名要能从这里传下去，否则脚本里写了 macro_alias 也没用，
        # 正文里就还得用 \numRESEXPZeroZeroOneRTwoZeroZeroOne{} 那种长名。
        macro_alias=spec.get("macro_alias"),
        direction=spec.get("direction", "neutral"),
        renderings=spec.get("renderings", {}) or {},
    )


def _auto_atom_id(name: str, trial_index: int, experiment_id: str) -> str:
    """A STABLE id: the same trial slot must reuse the same id across reruns.

    This is load-bearing for staleness. An earlier version hashed the condition
    string, so refitting a held parameter (gamma 0.0177 -> 0.025) produced a NEW
    atom id instead of updating the existing one. The old atoms stayed behind,
    nothing was recognised as changed, and the stale mechanism silently never
    fired -- the exact failure it exists to prevent.

    The axis VALUES must not enter the id, because a sweep over beta in
    {0.1, 0.177, 0.25} is the same three slots even after the values change.
    """
    slug = "".join(c if c.isalnum() else "-" for c in name.upper()).strip("-")
    exp_slug = "".join(c for c in experiment_id if c.isalnum())
    return f"RES-{exp_slug}-{slug[:18]}-{trial_index:03d}"


def _collect_metrics(atoms: List[ResultAtom], exp: Experiment):
    """Turn suitably-named atoms into Metric records on the experiment."""
    from .schemas import Metric

    out = []
    for a in atoms:
        if a.direction.value != "neutral" or "rmse" in a.name.lower():
            out.append(
                Metric(
                    name=a.name,
                    value=a.value,
                    unit=a.unit,
                    direction=a.direction,
                    definition=a.metric_def,
                )
            )
    return out
