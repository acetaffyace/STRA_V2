# STRA_V2 Execution State

Master Spec:
  docs/master_spec/STRA_V2_MASTER_PRODUCT_REBUILD_SPEC_1.1.md

Spec version:
  1.1

Baseline:
  main @ f56dacfc... (working checkout: integration/research-pipeline-v1 @ 2705e81)

Active milestone:
  M0 — Foundation Seal

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

Current work item:
  - integrate canonical runs with deterministic Research Core result identity
    and complete M0 fixture/recovery acceptance evidence

Next:
  - wire canonical run finalization to immutable Research Core result refs
  - add population compatibility checks for EXACT/SAFE_SUBSET/INCOMPATIBLE
  - add representative legacy migration/restart fixture coverage
  - validate frontend exact-run restoration against canonical resource IDs

Release blockers:
  - none identified yet

Required items:
  - none waived

Last verified commit:
  - f59acc7 — canonical M0 research identity foundation

Last validation:
  - 18 focused M0/compatibility tests passed after the implementation commit.
