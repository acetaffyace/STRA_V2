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

Current work item:
  - implement immutable SemanticRun identity and semantic_config_hash
    idempotency/lifecycle persistence

Next:
  - add SemanticUnit/SemanticMention immutable schema and UTF-8 evidence
    offsets
  - connect SemanticRun to durable semantic Jobs and exact-run status UI
  - validate taxonomy/catalog/configuration identity against M2 benchmark
    gates

Release blockers:
  - none identified yet

Required items:
  - none waived

Last verified commit:
  - 0780531 — deterministic workbench Segments projection

Last validation:
  - 21 M0/migration tests and 21 M1 workbench/core tests passed; dashboard
    typecheck and elevated production build passed; lint passed with five
    pre-existing warnings and no errors.

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
