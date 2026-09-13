"""Local runtime identity and isolation helpers.

The integration profile is deliberately explicit so a frontend cannot mistake
an older backend or a different SQLite instance for the product runtime.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_CONTRACT_VERSION = "unified-analysis-v1"
CAPABILITIES = [
    "analysis-runs-active",
    "version-review-start",
    "exact-run-dashboard",
    "unified-global-queue",
]


def profile() -> str:
    return os.getenv("SENTINEXT_RUNTIME_PROFILE", "integration").strip() or "integration"


def backend_port() -> int:
    return int(os.getenv("SENTINEXT_BACKEND_PORT", os.getenv("PORT", "8000")))


def database_path() -> str | None:
    raw = os.getenv("DATABASE_URL", "")
    if raw.startswith("sqlite:///"):
        return str(Path(raw[10:]).expanduser().resolve())
    return None


def classifier_variant() -> str:
    value = os.getenv("SENTINEXT_CLASSIFIER_PROMPT_VARIANT", "legacy").strip().lower()
    return value if value in {"legacy", "v3", "v3_1"} else "legacy"


def classifier_prompt_version() -> str:
    return {
        "legacy": "steam_review_insights_v16_basic_labels",
        "v3": "steam_review_classifier_v3_compact",
        "v3_1": "steam_review_classifier_v3_1_request_strict",
    }[classifier_variant()]


def git_value(args: list[str], fallback: str = "unknown") -> str:
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=2, check=True)
        return result.stdout.strip() or fallback
    except Exception:
        return fallback


def database_instance_id() -> str:
    path = database_path() or "default"
    digest = hashlib.sha256(f"{profile()}:{path}".encode()).hexdigest()[:12]
    return f"{profile()}-{digest}"


def runtime_info() -> dict[str, Any]:
    from .version import build_identity
    from . import db, migrations

    identity = build_identity(runtime_profile=profile())
    startup = db.startup_status()
    schema = db.schema_status() if startup["status"] == "ready" else {
        "latest_known": migrations.latest_known_schema_version(),
        "applied": 0,
        "status": "uninitialized",
    }
    return {
        **identity,
        "runtime_profile": profile(),
        "backend_port": backend_port(),
        "git_commit": identity["git_sha"],
        "git_branch": git_value(["branch", "--show-current"]),
        "api_contract_version": API_CONTRACT_VERSION,
        "schema": schema,
        # Legacy field retained for existing clients; schema.latest_known is
        # the authoritative runtime value.
        "schema_migration_version": schema["applied"],
        "startup": startup,
        "database_instance_id": database_instance_id(),
        "classifier_variant": classifier_variant(),
        "classifier_prompt_version": classifier_prompt_version(),
        "started_at": os.getenv("SENTINEXT_RUNTIME_STARTED_AT") or datetime.now(timezone.utc).isoformat(),
        "capabilities": CAPABILITIES,
    }
