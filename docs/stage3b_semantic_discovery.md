# Stage 3B — Open-Set Semantic Discovery & Taxonomy Audit

Stage 3B reads one completed Stage 3A Semantic Index and produces a
reproducible diagnostic report.  It does not re-embed, sample, name topics with
an LLM, modify taxonomy, or change Research Core/Stage 2E outputs.

```text
frozen Research Population + immutable Stage 3A index
        ↓
review-level normalized mean (discovery convenience)
        ↓
HDBSCAN density discovery + unit-level neighborhood audit
        ↓
dense / rare / outlier regions
        ↓
read-only taxonomy coverage audit
```

## Contract and effective parameters

`SemanticDiscoveryContract` is `semantic-discovery-contract-v1`:

- algorithm abstraction: `hdbscan-open-set-v2` (the algorithm version is part of structure identity);
- cosine metric over normalized Stage 3A vectors;
- `neighbor_k` defaults to 5;
- `rare_region_max_size` defaults to 10;
- review representation is `normalized_mean_unit`;
- unit-level audit is enabled by default;
- taxonomy audit version is `taxonomy-audit-v1`.

If `min_cluster_size` is omitted, the deterministic engineering heuristic is:

```text
N < 200       max(5, ceil(N * .03))
200 ≤ N ≤ 2000 max(8, ceil(N * .015))
N > 2000      max(15, ceil(N * .005))
```

This is a discovery heuristic, not a statistical truth or target topic count.
The report records requested and effective values, `min_samples`, metric,
population size, algorithm version and the full contract fingerprint.
The baseline is run once. Sensitivity uses only distinct 0.75× and 1.25×
perturbations; the baseline is never scored as a self-match. Region stability
is the mean best review-ID Jaccard overlap across those perturbations and is
also exposed in `stability_by_parameter`. If no valid perturbation exists the
fixed status is `not_estimable` and the score is null.

## Region semantics

- `dense_region`: a multi-review HDBSCAN region;
- `rare_region`: a small coherent HDBSCAN or local-neighborhood region;
- `outlier`: an unusual/unclustered point retained for inspection.

HDBSCAN label `-1` is never deleted.  Local cosine neighborhoods preserve
small coherent groups even when density clustering calls them unclustered.
Outlier scores and nearest/mean-k-neighbor similarity are diagnostics only;
they are not severity, importance, fraud, invalidity or sentiment scores.

Representative reviews are the 3–5 review IDs closest to the region centroid,
with reason `centroid_proximity`.  Evidence remains the original Steam review;
derived chunk text is not substituted for source evidence.  Stable region IDs
are hashes of discovery type, sorted member IDs and contract fingerprint, not
raw HDBSCAN labels.

Both review and unit support are reported.  Long reviews can contribute many
units; unit count is never an independent Research Population denominator.
Raw review support, unique semantic-text support and duplicate share remain
separate.  Stage 2E exact/near-copy/coordinated-expression overlap is optional
read-only context and never changes membership.

## Taxonomy audit

`taxonomy_audit.py` reads existing labels where available and distinguishes:

- `well_covered`;
- `mixed_existing_labels`;
- `potential_gap`;
- `insufficient_taxonomy_coverage`;
- `unlabeled`.

It reports labeled/unlabeled support, coverage rate, primary/all-label
distributions and entropy.  `other/general` is not combined with missing
labels.  Taxonomy is an audit target, never discovery training truth; no
`TAXONOMY_VERSION`, prompt, label row or classification payload is changed.
No discovery region is a prevalence or player-importance claim.

## Persistence and CLI

Migration 15 adds independent structure/history tables:

- `semantic_discovery_runs` — exact semantic-index/run/fingerprint provenance;
- `semantic_discovery_regions` — region primitives and JSON detail;
- `semantic_discovery_members` — review membership roles;
- `taxonomy_audit_regions` — coverage audit detail.

The migration is additive and idempotent.  A mismatched population or semantic
index fingerprint is rejected.  Re-running the same index and contract reuses
the completed discovery result.

Migration 16 adds `semantic_discovery_materializations`.  Stage 3B.1 splits
identity into two layers:

- **Structure identity** depends only on the immutable Stage 3A index/fingerprint,
  `SemanticDiscoveryContract`, `semantic-discovery-structure-v1`, and
  `hdbscan-open-set-v2`. It owns vectors, neighbors, HDBSCAN labels,
  components, representatives, and stability.
- **Context materialization** depends on a separate
  `semantic-discovery-context-v1` fingerprint containing only review metadata
  (`review_id`, language, voted_up, timestamp, semantic text hash), normalized
  taxonomy labels, and sorted Stage 2E key/intersection IDs. Changing context
  creates a new materialization without rerunning HDBSCAN; identical context
  reuses the materialization.

The completed-cache path checks lightweight index metadata and structure/context
identity before loading vector BLOBs.  Vectors are therefore not loaded for a
completed structure/materialization cache hit.  `include_unit_level_audit=false`
does not run unit-neighborhood work and returns the stable disabled schema:
`{status: "disabled", unit_n: N, rare_neighborhood_candidate_n: null, units: []}`.
All neighbor and threshold-component diagnostics use exact blockwise cosine
operations rather than an in-memory NxN similarity matrix.  The opt-in
`tooling/benchmark_semantic_discovery.py` reports runtime, HDBSCAN calls,
cumulative HDBSCAN time, RSS where available, and accounting status for
deterministic 1k/5k/12k fixtures; benchmark numbers are diagnostics, not CI
SLAs.

One local Windows diagnostic measured roughly 1.5s / 189MB RSS for 1,000
reviews, 3.8s / 226MB for 5,000 reviews with 10,000 semantic units, and
20.3s / 246MB for 12,000 reviews. Every indexed review was accounted for.
These are engineering observations, not acceptance thresholds.

Run discovery with:

```text
python tooling/run_semantic_discovery.py --index-id <semantic-index-id>
python tooling/run_semantic_discovery.py --run-id <research-run-id> --output discovery.json
```

No provider, API key, LLM, BERTopic, UMAP or frontend is required.

## Limitations and deferred work

Review-level means can blur multi-topic long reviews, so unit-level audit is
retained (`unit_level_audit` keeps per-unit neighborhood evidence for rare and
tail-topic inspection).  HDBSCAN structure is sensitive to density and finite samples;
stability diagnostics expose this rather than selecting parameters against the
current taxonomy.  Region support is not semantic prevalence, and no causal,
severity, public-opinion or review-bombing claim is made.

Stage 3B does not name topics, repair taxonomy, train a classifier, build a
semantic sample, add UMAP visualization, or integrate `/analyze`.  Those belong
to later explicit stages, especially Stage 3C taxonomy validation/evolution.

If a discovery backend fails, migration 15 records a `failed` structure run
with the exact index/contract identity and redacted, bounded error text; no
completed report or region rows are created.  A context-materialization failure
leaves the completed structure intact and records a failed materialization.
Research Core, Stage 2E, taxonomy rows, and the immutable Stage 3A index are
unchanged.  The report contract is now `semantic-discovery-report-v2`; prior
v1 rows remain historical and are not silently rewritten.
