"""Project, Task, and Problem schemas.

A project is one competition attempt. The phase field drives the whole UI:
after the problem is locked, the other letters must not occupy the interface.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from .common import Identified, MCMBase, ProjectPhase, RunMode


class Problem(Identified):
    """A competition problem statement (one of A-F)."""

    year: Optional[int] = None
    letter: Optional[str] = Field(default=None, description="A-F.")
    title: Optional[str] = None
    statement_path: Optional[str] = None
    data_paths: List[str] = Field(default_factory=list)
    task_ids: List[str] = Field(default_factory=list)
    status: str = Field(
        default="candidate",
        description="candidate | analysed | chosen | rejected.",
    )
    summary: Optional[str] = None

    def is_chosen(self) -> bool:
        return self.status == "chosen"


class Task(Identified):
    """A numbered sub-question.

    Tasks are the organizing principle for models: the dominant pattern is one
    model per task ("For task 2, we first establish...").
    """

    text: str = Field(..., min_length=1)
    index: Optional[int] = None
    requirement_refs: List[str] = Field(default_factory=list)
    model_ids: List[str] = Field(default_factory=list)


class ProjectConfig(MCMBase):
    """Top-level project state."""

    project_id: str = Field(default="mcm2025-A")
    name: Optional[str] = None
    phase: ProjectPhase = ProjectPhase.PROBLEM_SELECTION
    mode: RunMode = Field(
        default=RunMode.DEVELOPMENT,
        description="competition mode blocks network access and AI features.",
    )
    locked_problem_id: Optional[str] = None
    team_control_number: Optional[str] = None

    def is_locked(self) -> bool:
        return self.phase in (ProjectPhase.BUILD, ProjectPhase.FINALIZE) and bool(
            self.locked_problem_id
        )
