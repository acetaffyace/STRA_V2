"""P0.6 durable physical-call ledger correctness tests."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from apps.api.senti_next import cost_ledger


def test_migration_is_idempotent_and_adds_expected_indexes(tmp_path):
    path = tmp_path / "ledger.db"
    with sqlite3.connect(path) as conn:
        cost_ledger.migrate_llm_calls(conn)
        cost_ledger.migrate_llm_calls(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_calls)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(llm_calls)")}
    assert {"call_id", "operation_id", "run_id", "attempt_number", "estimated_cost", "cost_source", "pricing_version"} <= columns
    assert {"idx_llm_calls_run", "idx_llm_calls_created", "idx_llm_calls_provider_model", "idx_llm_calls_purpose"} <= indexes


def test_pricing_snapshot_is_deterministic_and_unknown_usage_is_not_zero():
    snapshot = cost_ledger.pricing_snapshot("deepseek", "deepseek-v4-flash")
    assert snapshot["pricing_version"] == "p0.6-pricing-v1"
    assert cost_ledger.estimate_cost(snapshot, 100, 20) is not None
    assert cost_ledger.estimate_cost(snapshot, None, 20) is None
    assert cost_ledger.pricing_snapshot("ollama", "local-model")["currency"] == "USD"
    assert cost_ledger.estimate_cost(cost_ledger.pricing_snapshot("ollama", "local-model"), 100, 20) is None


def test_physical_attempt_rows_and_aggregation(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'app.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    from apps.api.senti_next import db
    db.close_engine()
    db._engine = None
    db.init_db()
    from apps.api.senti_next.llm import llm_usage_context
    with llm_usage_context(run_id="run-a", app_id=7, operation="classify", phase="classifying"):
        call_a, operation_id = cost_ledger.start_call("deepseek", "deepseek-v4-flash", attempt_number=1, input_text="safe prompt")
        cost_ledger.finish_call(call_a, started_at=datetime.now(timezone.utc), status="failed", usage={"input_tokens": 100, "output_tokens": 20}, error=RuntimeError("schema"), retryable=True)
        call_b, operation_id_b = cost_ledger.start_call("deepseek", "deepseek-v4-flash", attempt_number=2, operation_id=operation_id, input_text="safe prompt")
        cost_ledger.finish_call(call_b, started_at=datetime.now(timezone.utc), status="completed", usage={"input_tokens": 100, "output_tokens": 18})
    with db.get_connection() as conn:
        rows = conn.exec_driver_sql("SELECT call_id, operation_id, run_id, status, estimated_cost, usage_status FROM llm_calls ORDER BY attempt_number").fetchall()
    summary = cost_ledger.summarize(run_id="run-a")
    assert len(rows) == 2
    assert rows[0][1] == rows[1][1] == operation_id
    assert all(row[2] == "run-a" for row in rows)
    assert rows[0][3] == "failed" and rows[0][4] is not None
    assert rows[1][3] == "completed" and rows[1][4] is not None
    assert summary["call_count"] == 2
    assert summary["retry_count"] == 1
    assert summary["failed_call_count"] == 1
    db.close_engine()
    db._engine = None


def test_unknown_usage_remains_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'unknown.db'}")
    from apps.api.senti_next import db
    db.close_engine(); db._engine = None; db.init_db()
    call_id, _ = cost_ledger.start_call("ollama", "local-model", purpose="chat")
    cost_ledger.finish_call(call_id, started_at=datetime.now(timezone.utc), status="completed", usage={})
    with db.get_connection() as conn:
        row = conn.exec_driver_sql("SELECT input_tokens, output_tokens, estimated_cost, cost_source, usage_status FROM llm_calls WHERE call_id=?", (call_id,)).fetchone()
    assert row == (None, None, None, "unavailable", "unavailable")
    db.close_engine(); db._engine = None


def test_production_summary_excludes_evaluation_workload(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'workload.db'}")
    from apps.api.senti_next import db
    db.close_engine(); db._engine = None; db.init_db()
    production_id, _ = cost_ledger.start_call("fixture", "fixture-model", purpose="classify")
    cost_ledger.finish_call(production_id, started_at=datetime.now(timezone.utc), status="completed", usage={"input_tokens": 10, "output_tokens": 2})
    from apps.api.senti_next.llm import llm_usage_context
    with llm_usage_context(workload_type="evaluation"):
        evaluation_id, _ = cost_ledger.start_call("fixture", "fixture-model", purpose="benchmark")
    cost_ledger.finish_call(evaluation_id, started_at=datetime.now(timezone.utc), status="completed", usage={"input_tokens": 1000, "output_tokens": 200})
    assert cost_ledger.summarize()["call_count"] == 1
    assert cost_ledger.summarize(workload_type="evaluation")["call_count"] == 1
    db.close_engine(); db._engine = None
