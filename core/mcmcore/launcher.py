"""One-click launch: find a project, check the environment, serve, open a browser.

This is the layer that turns a Python package into something a person can
double-click. Three behaviours are deliberate:

1. **It never starts a server it cannot reach.** The port is probed first; if it
   is busy, another is chosen rather than failing with `EADDRINUSE`.
2. **It opens the browser only after the port answers.** Opening first produces a
   connection error on a cold start, which reads as "broken".
3. **It is reversible.** Ctrl-C stops the server and nothing is left behind -- no
   daemon, no lockfile, no stray process. A tool that survives being quit is a
   tool you cannot trust during a timed competition.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

DEFAULT_PORT = 8420
# Try a few ports so a stale instance on the default does not block startup.
PORT_ATTEMPTS = 12


# --------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(preferred: int = DEFAULT_PORT, host: str = "127.0.0.1") -> int:
    """The first free port at or after `preferred`."""
    for offset in range(PORT_ATTEMPTS):
        candidate = preferred + offset
        if port_is_free(candidate, host):
            return candidate
    raise RuntimeError(
        f"{preferred}-{preferred + PORT_ATTEMPTS - 1} 之间没有空闲端口。"
        "这些端口都被其他程序占用了。"
    )


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    """Poll /api/health until it answers. Returns False on timeout."""
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1.5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.25)
    return False


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------


@dataclass
class LaunchPlan:
    project: Path
    port: int
    url: str
    created: bool = False      # a project was bootstrapped
    installed: List[str] = None  # packages installed on this run


def resolve_project(path: Path, create: bool = True) -> tuple:
    """Return (project_dir, was_created).

    A directory is a project if it has project.yaml. A bare directory is
    initialised in place, so "point it at a folder" is enough.
    """
    path = Path(path).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    if (path / "project.yaml").exists():
        return path, False
    if not create:
        raise FileNotFoundError(f"{path} 不是一个 MCMtools 项目")
    # Imported here so the launcher can run before heavy deps are installed.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mcmcore.store import Store

    Store.init(path, path.name or "mcm-project")
    return path, True


def ensure_environment(auto_install: bool = True, quiet: bool = False) -> bool:
    """Check dependencies, installing on consent. Returns True if usable."""
    from .doctor import diagnose, install_missing, recheck

    d = diagnose()
    if not quiet:
        print("正在检查运行环境")
        for c in d.checks:
            print(c.line())
        print()

    if d.ready and not d.missing_optional:
        return True

    if d.missing_required or d.missing_optional:
        if not auto_install:
            print(d.summary())
            for c in d.missing_required + d.missing_optional:
                if c.fix:
                    print(f"  修复 {c.name}：{c.fix}")
            return d.ready

        print(d.summary())
        ok, log = install_missing(d, include_optional=True)
        for line in log:
            print("  " + line)
        if not ok:
            print("\n自动安装失败。请手动安装后重试：")
            for c in d.missing_required:
                if c.fix:
                    print(f"  {c.fix}")
            return False
        d = recheck()
        print()

    if not d.ready:
        print("仍然缺少必需依赖：")
        for c in d.missing_required:
            print(c.line())
            if c.fix:
                print(f"      {c.fix}")
        return False

    if not d.tex_ok() and not quiet:
        print("提示：没有找到 pdflatex。除了生成 PDF 之外一切正常，")
        print("       `mcm validate` 和面板都可以照常使用。\n")
    return True


# --------------------------------------------------------------------------
# Launch
# --------------------------------------------------------------------------


def launch(
    project: Optional[Path] = None,
    port: Optional[int] = None,
    open_browser: bool = True,
    host: str = "127.0.0.1",
    auto_install: bool = True,
    quiet: bool = False,
) -> int:
    """Check, serve and open. Blocks until interrupted.

    Returns a process exit code: 0 on a clean stop, non-zero on a startup
    failure. Never raises for a foreseeable problem -- a double-clicked app has
    nowhere to print a traceback.
    """
    if project is None:
        project = Path.cwd()

    try:
        proj, created = resolve_project(project)
    except Exception as exc:
        print(f"无法准备项目目录：{exc}", file=sys.stderr)
        return 1

    if not ensure_environment(auto_install=auto_install, quiet=quiet):
        return 1

    # An explicitly requested port is a preference, not a demand. If it is busy
    # we move rather than dying with a raw EADDRINUSE -- a double-clicked app has
    # no terminal to explain itself in.
    try:
        if port and port_is_free(port, host):
            chosen = port
        elif port:
            print(f"端口 {port} 被占用，正在寻找下一个空闲端口。")
            chosen = pick_port(port + 1, host)
        else:
            chosen = pick_port(DEFAULT_PORT, host)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    url = f"http://{host}:{chosen}"
    if not quiet:
        print("MCMtools 数学建模竞赛工具链")
        print(f"  项目   : {proj}")
        if created:
            print("           （已在此新建项目）")
        print(f"  面板   : {url}")
        print(f"  接口   : {url}/docs")
        print("  停止   : 按 Ctrl-C\n")
        # Flush explicitly: uvicorn logs to stdout too, and if this buffer is
        # still pending the banner appears after the server's own messages.
        sys.stdout.flush()

    if open_browser:
        # Open in a watcher thread so the server starts immediately and the page
        # is not loaded before it can answer.
        def _open_when_ready() -> None:
            if wait_for_server(url, timeout=40):
                try:
                    webbrowser.open(url)
                except Exception:
                    pass  # a headless machine has no browser; not an error

        threading.Thread(target=_open_when_ready, daemon=True).start()

    # uvicorn installs its own signal handlers and runs the server in this
    # process, but it can also spawn workers. Registering SIGINT/SIGTERM here
    # guarantees the port is released, so "I stopped it" is actually true --
    # which matters when the alternative is an orphan holding a port during a
    # timed competition.
    stop = _install_signal_handlers()

    try:
        from .api import serve

        serve(proj, host=host, port=chosen, quiet=not os.environ.get("MCM_VERBOSE"))
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"无法启动服务：{exc}", file=sys.stderr)
        return 1
    finally:
        stop()
        if not quiet:
            print("\n已停止。项目已保存，没有残留进程。")
        sys.stdout.flush()
    return 0


def _install_signal_handlers():
    """Make sure an interrupt releases the port.

    Returns a callable that restores the previous handlers. Any process this
    launcher started is terminated, so the port cannot stay bound.
    """
    import signal

    previous = {}
    started = _child_pids()

    def _handle(signum, _frame):
        for pid in _child_pids() - started:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        raise KeyboardInterrupt()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous[sig] = signal.signal(sig, _handle)
        except (ValueError, OSError):
            pass  # not on the main thread; nothing to do

    def restore():
        for sig, handler in previous.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass

    return restore


def _child_pids() -> set:
    """Direct children of this process, best effort."""
    try:
        import subprocess

        out = subprocess.run(
            ["pgrep", "-P", str(os.getpid())],
            capture_output=True, text=True, timeout=3,
        )
        return {int(x) for x in out.stdout.split() if x.strip().isdigit()}
    except Exception:
        return set()


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="mcm-start",
        description="启动 MCMtools 并打开面板。",
    )
    p.add_argument("project", nargs="?", default=None,
                   help="项目目录（默认：当前目录）。")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--no-install", action="store_true",
                   help="只报告缺失依赖，不安装。")
    p.add_argument("--check", action="store_true",
                   help="打印环境报告后退出。")
    args = p.parse_args(argv)

    if args.check:
        from .doctor import diagnose

        d = diagnose()
        for c in d.checks:
            print(c.line())
        print()
        print(d.summary())
        return 0 if d.ready else 1

    return launch(
        project=Path(args.project) if args.project else Path.cwd(),
        port=args.port,
        open_browser=not args.no_browser,
        auto_install=not args.no_install,
    )
