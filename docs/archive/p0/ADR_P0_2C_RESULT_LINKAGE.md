# ADR P0.2c: Immutable General-Analysis Run Results

## Decision

Add `analysis_run_results`, keyed by `run_id`, for immutable completed results
of `analysis_runs.run_type = 'general_analysis'`. Keep `analysis_results` as
the existing `(user_id, app_id)` latest compatibility surface.

The successful general-analysis finalization is one SQLite transaction:

1. insert the immutable result row;
2. upsert the compatibility/latest row;
3. transition the general run to `completed`.

An insert is never updated. A second result for the same run is rejected by
the primary key and by the lifecycle guard. Failed and cancelled runs do not
have rows in `analysis_run_results`.

## Audit findings

`analysis_results` currently stores the analysis payload in separate JSON
columns (`metadata`, `insights`, `reviews`) with status, error, run and
fingerprint fields. Its unique `(user_id, app_id)` constraint means every
new analysis, auto-refresh, rebuild, failure, or cancellation can replace the
previous row. `save_analysis_result()` is used by the general analysis job,
request/progress paths, auto-refresh and rebuild paths; therefore it remains
the compatibility writer and is not converted into an historical writer.

`load_analysis_result(app_id)` is consumed by the analysis endpoint,
progress/SSE fallbacks, chat tools, chat context, game/starred-game paths and
analysis refresh logic. These consumers expect the current app-scoped row,
including non-completed statuses, so P0.2c does not change their semantics.

The existing `/runs` namespace is already the durable run API for Version
Review. A non-conflicting `/runs/{run_id}/result` endpoint may expose the
exact immutable general result; Version Review routes and metrics remain
unchanged.

## Schema and legacy policy

Migration v5 creates `analysis_run_results` with `run_id` as its primary key,
app/user linkage, the three existing result payload columns, snapshot/context
hashes, and creation/completion timestamps. It references `analysis_runs`.

No rows are synthesized from pre-v5 `analysis_results`: those rows do not
prove which historical execution produced the payload. Existing latest data
remains readable through `analysis_results`.

Alternatives rejected:

* Reusing `analysis_results`: incompatible with its intentional latest-row
  uniqueness and would break existing consumers.
* Versioning that table by adding a second key: would change its established
  read/write contract and make failure/cancellation semantics ambiguous.
* Reconstructing legacy history: would fabricate execution history.

## Failure and rollback

The dedicated finalizer uses one connection and lets any insert, latest-row,
or run-transition failure abort the transaction. File databases use the
existing pre-migration backup/restore framework before applying v5.

