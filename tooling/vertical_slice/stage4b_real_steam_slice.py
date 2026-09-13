"""Run the Stage 4B real Steam slice through the HTTP product lifecycle.

The runner deliberately reports only redacted aggregate/provenance fields. It
does not select a provider, download a model, import a fake backend, or print
the API response containing review payloads.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_APP_ID = 553850
DEFAULT_REVIEW_COUNT = 80
DEFAULT_LANGUAGE = "english"
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "blocked"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--app-id", type=int, default=DEFAULT_APP_ID)
    parser.add_argument("--review-count", type=int, default=DEFAULT_REVIEW_COUNT)
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--output-language", default="zh")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--summary-out", type=Path, default=None)
    return parser


def _request_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "app_id": args.app_id,
        "review_count": args.review_count,
        "language": args.language,
        "filter": "recent",
        "persist": True,
        "output_language": args.output_language,
    }


def _immutable_summary(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata") or {}
    report = result.get("research_report") or {}
    population = report.get("recommendation", {}).get("population", {})
    unified = result.get("unified_research_result") or {}
    semantic = result.get("semantic_measurement_result")
    return {
        "run_id": result.get("run_id"),
        "app_id": result.get("app_id"),
        "status": "completed",
        "population_n": population.get("valid_n") or metadata.get("analysis_population_count"),
        "research_report_schema": report.get("schema_version"),
        "collection_complete": metadata.get("collection_complete"),
        "truncated_by_max_reviews": metadata.get("truncated_by_max_reviews"),
        "stop_reason": metadata.get("stop_reason"),
        "semantic_status": result.get("semantic_status"),
        "semantic_present": semantic is not None,
        "unified_result_fingerprint": unified.get("result_fingerprint"),
        "quantitative_persisted": unified.get("quantitative") == report,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.review_count <= 0:
        raise ValueError("review-count must be positive")
    base_url = args.base_url.rstrip("/")
    payload = _request_payload(args)
    response = requests.post(f"{base_url}/analyze", json=payload, timeout=60)
    response.raise_for_status()
    accepted = response.json()
    run_id = accepted.get("run_id") or (accepted.get("metadata") or {}).get("run_id")
    if not run_id:
        raise RuntimeError("/analyze did not return run_id")

    deadline = time.monotonic() + args.timeout_seconds
    terminal: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status_response = requests.get(f"{base_url}/analysis/{args.app_id}", timeout=30)
        status_response.raise_for_status()
        current = status_response.json()
        if current.get("run_id") == run_id and current.get("status") in TERMINAL_STATUSES:
            terminal = current
            break
        time.sleep(max(args.poll_seconds, 0.1))
    if terminal is None:
        raise TimeoutError(f"run did not reach a terminal state: {run_id}")

    # Importing storage here reads the immutable result only after HTTP lifecycle
    # completion. It does not fall back to the mutable latest app result.
    from apps.api.senti_next import storage

    immutable = storage.get_analysis_run_result(run_id)
    if not immutable:
        raise RuntimeError(f"immutable result not found for run: {run_id}")
    summary = _immutable_summary(immutable)
    summary["estimate"] = _estimate(base_url, payload)
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def _estimate(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{base_url}/analyze/estimate", json=payload, timeout=120)
    if response.status_code >= 400:
        return {"status": "unavailable", "http_status": response.status_code}
    value = response.json()
    return {
        "status": "available",
        "reviews_considered": value.get("reviews_considered"),
        "cached_reviews": value.get("cached_reviews"),
        "needs_refresh_reviews": value.get("needs_refresh_reviews"),
        "llm_reviews": value.get("llm_reviews"),
        "reasons": value.get("reasons") or {},
    }


def main() -> int:
    args = build_parser().parse_args()
    print(json.dumps(run(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
