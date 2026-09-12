"""Typed, safe provider failures used by offline and live execution paths."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderFailure(RuntimeError):
    """A provider failure with safe diagnostic metadata.

    Metadata must never contain prompts, review text, credentials, or headers.
    """

    code: str
    message: str
    metadata: dict[str, Any] | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)
        self.metadata = dict(self.metadata or {})


class EmptyResponseError(ProviderFailure):
    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        super().__init__("EMPTY_RESPONSE", "Provider returned an empty response.", metadata, False)


class ProxyDependencyError(ProviderFailure):
    def __init__(self, message: str) -> None:
        super().__init__("PROXY_DEPENDENCY", message, {}, False)


class ConfigurationProviderError(ProviderFailure):
    def __init__(self, message: str) -> None:
        super().__init__("CONFIGURATION", message, {}, False)

