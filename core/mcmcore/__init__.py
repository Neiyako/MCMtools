"""MCMtools 核心包。

版本号只在这里定义一处，别处一律引用它。

为什么值得单独说：版本号散落多处时，打补丁的人没法判断"用户手上
这份到底修没修过那个 bug"。之前 `api.py` 里写死的 `0.4.0` 就是个
孤立字面量，和代码实际状态没有任何绑定关系。

发版流程：改这里的 `__version__`，然后 `git tag v<版本号>`。
用户报 bug 时让他跑 `./core/mcm --version`，一眼能对上是哪一份。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

__version__ = "0.5.0"

__all__ = ["__version__", "version_string", "git_revision"]


def git_revision(short: bool = True) -> Optional[str]:
    """当前 checkout 的 git 提交号；拿不到就返回 None。

    上报 bug 时附上这个值，能立刻排除"代码对不对得上"这一类问题。
    刻意不抛异常：装了 git 但目录不是仓库、或者根本没装 git，
    都不该影响程序启动。
    """
    import subprocess

    root = Path(__file__).resolve().parents[2]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short" if short else "HEAD", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    rev = (out.stdout or "").strip()
    return rev or None


def version_string(with_rev: bool = True) -> str:
    """给人和给机器看的版本串，例如 ``0.5.0+git.a1b2c3d``。

    带 git 号是因为"0.5.0"本身不足以定位一份出了问题的工作副本 ——
    中间可能有未发布的改动。
    """
    base = __version__
    if not with_rev:
        return base
    if os.environ.get("MCMTOOLS_NO_GIT") == "1":
        return base
    rev = git_revision()
    return f"{base}+git.{rev}" if rev else base
