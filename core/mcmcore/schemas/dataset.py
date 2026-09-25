"""Dataset schema and the data pipeline.

The proposed `raw -> cleaned -> processed -> features -> results` pipeline was
broadly right but wrong in one specific way: **`results` is not a data stage.**
Results are ResultAtoms produced by an Experiment. Mixing them into the data
lineage conflates two object types.

Each stage is an immutable, hash-addressed version. A stage never overwrites
its input.

Deliberately NOT built: a full data-versioning DAG with branching and merging.
Papers show LINEAR pipelines with at most one scenario split, so a
`parent_dataset_id` chain plus content hashes is sufficient.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import Field

from .common import DatasetSourceKind, DatasetStage, MCMBase


class DatasetSource(MCMBase):
    kind: DatasetSourceKind = DatasetSourceKind.EXTERNAL
    ref: Optional[str] = Field(
        default=None, description="'2024 MCM Problem C', a URL, or a citation key."
    )
    url: Optional[str] = None
    retrieved: Optional[str] = None


class Column(MCMBase):
    """One column of a dataset's schema.

    Drives EDA table generation and validation.
    """

    name: str
    dtype: str = Field(default="unknown", description="string | int64 | float64 | datetime | bool")
    unit: Optional[str] = None
    nullable: bool = True
    missing_count: Optional[int] = None
    outlier_count: Optional[int] = None
    description: Optional[str] = None


class Transformation(MCMBase):
    """One step of the audit trail: what was done, in order, and its effect."""

    step: str = Field(..., min_length=1, description="e.g. drop_duplicates, impute_missing")
    params: Dict[str, object] = Field(default_factory=dict)
    rows_before: Optional[int] = None
    rows_after: Optional[int] = None
    rows_affected: Optional[int] = None
    note: Optional[str] = None


class ColumnStats(MCMBase):
    """Summary statistics that feed the EDA section directly."""

    column: str
    count: Optional[int] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    p25: Optional[float] = None
    median: Optional[float] = None
    p75: Optional[float] = None
    max: Optional[float] = None
    missing: Optional[int] = None


class DatasetFile(MCMBase):
    path: str = Field(..., min_length=1)
    rows: Optional[int] = None
    bytes: Optional[int] = None
    content_hash: Optional[str] = None


class Dataset(MCMBase):
    """A versioned data asset with lineage."""

    dataset_id: str = Field(..., min_length=1)
    name: str
    version: int = Field(default=1, ge=1, description="Immutable; bump on any change.")
    stage: DatasetStage = DatasetStage.RAW
    source: DatasetSource = Field(default_factory=DatasetSource)
    parent_dataset_id: Optional[str] = Field(
        default=None, description="Lineage. Format: 'DS-001@2'."
    )
    content_hash: Optional[str] = Field(
        default=None, description="Reproducibility anchor, e.g. 'sha256:...'."
    )
    files: List[DatasetFile] = Field(default_factory=list)
    schema_: List[Column] = Field(
        default_factory=list,
        alias="schema",
        description="Column definitions. Aliased because 'schema' is reserved on BaseModel.",
    )
    transformations: List[Transformation] = Field(default_factory=list)
    stats: List[ColumnStats] = Field(default_factory=list)
    eda_figure_ids: List[str] = Field(default_factory=list)
    eda_table_ids: List[str] = Field(default_factory=list)
    used_by_experiments: List[str] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)

    model_config = MCMBase.model_config.copy()
    model_config["populate_by_name"] = True

    def versioned_id(self) -> str:
        return f"{self.dataset_id}@{self.version}"

    def total_rows(self) -> Optional[int]:
        rows = [f.rows for f in self.files if f.rows is not None]
        return sum(rows) if rows else None
