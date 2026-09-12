"""Small in-process provider operation circuit; no external queue required."""
from __future__ import annotations

import threading
import time

from .errors import ProviderFailure


class ProviderOperationCircuit:
    def __init__(self, cooldown_seconds: float = 30.0) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._opened_until: dict[str, float] = {}

    def check(self, key: str) -> None:
        with self._lock:
            until = self._opened_until.get(key, 0.0)
            if until > time.monotonic():
                raise ProviderFailure(
                    "PROVIDER_SERVER",
                    "Provider operation circuit is open after a systemic failure.",
                    {"circuit_key": key, "cooldown_seconds": round(until - time.monotonic(), 3)},
                    False,
                )
            if until:
                self._opened_until.pop(key, None)

    def open(self, key: str) -> None:
        with self._lock:
            self._opened_until[key] = time.monotonic() + self.cooldown_seconds

    def close(self, key: str) -> None:
        with self._lock:
            self._opened_until.pop(key, None)


provider_operation_circuit = ProviderOperationCircuit()

