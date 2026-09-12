# Presentation Projections V1 Contract

Date: 2026-08-26  
Branch: `presentation/projections-v1`  
Status: P1 contract for implementation

## Scope and non-goals

These are deterministic, read-only presentation contracts. They do not create analytical meaning, alter denominators, call an LLM, change taxonomy/prompts, mutate immutable results, or require a database migration. P2 `weekly_topic_prevalence` is explicitly deferred because its denominator and label provenance require a separate semantic gate.

Population provenance closure adds a new-run-only immutable metadata extension: `metadata.population_provenance`. It stores the exact run population's minimal temporal source rows (`review_id`, `timestamp_created`, `voted_up`) and a completeness/count marker. It is not a semantic sample and is not used to calculate classification metrics.

All projection requests are exact-run requests where a run is involved. The authoritative identity is `app_id + run_id`; a title or latest-run guess is never used.

## Shared rules

- Source rows are read from the exact immutable result for the requested run, or from the exact immutable Version Review V2 result and its existing run/design/event records.
- No projection queries all app reviews as a substitute for an exact run population.
- Unknown is represented as `null`, `available: false`, or an explicit `UNKNOWN` status according to the response contract. Unknown is never converted to zero.
- Time buckets use UTC calendar dates (`YYYY-MM-DD`) because stored review timestamps are Unix/UTC-compatible and this is deterministic across runtimes.
- A `day` bucket is a UTC calendar day. Continuous zero-review days are emitted only when an explicit `from` and `to` range is supplied; otherwise only observed days are returned.
- Projection responses include `projection_version: "presentation-projections-v1"` and exact source identity where applicable.

## P1. `daily_review_volume`

### Input source and exact scope

`storage.get_analysis_run(run_id)` plus `storage.get_analysis_run_result(run_id)`, restricted to `run_type=general_analysis` and `status=completed`. The immutable result's `metadata.population_provenance.rows` is the only temporal source.

The current immutable result stores a review payload capped by `SAMPLE_LIMIT`. New completed runs are available only when `metadata.population_provenance` has schema `general-population-temporal-v1`, `complete=true`, its row count equals `population_count`, every row has a unique `review_id`, integer `timestamp_created`, and boolean `voted_up`. Historical results without this metadata remain unavailable. The projection must not silently fall back to app-wide canonical reviews or the sampled `result.reviews` payload.

### Formula

For each exact result review with a valid `created_at`/`timestamp_created`:

`review_count(period) = count(review observations whose UTC timestamp falls in period)`

`review_count` counts review observations, not players.

### Response

```json
{
  "projection": "daily_review_volume",
  "projection_version": "presentation-projections-v1",
  "available": true,
  "run_id": "...",
  "app_id": 123,
  "bucket": "day",
  "bucket_timezone": "UTC",
  "population_scope": "exact_immutable_run_result",
  "population_count": 500,
  "window": {"start": "2026-08-01", "end": "2026-08-31"},
  "points": [{"period": "2026-08-01", "review_count": 12}],
  "unavailable_reason": null
}
```

### Null/unknown behavior and complexity

Missing or incomplete immutable rows return `available: false`, `points: []`, and a reason. No zero-filled point is returned without an explicit range. Complexity is O(n) over the immutable result payload, with O(d) output points.

## P1. `daily_recommendation_rate`

### Input source and exact scope

The same exact immutable general-analysis result and completeness gate as `daily_review_volume`.

### Formula and denominator

For each UTC day:

- `review_count` = valid review observations in the day;
- `recommended_count` = observations with canonical Steam `voted_up === true`;
- `recommendation_rate` = `recommended_count / review_count`.

This is Steam Recommendation Rate, never sentiment or satisfaction. A zero denominator returns `recommendation_rate: null`; it never returns `0%`.

### Response

```json
{
  "projection": "daily_recommendation_rate",
  "projection_version": "presentation-projections-v1",
  "available": true,
  "run_id": "...",
  "app_id": 123,
  "bucket": "day",
  "bucket_timezone": "UTC",
  "population_scope": "exact_immutable_run_result",
  "points": [{
    "period": "2026-08-01",
    "review_count": 12,
    "recommended_count": 10,
    "recommendation_rate": 0.833333
  }],
  "unavailable_reason": null
}
```

Complexity is O(n) over the immutable result payload. No minimum-support rule is introduced.

## P1. `recent_analysis_summary`

### Input source

`storage.list_analysis_history(limit)` supplies exact history rows. For each eligible completed general-analysis row, `storage.get_analysis_run(run_id)` and `storage.get_analysis_run_result(run_id)` provide exact counts and authoritative recommendation provenance. Existing starred-game metadata supplies artwork/title only when already present.

