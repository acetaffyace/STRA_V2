# Steam Review Enrichment v1 — Acceptance Matrix

| Requirement | Evidence |
|---|---|
| Capture and preserve source fields | `steam_enrichment.py`, `storage.upsert_reviews` |
| Null/false semantics | canonical parser and targeted tests |
| Derived labels | deterministic helper tests |
| Developer response separation | API model and evidence isolation test |
| Player FTS unaffected | FTS contamination test |
| Analytics unchanged | dataframe invariance test; analysis paths inert |
| Legacy backfill | migration test |
| Idempotent migration | migration rerun test |
| Coverage diagnostics | `get_database_stats()` |
| Full regression | `.venv311` backend pytest, compile/import, frontend typecheck/lint/build all pass |
