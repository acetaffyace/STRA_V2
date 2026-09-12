"""Desktop-specific entry point for the SentiNext backend.

Runs as a PyInstaller-frozen sidecar binary launched by Tauri.
Sets up SQLite database in the platform data directory and starts uvicorn.
"""
from __future__ import annotations

import argparse
import os
import sys
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

    # Use platformdirs for the data directory
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


def main() -> None:
    parser = argparse.ArgumentParser(description="SentiNext Desktop Backend")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    args = parser.parse_args()

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
