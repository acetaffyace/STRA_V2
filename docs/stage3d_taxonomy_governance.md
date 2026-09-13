# Stage 3D — Versioned Taxonomy Governance

Stage 3D creates an independent, human-governed registry for taxonomy
promotion. It does not change the frozen classifier, prompt, review labels,
Research Core, Stage 2E, or any Stage 3A–3C output.

## Registry and baseline

Migration 18 adds `taxonomy_snapshots`, `taxonomy_topics`,
`taxonomy_change_sets`, `taxonomy_change_items`, and the append-only
`taxonomy_activation_events` table. A fresh database materializes the
content-addressed `sentinext-taxonomy-v1` snapshot from the structured
stdlib-only registry. A regression test compares its canonical keys with the
classifier's existing v1 key set. Topic IDs are deterministic hashes of
canonical keys; snapshot IDs and taxonomy fingerprints are deterministic and
independent of row insertion order.

Published snapshots are immutable. Database triggers and service validation
reject in-place edits or deletes. A new taxonomy is always a complete snapshot
with a parent snapshot; older snapshots remain readable forever.

## Human-governed promotion

Only the latest Stage 3C human decision can make a candidate eligible. The
decision must be `approve_candidate` (the legacy `approve` spelling is
accepted), the recommendation must be `candidate_new_topic` or
`candidate_child_topic`, and evidence sufficiency must not be `insufficient`.
`taxonomy_boundary_review`, rejected/deferred candidates, key collisions,
missing parents, and duplicate promotions are rejected explicitly.

The CLI intentionally separates:

```text
plan-add → validate → apply → publish
```

`plan-add` records the candidate provenance and base fingerprint without
changing the active taxonomy. `validate` checks eligibility, canonical-key and
parent constraints, and stale-base protection. `apply` atomically creates a
complete draft snapshot. `publish` makes the draft immutable and appends an
activation event. `activate` is an explicit activation/rollback action and
never edits or retires a snapshot.

Use `tooling/manage_taxonomy.py` for `status`, `show`, `list-candidates`,
`plan-add`, `validate`, `apply`, `publish`, `diff`, `history`, `activate`, and
`trace`. `trace` links a promoted topic back to its Stage 3C candidate,
decision, evidence package, materialization, and (where persisted) underlying
semantic evidence.

## Compatibility boundary

The active registry is governance metadata only. Stage 3D does not update
`TAXONOMY_VERSION`, `ACTIVE_PROMPT_VERSION`, `review_labels`, or historical
taxonomy provenance. Classifier consumption and validation belong to Stage 3E.
No LLM calls, network requests, embedding work, clustering, relabeling, or
frontend work occur here.

## Audit and reproducibility

Every change set records its operator, base snapshot/fingerprint, explicit
topic definition, source candidate, and resulting snapshot. Activation history
is append-only, so rollback means activating an existing published snapshot.
`diff` exposes added/removed topics, display-name and description changes, and
parent changes without replaying change sets.

The canonical key is supplied explicitly by a human; candidate names are
reference material only. A child promotion must name an existing active parent
in the base snapshot. The registry is global/canonical: game-specific terms
may remain approved candidates without being promoted.

## Deferred scope

Stage 3D does not implement classifier integration/validation (Stage 3E),
taxonomy merge/split/delete governance, semantic sampling, topic prevalence,
Research Core changes, causal/version analysis, or dashboard UI. Existing
Stage 3A–3C artifacts and the frozen `sentinext-taxonomy-v1` classifier
contract remain unchanged.
