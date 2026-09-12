"""Small local P0.6 ledger overhead benchmark."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from apps.api.senti_next.cost_ledger import migrate_llm_calls


def main() -> None:
    path = Path(".p0_6-ledger-benchmark.db")
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        migrate_llm_calls(conn)
        started = time.perf_counter()
        for i in range(1000):
            conn.execute("INSERT INTO llm_calls (call_id, operation_id, purpose, provider, model_id, started_at, status, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'), 'completed', datetime('now'))", (f"call-{i}", f"op-{i // 20}", "classify", "fixture", "fixture-model"))
        conn.commit()
        insert_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        conn.execute("SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(estimated_cost),0) FROM llm_calls WHERE operation_id=?", ("op-1",)).fetchone()
        run_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        conn.execute("SELECT date(created_at), COUNT(*) FROM llm_calls GROUP BY date(created_at)").fetchall()
        daily_ms = (time.perf_counter() - started) * 1000
    finally:
        conn.close()
    path.unlink(missing_ok=True)
    print(f"inserts_1000_ms={insert_ms:.3f} per_run_ms={run_ms:.3f} daily_ms={daily_ms:.3f}")


if __name__ == "__main__":
    main()