### Fields and semantics

- `app_id`, `run_id`: exact identity;
- `game_title`, `artwork/header_image`: existing game identity/context, nullable;
- `run_type`, `analysis_mode`, `status`, `completed_at`: lifecycle fields;
- `requested_count`, `retrieved_count`, `analysis_population_count`, `classified_count`: kept separate;
- `recommendation_rate`: existing immutable insight/provenance value, nullable;
- `reopen_url`: generated only from both `app_id` and `run_id`.

Missing artwork or recommendation rate is `null`; no fallback value or latest substitution is allowed. Complexity is O(k) history rows plus exact-result lookups.

## P1. `version_comparison_population_strip`

### Input source and authority

`storage.get_analysis_run(run_id)` and its existing immutable `metrics.version_review_v2`, plus the stored run config and `storage.get_version_event` records. The endpoint returns unavailable for legacy/non-V2 results. It does not recalculate conclusions or mutate the result.

### Fields and semantics

The strip exposes existing V2 fields only: event IDs/dates, approved window days, raw counts, reviews/day, recommendation rates/delta, semantic sample counts, classified counts, coverage statuses/gate, and comparison status. Classified counts are returned only when present and provenance-safe; absent/default counts are `null`/`UNKNOWN`, never zero.

### Response

```json
{
  "projection": "version_comparison_population_strip",
  "projection_version": "presentation-projections-v1",
  "available": true,
  "run_id": "...",
  "app_id": 553850,
  "previous_event": {"event_id": "...", "event_date": "...", "event_name": "..."},
  "current_event": {"event_id": "...", "event_date": "...", "event_name": "..."},
  "window_days": 7,
  "raw_count_a": 831,
  "raw_count_b": 1573,
  "reviews_per_day_a": 118.7,
  "reviews_per_day_b": 224.7,
  "recommendation_rate_a": 0.80,
  "recommendation_rate_b": 0.78,
  "recommendation_delta_pp": -2.0,
  "semantic_sample_a": 831,
  "semantic_sample_b": 1000,
  "classified_count_a": null,
  "classified_count_b": null,
  "coverage_status_a": "COMPLETE",
  "coverage_status_b": "COMPLETE",
  "coverage_gate": "PASS",
  "comparison_status": "READY",
  "unavailable_reason": null
}
```

Complexity is O(1) over the immutable V2 result and at most two event lookups.

## P1. `provenance_strip`

### Input source

Exact `analysis_runs` row, immutable result metadata, and `analysis_designs` snapshot when present. Version Review provenance may also use the immutable run config and existing V2 result fields.

### Fields and meaning

The strip discloses run ID, app ID, source, mode, window, run type, result schema/version, taxonomy/prompt/provider/model IDs, analysis design ID, population counts, classified/fallback counts, completion time, and existing immutable hashes where present. It does not create an accuracy/confidence score or replace Evidence Grade.

All optional fields remain `null` when absent. Complexity is O(1) for the run plus one design lookup.

## Caching and performance

No cache is introduced in V1. All projections are O(n), O(k), or O(1) read-only calculations over immutable inputs. Each verification records input population, execution time, output point count, and query count where practical. Future exact-run caching is possible but is not required by current measured scope.

## Population provenance design decision

| Option | Correctness / reproducibility | Mutability risk | Storage / complexity | Decision |
|---|---|---|---|---|
| A. Review-ID manifest | Proves membership; still needs timestamp and recommendation fields for temporal output | Low if stored in immutable result | Small-to-medium; requires a second lookup unless source fields are included | Partial fit |
| B. Minimal immutable temporal rows | Proves membership and contains the exact temporal inputs needed by both P1 projections | Low; decoupled from later app-wide DB growth | O(N) small rows in existing immutable metadata; no migration/table | **Selected** |
| C. Completion-time daily aggregates | Reproducible for current two charts and smallest output | Low | Smallest storage, but cannot support future temporal slices or audit membership | Deferred as too narrow |
| D. Reconstruct canonical reviews later | Potentially low implementation cost | Unsafe if canonical rows, dedupe, or filters change after the run | No new storage, but historical proof is absent | Rejected |

Selected B persists `review_id`, `timestamp_created`, and `voted_up` for every exact analysis population row, plus `population_count`, `complete`, and schema version. Existing historical results without this extension remain unavailable and are not backfilled.

## P2 deferred

`weekly_topic_prevalence` is deferred. It requires validated compatible labels, `label_origin`, taxonomy-version provenance, and a classified semantic denominator. No P2 implementation or UI is included in this phase.
