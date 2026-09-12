# Presentation Projections V1 Implementation Report

Date: 2026-08-26  
Branch: `presentation/projections-v1`

## Scope completed

Implemented the P1 deterministic, read-only projection layer and minimal presentation hooks:

- `daily_review_volume`
- `daily_recommendation_rate`
- `recent_analysis_summary`
- `version_comparison_population_strip`
- `provenance_strip`

The implementation is in `apps/api/senti_next/presentation_projections.py` and is exposed through `apps/api/senti_next/routes/presentation.py`. The dashboard and Version Review pages consume the projections without changing existing visual composition or analytical semantics.

No LLM call, taxonomy/prompt change, database migration, derived table, cache, or analytical denominator change was introduced. P2 `weekly_topic_prevalence` remains deferred.

## Truthfulness boundary

The two daily projections require the immutable general-analysis result to prove that its stored review payload equals `analysis_population_count` and that every row has a valid timestamp. Existing integration general runs currently have `analysis_population_count = null`, so the daily endpoints correctly return `available: false` with `immutable_result_population_unknown`; they do not fall back to the app-wide review table or sampled payload.

The valid integration Version Review V2 run `3a738a76f94c4e6894e67bb171225d67` returns an available population strip with raw counts 831 / 1573, semantic samples 831 / 1000, classified counts 831 / 768, coverage `COMPLETE / COMPLETE`, gate `PASS`, and comparison status `READY`.

## Verification

- Backend projection/provenance unit tests: `9 passed`
- Dashboard TypeScript check: `npx tsc --noEmit` passed
- Full production build: PASS under the controlled elevated build environment. The earlier non-elevated run failed with Windows `spawn EPERM`, diagnosed as the execution environment's worker-spawn restriction.
- Benchmark evidence: `artifacts/benchmarks/presentation_projections_v1.json`

The benchmark uses 1,000 synthetic in-memory rows and does not open or mutate a runtime database. It measured 30 output points for each daily projection and records elapsed time and input population.

## Deferred items

Alerts, real-time monitoring, arbitrary cross-run shifts, custom Version Review windows, report export history, `new_reviews_since_previous_run`, and P2 weekly topic prevalence were not implemented. They require separate capability/semantic contracts.
