"""Safe local runtime checks used before starting a development backend."""
from __future__ import annotations

import importlib.util
import os
from urllib.parse import urlparse


def diagnose_runtime() -> dict[str, object]:
    missing = [name for name in ("pydantic", "fastapi", "sqlalchemy", "httpx") if importlib.util.find_spec(name) is None]
    proxy_values = [os.getenv(name, "").strip() for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")]
    socks_proxy = any(urlparse(value).scheme.lower().startswith("socks") for value in proxy_values if value)
    socksio_missing = socks_proxy and importlib.util.find_spec("socksio") is None
    return {
        "missing_required_packages": missing,
        "socks_proxy_detected": socks_proxy,
        "socksio_missing": socksio_missing,
        "ready": not missing and not socksio_missing,
    }


def assert_runtime_ready() -> None:
    result = diagnose_runtime()
    if result["missing_required_packages"]:
        raise RuntimeError("Missing backend dependencies: " + ", ".join(result["missing_required_packages"]))
    if result["socksio_missing"]:
        raise RuntimeError("SOCKS proxy detected but socksio is missing; install apps/api/requirements.txt")

