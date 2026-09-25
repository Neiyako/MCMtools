"""MCMtools core schemas — the object model.

Layer 1 (Core). This package depends on nothing else in mcmcore; it is the
contract that every other module reads and writes.

Import surface is deliberately flat so callers do not need to know the file
layout::

    from mcmcore.schemas import Experiment, ResultAtom, Dataset, Paper
"""

from __future__ import annotations

from .common import (
    ArtifactStatus,
    CaveatKind,
    CitationStyle,
    ClaimType,
    CouplingKind,
    DatasetSourceKind,
    DatasetStage,
    DispersionKind,
    EquationRole,
    ExperimentKind,
    ExperimentStatus,
    ImprovementVerb,
    LimitationKind,
    MCMBase,
    MetricDirection,
    ObjectiveSense,
    ParameterSource,
    ProjectPhase,
    Role,
    RunMode,
    RunStatus,
    Scope,
    SectionKind,
    Severity,
    SymbolRelation,
    ValidationKind,
    VariedAxis,
    Verdict,
)
from .dataset import (
    Column,
    ColumnStats,
    Dataset,
    DatasetFile,
    DatasetSource,
    Transformation,
)
from .experiment import (
    BaselineRef,
    Caveat,
    Claim,
    Experiment,
    Metric,
    Perturbation,
    ResultAtom,
    Run,
    Varied,
)
from .model import (
    Assumption,
    Equation,
    Limitation,
    NotationTable,
    Objective,
    Parameter,
    SensitivityAnalysis,
    Symbol,
    Validation,
)
from .paper import (
    AIUsage,
    AIToolEntry,
    ArtifactBinding,
    BuildState,
    Citation,
    Figure,
    LatexConfig,
    Paper,
    PaperSection,
    Reference,
    SummarySheet,
    Table,
)
from .project import Problem, ProjectConfig, Task

__all__ = [
    # common
    "ArtifactStatus", "CaveatKind", "CitationStyle", "ClaimType", "CouplingKind",
    "DatasetSourceKind", "DatasetStage", "DispersionKind", "EquationRole",
    "ExperimentKind", "ExperimentStatus", "ImprovementVerb", "LimitationKind",
    "MCMBase", "MetricDirection", "ObjectiveSense", "ParameterSource",
    "ProjectPhase", "Role", "RunMode",
    "RunStatus", "Scope", "SectionKind", "Severity", "SymbolRelation",
    "ValidationKind", "VariedAxis", "Verdict",
    # model
    "Assumption", "Equation",
    "NotationTable", "Objective", "Parameter",
    "SensitivityAnalysis", "Symbol", "Validation",
    # experiment
    "BaselineRef", "Caveat", "Claim", "Experiment", "Metric", "Perturbation",
    "ResultAtom", "Run", "Varied",
    # dataset
    "Column", "ColumnStats", "Dataset", "DatasetFile", "DatasetSource",
    "Transformation",
    # paper
    "AIUsage", "AIToolEntry", "ArtifactBinding", "BuildState", "Citation",
    "Figure", "LatexConfig", "Paper", "PaperSection", "Reference", "SummarySheet",
    "Table",
    # project
    "Problem", "ProjectConfig", "Task",
]
