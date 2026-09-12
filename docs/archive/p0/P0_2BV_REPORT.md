# P0.2bV Report — General Run Lifecycle Truth Correction

Status: **P0.2bV complete. Recommended GO for P0.2c.** P0.2c was not started.

## Previous timing inconsistency

The P0.2b implementation created a general run as `queued`, then performed
synchronous Steam ingestion/preparation, and only changed it to `running` when
the BackgroundTask began classification. For a 40-second fetch and 60-second
classification, the recorded interval omitted the first 40 seconds of actual
work. `queued` therefore incorrectly contained execution, and `started_at` did
not represent the first work timestamp.

## Corrected lifecycle ordering

The ordinary synchronous ingestion path remains unchanged for compatibility.
The lifecycle is now:

```text
validate request
  -> create run: queued
  -> immediately before first real work:
       queued -> running, phase=ingesting, started_at=now
  -> synchronous Steam fetch/preparation
  -> persist running result snapshot
  -> phase=classifying
  -> schedule existing BackgroundTask
  -> BackgroundTask verifies the same run is already running
  -> classification/aggregation
  -> completed / failed / cancelled
```

`queued` now means created but not executing. `running` includes ingestion,
classification, aggregation, and summarization. Steam fetching was not moved
to a worker and `/analyze` response timing was not redesigned.

## `started_at` semantics

`started_at` is set by the first `queued -> running` transition immediately
before synchronous ingestion. The storage transition uses
`COALESCE(started_at, ...)`, so repeated status updates and BackgroundTask
handoff never reset it. Tests verify that the timestamp remains unchanged after
the handoff and through later running-phase updates.

The BackgroundTask no longer performs `queued -> running`. It receives the
existing `run_id`, checks that the durable status is `running`, and continues
the same execution identity. If it finds an unexpected non-running state, it
does not invent a second start.

## Ingestion failure and cancellation

Any synchronous fetch/preparation exception after start transitions:

```text
running + ingesting -> failed
```

The error and terminal timestamp are persisted, progress is cleared, and no
queued/running run is left behind.

The existing `/progress/{app_id}/cancel` endpoint now resolves the active
general run durably. During ingestion, the progress callback observes both the
existing progress cancellation flag and the Run cancellation signal. It stops
the work and only then records:

```text
running + ingesting -> cancelled
```

Queued cancellation remains immediate because execution has not started. The
same local-first cancellation model is retained; no distributed cancellation
system was added.

## Background handoff and schedule failure

After ingestion and preparation, the same Run remains `running` and its phase
changes to `classifying`. Scheduling does not create a new Run, generate a new
execution ID, or reset `started_at`.

If `BackgroundTasks.add_task()` raises, the existing running Run transitions to
`failed` with `schedule failed: ...`; the existing result snapshot is also
updated to failed. This closes the previously possible active-run gap.

## Duplicate/concurrent Analyze window

The audit found that the old result-based guard could not protect the interval
between Run creation and `analysis_results` snapshot creation. P0.2bV now
checks the durable `analysis_runs` table for an active general Run for the same
app before creating another one. A second overlapping request receives 429 and
the first Run remains the sole active execution. Concurrent active runs for the
same app/user are intentionally rejected; this phase does not redesign global
concurrency.

The existing all-app active-run guard remains in place for other apps. Version
Review runs are not included in the general lifecycle guard.

## Status/phase contract tests

The P0.2bV tests cover:

- storage-created Run initially queued;
- first work transition to running/ingesting and one-time `started_at`;
- classification phase change without lifecycle restart;
- BackgroundTask handoff with unchanged timestamp and identity;
- success to completed;
- synchronous ingestion failure to failed;
- scheduling failure from running to failed;
- ingestion cancellation after callback stop confirmation;
- same-app overlapping Analyze rejection;
- terminal transition protection.

Results:

```text
full backend pytest: 70 passed, 6 xfailed
P0.2bV tests: 9 passed
P0 migration/P0.2a suites: PASS
compileall apps tooling: PASS
import smoke: PASS
```

The six xfails remain unrelated future-P0 contracts. The warnings are existing
Pydantic v2 deprecation warnings from `.dict()`/`.copy()` usage; they are not
new lifecycle failures and were not expanded into unrelated refactoring.

## Files changed and compatibility impact

- `apps/api/senti_next/routes/analysis.py` — first-work transition, phase
  handoff, ingestion failure/cancellation handling, same-app durable guard.
- `apps/api/tests/test_p0_2b_lifecycle.py` — lifecycle-truth and concurrency
  regression tests.
- `P0_2BV_REPORT.md` — this verification record.

The change preserves synchronous ingestion, result payload structure and reads,
progress/SSE compatibility, Version Review lifecycle semantics, FTS, and all
P0.2c result-linkage decisions. Runtime overhead is limited to the existing
SQLite Run transition/cancellation checks; no new worker or infrastructure was
introduced.

## Final gate

**GO for P0.2c**, subject to the separate immutable-result-linkage schema gate.
Execution stops after P0.2bV.
