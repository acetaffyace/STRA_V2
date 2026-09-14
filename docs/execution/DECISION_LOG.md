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
- Commit: `77bb1ca`.

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

## 2026-09-14 — Treat semantic execution as a durable resource operation

- Decision: `POST /research-runs/{run_id}/semantic-runs` creates or resolves
  one exact SemanticRun and one idempotent `semantic_v2_generation` Job; the
  deterministic evidence stage runs behind that Job and exposes the Job with
  `GET /semantic-runs/{semantic_run_id}`.
- Reason: a client retry or backend restart must retain the same semantic
  identity and progress state. Reviews without a validated assignment remain
  unresolved and produce `PARTIAL`, never an invented topic.
- Affected contracts/files: `research_runs.py`, `semantic_run_store.py`,
  Dashboard API client and exact status panel.
- Commit: `bc6accc`.

## 2026-09-14 — Keep Game/Archetype catalogs separate from Core Taxonomy

- Decision: persist content-addressed `game` and `archetype` catalog versions
  with immutable entries and explicit `DRAFT → PUBLISHED → RETIRED` status
  transitions. Game catalogs require an app binding; archetype catalogs cannot
  be app-bound.
- Reason: Core Taxonomy V2 remains stable and broad, while accepted specific
  topics are persistent, scoped and governed rather than regenerated per run.
- Migration impact: additive migration 27; no historical taxonomy or review
  labels are rewritten.
- Affected contracts/files: `topic_catalog_schema.py`,
  `topic_catalog_store.py`, `db.py`, `migrations.py`.
- Commit: `60b874a`.

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

## 2026-09-14 — Materialize review-level semantic rollups separately from mentions

- Decision: persist unique review/topic and review/topic/signal rollups keyed
  by the exact SemanticRun and ReviewSnapshot, while keeping immutable
  SemanticMention rows as evidence-level truth.
- Reason: topic prevalence is a review-level metric; mention multiplicity or
  repeated spans must never inflate the formal numerator.
- Migration impact: additive migration 28 with uniqueness and immutability
  triggers; existing mentions and historical results are unchanged.
- Affected contracts/files: `semantic_rollup_schema.py`,
  `semantic_run_store.py`, `db.py`, `migrations.py`.
- Commit: `12cf7d4`.

## 2026-09-14 — Keep local prototype uncertainty explicit

- Decision: SemanticRun execution may explicitly enable a local or deterministic
  fake prototype backend; only HIGH/MEDIUM matches create mentions, and missing,
  unpinned or invalid local model artifacts leave reviews unresolved and mark
  the run PARTIAL with a machine-readable reason.
- Reason: local-first processing must be reproducible and must not turn model
  availability or raw similarity into an invented probability or catch-all
  topic.
- Affected contracts/files: `semantic_prototypes.py`, `embedding_backend.py`,
  `semantic_run_store.py`, `semantic_adjudication.py`.
- Commits: `ac38a96`, `6706d4f`.

## 2026-09-14 — Govern emerging topics as reviewable candidates

- Decision: discovery emits content-addressed EmergingTopicCandidate rows with
  explicit lifecycle transitions; accepting a candidate requires a separately
  chosen target topic and never mutates Core or Game catalogs automatically.
- Reason: clustering is a discovery/refinement tool, not final label authority;
  promotion must remain auditable and reversible at the governance boundary.
- Migration impact: additive migration 29 with immutable identity and no-delete
  triggers.
- Affected contracts/files: `emerging_topic_schema.py`,
  `emerging_topic_store.py`, `db.py`, `migrations.py`.
- Commit: `a63a3ca`.

## 2026-09-14 — Version benchmark assets and measured evaluation output

- Decision: require a manifest with dataset/taxonomy/code identity and SHA-256
  asset hashes before accepting Semantic V2 benchmark evidence; evaluation
  reports expose support-aware §12 metrics and language slices.
- Reason: existing V1 labels and the 60-review unlabeled smoke fixture cannot
  establish the M2 product gates. The validator therefore fails closed instead
  of silently reusing incompatible assets.
- Affected contracts/files: `tooling/evals/semantic_v2/`,
  `tests/unit/test_m2_semantic_benchmark_assets.py`,
  `tests/unit/test_m2_semantic_evaluation_report.py`.
- Commit: `bb97bbd`, `564b167`.

## 2026-09-14 — Make Discovery Pool coverage explicit and deterministic

- Decision: construct a reason-coded Discovery Pool from LOW, sampled MEDIUM,
  high-volume HIGH, recent-burst and novelty/outlier sources; sample each
  candidate cluster through central, diverse and boundary evidence sets.
- Reason: discovery must not be limited to LOW confidence or arbitrary first-N
  reviews, because broad HIGH topics can contain emerging substructure.
- Affected contracts/files: `semantic_discovery_pool.py` and its unit tests.
- Commit: `5e8f088`.

## 2026-09-14 — Keep cluster adjudication data-only and selective

- Decision: expose a provider-neutral adjudication boundary that sends only a
  selected cluster's bounded structured context, wraps review text as data,
  and schema-validates the response before any mention/candidate mutation.
- Reason: provider calls must be selective, prompt-injection-safe and unable to
  mutate production taxonomy directly; malformed output is rejected closed.
- Affected contracts/files: `semantic_adjudication.py` and its unit tests.
- Commit: `4145497`.

## 2026-09-14 — Make SemanticRun evidence directly addressable

- Decision: expose immutable SemanticMention plus SemanticUnit source identity
  and UTF-8 offsets through the SemanticRun resource, with topic/signal
  filters available in the persistence service and the Dashboard.
- Reason: Signals and Evidence must drill into the exact run-scoped source;
  a status-only resource cannot satisfy auditability or evidence inspection.
- Affected contracts/files: `semantic_run_store.py`, `research_runs.py`,
  Dashboard API/types/rendering and evidence tests.
- Commit: `b54ae00`.

## 2026-09-14 — Separate human benchmark production from benchmark evaluation

- Decision: define separate Boundary Suite and Evaluation Holdout record
  schemas/manifests; export only deterministic `UNLABELED` candidates from
  real review data; require human first-pass/final provenance and reject model
  generated labels and holdout calibration/training use.
- Reason: §12 uses the Boundary Suite for repeatable development regression but
  requires the Holdout to remain independent for final gates. Gold labels must
  come from the human workflow, never from a model or legacy taxonomy remap.
- Affected contracts/files: `tooling/evals/semantic_v2/schemas/`, separate
  manifest examples, `validate_assets.py`, `export_candidates.py`, README and
  benchmark tests.
- Commit: recorded in `EXECUTION_STATE.md` after verification.
