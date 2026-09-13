#!/usr/bin/env python3
"""Deterministic smoke for the actual frozen Windows desktop sidecar."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get_json(url: str) -> tuple[int, dict]:
    with urlopen(url, timeout=3) as response:
        body = json.loads(response.read().decode("utf-8"))
        return int(response.status), body


def _run_self_test(exe: Path, env: dict[str, str]) -> None:
    result = subprocess.run([str(exe), "--self-test"], env=env, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"self_test_failed: {result.stdout[-2000:]} {result.stderr[-2000:]}")
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"self_test_failed: invalid output {result.stdout[-2000:]}") from exc
    if payload.get("self_test") != "passed":
        raise RuntimeError(f"self_test_failed: {payload}")


def run(exe: Path, *, timeout_seconds: float = 60.0) -> dict:
    if not exe.is_file():
        raise FileNotFoundError(f"build_failed: {exe}")
    with tempfile.TemporaryDirectory(prefix="sentinext-desktop-smoke-") as temp_dir:
        env = os.environ.copy()
        env["SENTINEXT_DATA_DIR"] = temp_dir
        _run_self_test(exe, env)

        port = _free_port()
        env["SENTINEXT_BACKEND_PORT"] = str(port)
        log_fd, log_name = tempfile.mkstemp(prefix="sentinext-sidecar-", suffix=".log")
        os.close(log_fd)
        log_path = Path(log_name)
        log_handle = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(
            [str(exe), "--port", str(port)],
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + timeout_seconds
        health: dict = {}
        health_status = 0
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    log_handle.flush()
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                    raise RuntimeError(f"unexpected_exit: code={process.returncode} {tail}")
                try:
                    health_status, health = _get_json(f"http://127.0.0.1:{port}/health")
                    if health.get("status") == "startup_failed":
                        raise RuntimeError(f"startup_failed: {health}")
                    if health_status == 200 and health.get("status") in {"ready", "ok"}:
                        break
                except HTTPError as exc:
                    try:
                        payload = json.loads(exc.read().decode("utf-8"))
                    except (ValueError, OSError):
                        payload = {}
                    if payload.get("status") == "startup_failed":
                        raise RuntimeError(f"startup_failed: {payload}") from exc
                except (URLError, TimeoutError, ConnectionError):
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError(f"health_timeout: {health}")

            info_status, info = _get_json(f"http://127.0.0.1:{port}/runtime-info")
            if info_status != 200:
                raise RuntimeError(f"runtime_info_invalid: status={info_status} body={info}")
            schema = info.get("schema") or {}
            if schema.get("status") != "current" or schema.get("applied") != schema.get("latest_known"):
                raise RuntimeError(f"schema_not_current: {schema}")
            if info.get("runtime_profile") != "desktop":
                raise RuntimeError(f"runtime_info_invalid: {info}")
            if info.get("app_version") == "0.8.2":
                raise RuntimeError("runtime_info_invalid: stale application version")
            return {"port": port, "health": health, "runtime_info": info}
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
            if os.name == "nt":
                # PyInstaller/uvicorn may leave a short-lived child holding
                # the inherited log handle; terminate the process tree before
                # TemporaryDirectory cleanup on Windows.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
                # One-file PyInstaller bootstraps can detach the extracted
                # child before the parent reports exit.  The image name is
                # the exact generated sidecar, so clean up that child too.
                subprocess.run(
                    ["taskkill", "/IM", exe.name, "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            if process.poll() is None:
                process.wait(timeout=10)
            log_handle.close()
            try:
                log_path.unlink(missing_ok=True)
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke the frozen STRA desktop sidecar")
    parser.add_argument("--exe", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.exe.resolve())
    except Exception as exc:
        print(f"desktop-runtime-smoke: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"desktop_runtime_smoke": "passed", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
