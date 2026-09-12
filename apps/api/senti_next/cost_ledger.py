"""Durable, append-only LLM physical-call cost ledger."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from . import db

logger = logging.getLogger(__name__)

PRICING_VERSION = "p0.6-pricing-v1"
PRICING_SOURCE = "application-pricing-registry"

# Prices are USD per million tokens. Keep this registry versioned and snapshot
# the selected values into every row; never price historical calls at read time.
PRICING_REGISTRY: dict[tuple[str, str], dict[str, Any]] = {
    ("deepseek", "deepseek-v4-flash"): {"input": 0.14, "output": 0.28, "cached_input": 0.014, "currency": "USD"},
    ("deepseek", "deepseek-v4-pro"): {"input": 0.27, "output": 1.10, "cached_input": 0.027, "currency": "USD"},
}


def migrate_llm_calls(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            call_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            run_id TEXT,
            user_id TEXT,
            app_id INTEGER,
            purpose TEXT NOT NULL,
            phase TEXT,
            provider TEXT NOT NULL,
            model_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            latency_ms REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            total_tokens INTEGER,
            cached_input_tokens INTEGER,
            reasoning_tokens INTEGER,
            usage_status TEXT NOT NULL DEFAULT 'unavailable',
            attempt_number INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'started',
            error_type TEXT,
            error_code TEXT,
            fallback_used INTEGER NOT NULL DEFAULT 0,
            retryable INTEGER,
            currency TEXT,
            input_unit_price REAL,
            output_unit_price REAL,
            cached_input_unit_price REAL,
            estimated_cost REAL,
            provider_reported_cost REAL,
            cost_source TEXT NOT NULL DEFAULT 'unavailable',
            pricing_version TEXT,
            pricing_source TEXT,
            priced_at TEXT,
            prompt_version TEXT,
            taxonomy_version TEXT,
            input_hash TEXT,
            workload_type TEXT NOT NULL DEFAULT 'production',
            requested_review_count INTEGER,
            classified_review_count INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_run ON llm_calls(run_id, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_provider_model ON llm_calls(provider, model_id, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_purpose ON llm_calls(purpose, created_at DESC)")
    # Batch provenance is additive so existing desktop databases remain
    # readable and historical rows retain their original meaning.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(llm_calls)").fetchall()}
    additions = {
        "batch_id": "TEXT",
        "parent_batch_id": "TEXT",
        "review_count": "INTEGER",
        "is_retry": "INTEGER NOT NULL DEFAULT 0",
        "retry_reason": "TEXT",
        "split_depth": "INTEGER NOT NULL DEFAULT 0",
        "requested_max_tokens": "INTEGER",
        "finish_reason": "TEXT",
        "raw_response_chars": "INTEGER",
        "schema_valid": "INTEGER",
    }
    for name, declaration in additions.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE llm_calls ADD COLUMN {name} {declaration}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _context() -> dict[str, Any]:
    try:
        from .llm import _LLM_USAGE_CONTEXT
        return dict(_LLM_USAGE_CONTEXT.get() or {})
    except Exception:
        return {}


def input_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pricing_snapshot(provider: str, model_id: str) -> dict[str, Any]:
    price = PRICING_REGISTRY.get((provider, model_id))
    if not price:
        return {"currency": "USD", "pricing_version": PRICING_VERSION, "pricing_source": PRICING_SOURCE}
    return {**price, "pricing_version": PRICING_VERSION, "pricing_source": PRICING_SOURCE}


def estimate_cost(snapshot: dict[str, Any], input_tokens: int | None, output_tokens: int | None, cached_input_tokens: int | None = None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    cached = min(max(int(cached_input_tokens or 0), 0), int(input_tokens))
    regular_input = int(input_tokens) - cached
    if "input" not in snapshot or "output" not in snapshot:
        return None
    if snapshot.get("input") is None or snapshot.get("output") is None:
        return None
    if snapshot.get("cached_input") is None:
        snapshot = {**snapshot, "cached_input": snapshot["input"]}
    amount = (regular_input / 1_000_000) * float(snapshot["input"])
    amount += (cached / 1_000_000) * float(snapshot.get("cached_input", snapshot["input"]))
    amount += (int(output_tokens) / 1_000_000) * float(snapshot["output"])
    return round(amount, 12)


def start_call(provider: str, model_id: str, *, attempt_number: int | None = None, input_text: str | None = None, purpose: str | None = None, operation_id: str | None = None, requested_max_tokens: int | None = None) -> tuple[str, str]:
    ctx = _context()
    explicit_attempt = int(attempt_number if attempt_number is not None else 1)
    context_attempt = int(ctx.get("attempt_number") or 1)
    # A dynamic-batch retry invokes the provider's own retry loop again. Keep
    # the outer batch attempt in the ledger while preserving inner retries:
    # outer attempt 2 + provider attempt 1 => ledger attempt 2;
    # outer attempt 2 + provider attempt 2 => ledger attempt 3.
    attempt_number = max(explicit_attempt, context_attempt + explicit_attempt - 1)
    call_id = str(uuid.uuid4())
    operation_id = str(operation_id or ctx.get("operation_id") or uuid.uuid4())
    snapshot = pricing_snapshot(provider, model_id)
    started = _now()
    try:
        with db.get_connection() as conn:
            conn.execute(text("""
                INSERT INTO llm_calls (
                    call_id, operation_id, run_id, user_id, app_id, purpose, phase,
                    provider, model_id, started_at, attempt_number, status,
                    currency, input_unit_price, output_unit_price, cached_input_unit_price,
                    pricing_version, pricing_source, priced_at, prompt_version,
                    taxonomy_version, input_hash, workload_type, requested_review_count,
                    created_at, batch_id, parent_batch_id, review_count,
                    is_retry, retry_reason, split_depth, requested_max_tokens
                ) VALUES (
                    :call_id, :operation_id, :run_id, :user_id, :app_id, :purpose, :phase,
                    :provider, :model_id, :started_at, :attempt_number, 'started',
                    :currency, :input_price, :output_price, :cached_price,
                    :pricing_version, :pricing_source, :priced_at, :prompt_version,
                    :taxonomy_version, :input_hash, :workload_type, :requested_count,
                    :created_at, :batch_id, :parent_batch_id, :review_count,
                    :is_retry, :retry_reason, :split_depth, :requested_max_tokens
                )
            """), {
                "call_id": call_id, "operation_id": operation_id,
                "run_id": ctx.get("run_id"), "user_id": ctx.get("user_id", "local"),
                "app_id": ctx.get("app_id"), "purpose": purpose or ctx.get("operation") or "unknown",
                "phase": ctx.get("phase"), "provider": provider, "model_id": model_id,
                "started_at": started, "attempt_number": attempt_number,
                "currency": snapshot.get("currency"), "input_price": snapshot.get("input"),
                "output_price": snapshot.get("output"), "cached_price": snapshot.get("cached_input"),
                "pricing_version": snapshot.get("pricing_version"), "pricing_source": snapshot.get("pricing_source"),
                "priced_at": started, "prompt_version": ctx.get("prompt_version"),
                "taxonomy_version": ctx.get("taxonomy_version"), "input_hash": input_hash(input_text),
                "workload_type": ctx.get("workload_type", "production"),
                "requested_count": ctx.get("requested_review_count"), "created_at": started,
                "batch_id": ctx.get("batch_id"), "parent_batch_id": ctx.get("parent_batch_id"),
                "review_count": ctx.get("review_count"), "is_retry": int(bool(ctx.get("is_retry", False))),
                "retry_reason": ctx.get("retry_reason"), "split_depth": int(ctx.get("split_depth") or 0),
                "requested_max_tokens": requested_max_tokens,
            })
    except Exception:
        # Telemetry must not discard the provider result. The error is logged
        # loudly enough for operators/tests to observe.
        logger.exception("LLM cost ledger start failed for %s", call_id)
    return call_id, operation_id


def finish_call(call_id: str, *, started_at: datetime, status: str, usage: dict[str, int | None] | None = None, error: Exception | None = None, fallback_used: bool = False, retryable: bool | None = None, metadata: dict[str, Any] | None = None) -> None:
    usage = usage or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    cached_tokens = usage.get("cached_input_tokens")
    metadata = metadata or {}
    completed = _now()
    elapsed_ms = round((completed - started_at).total_seconds() * 1000, 3)
    try:
        with db.get_connection() as conn:
            row = conn.execute(text("SELECT input_unit_price, output_unit_price, cached_input_unit_price, currency FROM llm_calls WHERE call_id=:call_id"), {"call_id": call_id}).fetchone()
            snapshot = {"input": row[0], "output": row[1], "cached_input": row[2]} if row else {}
            estimated = estimate_cost(snapshot, input_tokens, output_tokens, cached_tokens)
            conn.execute(text("""
                UPDATE llm_calls SET completed_at=:completed_at, latency_ms=:latency_ms,
                    input_tokens=:input_tokens, output_tokens=:output_tokens,
                    total_tokens=:total_tokens, cached_input_tokens=:cached_tokens,
                    usage_status=:usage_status, estimated_cost=:estimated_cost,
                    cost_source=:cost_source, status=:status, error_type=:error_type,
                    error_code=:error_code, fallback_used=:fallback_used, retryable=:retryable,
                    finish_reason=:finish_reason, raw_response_chars=:raw_response_chars,
                    schema_valid=:schema_valid
                WHERE call_id=:call_id AND status='started'
            """), {
                "call_id": call_id, "completed_at": completed, "latency_ms": elapsed_ms,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "total_tokens": total_tokens, "cached_tokens": cached_tokens,
                "usage_status": "available" if input_tokens is not None or output_tokens is not None else "unavailable",
                "estimated_cost": estimated, "cost_source": "token_estimate" if estimated is not None else "unavailable",
                "status": status, "error_type": type(error).__name__ if error else None,
                "error_code": getattr(error, "status_code", None) if error else None,
                "fallback_used": int(bool(fallback_used)), "retryable": None if retryable is None else int(retryable),
                "finish_reason": metadata.get("finish_reason"),
                "raw_response_chars": metadata.get("raw_response_chars"),
                "schema_valid": metadata.get("schema_valid"),
            })
    except Exception:
        logger.exception("LLM cost ledger finish failed for %s", call_id)


def summarize(*, run_id: str | None = None, operation_type: str | None = None, provider: str | None = None, since: str | None = None, workload_type: str | None = "production") -> dict[str, Any]:
    clauses, params = ["1=1"], {}
    if run_id is not None:
        clauses.append("run_id=:run_id"); params["run_id"] = run_id
    if operation_type is not None:
        clauses.append("purpose=:purpose"); params["purpose"] = operation_type
    if provider is not None:
        clauses.append("provider=:provider"); params["provider"] = provider
    if since is not None:
        clauses.append("created_at >= :since"); params["since"] = since
    if workload_type is not None:
        clauses.append("workload_type=:workload_type"); params["workload_type"] = workload_type
    where = " AND ".join(clauses)
    with db.get_connection() as conn:
        row = conn.execute(text(f"""SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(cached_input_tokens),0), COALESCE(SUM(attempt_number-1),0), SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), COALESCE(SUM(estimated_cost),0) FROM llm_calls WHERE {where}"""), params).fetchone()
    return {"call_count": int(row[0] or 0), "input_tokens": int(row[1] or 0), "output_tokens": int(row[2] or 0), "cached_input_tokens": int(row[3] or 0), "retry_count": int(row[4] or 0), "failed_call_count": int(row[5] or 0), "estimated_cost": float(row[6] or 0), "currency": "USD", "workload_type": workload_type}


def list_calls(*, run_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    with db.get_connection() as conn:
        rows = conn.execute(text("SELECT call_id, operation_id, run_id, app_id, purpose, phase, provider, model_id, started_at, completed_at, latency_ms, input_tokens, output_tokens, total_tokens, cached_input_tokens, usage_status, attempt_number, status, estimated_cost, cost_source, pricing_version, workload_type FROM llm_calls WHERE (:run_id IS NULL OR run_id=:run_id) ORDER BY created_at DESC LIMIT :limit"), {"run_id": run_id, "limit": max(1, min(int(limit), 1000))}).mappings().all()
    return [dict(row) for row in rows]
