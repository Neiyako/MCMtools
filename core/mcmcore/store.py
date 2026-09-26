"""YAML persistence for the object model.

One loader/saver per object type, plus the on-disk project layout.

Design choices:
  - YAML because it is human-editable, diffable, and comment-friendly. During a
    96-hour contest a teammate must be able to fix a parameter by hand.
  - Round-trip fidelity: dump then load must be identity, because an audit is
    only meaningful if the record you audit is the record you wrote.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

import yaml
from pydantic import BaseModel

from .mathstore import MathStore
from .params import ParameterStore
from .schemas import (
    Claim,
    Dataset,
    Experiment,
    Figure,
    Paper,
    Problem,
    ProjectConfig,
    Reference,
    ResultAtom,
    Run,
    Table,
    Task,
)

T = TypeVar("T", bound=BaseModel)


# --------------------------------------------------------------------------
# Serialisation helpers
# --------------------------------------------------------------------------


def _to_plain(obj: Any) -> Any:
    """把枚举、pydantic 模型、numpy 标量转成 YAML 能写的普通结构。

    numpy 那一条必须留着：科研代码里 `np.mean(x)` 这类调用遍地都是，
    返回的是 np.float64 而不是 float。yaml.safe_dump 不认识它，会直接
    抛 "cannot represent an object" —— 而且是在**写运行归档时**才炸，
    代码本身已经跑完了。这个坑真实踩到过。
    """
    if isinstance(obj, Enum):
        return obj.value
    # numpy 标量：有 .item() 的都不是原生 Python 类型
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        try:
            return obj.item()
        except (AttributeError, ValueError):
            pass
    if isinstance(obj, BaseModel):
        return {k: _to_plain(v) for k, v in obj.model_dump(by_alias=True).items()}
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    return obj


def dump_yaml(obj: BaseModel, path: Path) -> None:
    """Write an object to YAML, creating parent directories as needed.

    Re-validates before serialising. This is what stops an in-place list
    mutation (``m.validation.append({...})``) from silently writing an
    unvalidated structure to disk: the round-trip through ``model_validate``
    either coerces the dict into the right model or raises loudly.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, BaseModel):
        # Rebuild from __dict__ (raw Python values) rather than model_dump(),
        # which emits a serializer warning for an in-place-appended dict before
        # validation ever gets a chance to coerce it.
        obj = type(obj).model_validate(
            {k: v for k, v in obj.__dict__.items() if k in type(obj).model_fields}
        )
    plain = _to_plain(obj)
    text = yaml.safe_dump(
        plain, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    )
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> Dict[str, Any]:
    """Read a YAML mapping from disk."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no such file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping, got {type(data).__name__}")
    return data


def _load_as(cls: Type[T], path: Path) -> T:
    return cls(**load_yaml(path))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Project layout
# --------------------------------------------------------------------------


class ProjectLayout:
    """Owns the on-disk paths of one competition attempt.

    Layout::

        <root>/
          project.yaml
          problems/
          data/DS-001/{dataset.yaml, raw/, cleaned/, ...}
          models/M03/model.yaml
          experiments/EXP-026/experiment.yaml
          results/atoms.yaml
          figures/FIG-011.{pdf,yaml}
          tables/TAB-008.{tex,yaml}
          paper/paper.yaml
          audit/
          export/
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # -- directories -------------------------------------------------------
    def ensure(self) -> "ProjectLayout":
        for sub in (
            "problems",
            "data",
            "math",
            "params",
            "experiments",
            "results",
            "figures",
            "tables",
            "paper",
            "paper/sections",
            "audit",
            "export",
        ):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        return self

    # -- config ------------------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.root / "project.yaml"

    def load_config(self) -> ProjectConfig:
        if not self.config_path.exists():
            return ProjectConfig()
        return _load_as(ProjectConfig, self.config_path)

    def save_config(self, cfg: ProjectConfig) -> None:
        dump_yaml(cfg, self.config_path)

    # -- generic object paths ---------------------------------------------
    def experiment_path(self, exp_id: str) -> Path:
        return self.root / "experiments" / exp_id / "experiment.yaml"

    def dataset_path(self, dataset_id: str) -> Path:
        return self.root / "data" / dataset_id / "dataset.yaml"

    def figure_path(self, fig_id: str) -> Path:
        return self.root / "figures" / f"{fig_id}.yaml"

    def table_path(self, tab_id: str) -> Path:
        return self.root / "tables" / f"{tab_id}.yaml"

    @property
    def atoms_path(self) -> Path:
        return self.root / "results" / "atoms.yaml"

    @property
    def claims_path(self) -> Path:
        return self.root / "results" / "claims.yaml"

    @property
    def runs_path(self) -> Path:
        return self.root / "results" / "runs.yaml"

    @property
    def paper_path(self) -> Path:
        return self.root / "paper" / "paper.yaml"

    @property
    def references_path(self) -> Path:
        return self.root / "paper" / "references.yaml"

    def problem_path(self, problem_id: str) -> Path:
        return self.root / "problems" / f"{problem_id}.yaml"

    def task_path(self, task_id: str) -> Path:
        return self.root / "problems" / f"{task_id}.yaml"


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


