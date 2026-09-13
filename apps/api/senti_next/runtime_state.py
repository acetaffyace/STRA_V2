"""Thread-safe startup state used by health and endpoint gating."""
from __future__ import annotations

from enum import Enum
import threading


class StartupStatus(str, Enum):
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"


_lock = threading.RLock()
_status = StartupStatus.STARTING
_failure_reason: str | None = None


def reset() -> None:
    global _status, _failure_reason
    with _lock:
        _status = StartupStatus.STARTING
        _failure_reason = None


def mark_starting() -> None:
    reset()


def mark_ready() -> None:
    global _status, _failure_reason
    with _lock:
        _status = StartupStatus.READY
        _failure_reason = None


def mark_failed(reason: str) -> None:
    global _status, _failure_reason
    with _lock:
        _status = StartupStatus.FAILED
        # Keep diagnostics bounded and free of tracebacks/paths.
        cleaned = " ".join(str(reason).split())
        _failure_reason = cleaned[:200] or "startup_initialization_failed"


def status(*, legacy_event_set: bool = False) -> StartupStatus:
    with _lock:
        current = _status
    # A few legacy unit tests set startup_complete directly. Treat that as a
    # compatibility READY signal only while no explicit failure was recorded.
    if current is StartupStatus.STARTING and legacy_event_set:
        return StartupStatus.READY
    return current


def raw_status() -> StartupStatus:
    """Return the explicit state, ignoring the legacy compatibility event."""
    with _lock:
        return _status


def failure_reason() -> str | None:
    with _lock:
        return _failure_reason


def snapshot(*, legacy_event_set: bool = False) -> dict[str, str | None]:
    current = status(legacy_event_set=legacy_event_set)
    return {"status": current.value, "reason": failure_reason() if current is StartupStatus.FAILED else None}
