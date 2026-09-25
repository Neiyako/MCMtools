"""Pick a Python that can actually run MCMtools.

Choosing by version number alone is wrong, and this was learned the hard way:
on a machine with both the system Python 3.9 (which had every dependency
installed) and a newer Homebrew Python 3.13 (which had only some), preferring
the *newer* one selected an interpreter that could not run the tool -- and then
the automatic install failed on a TLS certificate error, so startup aborted
even though a perfectly working interpreter was sitting right next to it.

The rule is therefore: **a candidate is viable only if it can import what the
tool needs.** Version is a floor, not the objective.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

# Import name -> pip name. The core set that must be importable to serve.
REQUIRED_IMPORTS = ("pydantic", "yaml", "numpy", "matplotlib")
PANEL_IMPORTS = ("fastapi", "uvicorn")


def _run(exe: str, code: str, timeout: int = 20) -> Optional[str]:
    try:
        out = subprocess.run(
            [exe, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def version_of(exe: str) -> Optional[Tuple[int, int]]:
    out = _run(exe, "import sys;print('%d.%d' % sys.version_info[:2])")
    if not out:
        return None
    try:
        major, minor = (int(x) for x in out.strip().split("."))
        return (major, minor)
    except ValueError:
        return None


def missing_deps(exe: str) -> List[str]:
    """Which required packages this interpreter cannot import.

    `import importlib.util` must be explicit -- `import importlib` alone does not
    bind the `util` submodule, so `importlib.util.find_spec` raises
    AttributeError. Getting that wrong made this function report EVERY package
    as missing on a machine that had all of them, which would have pushed a
    perfectly working install down the (failing) auto-install path.
    """
    code = (
        "import importlib.util\n"
        f"names = {REQUIRED_IMPORTS!r}\n"
        "print(','.join(n for n in names "
        "if importlib.util.find_spec(n) is None))\n"
    )
    out = _run(exe, code)
    if out is None:
        return list(REQUIRED_IMPORTS)  # 解释器本身有问题
    return [n for n in out.strip().split(",") if n]


def candidates() -> List[str]:
    """本机上所有可能的 Python 3，新版本在前。"""
    if platform.system() == "Windows":
        names = ["py", "python3", "python"]
        found = [shutil.which(n) for n in names]
        # `py` 是启动器，不是解释器本身；用它时要加 -3。
        return [f for f in found if f]

    fixed = [
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
    ]
    found = [p for p in fixed if os.access(p, os.X_OK)]
    found += [shutil.which(n) for n in ("python3.13", "python3.12", "python3.11",
                                        "python3.10", "python3.9", "python3")]
    # 去重但保序
    seen, out = set(), []
    for f in found:
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def choose(min_version: Tuple[int, int] = (3, 9), verbose: bool = False) -> str:
    """返回一个**能跑起来**的 Python 路径。

    优先选依赖齐全的；没有的话退回到版本够新的那个，交给启动器去装。
    """
    viable, need_install = [], []

    for exe in candidates():
        v = version_of(exe)
        if v is None or v < min_version:
            if verbose and v:
                print(f"  跳过 {exe}：Python {v[0]}.{v[1]} 版本过低")
            continue
        miss = missing_deps(exe)
        if miss:
            need_install.append((exe, v, miss))
            if verbose:
                print(f"  {exe}: Python {v[0]}.{v[1]}，缺少 {', '.join(miss)}")
        else:
            viable.append((exe, v))
            if verbose:
                print(f"  {exe}: Python {v[0]}.{v[1]}，依赖齐全")

    if viable:
        # 依赖都齐全时，才按版本高低选。
        viable.sort(key=lambda t: t[1], reverse=True)
        return viable[0][0]

    if need_install:
        # 没有一个是齐全的。挑缺得最少的那个（安装量最小、最可能成功），
        # 并列时挑版本新的。
        need_install.sort(key=lambda t: (len(t[2]), -t[1][0], -t[1][1]))
        return need_install[0][0]

    return sys.executable
