# Decision Log

## 2026-09-14 — Add canonical M0 identity graph additively to migration 24

- Decision: keep the existing migration ledger at version 24 and extend its
  additive research-population migration with the versioned
  ReviewSnapshot/PopulationSnapshot/ResearchRun/Job tables.
- Context: the repository already shipped migration 24 for a legacy
  run-linked population payload, while the Master Spec requires a richer
  immutable identity graph. Creating a new ledger version would make the
  existing sealed migration contract and current fixture assertions diverge.
- Alternatives considered: replace the legacy tables; add a migration 25;
  add the canonical tables within the existing migration-24 bridge.
- Reason: the chosen path preserves historical readers and migration-24
  recovery behavior while making new canonical writes additive and
  transaction-safe. Canonical rows carry their own schema-version fields and
  remain distinct from legacy compatibility data.
- Affected contracts/files: `foundation_schema.py`,
  `research_population_snapshot_schema.py`, `research_contracts.py`,
  `research_run_store.py`, `storage.py`, and the resource routes.
- Migration impact: no legacy rows are backfilled because exact canonical
  provenance cannot be inferred; new general runs are bridged when their
  population is frozen.
- Commit: recorded in `EXECUTION_STATE.md` after verification.
