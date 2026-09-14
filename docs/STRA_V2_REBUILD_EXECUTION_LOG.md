# STRA V2 Rebuild Execution Log

## M0 — Foundation Seal

- Status: IN_PROGRESS
- Scope implemented: canonical immutable review/population/run identity
  contracts; UTC anchored half-open windows; durable idempotent jobs; additive
  legacy bridge for current general-analysis population freezes.
- Contracts affected: ReviewSnapshot, PopulationSnapshot, ResearchRun,
  ResearchContext, Job, SamplingContract time semantics.
- Database migration(s): migration 24 extended with canonical M0 tables and
  immutability triggers; legacy tables retained unchanged.
- API changes: `POST/GET /research-runs`, `GET /population-snapshots/{id}`,
  `POST/GET /jobs`, and `POST /jobs/{id}/cancel`.
- Frontend changes: none in this work unit; exact-run UI restoration remains
  an M0 follow-up acceptance item.
- Tests executed: `tests/unit/test_m0_foundation_contracts.py`,
  `tests/integration/test_stage4b_r1_backend_repair.py`, and
  `tests/unit/test_p0_2a_run_schema.py` — 18 passed.
- Known limitations: canonical ResearchRun is currently a persistence
  foundation and is not yet the sole immutable Research Core result reader;
  population compatibility service and frontend restoration remain open.
- Commit SHA(s): pending first implementation commit.
- Deviation: canonical tables are attached to the existing migration-24
  bridge to preserve the repository's sealed migration-version contract; see
  `docs/execution/DECISION_LOG.md`.
