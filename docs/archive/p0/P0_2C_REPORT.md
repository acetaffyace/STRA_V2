# P0.2c Report — Immutable General-Analysis Run Results

## Scope and outcome

P0.2c is complete. Every successful general analysis now persists one exact,
immutable result by `run_id`, while `analysis_results` remains the existing
app-scoped latest compatibility surface. P0.3a was not started.

## Audit finding

`analysis_results` stores `metadata`, `insights`, and `reviews` as JSON text,
plus status/error/run and snapshot/context fields. Its unique key is
`(user_id, app_id)`, so `save_analysis_result()` overwrites the prior row.
It is written by the general job, request/progress paths, failure/cancel
paths, rebuild and auto-refresh flows.

`load_analysis_result(app_id)` is used by `GET /analysis/{app_id}`, progress
and SSE fallbacks, chat tools/context, game/starred-game paths, and refresh
logic. These consumers depend on the current row, including running, failed,
and cancelled statuses. P0.2c therefore preserves that contract and does not
silently change it to latest-completed-only.

The full rationale is in [ADR_P0_2C_RESULT_LINKAGE.md](ADR_P0_2C_RESULT_LINKAGE.md).

## Architecture

Added `analysis_run_results`, one row per `general_analysis` run:

- `run_id` primary key and foreign key to `analysis_runs`;
- `user_id`, `app_id` linkage;
- `metadata`, `insights`, `reviews` immutable payload columns;
- `snapshot_hash`, `context_hash`;
- `created_at`, `completed_at`.

External-content or trigger-based FTS is unrelated and was not changed.
Version Review results/metrics remain outside this table. Reusing the latest
table or reconstructing legacy history was rejected because either would
break the existing contract or fabricate execution history.

## Migration

Schema version 5 creates the table with `CREATE TABLE IF NOT EXISTS` and does
not backfill old `analysis_results` rows. File databases use the existing
backup-before-migration and restore-on-error framework with `.p0_2c.bak`.
Fresh and upgraded databases both reach migration versions 1 through 5.

## Transaction and lifecycle behavior

`finalize_general_analysis_run()` uses one database connection and transaction:

1. validate the run is the matching, running, general-analysis run;
2. insert `analysis_run_results` without a conflict/update clause;
3. upsert `analysis_results` as completed/latest;
4. transition `analysis_runs` to completed and write counts;
5. commit on successful context exit.

Any failure rolls back all three effects. Failed and cancelled paths continue
to write the compatibility row when applicable but do not insert an immutable
result. A second finalization is rejected after the run is terminal, and the
primary key prevents duplicate result rows.

## Historical reads and compatibility

Added `GET /runs/{run_id}/result`, which returns only the exact immutable
general-analysis result and returns 404 when no completed result exists. The
existing `/runs/{run_id}` and Version Review routes are unchanged.

Legacy pre-v5 `analysis_results` rows remain readable only through the latest
surface; no historical result is invented for them.

## Tests

Added `test_p0_2c_results.py` covering:

- two successful runs preserving A while latest moves to B;
- failed/cancelled runs having no immutable row;
- insert-once behavior;
- rollback when latest persistence fails;
- v5 schema presence and no legacy backfill.

Validation after the change:

- backend pytest: **70 passed, 6 xfailed**;
- `compileall`: passed;
- import smoke: passed;
- existing Version Review and P0 contract/migration tests: passed.

The six xfails are the existing future-P0 cases and remain xfail; no new
regression was introduced.

## Performance check

On the local in-memory SQLite fixture, 30 latest-row writes averaged **0.125
ms/run**. Thirty atomic P0.2c finalizations (run transition plus immutable
insert plus latest upsert) averaged **0.790 ms/run**, approximately **0.665
ms/run** and **532.6%** above the single latest-write baseline. This is a
small local microbenchmark, not a production SLA; the extra cost is the
durable history insert and lifecycle update. No search or review-ingestion
path was materially changed.

## Files changed

- `apps/api/senti_next/result_schema.py`
- `apps/api/senti_next/migrations.py`
- `apps/api/senti_next/db.py`
- `apps/api/senti_next/storage.py`
- `apps/api/senti_next/routes/analysis.py`
- `apps/api/senti_next/routes/runs.py`
- `apps/api/tests/test_p0_2c_results.py`
- migration/version expectation updates in existing tests
- `ADR_P0_2C_RESULT_LINKAGE.md`

## Rollback and risks

Before applying v5 to a file database, the migration framework creates the
`.p0_2c.bak` backup. Migration failure rolls back and restores that backup.
Runtime finalization failure is transactionally rolled back; the run remains
non-completed so the caller can mark it failed through the existing failure
path.

Known risk: result payloads intentionally duplicate the three JSON payload
columns from the latest table, increasing storage per successful run. This is
the required trade-off for immutable, exact historical reads without
changing existing consumers.

## P0.2a recommendation

**GO for P0.3a**, subject to the next human gate. P0.2c is complete and this
turn stops here.
