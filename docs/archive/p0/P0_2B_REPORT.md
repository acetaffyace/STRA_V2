# P0.2b Report — General Analysis Run Lifecycle

Status: **P0.2b complete. Recommended GO for P0.2c.** P0.2c was not started.

## Previous Analyze lifecycle audit

Before P0.2b, ordinary `POST /analyze` performed review fetching and progress
initialization synchronously in the request handler, persisted an
`analysis_results` row with `status='running'`, and then scheduled only the
classification/insight job through FastAPI `BackgroundTasks`. The background
job generated a separate transient hash-based run ID, persisted completed,
cancelled, or failed result payloads, and used the `progress` table as the
operational signal.

Cancellation set `progress.cancelled`; the classification callback observed it
at batch boundaries and raised `InterruptedError`. The progress polling and SSE
endpoints read `progress` first and fell back to `analysis_results`. Existing
in-memory protection was minimal; `analysis_results.status` and progress age
were used to reject or clear duplicate/stale work. Startup had no durable
general-run recovery policy.

## Final state machine

General runs use:

```text
queued -> running -> completed
   |         |          |
   v         v          v
cancelled  failed     terminal
```

Allowed transitions are explicitly enforced in storage:

- `queued -> running | failed | cancelled`;
- `running -> completed | failed | cancelled`;
- terminal states are idempotent only to themselves.

Version Review continues to use its existing `created`, `running`,
`metrics_ready`, and `failed` behavior. General lifecycle helpers reject
mutation of Version Review runs, and the existing Version Review metrics writer
rejects general runs.

## Status, phase, and mutability

Migration v4 adds nullable `phase` and `cancel_requested` columns. `status` is
lifecycle truth; `phase` is work-stage information such as `ingesting`,
`classifying`, `aggregating`, and `summarizing`.

Immutable identity/configuration includes `run_id`, `run_type`, user/app
identity, requested scope, languages/count, and selected provider/model/prompt/
taxonomy/analysis configuration. Execution observations are mutable while
running: timestamps, counts, error, status, phase, and cancellation signal.
Terminal transitions set `completed_at`; terminal general rows cannot return to
queued/running through storage helpers. Final provenance is therefore frozen
after completion, failure, or cancellation except through an explicit future
repair path.

## Run creation and execution ordering

`POST /analyze` now:

```text
validate provider/request
-> create analysis_runs(run_type='general_analysis', status='queued')
-> perform the existing synchronous fetch/preparation path
-> persist the existing analysis_results running snapshot
-> schedule background classification
-> return the same response shape plus the already-supported optional run_id
```

The existing synchronous fetch path was retained for compatibility. Its fetch
progress callback observes the durable cancellation signal. When the
background job actually starts, it performs `queued -> running` and sets
`started_at` once. Scheduling failure immediately changes the queued run to
failed and persists the error; no orphan queued run remains.

Completion is recorded only after the existing `analysis_results` completion
write succeeds. Failure paths persist the error and fail the run even if a
secondary result write also fails. Observed retrieved/valid/classified counts
are recorded when available; unknown counts remain NULL.

The existing `analysis_results.run_id` field is populated with the same
execution identity for this run. Its payload structure and read semantics were
not redesigned; latest-result linkage remains a later P0.2c concern.

## Cancellation and interruption policy

- A queued general run is marked `cancelled` immediately.
- A running run receives `cancel_requested=1`; it remains running until the
  execution callback observes the signal and exits.
- Only then is it marked `cancelled` with `completed_at` and an error message.
- The existing progress cancellation flag remains as a compatibility signal.
- On startup, queued/running general runs left by a previous process are marked
  `failed` with `interrupted by process restart` and a terminal timestamp.
  Full resume/retry is intentionally deferred.

`analysis_runs` is now lifecycle source of truth. `progress` remains the
compatibility/progress surface for existing polling and SSE clients; it is not
used to infer durable lifecycle completion.

## Version Review compatibility

No Version Review route, status value, execution ordering, metrics payload, or
API response contract was rewritten. Existing Version Review creation,
execution, metrics, evidence, recommendations, comparison, and topic tests
remain passing.

## Tests and validation

New P0.2b tests cover:

- queued creation and unique run ID before scheduling;
- queued-to-running start and one-time `started_at`;
- successful completion after result persistence;
- failure/error persistence and no stuck running state;
- scheduling failure;
- queued cancellation;
- running cancellation signal and confirmed stop;
- terminal transition rejection and idempotent same-state updates;
- interrupted process startup recovery;
- Version Review compatibility.

Results:

```text
full backend pytest: 67 passed, 6 xfailed
P0.2b lifecycle tests: 6 passed
P0 migration/P0.2a suites: PASS
compileall apps tooling: PASS
import smoke: PASS
```

The six xfails remain unrelated future-P0 contracts. No unexpected regression
was observed.

## Files changed and impact

- `apps/api/senti_next/storage.py` — general run creation, transitions,
  cancellation, recovery access, and Version Review writer guard.
- `apps/api/senti_next/run_schema.py` — interrupted-run recovery helper.
- `apps/api/senti_next/db.py` — migration v4 and startup recovery.
- `apps/api/senti_next/migrations.py` — schema version 4.
- `apps/api/senti_next/routes/analysis.py` — general run creation, start,
  completion/failure/cancellation wiring, and scheduling failure handling.
- `apps/api/tests/test_p0_2b_lifecycle.py` — lifecycle contract tests.
- `P0_2B_REPORT.md` — this audit and gate record.

Runtime overhead is limited to a few SQLite reads/writes per run transition and
one durable cancellation flag check at existing fetch/classification batch
boundaries. Storage overhead is two lifecycle columns plus one row in the
existing `analysis_runs` table per general execution. No new worker system,
index, result payload, frontend flow, or metric linkage was added.

## Rollback and known risks

Migration v4 is additive and runs through the P0.0A backup/restore framework;
failed file migrations restore the pre-v4 database. The main remaining risk is
that FastAPI `BackgroundTasks` is still process-local and not durable; P0.2b
does not introduce a persistent worker or resume system. Startup recovery makes
this failure mode explicit instead of leaving runs indefinitely running.

## Final gate

**GO for P0.2c**, subject to the user’s explicit result-linkage gate. Execution
stops after P0.2b.
