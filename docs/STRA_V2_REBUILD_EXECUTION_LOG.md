# STRA V2 Rebuild Execution Log

## M0 — Foundation Seal

- Status: COMPLETE
- Scope implemented: canonical immutable review/population/run identity
  contracts; UTC anchored half-open windows; durable idempotent jobs; additive
  legacy bridge for current general-analysis population freezes; deterministic
  population reuse compatibility; canonical offline fixture creation.
- Contracts affected: ReviewSnapshot, PopulationSnapshot, ResearchRun,
  ResearchContext, Job, SamplingContract time semantics.
- Database migration(s): migration 24 extended with canonical M0 tables and
  immutability triggers; legacy tables retained unchanged.
- API changes: `POST/GET /research-runs`, `GET /population-snapshots/{id}`,
  `POST/GET /jobs`, `POST /jobs/{id}/cancel`, and
  `POST /population-compatibility/check`.
- Frontend changes: exact-run dashboard restoration honors the URL's run ID
  and cannot be overwritten by a newer in-memory task completion.
- Tests executed: `tests/unit/test_m0_foundation_contracts.py`,
  `tests/integration/test_stage4b_r1_backend_repair.py`, and
  `tests/unit/test_p0_2a_run_schema.py` — 21 passed; dashboard typecheck
  passed; lint passed with warnings only.
- M0 acceptance: canonical restart and relative-window stability, duplicate
  submission, retryable/non-retryable job recovery, and legacy 23-to-24
  additive migration are all covered. Canonical completion now references
  the insert-once `analysis_run_results:<run_id>` row.
- Commit SHA(s): f59acc7, 88a38f7, b22210b, e44e269, d7ce72f, d53f84b,
  cf3a1ea.
- Deviation: canonical tables are attached to the existing migration-24
  bridge to preserve the repository's sealed migration-version contract; see
  `docs/execution/DECISION_LOG.md`.

## M1 — Canonical Research Workbench

- Status: IN_PROGRESS
- Current work item: reconcile the dashboard's remaining page-local
  segment/trend fallbacks with exact persisted Research Core projections.
- M0 handoff: canonical run/population/job identity is sealed; M1 may use the
  legacy result tables as a compatibility boundary but must preserve exact
  run IDs and never restore formal results from StarredGame samples.