class Store:
    """High-level read/write facade over a ProjectLayout."""

    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root)
        self.root = Path(root)
        # 项目级内容区：math 管符号/公式/假设，params 管参数与来源。
        # 两者都由独立模块负责读写，Store 只做转发。
        self.math = MathStore(self.root)
        self.params = ParameterStore(self.root)

    # -- lifecycle ---------------------------------------------------------
    @classmethod
    def init(cls, root: Path, project_id: str = "mcm-project") -> "Store":
        store = cls(root)
        store.layout.ensure()
        if not store.layout.config_path.exists():
            store.layout.save_config(ProjectConfig(project_id=project_id))
        return store

    @classmethod
    def open(cls, root: Path) -> "Store":
        store = cls(root)
        if not store.layout.config_path.exists():
            raise FileNotFoundError(
                f"{root} is not an MCMtools project (no project.yaml). "
                f"Run 'mcm init' first."
            )
        return store

    # -- experiments -------------------------------------------------------
    def save_experiment(self, exp: Experiment) -> Path:
        path = self.layout.experiment_path(exp.id)
        dump_yaml(exp, path)
        return path

    def load_experiment(self, exp_id: str) -> Experiment:
        return _load_as(Experiment, self.layout.experiment_path(exp_id))

    def list_experiments(self) -> List[Experiment]:
        base = self.root / "experiments"
        if not base.is_dir():
            return []
        out = []
        for d in sorted(base.iterdir()):
            p = d / "experiment.yaml"
            if p.exists():
                out.append(_load_as(Experiment, p))
        return out

    def experiment_ids(self) -> List[str]:
        return [e.id for e in self.list_experiments()]

    # -- datasets ----------------------------------------------------------
    def save_dataset(self, ds: Dataset) -> Path:
        path = self.layout.dataset_path(ds.dataset_id)
        dump_yaml(ds, path)
        return path

    def load_dataset(self, dataset_id: str) -> Dataset:
        return _load_as(Dataset, self.layout.dataset_path(dataset_id))

    def list_datasets(self) -> List[Dataset]:
        base = self.root / "data"
        if not base.is_dir():
            return []
        out = []
        for d in sorted(base.iterdir()):
            p = d / "dataset.yaml"
            if p.exists():
                out.append(_load_as(Dataset, p))
        return out

    # -- artifacts ---------------------------------------------------------
    def save_figure(self, fig: Figure) -> Path:
        path = self.layout.figure_path(fig.id)
        dump_yaml(fig, path)
        return path

    def load_figure(self, fig_id: str) -> Figure:
        return _load_as(Figure, self.layout.figure_path(fig_id))

    def list_figures(self) -> List[Figure]:
        base = self.root / "figures"
        if not base.is_dir():
            return []
        return [_load_as(Figure, p) for p in sorted(base.glob("*.yaml"))]

    def save_table(self, tab: Table) -> Path:
        path = self.layout.table_path(tab.id)
        dump_yaml(tab, path)
        return path

    def load_table(self, tab_id: str) -> Table:
        return _load_as(Table, self.layout.table_path(tab_id))

    def list_tables(self) -> List[Table]:
        base = self.root / "tables"
        if not base.is_dir():
            return []
        return [_load_as(Table, p) for p in sorted(base.glob("*.yaml"))]

    # -- results -----------------------------------------------------------
    def save_atoms(self, atoms: List[ResultAtom]) -> Path:
        path = self.layout.atoms_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {"atoms": [_to_plain(a) for a in atoms]},
                sort_keys=False,
                allow_unicode=True,
                width=100,
            ),
            encoding="utf-8",
        )
        return path

    def load_atoms(self) -> List[ResultAtom]:
        path = self.layout.atoms_path
        if not path.exists():
            return []
        data = load_yaml(path)
        return [ResultAtom(**a) for a in data.get("atoms", [])]

    def append_atoms(self, atoms: List[ResultAtom]) -> None:
        """Merge new atoms by atom_id, replacing same-id entries."""
        existing = {a.atom_id: a for a in self.load_atoms()}
        for a in atoms:
            existing[a.atom_id] = a
        self.save_atoms(list(existing.values()))

    def save_claims(self, claims: List[Claim]) -> Path:
        path = self.layout.claims_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {"claims": [_to_plain(c) for c in claims]},
                sort_keys=False,
                allow_unicode=True,
                width=100,
            ),
            encoding="utf-8",
        )
        return path

    def load_claims(self) -> List[Claim]:
        path = self.layout.claims_path
        if not path.exists():
            return []
        return [Claim(**c) for c in load_yaml(path).get("claims", [])]

    def save_runs(self, runs: List[Run]) -> Path:
        path = self.layout.runs_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {"runs": [_to_plain(r) for r in runs]},
                sort_keys=False,
                allow_unicode=True,
                width=100,
            ),
            encoding="utf-8",
        )
        return path

    def load_runs(self) -> List[Run]:
        path = self.layout.runs_path
        if not path.exists():
            return []
        return [Run(**r) for r in load_yaml(path).get("runs", [])]

    # -- paper -------------------------------------------------------------
    def save_paper(self, paper: Paper) -> Path:
        dump_yaml(paper, self.layout.paper_path)
        return self.layout.paper_path

    def load_paper(self) -> Paper:
        if not self.layout.paper_path.exists():
            return Paper()
        return _load_as(Paper, self.layout.paper_path)

    def save_references(self, refs: List[Reference]) -> Path:
        path = self.layout.references_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                {"references": [_to_plain(r) for r in refs]},
                sort_keys=False,
                allow_unicode=True,
                width=100,
            ),
            encoding="utf-8",
        )
        return path

    def load_references(self) -> List[Reference]:
        path = self.layout.references_path
        if not path.exists():
            return []
        return [Reference(**r) for r in load_yaml(path).get("references", [])]

    # -- problems / tasks --------------------------------------------------
    def save_problem(self, problem: Problem) -> Path:
        path = self.layout.problem_path(problem.id)
        dump_yaml(problem, path)
        return path

    def load_problem(self, problem_id: str) -> Problem:
        return _load_as(Problem, self.layout.problem_path(problem_id))

    def list_problems(self) -> List[Problem]:
        base = self.root / "problems"
        if not base.is_dir():
            return []
        out = []
        for p in sorted(base.glob("*.yaml")):
            if p.stem.startswith("T-"):
                continue
            out.append(_load_as(Problem, p))
        return out

    def save_task(self, task: Task) -> Path:
        path = self.layout.task_path(task.id)
        dump_yaml(task, path)
        return path

    def list_tasks(self) -> List[Task]:
        base = self.root / "problems"
        if not base.is_dir():
            return []
        return [_load_as(Task, p) for p in sorted(base.glob("T-*.yaml"))]
