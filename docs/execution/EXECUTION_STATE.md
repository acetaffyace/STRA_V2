# STRA_V2 Execution State

Master Spec:
  docs/master_spec/STRA_V2_MASTER_PRODUCT_REBUILD_SPEC_1.1.md

Spec version:
  1.1

Baseline:
  main @ f56dacfc... (working checkout: integration/research-pipeline-v1 @ 2705e81)

Active milestone:
  M2 — Semantic Engine V2 vertical slice

Milestone status:
  IN_PROGRESS

Completed:
  - M0-WP1: canonical ReviewSnapshot, PopulationSnapshot and ResearchRun
    contracts/tables added additively; exact ordered membership and content
    hashes are persisted.
  - M0-WP2: UTC anchored half-open formal windows and durable Job state with
    idempotency, transitions, cancellation and restart recovery added.
  - M0-WP3: current general-analysis population freeze now dual-writes the
    canonical graph while preserving legacy compatibility readers.
  - M0-WP4: deterministic population reuse compatibility returns EXACT,
    SAFE_SUBSET, or INCOMPATIBLE with machine-readable reasons; offline
    fixtures now freeze canonical runs before finalization.
  - M0-WP5: exact-run dashboard URL restoration is protected from newer
    in-memory task state; canonical completion references the insert-once
    immutable analysis result row.
  - M0-WP6: canonical restart/window-stability, duplicate-submit, job
    recovery, and legacy 23-to-24 migration evidence pass.
  - M1-WP1: exact-run Workbench presentation now exposes deterministic
    Overview, language/at-review-playtime Segments, exact Trends and run-scoped
    Evidence without a StarredGame/sample fallback for formal views.
  - M2-WP1: immutable SemanticRun configuration identity now binds each run
    to the canonical ResearchRun population hash; canonical config hashing,
    idempotency, lifecycle, partial progress and result references persist.
  - M2-WP2: immutable SemanticUnit and SemanticMention evidence tables now
    preserve UTF-8 byte offsets, exact text snapshots, source hashes, one-core
    topic cardinality, optional secondary topics/signals and assignment
    provenance.

Current work item:
  - connect SemanticRun generation to durable semantic Jobs and exact-run
    status/reopen UI

Next:
  - validate taxonomy/catalog/configuration identity against M2 benchmark
    gates

Release blockers:
  - none identified yet

Required items:
  - none waived

Last verified commit:
  - 54e4ba9 — stabilize schema and provider identity assertions

Last validation:
  - full pytest passed (with two expected skips); the M2 SemanticRun and
    SemanticUnit/SemanticMention suites and migration upgrade tests passed;
    dashboard typecheck and elevated production build passed; lint passed
    with five pre-existing warnings and no errors.

M1 exit evidence:
  - quantitative-only Research Reports now carry exact language and
    at-review playtime segment denominators;
  - canonical dashboard presentation renders deterministic Overview and
    Segments, daily exact-run Trends, and run-scoped Evidence links;
  - unfiltered formal views do not derive segments/trends from the capped
    review sample; filtered views are visibly exploratory.

M0 exit evidence:
  - deterministic canonical ResearchRun reopens to the same ordered
    PopulationSnapshot after engine restart;
  - anchored relative windows remain byte-for-byte stable on reopen;
  - duplicate ResearchRun and Job submissions resolve to one formal resource;
  - retryable interrupted jobs requeue and non-retryable jobs fail explicitly;
  - migration 23-to-24 is additive/idempotent and creates all canonical M0
    tables while retaining legacy rows;
  - dashboard exact-run links preserve the requested run against later task
    completion, and finalized runs reference
    `analysis_run_results:<run_id>`.
