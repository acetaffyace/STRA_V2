"""Desktop-specific entry point for the SentiNext backend.

Runs as a PyInstaller-frozen sidecar binary launched by Tauri.
Sets up SQLite database in the platform data directory and starts uvicorn.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path


def _setup_env(port: int) -> None:
    """Configure environment variables for desktop mode."""
    # Keep packaged runtime identity distinct from the canonical integration
    # profile and report the actual sidecar port selected by the Tauri shell.
    os.environ["SENTINEXT_RUNTIME_PROFILE"] = "desktop"
    os.environ["SENTINEXT_BACKEND_PORT"] = str(port)
    # Freeze the packaged desktop build to the validated classifier and the
    # production batching defaults used by the local integration runtime.
    os.environ["SENTINEXT_CLASSIFIER_PROMPT_VARIANT"] = "v3_1"
    os.environ["SENTINEXT_REVIEW_PREPROCESS_MODE"] = "active"
    os.environ["SENTINEXT_DYNAMIC_BATCH_ENABLED"] = "true"
    os.environ.setdefault("SENTINEXT_LLM_BATCH_SIZE", "100")
    os.environ.setdefault("SENTINEXT_MAX_PARALLEL_BATCHES", "10")

    # Explicit CI/runtime-smoke directories override the legacy default.  If
    # unset, preserve the existing SentiNext platformdirs location exactly.
    explicit_dir = os.getenv("SENTINEXT_DATA_DIR", "").strip()
    if explicit_dir:
        data_dir = Path(explicit_dir).expanduser()
    else:
        try:
            from platformdirs import user_data_dir
            data_dir = Path(user_data_dir("SentiNext", "SentiNext"))
        except ImportError:
            data_dir = Path.home() / ".sentinext" / "data"

    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "sentinext.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    # Allow all origins for local Tauri webview
    os.environ["SENTINEXT_ALLOWED_ORIGINS"] = f"http://127.0.0.1:{port},http://localhost:{port},http://tauri.localhost,tauri://localhost,https://tauri.localhost"

    # Use the same data dir for LLM config and API keys
    os.environ.setdefault("SENTINEXT_DATA_DIR", str(data_dir))

    # Set log file location
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SENTINEXT_LOG_FILE"] = str(log_dir / "backend.log")


def _run_self_test() -> int:
    """Run deterministic checks inside the frozen executable itself."""
    with tempfile.TemporaryDirectory(prefix="sentinext-runtime-self-test-") as temp_dir:
        os.environ["SENTINEXT_DATA_DIR"] = temp_dir
        _setup_env(0)
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(temp_dir) / 'self-test.db'}"
        try:
            # Import the same production modules the sidecar serves.  These
            # imports deliberately do not download models or call providers.
            import apps.api.main  # noqa: F401
            from apps.api.senti_next import db, migrations
            from apps.api.senti_next.research_core import build_snapshot_research_report
            import apps.api.senti_next.rate_inference  # noqa: F401
            import apps.api.senti_next.embedding_backend  # noqa: F401
            import apps.api.senti_next.semantic_index  # noqa: F401
            import apps.api.senti_next.semantic_index_storage  # noqa: F401
            import apps.api.senti_next.semantic_discovery  # noqa: F401
            import apps.api.senti_next.semantic_discovery_storage  # noqa: F401

            db.close_engine()
            db.init_db()
            report = build_snapshot_research_report(
                [
                    {
                        "recommendationid": "runtime-self-test-1",
                        "review": "Runtime smoke review",
                        "voted_up": True,
                        "timestamp_created": 1700000000,
                    }
                ],
                metadata={"collection_complete": True},
            )
            if report.get("schema_version") != "research-report-v1":
                raise RuntimeError("research_core_schema_invalid")
            if report["population"]["review_count"] != 1 or "recommendation" not in report:
                raise RuntimeError("research_core_population_smoke_failed")
            with db.get_connection() as conn:
                schema = migrations.schema_status(conn.connection.driver_connection)
            if schema["status"] != "current" or schema["applied"] != schema["latest_known"]:
                raise RuntimeError(f"schema_not_current:{schema}")
            print(json.dumps({
                "self_test": "passed",
                "research_core": "passed",
                "stage3_imports": "passed",
                "schema": schema,
            }, sort_keys=True))
            return 0
        except Exception as exc:
            print(json.dumps({"self_test": "failed", "error": str(exc)[:200]}, sort_keys=True), file=sys.stderr)
            return 1
        finally:
            try:
                from apps.api.senti_next import db
                db.close_engine()
            except Exception:
                pass
            # apps.api.main installs a rotating file handler at import time;
            # close it before TemporaryDirectory cleanup on Windows.
            root_logger = logging.getLogger()
            for handler in list(root_logger.handlers):
                try:
                    handler.flush()
                    handler.close()
                finally:
                    root_logger.removeHandler(handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="SentiNext Desktop Backend")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--self-test", action="store_true", help="Run packaged runtime smoke and exit")
    args = parser.parse_args()

    if args.self_test:
        raise SystemExit(_run_self_test())

    _setup_env(args.port)

    # Import after env is set so db.get_database_url() sees SQLite URL
    import uvicorn

    # Add the api directory to sys.path so 'apps.api' package resolves
    api_dir = Path(__file__).resolve().parent.parent.parent / "api"
    if api_dir.exists() and str(api_dir.parent) not in sys.path:
        sys.path.insert(0, str(api_dir.parent.parent))

    uvicorn.run(
        "apps.api.main:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
