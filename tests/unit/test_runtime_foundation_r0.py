from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import sqlite3
import sys

import pytest

from fastapi.responses import JSONResponse

from apps.api.senti_next import db, migrations, runtime_state
from apps.api.senti_next.routes.settings import healthcheck
from apps.api.senti_next.version import APP_VERSION


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def restore_legacy_test_startup_state():
    """Do not leak explicit startup-state mutations into unrelated tests."""
    yield
    runtime_state.reset()
    db.startup_complete.set()


def test_dependency_topology_has_shared_core_and_desktop_reuses_it() -> None:
    core = (ROOT / "apps/api/requirements-core.txt").read_text(encoding="utf-8")
    desktop = (ROOT / "apps/desktop/pyinstaller/requirements-desktop.txt").read_text(encoding="utf-8")
    assert "statsmodels==0.14.5" in core
    assert "socksio==1.0.0" in core
    assert "onnxruntime==1.20.1" in core
    assert "hdbscan==0.8.40" in core
    assert "-r ../../api/requirements-core.txt" in desktop
    assert "statsmodels" not in desktop


def test_migration_registry_is_unique_and_has_single_latest_source() -> None:
    versions = [version for version, _ in migrations.MIGRATION_REGISTRY]
    assert versions == sorted(set(versions))
    assert migrations.latest_known_schema_version() == 23
    assert not hasattr(migrations, "CURRENT_SCHEMA_VERSION")


def test_fresh_database_reaches_latest_known_schema(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'fresh.db'}")
    db.close_engine()
    db.init_db()
    with db.get_connection() as conn:
        status = migrations.schema_status(conn.connection.driver_connection)
    assert status["status"] == "current"
    assert status["applied"] == status["latest_known"]
    db.close_engine()


def test_applied_schema_status_reports_ahead_without_silent_current() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT, description TEXT)")
    conn.execute("INSERT INTO schema_migrations(version, description) VALUES (999, 'future')")
    assert migrations.schema_status(conn)["status"] == "ahead"
    conn.close()


def test_explicit_data_directory_overrides_legacy_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SENTINEXT_DATA_DIR", str(tmp_path / "runtime"))
    assert Path(db._default_sqlite_path()) == tmp_path / "runtime" / "sentinext.db"


def test_startup_state_machine_failure_is_not_ready(monkeypatch) -> None:
    runtime_state.reset()
    db.startup_complete.clear()
    assert db.startup_status()["status"] == "starting"
    runtime_state.mark_failed("migration failed: secret path omitted")
    assert db.startup_status()["status"] == "failed"
    assert runtime_state.failure_reason() == "migration failed: secret path omitted"
    runtime_state.mark_ready()
    db.startup_complete.set()
    assert db.startup_status()["status"] == "ready"


def test_health_returns_503_for_failed_startup(monkeypatch) -> None:
    runtime_state.reset()
    db.startup_complete.clear()
    runtime_state.mark_failed("migration_failed")
    response = healthcheck()
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert response.body and b"startup_failed" in response.body
    runtime_state.reset()


def test_canonical_version_matches_desktop_metadata() -> None:
    tauri = json.loads((ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    desktop_package = json.loads((ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))
    cargo = (ROOT / "apps/desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8")
    assert APP_VERSION == "0.9.0-alpha.1"
    assert tauri["version"] == APP_VERSION
    assert desktop_package["version"] == APP_VERSION
    assert f'version = "{APP_VERSION}"' in cargo


def test_frozen_self_test_and_runtime_smoke_are_declared() -> None:
    desktop_main = (ROOT / "apps/desktop/pyinstaller/desktop_main.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/desktop-runtime-smoke.yml").read_text(encoding="utf-8")
    assert "--self-test" in desktop_main
    assert "desktop-runtime-smoke" in workflow
    assert "smoke_desktop_sidecar.py" in workflow


def test_build_info_reads_version_without_importing_api_package(monkeypatch) -> None:
    """The outer host Python need not have desktop analytical dependencies."""
    build_path = ROOT / "apps/desktop/pyinstaller/build.py"
    spec = importlib.util.spec_from_file_location("stage_r0_build", build_path)
    assert spec and spec.loader
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)

    # Simulate the host interpreter before the clean desktop venv exists: the
    # package initializer and pandas are deliberately unavailable.  runpy on
    # version.py must still produce build metadata from stdlib-only code.
    monkeypatch.setitem(sys.modules, "apps.api.senti_next", None)
    monkeypatch.setitem(sys.modules, "pandas", None)
    info_path = build.write_build_info(ROOT)
    try:
        payload = json.loads(info_path.read_text(encoding="utf-8"))
        assert payload["app_version"] == APP_VERSION
        assert payload["git_sha"]
    finally:
        info_path.unlink(missing_ok=True)
