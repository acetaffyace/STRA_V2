# P0 Local Operations Runbook

## Environment and startup

- Python: 3.10+; repository validation uses `.venv311\Scripts\python.exe`.
- Node: 20+; frontend is `apps/dashboard`.
- Backend: from repository root, run `./run_backend_local.sh` (or the
  documented PowerShell-equivalent `uvicorn apps.api.main:app --reload`).
- Frontend: from `apps/dashboard`, run `npm run dev`.
- Production frontend verification: `npx tsc --noEmit`, `npm run lint`,
  `npm run build`.

## Database

SQLite defaults to the platformdirs SentiNext data directory. Override with
`DATABASE_URL=sqlite:///absolute/path/sentinext.db`. On startup the existing
migration runner applies versions 1 through 8 idempotently; no manual SQL is
required.

## Backup and restore

Use the existing SQLite backup framework:

```python
from apps.api.senti_next.migrations import backup_database, restore_database
backup_database("path/to/sentinext.db", "path/to/sentinext.db.backup")
restore_database("path/to/sentinext.db.backup", "path/to/sentinext.db")
```

P0 migrations create version-specific `.bak` files and restore on migration
failure where configured. Stop the app before manual restore.

## FTS diagnostics

Use `verify_fts_integrity()` for duplicate/missing/orphan/drift checks and
`rebuild_fts()` for explicit repair. These are diagnostic/admin operations and
are not silently run on every normal startup.

## Runs, results, evidence and cost

- Inspect run status: `GET /runs/{run_id}`
- Retrieve immutable result: `GET /runs/{run_id}/result`
- Retrieve run evidence: `GET /runs/{run_id}/evidence`
- Retrieve run LLM cost and physical calls: `GET /runs/{run_id}/llm-cost`
- Production cost summary: `GET /llm-cost/summary`
- Evaluation-only cost summary: `GET /llm-cost/summary?workload_type=evaluation`

The cost ledger records provider attempts and token estimates; it is not a
billing-grade exactly-once financial system. Missing usage remains unavailable.

## Credentials and restart behavior

Set provider credentials in `.env.local` or the OS environment; never commit
keys. Supported variables include `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`,
`XAI_API_KEY`, and `OPENAI_API_KEY`. Do not paste keys into reports or logs.

FastAPI BackgroundTasks are not durable workers. After a process restart,
queued/running general analyses are marked failed with interruption semantics;
rerun them safely. No Redis/Celery worker is required for local use.

## Common diagnostics

1. Check `GET /health`.
2. Check database path and `schema_migrations`.
3. Check `/runs/{run_id}` and `/runs/{run_id}/llm-cost`.
4. Run the canonical backend pytest suite and import smoke.
5. Run FTS integrity verification if search results appear stale.
