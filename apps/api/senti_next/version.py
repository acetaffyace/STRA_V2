"""Canonical STRA runtime/build identity."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

APP_VERSION = "0.9.0-alpha.1"


def git_sha() -> str:
    """Return the build commit, preferring injected frozen-build metadata."""
    injected = os.getenv("SENTINEXT_GIT_SHA", "").strip()
    if injected:
        return injected
    info_path = Path(__file__).with_name("build_info.json")
    try:
        payload = json.loads(info_path.read_text(encoding="utf-8"))
        value = str(payload.get("git_sha", "")).strip()
        if value:
            return value
    except (OSError, ValueError, TypeError):
        pass
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def build_identity(*, runtime_profile: str = "integration") -> dict[str, str]:
    return {
        "app_version": APP_VERSION,
        "git_sha": git_sha(),
        "runtime_profile": runtime_profile,
    }
