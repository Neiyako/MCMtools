"""Experiment-domain schemas: the real unit of work, and the result chain.

The central correction to the naive design: an Experiment is NOT a script. It
is a *protocol* — a declared variation applied to a model+dataset, producing
typed result atoms. 86% of modern papers run a sensitivity analysis, and the
dominant design states its invariant verbatim:

    "In each parameter analysis, we only varied that parameter while keeping
     the other parameters at their default values."  -- 2023 C/2301192

The second correction: Result is SPLIT into Run (a raw execution record) and
ResultAtom (one typed number). This is what makes numeric auditing mechanical:
69% of papers repeat a precise number internally and ~73% of summary numbers
reappear verbatim in the body, so the number needs exactly one home.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import Field

from .common import (
    CaveatKind,
    ClaimType,
    DispersionKind,
    ExperimentKind,
    ExperimentStatus,
    Identified,
    MCMBase,
    MetricDirection,
    RunStatus,
    VariedAxis,
)


class Varied(MCMBase):
    """One axis along which the experiment varies.

    Either explicit ``values`` or a ``range`` with ``step``. Real examples:
    `p in [0.05, 0.3]`, `n in [50, 175]`, `beta in {5%, 10%, 15%}`,
    `c_i in {0.8, 1.2}`, and `lambda_3, lambda_9 in units of 0.01 from 0.01 to 1`.
    """

    name: str = Field(..., min_length=1, description="Parameter or factor name.")
    values: List[object] = Field(default_factory=list)
    range: Optional[List[float]] = Field(
        default=None, description="[low, high] when a continuous sweep."
    )
    step: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None


class BaselineRef(MCMBase):
    """Every chain in the corpus is expressed as a delta against an anchor.

    Anchors observed: `c_i = 1`, "traditional grid strategy", "the original
    model in section 3", a prior model run, or a plain single-model baseline.
    """

    kind: str = Field(
        default="none",
        description="experiment | model | literature | value | none.",
    )
    ref: Optional[str] = None
    description: Optional[str] = None


class Perturbation(MCMBase):
    """Robustness experiments ALWAYS declare the kernel.

    "Gaussian ... variance of noise to be 0.01 and 0.02 times the original
    value" (2022 C/2200401); "1% random noise of initial value"
    (2017 F/64486); "add and subtract 5% of Finland's GDP per capita"
    (2022 F/2220722).
    """

    distribution: str = Field(
        default="gaussian", description="gaussian | uniform | multiplicative | resample."
    )
    magnitude: Optional[float] = None
    magnitude_unit: str = Field(default="relative", description="relative | absolute.")
    applies_to: Optional[str] = None


class Metric(MCMBase):
    """A measured quantity. NOT a fixed enum.

    Metrics are problem-type dependent: RMSE is C-only (49 of 53 occurrences),
    MAE is C-only (27/27), while E/F use entropy weight and TOPSIS and A uses
    Shannon diversity. ROC/AUC appears in only 4 of 237 modern papers.
    """

    name: str = Field(..., min_length=1)
    value: Optional[object] = None
    unit: Optional[str] = None
    direction: MetricDirection = MetricDirection.NEUTRAL
    dispersion: Optional[float] = None
    dispersion_kind: DispersionKind = DispersionKind.NONE
    per_variant: Dict[str, object] = Field(
        default_factory=dict,
        description="For comparison tables: {variant_name: value}.",
    )
    definition: Optional[str] = Field(
        default=None,
        description="Papers define direction/meaning in prose; stored so it can be quoted.",
    )


class Caveat(MCMBase):
    """83% of winning papers discuss weaknesses; 47% state limitations."""

    kind: CaveatKind = CaveatKind.OTHER
    text: str


class Claim(MCMBase):
    """A sentence that a result supports.

    The minimum linkable unit is (experiment -> result_atom -> sentence). Each
    corpus chain has 3-6 such links.
    """

    text: str = Field(..., min_length=1)
    claim_type: ClaimType = ClaimType.OTHER
    result_atom_ids: List[str] = Field(default_factory=list)
    location: Optional[str] = Field(
        default=None,
        description=(
            "Where the claim is stated. The same number recurs in 2-4 places "
            "(abstract, prose, table cell, figure caption)."
        ),
    )
    section_id: Optional[str] = None


class Experiment(Identified):
    """A protocol: what varies, what is held fixed, and why."""

    # --- identity & provenance ---
    label: Optional[str] = None
    kind: ExperimentKind = ExperimentKind.OTHER
    model_id: Optional[str] = None
    dataset_id: Optional[str] = None
    task_refs: List[str] = Field(default_factory=list)
    section_ref: Optional[str] = None

    # --- lineage: a DAG, not a list ---
    parent_experiment_ids: List[str] = Field(
        default_factory=list,
        description="Experiments consume other experiments' outputs.",
    )
    variant_of: Optional[str] = Field(
        default=None,
        description=(
            "Ablation is modelled here, NOT as a separate type: the word "
            "'ablation' appears 0 times in the modern corpus, but 34% of papers "
            "do it ('without considering the vaccine')."
        ),
    )
    removed_components: List[str] = Field(default_factory=list)
    supersedes: Optional[str] = None

    # --- motivation (papers always give one) ---
    motivation: Optional[str] = Field(
        default=None,
        description=(
            "e.g. a parameter 'is endowed with a strong artificiality'; an "
            "'arbitrary given constant, since no such real data could be found'."
        ),
    )
    uncertainty_rationale: Optional[str] = None

    # --- the protocol ---
    varied: List[Varied] = Field(default_factory=list)
    held_fixed: List[str] = Field(
        default_factory=list,
        description="The OAT invariant, stated verbatim in real papers.",
    )
    varied_axis: VariedAxis = VariedAxis.NONE

    method: Optional[str] = Field(
        default=None, description="backtest | sobol | monte_carlo | bootstrap | CV | ..."
    )
    baseline_ref: BaselineRef = Field(default_factory=BaselineRef)

    n_runs: Optional[int] = Field(
        default=None,
        description="30% of papers state an explicit count (9, 30, 50, 100, 500, 1000, 10000).",
    )
    n_folds: Optional[int] = None
    aggregation: Optional[str] = Field(
        default=None,
        description="Always stated where multiple runs exist: 'mean and standard deviation'.",
    )
    perturbation: Optional[Perturbation] = None
    readout_condition: Optional[str] = Field(
        default=None,
        description="'t = 1000', 'year 50', 'time steps (300,600,1800,3600)', 'March 1, 2023'.",
    )

    max_iterations: Optional[int] = None
    convergence_criterion: Optional[str] = Field(
        default=None,
        description=(
            "OPTIONAL and normally empty: 0 of 237 modern papers report a "
            "numeric tolerance. Papers say 'converges after 50 iterations'."
        ),
    )
    converged_at: Optional[int] = Field(
        default=None,
        description="Used as a RESULT, not just a control: 'converges after 50 iterations.'",
    )
    hyperparameters: Dict[str, object] = Field(default_factory=dict)
    train_test_split: Optional[str] = Field(
        default=None, description="'80% training / 20% testing'."
    )

    entrypoint: Optional[str] = Field(
        default=None,
        description=(
            "Path to the code that performs this experiment, as "
            "'experiments/EXP-001/run.py:run' relative to the project root. "
            "The function receives the resolved parameter dict for one trial "
            "and returns {'atoms': [...]}."
        ),
    )
    software: Optional[str] = None
    random_seed: Optional[int] = Field(
        default=None,
        description=(
            "Record but NEVER require: only ~5% of papers report a seed, and "
            "mostly inside appendix code."
        ),
    )
    runtime_seconds: Optional[float] = Field(
        default=None,
        description="Only 3%; but decisive when a method was rejected for slowness.",
    )

    # --- outcome ---
    status: ExperimentStatus = ExperimentStatus.PLANNED
    failure_reason: Optional[str] = Field(
        default=None,
        description=(
            "Load-bearing. The best paper documents two rejected methods "
            "(KKT: '250 variables ... we have to give up'; PSO: 'takes a very "
            "long time to converge') before the accepted one."
        ),
    )
    metrics: List[Metric] = Field(default_factory=list)
    result_atom_ids: List[str] = Field(
        default_factory=list, description="Populated by the runner."
    )
    run_ids: List[str] = Field(default_factory=list, description="Populated by the runner.")
    figure_ids: List[str] = Field(default_factory=list)
    table_ids: List[str] = Field(default_factory=list)
    claim_ids: List[str] = Field(default_factory=list)
    caveats: List[Caveat] = Field(default_factory=list)

    # --- integrity helpers ---

    def held_fixed_ok(self) -> bool:
        """An OAT sweep must declare what it held fixed.

        This is the single most reliable structural signature of a real MCM
        sensitivity experiment.
        """
        if self.kind != ExperimentKind.SENSITIVITY_OAT:
            return True
        return bool(self.held_fixed) and len(self.varied) == 1

    def n_trials(self) -> Optional[int]:
        """Total concrete trials implied by the varied axes."""
        if not self.varied:
            return None
        total = 1
        for v in self.varied:
            if v.values:
                total *= len(v.values)
            elif v.range and v.step:
                span = v.range[1] - v.range[0]
                total *= int(round(span / v.step)) + 1
            else:
                return None
        return total * (self.n_runs or 1)


class Run(MCMBase):
    """One execution of an Experiment. Machine-written, never hand-edited."""

    run_id: str = Field(..., min_length=1)
    experiment_id: str = Field(..., min_length=1)
    resolved_parameters: Dict[str, object] = Field(default_factory=dict)
    random_seed: Optional[int] = None
    started_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    exit_code: Optional[int] = None
    status: RunStatus = RunStatus.SUCCESS
    software: Optional[str] = None
    artifact_paths: List[str] = Field(default_factory=list)
    stderr_tail: Optional[str] = Field(
        default=None, description="Kept so a FAILED run stays diagnosable."
    )


class ResultAtom(MCMBase):
    """ONE typed number — the single source of truth for every number in the paper.

    Everything downstream renders it; nothing re-types it. This is the
    mechanism that makes the target question answerable: if EXP-026's RMSE
    changes from 0.0832 to 0.0791, the paper cannot keep saying 0.0832, because
    the paper never stored 0.0832 — it stored a reference.

    ``condition`` is mandatory in spirit because a value is meaningless without
    it: `P=0.02%@2030` and `P=8.25%@2039` are different results.
    """

    atom_id: str = Field(..., min_length=1)
    run_id: Optional[str] = None
    experiment_id: Optional[str] = None
    name: str = Field(..., min_length=1)
    value: object = Field(..., description="Scalar, or a small list/vector.")
    unit: Optional[str] = None
    format: str = Field(
        default="%.4g",
        description="Canonical printf-style rendering used by the paper compiler.",
    )
    condition: Optional[str] = Field(
        default=None,
        description="'cost_gold=0.01, cost_btc=0.02', '@2039', '@year 50'.",
    )
    metric_def: Optional[str] = None
    # 短宏名。自动生成的宏名是 \numRESEXPZeroZeroOneRTwoZeroZeroOne{} ——
    # 唯一但没法读，写进正文打断思路，改起来还要数零的个数。
    # 作者给一个别名（如 r_squared），正文里就写 \numRSquared{}。
    # 只允许字母：LaTeX 控制序列不能含数字。
    macro_alias: Optional[str] = Field(
        default=None,
        description="短宏名，如 'r_squared'。只用字母。留空则用自动长名。",
    )
    direction: MetricDirection = MetricDirection.NEUTRAL
    renderings: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Alternate renderings for unit-normalised comparison. The corpus "
            "reports the same quantity as '83.77 %' and '0.8377', so the "
            "auditor must normalize before comparing."
        ),
    )

    def rendered(self, rendering: Optional[str] = None) -> str:
        """Render the canonical (or a named alternate) string form."""
        if rendering and rendering in self.renderings:
            return self.renderings[rendering]
        try:
            return self.format % float(self.value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return str(self.value)

    def numeric(self) -> Optional[float]:
        """Best-effort float for numeric comparison."""
        if isinstance(self.value, bool):
            return None
        if isinstance(self.value, (int, float)):
            return float(self.value)
        try:
            return float(str(self.value))
        except (TypeError, ValueError):
            return None


__all__ = [
    "BaselineRef",
    "Caveat",
    "Claim",
    "Experiment",
    "Metric",
    "Perturbation",
    "ResultAtom",
    "Run",
    "Varied",
]
