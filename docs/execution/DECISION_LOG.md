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

## 2026-09-14 — Point canonical completion at the immutable result row

- Decision: after the legacy `analysis_run_results` insert commits, finalize
  the bridged canonical ResearchRun with
  `immutable_result_ref=analysis_run_results:<run_id>`.
- Reason: the canonical run must identify the exact persisted Research Core
  result without duplicating or rewriting the analytical payload. The legacy
  result table remains the compatibility storage boundary during M1.
- Affected contracts/files: `research_run_store.py` and `storage.py`.
- Commit: `d7ce72f`.

## 2026-09-14 — Version SemanticRun configuration independently from results

- Decision: persist an immutable SemanticRun for each canonical ResearchRun
  and canonical semantic configuration hash, with explicit lifecycle,
  population binding, progress and result-reference fields.
- Reason: semantic outputs must be reproducible and reopenable; changing any
  material engine, taxonomy, embedding, calibration, segmentation or
  assignment identity must create a new run instead of mutating prior output.
- Migration impact: additive migration 25; existing research and legacy
  analysis rows remain readable and are not inferred into semantic runs.
- Affected contracts/files: `semantic_run_schema.py`,
  `semantic_run_store.py`, `research_contracts.py`, `db.py`.
- Commit: `34d76f3`.

## 2026-09-14 — Store semantic evidence as immutable UTF-8 byte ranges

- Decision: SemanticUnit offsets are UTF-8 byte offsets into the exact
  ReviewSnapshot content, and SemanticMention stores one required core topic
  with optional secondary topic, signal and adjudication provenance.
- Reason: byte-addressed evidence prevents normalization drift and makes UI
  evidence links auditable; immutable mention identity prevents silent topic
  reassignment in a completed run.
- Migration impact: additive migration 26 with update/delete immutability
  triggers; invalid UTF-8 boundaries and text-snapshot conflicts are rejected
  before persistence.
- Affected contracts/files: `semantic_unit_schema.py`,
  `semantic_run_store.py`, `research_contracts.py`, `db.py`.
- Commit: `34d76f3`.
