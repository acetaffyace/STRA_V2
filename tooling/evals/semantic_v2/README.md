# Semantic Engine V2 evaluation assets

This directory defines the reproducible asset contract required by Master
Spec §12. It does not manufacture labels. A release manifest must point to
two human-labeled, disjoint JSONL assets:

- `boundary_regression`: 200–500 labeled examples with a `boundary_pair`;
- `holdout`: 300–600 labeled examples, with at least 50 each for EN, ZH and
  JA when those primary-language slices are available.

Each record must use `stra-core-taxonomy-v2`, preserve the exact source review
text, and include `gold.core_topic_ids` plus exact-substring
`gold.evidence_spans`. The manifest records the dataset version, taxonomy,
evaluation commit, and SHA-256 for each asset. Run:

```powershell
py tooling/evals/semantic_v2/validate_assets.py path/to/manifest.json
```

The validator intentionally fails when the assets are missing, use the old
`sentinext-taxonomy-v1`, overlap, or do not meet the declared support bounds.
The existing `tooling/benchmarks/datasets/bench_v2` fixture is an unlabeled
60-review smoke dataset and is not a §12 release asset.

