# Presentation Projections V1 Population Provenance

Date: 2026-08-26  
Branch: `presentation/projections-v1`

## Pipeline audit

The current general-analysis path is:

`Steam fetch → dedupe/sort/filter in request path → all_reviews passed to background job → semantic/provider labeling over all_reviews → DataFrame aggregation → sampled reviews payload persisted`

The exact analysis population exists in memory as `all_reviews` in `_run_analysis_job`. At that point it is the post-acquisition population used for the current-snapshot analysis. `total_reviews = len(all_reviews)` is therefore the exact run population count.

The prior persistence defect had two parts:

1. Historical runs predated reliable population provenance and have `analysis_population_count = null` in `analysis_runs`.
2. The immutable result stores `reviews_payload` capped by `SAMPLE_LIMIT`, so the stored sampled reviews cannot identify the full population.

The route now passes `analysis_population_count = total_reviews` explicitly during completion instead of relying only on the metadata field. It also stores a new-run immutable metadata extension before result insertion.

## Selected closure design

The selected design is B: minimal immutable temporal source rows in the existing immutable result metadata:

```json
{
  "population_provenance": {
    "schema_version": "general-population-temporal-v1",
    "population_count": 500,
    "complete": true,
    "rows": [
      {"review_id": "...", "timestamp_created": 1700000000, "voted_up": true}
    ]
  }
}
```

The rows are created from the exact `all_reviews` list before semantic sampling and before the capped UI/result review payload is produced. `review_id` is taken from Steam `recommendationid` (with the normalized `review_id` field as compatibility fallback). The contract requires every row to have a unique ID, integer timestamp, and boolean `voted_up`; otherwise the provenance is marked incomplete and the daily projections remain unavailable.

This preserves exact membership and the two temporal inputs needed by the P1 projections. It is independent of later app-wide database growth and does not require a migration or derived table.

## Design comparison

- A, an ID-only manifest, proves membership but needs another immutable source for timestamps and recommendation values. B contains those required fields and is therefore safer for the current projections.
- C, precomputed daily aggregates, is smaller but loses exact membership and future temporal-slice reuse. It is not selected as the primary contract.
- D, reconstructing from canonical reviews later, is not historical-proof because canonical rows, dedupe, or filters can change after the run. It is rejected.

## Historical policy

No historical immutable result is backfilled or rewritten. A historical run without `population_provenance` returns:

`available: false` with `historical_run_population_provenance_unavailable`.

`analysis_population_count` by itself is deliberately insufficient. A populated count plus a sampled result payload does not identify the exact temporal source rows.

## Mutation and denominator boundary

The projection reads only the immutable provenance rows. It does not read current app-wide reviews, does not use the semantic sample, does not use classification labels, and does not change the analytical denominator. `voted_up` remains the Steam recommendation numerator field.

## Real-run status

No paid/provider call was made during closure. A fresh real general run must be used for runtime acceptance; an old historical run cannot prove the new contract. If a fresh run requires a provider call, the exact gate is `REAL_GENERAL_RUN_ACCEPTANCE_REQUIRES_PROVIDER_APPROVAL`.
