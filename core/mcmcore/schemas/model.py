"""数学内容的 schema：符号、公式、假设、参数。

这里的类型过去挂在 `Model` 对象下面。拆掉模型层之后它们变成**项目级**的：
一篇论文只有一张符号表、一套公式编号。

历史说明（保留以免后来者困惑）：A Model is NOT `model.py`. The corpus shows
2-4 named models per paper, each
with symbols, equations, assumptions, parameters, typed coupling to siblings,
and an explicit relationship to a baseline.

Every field that the modal paper does not supply is Optional or defaults to an
UNKNOWN enum member. That is a measured decision, not laziness:
  - only 36% of papers number assumptions
  - only 11% use explicit model-scoped assumption language
  - 44% have no notation table
  - no paper supplies a systematic state/decision/parameter taxonomy
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import Field, field_validator

from .common import (
    CouplingKind,
    EquationRole,
    Identified,
    ImprovementVerb,
    LimitationKind,
    MCMBase,
    ObjectiveSense,
    ParameterSource,
    Role,
    Scope,
    SymbolRelation,
    ValidationKind,
)


class Symbol(Identified):
    """One mathematical symbol, scoped to a model.

    Model-scoping is the only safe containment: symbol reuse across models is
    measurably real (17/383 papers, plus a documented table-vs-body
    contradiction on `r1` in the 2024 A paper).
    """

    glyph: str = Field(..., min_length=1, description="The symbol as printed.")
    meaning: str = Field(..., min_length=1, description="The universal 2nd column.")
    role: Role = Field(
        default=Role.UNKNOWN,
        description="Defaults to UNKNOWN: most papers give no role column.",
    )
    unit: Optional[str] = Field(
        default=None,
        description="A real minority carry units. '/' conventionally means dimensionless.",
    )
    domain: Optional[str] = Field(
        default=None,
        description="Index range or value band, e.g. '(j=1,2,...,5)' or '0.0443-0.1678'.",
    )
    redefines: Optional[str] = Field(
        default=None,
        description="id of a symbol this one collides with/redefines.",
    )
    time_varying: bool = Field(
        default=False,
        description="Distinguishes l1(t) from r1; drives simulation vs closed form.",
    )

    @field_validator("glyph")
    @classmethod
    def _glyph_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("symbol glyph must not be blank")
        return v


class Parameter(Identified):
    """A named constant of a model.

    Parameters need their own record type, separate from the symbol table:
    2021 E/2102057's "Table 2: Chinese Constants" carries values that the
    notation table does not. 105/237 modern papers have a parameter-captioned
    table; one declares 26 parameters + 6 initial conditions.
    """

    name: str = Field(..., min_length=1)
    value: Optional[object] = Field(
        default=None,
        description="Scalar or list. Papers print both (k=0.3 and k in {4.5,5,5.5}).",
    )
    unit: Optional[str] = None
    source: ParameterSource = Field(
        default=ParameterSource.UNKNOWN,
        description="Verbatim taxonomy from 2023 B/2318300: literature | data | calculated.",
    )
    source_ref: Optional[str] = Field(
        default=None, description="Citation key or dataset id backing the value."
    )
    candidate_values: List[object] = Field(
        default_factory=list,
        description=(
            "Papers print REJECTED candidates too: 2016 A/44398 Table 11 lists "
            "rho*c = 3300,3800,4200,3300 and k = 0.3,0.21,0.5*,0.543 before choosing."
        ),
    )
    confidence: Optional[str] = Field(
        default=None,
        description=(
            "Papers admit weak values verbatim: 'endowed with a strong "
            "artificiality'; 'merely an arbitrary given constant'; 'semi-educated guess'."
        ),
    )
    scope: Optional[str] = Field(
        default=None,
        description=(
            "Per-region / per-species / per-scenario parameter sets are common: "
            "2020 A/32150 (3 countries), 2021 A/2110178 (3 fungi), 2022 E/2202171 (3 zones)."
        ),
    )
    fitted_by: Optional[str] = Field(
        default=None, description="e.g. 'MSE loss with genetic algorithm'."
    )


class Assumption(Identified):
    """A modelling assumption, with a scope.

    A flat list loses the distinction between "All of our models rely on..."
    and "We will use the following assumptions in this section". 2019 B/1908286
    has a literal "Assumptions in This Model" heading.
    """

    text: str = Field(..., min_length=1)
    scope: Scope = Field(default=Scope.UNKNOWN)
    label: Optional[str] = Field(
        default=None,
        description=(
            "Stored, not derived: numbering is inconsistent (36% numbered, "
            "modal max 4, some papers reach 34)."
        ),
    )
    justification: Optional[str] = None
    justification_marker: Optional[str] = Field(
        default=None,
        description="Papers use glyph markers that carry meaning: 'Justification:', 'Reason N.', '>>'.",
    )
    referenced_by: List[str] = Field(
        default_factory=list,
        description="Assumptions are cited inside derivations ('According to Assumption 4').",
    )


class Equation(Identified):
    """A numbered equation.

    Equation numbers are a paper-GLOBAL counter spanning models, but 56% of
    papers never cross-reference one in prose (median 0 explicit `Eq. (n)`).
    So ownership must be STORED, never inferred from usage.
    """

    number: Optional[str] = Field(
        default=None,
        description="Global paper counter. Mostly numeric; lettered sub-cases exist ('C','D').",
    )
    latex: str = Field(..., min_length=1, description="LaTeX source of the equation.")
    role: EquationRole = Field(default=EquationRole.UNKNOWN)
    is_numbered: bool = Field(
        default=True,
        description="Governing equations are sometimes displayed unnumbered entirely.",
    )
    conditions: Optional[str] = Field(
        default=None,
        description="Initial/boundary conditions are part of the model statement.",
    )
    uses: List[str] = Field(
        default_factory=list,
        description="ids of equations this one depends on ('Combining Eq(7)').",
    )


class Objective(MCMBase):
    """Some models have TWO competing objectives; some have none."""

    expressions: List[str] = Field(default_factory=list)
    sense: ObjectiveSense = ObjectiveSense.NONE
    description: Optional[str] = None


class Validation(MCMBase):
    """One validation act. Six kinds are attested and not interchangeable."""

    kind: ValidationKind = ValidationKind.NONE_STATED
    description: Optional[str] = None
    metric: Optional[str] = None
    value: Optional[object] = None


class SensitivityAnalysis(MCMBase):
    """77% of papers run one, aimed at specific parameters of specific models."""

    parameters: List[str] = Field(default_factory=list)
    ranges: Optional[str] = None
    conclusion: Optional[str] = None
    experiment_id: Optional[str] = Field(
        default=None, description="Link to the Experiment that performed this."
    )


class Limitation(MCMBase):
    """Model-level, naming a specific mechanism of error.

    Distinct in content from paper-level Strengths/Weaknesses even when the
    heading is shared.
    """

    text: str
    kind: LimitationKind = LimitationKind.OTHER


class NotationTable(MCMBase):
    """The paper-level Notations table is a VIEW over model-scoped symbols.

    Near-universal disclaimer: "There are some variables that are not listed
    here and will be discussed in detail in each section." So the table must
    never be treated as the authoritative symbol scope.
    """

    exhaustive: bool = False
    disclaimer: Optional[str] = Field(
        default=None,
        description="Default disclaimer text is injected when exhaustive is false.",
    )
    unit_column: bool = Field(
        default=False, description="A real minority carry a Unit column."
    )
