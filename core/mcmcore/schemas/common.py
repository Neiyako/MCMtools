"""Shared enums and base types for the MCMtools object model.

Design rules established by the corpus analysis:

1. Every enum has an ``UNKNOWN``/``NONE`` member where the corpus shows the modal
   paper does not supply the value. Measured: 64% of papers do not number
   assumptions, 44% have no notation table, and no paper provides a systematic
   state/decision/parameter taxonomy. Requiring those fields would make the
   model unusable on the majority of real papers.

2. Enum values are lowercase snake_case strings so they round-trip cleanly
   through YAML and stay readable in a diff.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrEnum(str, Enum):
    """A string enum that serialises to its value.

    Python 3.9 has no ``enum.StrEnum``, so we define our own.
    """

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


# --------------------------------------------------------------------------
# Cross-cutting: everything that the corpus shows is frequently absent gets an
# explicit UNKNOWN so that "not stated in the paper" is representable and is
# never silently conflated with a real value.
# --------------------------------------------------------------------------


class Role(StrEnum):
    """What kind of quantity a symbol is.

    Default MUST be UNKNOWN. Only a minority of papers separate state from
    parameter (2023 C/2307166 names "4 variables and 4 parameters"; 2023
    B/2315379 has a decision-variable table). The default presentation is a
    flat symbol list mixing all roles with no role column.
    """

    STATE = "state"
    DECISION = "decision"
    PARAMETER = "parameter"
    DERIVED = "derived"
    INDEX = "index"
    EXOGENOUS_DATA = "exogenous_data"
    OUTPUT_METRIC = "output_metric"
    UNKNOWN = "unknown"


class Scope(StrEnum):
    """Where an assumption applies.

    Only 11% of papers use explicit model-scoped language, but the best papers
    clearly maintain two scopes and say so ("The assumptions that are used in
    every model are summarized below. The additional assumptions for each
    individual model will be detailed along with the introduction and
    description of that model." — 2016 A/44845, p.5).
    """

    PAPER = "paper"
    MODEL = "model"
    SECTION = "section"
    UNKNOWN = "unknown"


class SymbolRelation(StrEnum):
    """How a symbol in one model relates to a same-named symbol in another.

    17/383 papers (4%, conservative lower bound) literally redefine a symbol
    with two distinct meanings, e.g. `Chi` = genre-central-node vs
    artist-central-node (2021 D/2124497).
    """

    IDENTICAL = "identical"
    REDEFINED = "redefined"
    DERIVED = "derived"


class ParameterSource(StrEnum):
    """Provenance of a parameter value.

    Verbatim taxonomy from 2023 B/2318300: values "were found either from
    literature (in a peer-edited research paper), from data (in official data
    sets), or calculated (constructed from our model and assumptions)".
    Papers also openly flag weak values as SEMI_EDUCATED_GUESS.
    """

    LITERATURE = "literature"
    DATASET = "dataset"
    FITTED = "fitted"
    ASSUMED = "assumed"
    DERIVED = "derived"
    SEMI_EDUCATED_GUESS = "semi_educated_guess"
    UNKNOWN = "unknown"


class EquationRole(StrEnum):
    """What an equation does in the argument."""

    GOVERNING = "governing"
    DEFINITION = "definition"
    CONSTRAINT = "constraint"
    OBJECTIVE = "objective"
    TRANSFORMATION = "transformation"
    METRIC = "metric"
    CALIBRATION = "calibration"
    UNKNOWN = "unknown"


class ObjectiveSense(StrEnum):
    MIN = "min"
    MAX = "max"
    DUAL = "dual"
    NONE = "none"


class CouplingKind(StrEnum):
    """Four distinct coupling kinds are observed in real papers.

    A single parent pointer cannot express them.
    """

    OUTPUT = "output"
    SHARED_PARAMETER = "shared_parameter"
    FEEDBACK = "feedback"
    REGRESSION = "regression"


class ImprovementVerb(StrEnum):
    """The observed vocabulary is specific and carries meaning.

    "modified for the nature of the larval and adult bank" is not the same
    claim as "inspired by".
    """

    INHERIT = "inherit"
    BUILD_ON = "build_on"
    EXTEND = "extend"
    MODIFY = "modify"
    IMPROVE = "improve"
    ADAPT = "adapt"
    OPTIMIZE = "optimize"
    INSPIRE = "inspire"
    SUPPLEMENT = "supplement"
    UNKNOWN = "unknown"


class ValidationKind(StrEnum):
    """Six distinct validation kinds are observed and are not interchangeable.

    Attested: external data, literature, held-out, cross-validation,
    statistical test, internal agreement, bootstrap interval, transfer case
    study, sensitivity. "none_stated" is common. Dimensional analysis was NOT
    observed in the corpus.
    """

    EXTERNAL_DATA = "external_data"
    LITERATURE = "literature"
    HELD_OUT = "held_out"
    CROSS_VALIDATION = "cross_validation"
    STATISTICAL_TEST = "statistical_test"
    INTERNAL_AGREEMENT = "internal_agreement"
    BOOTSTRAP_INTERVAL = "bootstrap_interval"
    TRANSFER_CASE_STUDY = "transfer_case_study"
    SENSITIVITY = "sensitivity"
    NONE_STATED = "none_stated"


class LimitationKind(StrEnum):
    """Recurring failure admissions, which have different remediation.

    All attested verbatim: "the formulas of our model in terms of sex ratio
    regulation are given by ourselves" (formula_ungrounded); "Some of our
    parameters are based on a semi-educated guess" (parameter_uncertainty);
    "we generalized some species into uniform species" (aggregation_loss);
    "the number of real data used to validate the model is too small"
    (data_insufficiency).
    """

    STRUCTURAL = "structural"
    FORMULA_UNGROUNDED = "formula_ungrounded"
    PARAMETER_UNCERTAINTY = "parameter_uncertainty"
    AGGREGATION_LOSS = "aggregation_loss"
    DATA_INSUFFICIENCY = "data_insufficiency"
    TEMPORAL_SCOPE = "temporal_scope"
    VALIDATION_WEAKNESS = "validation_weakness"
    UNDERPERFORMS_BASELINE = "underperforms_baseline"
    OTHER = "other"


# --------------------------------------------------------------------------
# Experiment / result vocabulary
# --------------------------------------------------------------------------


class ExperimentKind(StrEnum):
    """The real unit of work is a sweep with a declared invariant.

    86% of modern papers run a sensitivity analysis; it is the most reliable
    anchor for "computation happened here". (The heading "Numerical
    Simulation" appears exactly once in 346 papers.)

    SENSITIVITY_OAT is the dominant design.
    """

    SENSITIVITY_OAT = "sensitivity_oat"
    SENSITIVITY_GRID = "sensitivity_grid"
    MODEL_COMPARISON = "model_comparison"
    ROBUSTNESS_NOISE = "robustness_noise"
    MONTE_CARLO = "monte_carlo"
    CROSS_VALIDATION = "cross_validation"
    OPTIMIZATION_RUN = "optimization_run"
    CONVERGENCE_STUDY = "convergence_study"
    SIMULATION = "simulation"
    TRAIN_TEST = "train_test"
    SCENARIO = "scenario"
    BACKTEST = "backtest"
    ERROR_ANALYSIS = "error_analysis"
    OTHER = "other"


class ExperimentStatus(StrEnum):
    """FAILED and REJECTED are load-bearing.

    83% of winning papers discuss weaknesses; the best documents two rejected
    methods before the accepted one (2016 C/47823: KKT had "250 variables ...
    we have to give up"; plain PSO "takes a very long time to converge and does
    not produce the optimal values"). Without these states that argument is
    unreconstructable.
    """

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class VariedAxis(StrEnum):
    PARAMETER = "parameter"
    MODEL_IDENTITY = "model_identity"
    INPUT_DATA = "input_data"
    STRUCTURE = "structure"
    NONE = "none"


class MetricDirection(StrEnum):
    """Papers define this explicitly.

    "The larger the R2 ... the smaller the MSE, RMSE and MAE indicate the
    higher the prediction accuracy of the model" (2023 C/2310767).
    """

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    NEUTRAL = "neutral"


class DispersionKind(StrEnum):
    """std vs 95% CI vs bootstrap PI vs box-plot spread mean different things.

    Error bars are notably ABSENT (0/237 papers); papers use std dev, CIs,
    and box plots instead.
    """

    NONE = "none"
    STD = "std"
    STD_ERROR = "std_error"
    CONFIDENCE_INTERVAL = "confidence_interval"
    PREDICTION_INTERVAL = "prediction_interval"
    QUANTILE_RANGE = "quantile_range"
    IQR = "iqr"


class RunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"


# --------------------------------------------------------------------------
# Dataset vocabulary
# --------------------------------------------------------------------------


class DatasetStage(StrEnum):
    """raw is immutable; each stage is a new version, never an overwrite."""

    RAW = "raw"
    STAGED = "staged"
    CLEANED = "cleaned"
    PROCESSED = "processed"
    FEATURES = "features"


class DatasetSourceKind(StrEnum):
    COMPETITION_PROVIDED = "competition_provided"
    EXTERNAL = "external"
    DERIVED = "derived"
    SIMULATED = "simulated"


# --------------------------------------------------------------------------
# Artifact / paper vocabulary
# --------------------------------------------------------------------------


class ArtifactStatus(StrEnum):
    """STALE is what prevents figures diverging from their results.

    When a bound ResultAtom changes, every artifact bound to it becomes stale
    and must be regenerated.
    """

    GENERATED = "generated"
    STALE = "stale"
    MISSING = "missing"
    FAILED = "failed"


class SectionKind(StrEnum):
    """Canonical section kinds.

    Presence tiers measured over N=415 (union of two detectors):
      MANDATORY >80%: references 92.0%, introduction 87.5%
      COMMON 40-80%: abstract 64.6, assumptions 57.1, conclusion 53.0,
                     model 48.9, sensitivity 47.0, notations 45.1
      OPTIONAL <40%: strengths_weaknesses 38.6, restatement 37.8,
                     our_work 36.4, appendix 33.0, background 30.6,
                     data 12.0, model_evaluation 11.3
      ABSENT: literature_review 0.0%  -> never template it
    """

    SUMMARY = "summary"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    BACKGROUND = "background"
    RESTATEMENT = "restatement"
    OUR_WORK = "our_work"
    ASSUMPTIONS = "assumptions"
    NOTATIONS = "notations"
    DATA = "data"
    MODEL = "model"
    # SOLUTION 与 SCENARIO 是题型骨架真正需要的两节：
    # 机理题要"数值格式与验证"、政策题要"情景对比"，
    # 都不是 model 或 sensitivity 能覆盖的。语料里这两类内容
    # 通常写在 Model 之内，但独立成节更好找、也更好引用。
    SOLUTION = "solution"
    SCENARIO = "scenario"
    SENSITIVITY = "sensitivity"
    MODEL_EVALUATION = "model_evaluation"
    STRENGTHS_WEAKNESSES = "strengths_weaknesses"
    CONCLUSION = "conclusion"
    REFERENCES = "references"
    APPENDIX = "appendix"
    MEMORANDUM = "memorandum"
    REPORT_ON_AI = "report_on_ai"
    OTHER = "other"


class CitationStyle(StrEnum):
    NUMERIC = "numeric"
    AUTHOR_YEAR = "author_year"


class ClaimType(StrEnum):
    """Attested claim kinds, each with different evidential force."""

    QUALITY = "quality"
    SUPERIORITY = "superiority"
    STABILITY = "stability"
    SIGNIFICANCE = "significance"
    NO_DIFFERENCE = "no_difference"
    PROBABILITY = "probability"
    RECOMMENDATION = "recommendation"
    OTHER = "other"


class CaveatKind(StrEnum):
    DATA_LIMITATION = "data_limitation"
    ASSUMPTION_ERROR = "assumption_error"
    TRANSFER_FAILURE = "transfer_failure"
    RUNTIME_COST = "runtime_cost"
    NON_REPRODUCIBILITY = "non_reproducibility"
    GENERALIZATION = "generalization"
    MANUAL_EFFORT = "manual_effort"
    MODEL_INADEQUACY = "model_inadequacy"
    REGIME_DEPENDENCE = "regime_dependence"
    OTHER = "other"


class ProjectPhase(StrEnum):
    """The workflow is a state machine with a one-time decision and a lock.

    After the problem is locked, A-F must not occupy the main interface.
    """

    PROBLEM_SELECTION = "problem_selection"
    PROBLEM_LOCKED = "problem_locked"
    BUILD = "build"
    FINALIZE = "finalize"


class RunMode(StrEnum):
    """AI-assisted development vs offline competition operation."""

    DEVELOPMENT = "development"
    COMPETITION = "competition"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Verdict(StrEnum):
    READY = "ready"
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    NOT_READY = "not_ready"


# --------------------------------------------------------------------------
# Base model
# --------------------------------------------------------------------------


class MCMBase(BaseModel):
    """Base for all MCMtools objects.

    ``extra="forbid"`` is deliberate: a typo in a hand-written YAML file should
    be a loud error, not a silently ignored key. The whole point of the tool is
    that the record and the reality agree.

    ``validate_assignment`` catches attribute assignment but NOT in-place list
    mutation: ``m.validation.append({...})`` leaves a raw dict inside a typed
    list, which then serialises with a warning. Use :meth:`revalidate` after
    such an append, or construct with validated model instances.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )

    def revalidate(self) -> "MCMBase":
        """Rebuild in place so in-place list/dict mutations get validated.

        Returns self so it can be chained: ``m.validation.append({...}); m.revalidate()``
        """
        rebuilt = type(self).model_validate(
            {k: v for k, v in self.__dict__.items() if k in type(self).model_fields}
        )
        for name in type(self).model_fields:
            object.__setattr__(self, name, getattr(rebuilt, name))
        return self


class Identified(MCMBase):
    """Anything with a stable id, so cross-references have a target.

    Assumptions, equations, and subsystem relations are all cited by
    name/number inside papers ("according to Assumption 4", "sub-model iii"),
    so ids must be stable.
    """

    id: str = Field(..., min_length=1, description="Stable identifier.")


class Provenanced(MCMBase):
    """Carries an optional free-text provenance note."""

    note: Optional[str] = Field(
        default=None, description="Free-text provenance or explanation."
    )
