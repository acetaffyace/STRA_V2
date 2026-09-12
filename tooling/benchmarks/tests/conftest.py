"""Test fixtures that avoid host-specific pytest temp directory ACLs."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def tmp_path() -> Path:
    """Provide an isolated writable directory under the repository workspace.

    Some managed Windows environments deny directory enumeration under the
    user's global pytest temp root. Keeping benchmark artifacts local makes the
    tests deterministic without changing production code or benchmark inputs.
    """
    path = Path.cwd() / ".benchmark-test-tmp" / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
