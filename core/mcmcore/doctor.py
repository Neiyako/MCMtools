"""First-run environment check.

The tool must be usable by someone who has never opened a terminal: they
double-click, and either it works or it tells them in one sentence what to do.
That rules out two common approaches:

* **Failing on ImportError.** A traceback is not an instruction. Every missing
  dependency is detected up front, named, and installed on consent.
* **Silently installing everything.** TeX Live is ~2GB and takes twenty minutes.
  It is checked, and if it is absent the tool still runs -- it just cannot
  produce a PDF, and says so. Rendering the paper is optional; auditing it is
  not.

The distinction the checks encode: **required** dependencies block startup,
**optional** ones degrade a feature. Nothing is ever quietly skipped.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


# --------------------------------------------------------------------------
# What the tool needs
# --------------------------------------------------------------------------

# (import name, pip name, minimum version or None, why it matters)
REQUIRED: Tuple[Tuple[str, str, Optional[str], str], ...] = (
    ("pydantic", "pydantic", "2.0", "类型化数据结构：整个对象模型的基础"),
    ("yaml", "pyyaml", "6.0", "项目文件的磁盘格式"),
    ("numpy", "numpy", None, "图表生成"),
    ("matplotlib", "matplotlib", None, "图表生成"),
)

OPTIONAL: Tuple[Tuple[str, str, Optional[str], str], ...] = (
    ("fastapi", "fastapi", None, "浏览器面板"),
    ("uvicorn", "uvicorn", None, "浏览器面板"),
    ("pandas", "pandas", None, "数据集统计"),
    ("jinja2", "jinja2", None, "模板渲染"),
)

# TeX lives outside pip and is found, not imported.
TEX_CANDIDATES = (
    "pdflatex",
    "/Library/TeX/texbin/pdflatex",
    "/usr/local/texlive/2026/bin/universal-darwin/pdflatex",
    "/opt/homebrew/bin/pdflatex",
    "/usr/bin/pdflatex",
)


@dataclass
class Check:
    """One environment fact, with the command that fixes it."""

    name: str
    ok: bool
    required: bool
    detail: str = ""
    fix: Optional[str] = None
    version: Optional[str] = None

    def line(self) -> str:
        mark = "正常" if self.ok else ("缺失" if self.required else "可选")
        v = f" {self.version}" if self.version else ""
        d = f"  {self.detail}" if self.detail else ""
        return f"  [{mark}] {self.name}{v}{d}"


@dataclass
class Diagnosis:
    checks: List[Check] = field(default_factory=list)
    python_ok: bool = True
    python_detail: str = ""

    @property
    def missing_required(self) -> List[Check]:
        return [c for c in self.checks if not c.ok and c.required]

    @property
    def missing_optional(self) -> List[Check]:
        return [c for c in self.checks if not c.ok and not c.required]

    @property
    def ready(self) -> bool:
        return self.python_ok and not self.missing_required

    def tex_ok(self) -> bool:
        return any(c.name == "pdflatex" and c.ok for c in self.checks)

    def summary(self) -> str:
        if self.ready and not self.missing_optional:
            return "环境就绪。"
        if self.ready:
            names = ", ".join(c.name for c in self.missing_optional)
            return f"环境就绪。可选依赖缺失：{names}。"
        names = ", ".join(c.name for c in self.missing_required)
        return f"缺少必需依赖：{names}。"


# --------------------------------------------------------------------------
# Probing
# --------------------------------------------------------------------------


def _version_of(module) -> Optional[str]:
    v = getattr(module, "__version__", None)
    if v:
        return str(v)
    try:
        from importlib.metadata import version as _v

        return _v(module.__name__)
    except Exception:
        return None


def _meets(found: Optional[str], minimum: Optional[str]) -> bool:
    if minimum is None or not found:
        return True
    def parts(s):
        out = []
        for chunk in s.split("."):
            digits = "".join(ch for ch in chunk if ch.isdigit())
            if digits == "":
                break
            out.append(int(digits))
        return out
    a, b = parts(found), parts(minimum)
    return a >= b[: len(a)] if a else True


def check_python(min_version: Tuple[int, int] = (3, 9)) -> Tuple[bool, str]:
    """Python 3.9+ is required.

    Not a guess: the codebase avoids PEP 604 unions (`str | None`) precisely
    because 3.9 is the floor, and `Optional[...]` is used everywhere instead.
    """
    v = sys.version_info
    ok = (v.major, v.minor) >= min_version
    return ok, f"Python {v.major}.{v.minor}.{v.micro}"


def find_tex() -> Optional[str]:
    """Locate pdflatex without relying on PATH (TeX Live often is not on it)."""
    found = shutil.which("pdflatex")
    if found:
        return found
    for cand in TEX_CANDIDATES:
        p = Path(cand)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def diagnose(verbose: bool = True) -> Diagnosis:
    """Probe the environment. Never installs anything."""
    d = Diagnosis()
    d.python_ok, d.python_detail = check_python()

    for import_name, pip_name, minimum, why in REQUIRED:
        c = _probe(import_name, pip_name, minimum, why, required=True)
        d.checks.append(c)

    for import_name, pip_name, minimum, why in OPTIONAL:
        c = _probe(import_name, pip_name, minimum, why, required=False)
        d.checks.append(c)

    tex = find_tex()
    d.checks.append(Check(
        name="pdflatex",
        ok=tex is not None,
        required=False,
        detail=tex or "未找到 —— 可以审计论文，但不能生成 PDF",
        fix=("安装 TeX Live：https://tug.org/texlive/ "
             "（macOS: brew install --cask mactex-no-gui；"
             "Windows: https://tug.org/texlive/windows.html）"),
        version=None,
    ))
    return d


def _probe(import_name, pip_name, minimum, why, required) -> Check:
    try:
        module = importlib.import_module(import_name)
    except ImportError:
        return Check(
            name=import_name, ok=False, required=required,
            detail=f"用于{why}",
            fix=f"{sys.executable} -m pip install {pip_name}",
        )
    version = _version_of(module)
    if not _meets(version, minimum):
        return Check(
            name=import_name, ok=False, required=required,
            detail=f"需要 >= {minimum}，用于{why}",
            fix=f"{sys.executable} -m pip install -U '{pip_name}>={minimum}'",
            version=version,
        )
    return Check(name=import_name, ok=True, required=required,
                 detail=why, version=version)


# --------------------------------------------------------------------------
# Installing
# --------------------------------------------------------------------------


def install_missing(
    diagnosis: Diagnosis,
    include_optional: bool = True,
    dry_run: bool = False,
) -> Tuple[bool, List[str]]:
    """Install what is missing. Returns (success, log lines).

    Only pip packages are installed; TeX is reported, never auto-installed,
    because a 2GB download is not something to start without asking.
    """
    targets = list(diagnosis.missing_required)
    if include_optional:
        targets += diagnosis.missing_optional

    # TeX is not a pip package.
    targets = [c for c in targets if c.name != "pdflatex"]

    if not targets:
        return True, ["没有需要安装的"]

    log: List[str] = []
    # One pip run for everything is faster and yields a single clear failure.
    pkgs = []
    for c in targets:
        # Recover the pip name from the fix command, which already encodes it.
        if c.fix and " -m pip install " in c.fix:
            pkgs.append(c.fix.split(" -m pip install ", 1)[1].strip().strip("'\""))
        else:
            pkgs.append(c.name)

    cmd = [sys.executable, "-m", "pip", "install", "--user"] + pkgs
    log.append("$ " + " ".join(cmd))
    if dry_run:
        return True, log

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1800,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.append(f"失败：{type(exc).__name__}: {exc}")
        return False, log

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        log.append(f"pip 退出码 {proc.returncode}")
        log.extend("  " + ln for ln in tail)
        return False, log

    log.append("已安装：" + "、".join(pkgs))
    return True, log


def recheck() -> Diagnosis:
    """Re-probe after an install, with import caches invalidated."""
    importlib.invalidate_caches()
    return diagnose()
