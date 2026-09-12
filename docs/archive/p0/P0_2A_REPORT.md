# P0.2a Report — General Analysis Run Schema

Status: **P0.2a complete. Recommended GO for P0.2b.** P0.2b was not started.

## Existing `analysis_runs` audit

The current table was a Version Review execution record:

| Existing field | Observed meaning | Mutability |
|---|---|---|
| `run_id` | Version Review execution identity; primary key | immutable |
| `user_id` | local-user ownership/filter | immutable |
| `target_app_id` | game/app identity | immutable |
| `event_id` | verified `version_events` anchor and FK | immutable |
| `config` | serialized Version Review configuration snapshot | immutable |
| `status` | created/running/metrics-ready/failed state | mutable by existing helper |
| `metrics` | serialized Version Review derived payload | mutable by existing helper |
| `error` | latest execution error | mutable |
| `created_at` | creation timestamp | immutable |
| `updated_at` | last persistence update | mutable |

`storage.create_analysis_run()`, `get_analysis_run()`,
`list_analysis_runs()`, and `save_analysis_run_metrics()` are the complete
analysis-runs storage surface. `routes/runs.py` creates and exposes these IDs,
executes Version Review runs, and writes metrics. `version_analysis.py` is the
deterministic metrics builder and does not persist runs directly.

The ordinary `/analyze` path does not use `analysis_runs`; it persists the
latest app-level snapshot in `analysis_results`, whose existing `run_id` is
not changed in P0.2a. `analysis_results` and its helpers were not redesigned.
`docs/PLAYER_VOICE_RUNS.md` defines `run_id` as the reproducible event-review
identity and `app_id` as game identity.

## One-table decision

One generalized `analysis_runs` entity is safe and preferred. All current
writers are Version Review writers, so existing rows can be classified as
`version_review` without inference from fabricated provenance. A separate
general-run table would create a second ID and lifecycle system while solving
no observed compatibility problem.

The decision and mutability contract are recorded in
[ADR_P0_2A_RUN_SCHEMA.md](ADR_P0_2A_RUN_SCHEMA.md).

`run_type` is ordinary TEXT, not a SQLite ENUM. Application constants are:
`version_review`, `general_analysis`, and `legacy`. Future types can be added
without a table rewrite.

## Final schema fields added

Migration v3 adds:

- identity: `run_type`;
- lifecycle: `started_at`, `completed_at`;
- scope: `data_cutoff`, `window_start`, `window_end`,
  `requested_languages`, `requested_review_count`;
- observed counts: `retrieved_count`, `valid_review_count`,
  `classified_count`, `fallback_count`, `enriched_count`;
- analysis identity: `scope_fingerprint`, `taxonomy_version`,
  `prompt_version`, `analysis_version`, `provider`, `model_id`.

All new provenance and lifecycle fields are nullable except `run_type`, which
defaults to `version_review`. No result JSON was added. Existing `config` and
`metrics` remain in place.

`event_id` is now nullable, while its FK remains valid when populated. This is
the only required table-copy change: SQLite cannot remove the old NOT NULL
constraint with an additive ALTER. `target_app_id` remains required and is the
shared app identity for both run types.

## Migration and compatibility

- Version: **3**, `generalized analysis_runs schema`.
- Uses the P0.0A ordered migration and backup/restore framework.
- Creates `analysis_runs_v3`, copies every existing value, assigns existing
  rows `run_type='version_review'`, drops the old table, renames the new table,
  and recreates the two existing indexes.
- No historical counts, fingerprints, model, prompt, taxonomy, or cutoff
  values are fabricated; unavailable fields remain NULL.
- Fresh initialization and upgraded legacy fixtures expose identical final
  `analysis_runs` columns.
- Existing Version Review storage helpers continue to create/read/update rows;
  existing route response shapes and `run_id` values are unchanged.
- A general-shaped row with `event_id=NULL`, `run_type='general_analysis'`,
  and version-specific fields NULL inserts successfully.

No new index was added. Existing access patterns are already covered by
`(user_id, created_at)` and `(target_app_id, created_at)`; adding a speculative
run-type index would violate the phase scope.

## Tests and validation

New P0.2a tests cover:

- fresh generalized schema and migration ledger version 3;
- legacy Version Review data preservation and classification;
- existing Version Review storage compatibility;
- general run with nullable Version Review scope;
- unknown provenance remaining NULL;
- repeated startup/migration idempotence;
- fresh/upgraded schema parity;
- migration failure restoring existing runs from backup.

Results:

```text
full backend pytest: 60 passed, 6 xfailed
P0.2a schema tests: 5 passed
compileall apps tooling: PASS
import smoke: PASS
```

The six xfails remain unrelated future-P0 contracts. No unexpected regression
was observed.

## Performance, storage, rollback, and risks

The migration copies only `analysis_runs`; it does not touch reviews, FTS,
analysis results, or payload tables. Runtime cost is proportional to the
number of existing run rows and is paid once during migration. The new nullable
columns add fixed per-row schema width; no new index or result payload storage
was introduced.

Rollback is automatic for file databases through the P0.0A backup taken before
the table copy. On migration failure, the original table and all existing run
records are restored. The main future risk is that P0.2b must enforce the
mutability/lifecycle contract; P0.2a intentionally does not add that state
machine.

## Final gate

**GO for P0.2b**, subject to the user’s explicit lifecycle gate. Execution stops
after P0.2a.
