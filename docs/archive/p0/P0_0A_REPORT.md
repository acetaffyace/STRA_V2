# P0.0A Report — Baseline, Contract Harness, Migration Foundation

Status: **P0.0A complete; P0.1 FTS is not started.**

## Baseline and checkpoint

- Branch: `codex/p0-player-voice-hardening`
- Checkpoint commit: `7ec4adc` (`checkpoint: baseline before P0 hardening`)
- No existing files were deleted, reverted, stashed, or overwritten.
- The checkpoint includes the previously dirty project state plus the audit documents.
- Current P0.0A implementation changes are intentionally after that checkpoint and remain reviewable as working-tree changes.

## Files changed

Added:

- `apps/api/senti_next/migrations.py`
- `apps/api/tests/test_p0_migration.py`
- `apps/api/tests/test_p0_contracts.py`
- `P0_0A_REPORT.md`

Modified:

- `apps/api/senti_next/db.py` — creates and records `schema_migrations` bootstrap version 1.

No FTS schema, review key, analysis run, dashboard, ingestion, or provider business logic was changed.

## Contract harness

Regression coverage is separate from future-P0 coverage.

Regression tests that must remain green:

- database initialization;
- one review upsert and current FTS searchability;
- migration fresh database, existing database, repeated startup/idempotency;
- backup creation and source preservation;
- failed migration restore.

Future-P0 tests are explicit non-strict `xfail` tests and are not treated as regressions:

- repeated upsert/update/delete FTS invariant;
- complete label cache identity;
- metric provenance contract;
- fallback exclusion from formal denominators;
- fabricated quote rejection;
- one provider attempt represented as a future ledger record.

The full pytest suite could not run because neither the system Python nor the bundled Python has `pytest` installed. The changed files pass AST parsing. A direct temporary-file smoke test passed migration ordering, idempotent re-run, backup/restore, and failed-migration restore.

An existing pre-P0 syntax issue was also surfaced by the repository-wide AST smoke: `apps/api/evaluate_labeling.py:365-366` has an `else` with an unindented body. It is recorded as a pre-existing regression/blocker and was not changed in P0.0A.

## Migration architecture

Chosen: a small internal SQLite migration foundation, not Alembic.

Rationale:

- `apps/desktop/pyinstaller/requirements-desktop.txt` explicitly excludes Alembic.
- `apps/desktop/pyinstaller/sentinext-backend.spec` excludes Alembic from the frozen bundle.
- The application is local-first and SQLite-only; a small ordered runner avoids a new desktop dependency.
- The runner supports ordered version entries, idempotent application, per-migration transactions, logging, and optional backup/restore on failure.

The current application schema is recorded as version 1, `legacy schema bootstrap`. The runner deliberately contains no FTS migration. P0.1 must add that as a later, separately reviewed migration.

## Backup / restore behavior

`migrations.py` uses SQLite's backup API to create a consistent backup before a migration run when a source file exists. On migration failure it rolls back the active transaction and, when `restore_on_error=True`, restores the pre-run backup. Backup creation and failed-migration restore were directly smoke-tested against temporary workspace SQLite files. Source DB contents were preserved after backup and restore.

## Required discovery for P0.1

### Rowid

`reviews` has `id INTEGER PRIMARY KEY AUTOINCREMENT` in `apps/api/senti_next/db.py:119-127`; this is a normal stable SQLite rowid alias. It is suitable for an external-content FTS `content_rowid` design, subject to verifying update/delete trigger behavior in P0.1 tests.

### Review upsert semantics

`apps/api/senti_next/storage.py:148-155` uses:

```sql
INSERT INTO reviews (...)
ON CONFLICT(review_id) DO UPDATE SET
    data = EXCLUDED.data,
    timestamp_updated = EXCLUDED.timestamp_updated
```

No `INSERT OR REPLACE` production path was found. The existing global `review_id` uniqueness model remains unchanged.

### Cross-app collision audit

Query executed against the existing local database:

```sql
SELECT review_id, COUNT(DISTINCT app_id)
FROM reviews
GROUP BY review_id
HAVING COUNT(DISTINCT app_id) > 1;
```

Result: **0 rows**, with **0 total reviews** in the local database. This is a valid current-data result but not historical proof; keep the global key model and add a non-empty fixture/data audit before considering any key change.

### FTS write-path inventory

Production write path:

- `apps/api/senti_next/storage.py:170-180` directly inserts into `reviews_fts` after `upsert_reviews()`.

Other references:

- `apps/api/senti_next/db.py:146-150` creates the standalone FTS table.
- `apps/api/senti_next/dialect.py:110-115` reads/matches/ranks FTS.
- `apps/api/senti_next/storage.py:176-180` is the only production direct FTS insert found.
- `apps/api/tests/test_sqlite_compat.py:143-147` directly inserts FTS rows in a test fixture.
- Review deletion occurs in `storage.py:238`, `795`, and `889`, with no corresponding FTS delete path.

## Performance impact

- P0.0A adds one small schema-version table check/insert during startup.
- Migration/backup work is file-local and only runs when explicitly applying migrations; no normal analysis path was changed.
- No per-token SQLite writes were introduced.
- No FTS trigger overhead exists yet because P0.1 has not started.

## Compatibility risks

- Existing `db.init_db()` still owns the legacy idempotent DDL and now records bootstrap version 1; future migrations must not duplicate or bypass this marker.
- The migration runner currently operates on SQLite file paths. Integration with the application startup URL and desktop lifecycle should be reviewed before adding non-bootstrap migrations.
- The repository cannot currently run pytest in the available environments; dependency setup is required before claiming backend regression status.
- Existing `apps/api/evaluate_labeling.py` syntax failure blocks repository-wide compile/import smoke.

## Rollback procedure

1. Stop before P0.1 if any P0.0A gate fails.
2. For the new migration foundation, restore the checkpoint commit `7ec4adc` or revert only the P0.0A working-tree changes after review.
3. For any future migration run, restore the pre-run SQLite backup; never delete canonical reviews.
4. Do not alter `review_id` semantics or FTS objects as part of rollback.

## Gate result / P0.1 blockers

**NO-GO for P0.1 until human review** of:

- changed migration runner and startup integration;
- installation of pytest/dependencies and passing existing backend tests;
- the pre-existing `evaluate_labeling.py` syntax error;
- a non-empty historical review dataset or fixture for meaningful collision validation.

P0.1 FTS migration has not been performed. The next permitted action, after this report is reviewed and the test environment is repaired, is to run the P0.0A regression/migration suite and then obtain a human GO decision before writing FTS migration SQL.
