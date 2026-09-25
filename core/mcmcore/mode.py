"""Competition-mode enforcement.

The project's premise is that AI-assisted development happens **before** the
competition and the competition itself runs offline. Until now that was only a
recorded intent: `mode: competition` in project.yaml changed which audit checks
ran, but nothing actually stopped a network call or an AI-assisted edit.

A recorded intent is not a guarantee. This module makes it one, with three
deliberately different strengths of enforcement:

1. **Network guard** — hard block. A socket connection attempt raises. This is
   the real thing: it cannot be forgotten, and it fails loudly rather than
   silently working.
2. **Provenance stamping** — every number written during competition mode is
   stamped with the phase it was produced in. This does not prevent anything; it
   makes retroactive honesty possible, because a result produced at 03:00 on day
   two of the competition is permanently distinguishable from one produced in
   the months before.
3. **AI-assist block** — the CLI refuses AI-assisted commands in competition
   mode. The competition has no AI features to call today, so this is a guard
   against ones added later.

Why the guard is not "just turn off wifi": the failure mode we care about is a
*forgotten* import inside a pipeline or a charting library phoning home for a
font. A socket-level block catches exactly that and names the call site.
"""

from __future__ import annotations

import socket
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .schemas import RunMode


class CompetitionModeViolation(RuntimeError):
    """Raised when competition mode prevents an action."""


# --------------------------------------------------------------------------
# Current mode
# --------------------------------------------------------------------------


@dataclass
class ModeState:
    """Process-wide record of the active mode and anything it blocked."""

    mode: RunMode = RunMode.DEVELOPMENT
    violations: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def competition(self) -> bool:
        return self.mode == RunMode.COMPETITION


_state = ModeState()
_lock = threading.Lock()


def current_mode() -> RunMode:
    return _state.mode


def is_competition() -> bool:
    return _state.competition


def recorded_violations() -> List[Dict[str, Any]]:
    """Every blocked attempt, for the audit trail."""
    return list(_state.violations)


def set_mode(mode: RunMode) -> None:
    _state.mode = mode


@contextmanager
def competition_mode(enabled: bool = True):
    """Temporarily force a mode, restoring the previous one on exit."""
    previous = _state.mode
    _state.mode = RunMode.COMPETITION if enabled else RunMode.DEVELOPMENT
    try:
        yield _state
    finally:
        _state.mode = previous


def _record(kind: str, detail: str) -> None:
    with _lock:
        _state.violations.append({
            "kind": kind,
            "detail": detail,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })


# --------------------------------------------------------------------------
# 1. Network guard
# --------------------------------------------------------------------------


class NetworkBlocked(CompetitionModeViolation):
    pass


# Addresses that are always allowed: the loopback interface and the Unix socket
# family are local by definition. Blocking them would break things that have
# nothing to do with reaching the outside world.
_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})


def _is_local(address: Any) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if not isinstance(host, str):
        return False
    if host in _LOCAL_HOSTS:
        return True
    # 127.0.0.0/8
    return host.startswith("127.")


_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_getaddrinfo = socket.getaddrinfo
_patched = False


def _guarded_connect(self, address, *args, **kwargs):
    if _state.competition and not _is_local(address):
        detail = f"connect to {address!r}"
        _record("network", detail)
        raise NetworkBlocked(
            f"Competition mode blocks network access: {detail}. "
            "The toolchain is offline by design during the competition. "
            "Disable competition mode to allow this."
        )
    return _original_connect(self, address, *args, **kwargs)


def _guarded_connect_ex(self, address, *args, **kwargs):
    if _state.competition and not _is_local(address):
        detail = f"connect_ex to {address!r}"
        _record("network", detail)
        raise NetworkBlocked(
            f"Competition mode blocks network access: {detail}."
        )
    return _original_connect_ex(self, address, *args, **kwargs)


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    # DNS is the first thing that leaks intent, but resolving a localhost name
    # is legitimate, so only block non-local lookups.
    if _state.competition and host not in _LOCAL_HOSTS:
        if not (isinstance(host, str) and host.startswith("127.")):
            detail = f"DNS lookup of {host!r}"
            _record("dns", detail)
            raise NetworkBlocked(
                f"Competition mode blocks DNS lookups: {detail}."
            )
    return _original_getaddrinfo(host, port, *args, **kwargs)


def install_network_guard() -> None:
    """Patch socket entry points. Idempotent."""
    global _patched
    if _patched:
        return
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.getaddrinfo = _guarded_getaddrinfo
    _patched = True


def remove_network_guard() -> None:
    """Restore the original socket functions (used by tests)."""
    global _patched
    if not _patched:
        return
    socket.socket.connect = _original_connect
    socket.socket.connect_ex = _original_connect_ex
    socket.getaddrinfo = _original_getaddrinfo
    _patched = False


def network_guard_installed() -> bool:
    return _patched


@contextmanager
def enforce_network_block(enabled: bool = True):
    """Install the guard for the duration of a block."""
    if enabled:
        install_network_guard()
        _state.mode = RunMode.COMPETITION
    try:
        yield
    finally:
        if enabled:
            remove_network_guard()


# --------------------------------------------------------------------------
# 2. Provenance stamping
# --------------------------------------------------------------------------


def stamp_provenance(metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Tag a result record with the mode and time it was produced in.

    This is the honest half of enforcement. It blocks nothing, but it means a
    number computed during the competition is permanently distinguishable from
    one computed beforehand, so a later reviewer can tell which is which without
    trusting anyone's memory.
    """
    out = dict(metadata or {})
    out["produced_in_mode"] = _state.mode.value
    out["produced_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


# --------------------------------------------------------------------------
# 3. AI-assist block
# --------------------------------------------------------------------------


def require_development(feature: str) -> None:
    """Refuse an AI-assisted feature while competition mode is active."""
    if _state.competition:
        _record("ai_feature", feature)
        raise CompetitionModeViolation(
            f"'{feature}' is an AI-assisted development feature and is "
            "unavailable in competition mode. The competition period must not "
            "depend on AI."
        )


def mode_status() -> Dict[str, Any]:
    """A summary for the API and the Overview screen."""
    return {
        "mode": _state.mode.value,
        "competition": _state.competition,
        "network_guard_installed": _patched,
        "violations": recorded_violations(),
        "blocked_outbound": [
            v for v in recorded_violations() if v["kind"] in ("network", "dns")
        ],
    }
