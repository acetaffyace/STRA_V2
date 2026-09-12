# Provenance Acceptance Run Plan

Date: 2026-08-26  
Branch: `presentation/projections-v1`  
Game: `STEINS;GATE RE:BOOT` (`app_id=4012810`)  
Runtime source: existing local `agent-a` review cache  
Status: dry-run estimate only — provider call not started

## Candidate estimates

The estimates use the current local review population and the same label-reuse estimator used before a general analysis run. Candidate rows are the first N reviews in the current local run input order. UTC dates are derived from each row's immutable `timestamp_created` field.

| Requested population | Estimated provider classifications | Cached classifications | Short/rule-handled reviews | Distinct UTC dates | Exact provenance | Daily volume reconciliation | Daily recommendation reconciliation |
|---:|---:|---:|---:|---:|---|---|---|
| 20 | 14 | 0 | 6 | 2 (`2026-08-24`, `2026-08-25`) | Yes, if the new-run provenance contract persists all 20 rows | Yes; 20 total across 2 buckets | Yes; `voted_up` numerator and 20-row denominator |
| 50 | 39 | 0 | 11 | 2 (`2026-08-24`, `2026-08-25`) | Yes, if the new-run provenance contract persists all 50 rows | Yes; 50 total across 2 buckets | Yes; `voted_up` numerator and 50-row denominator |
| 100 | 78 | 0 | 22 | 3 (`2026-08-23`–`2026-08-25`) | Yes, if the new-run provenance contract persists all 100 rows | Yes; 100 total across 3 buckets | Yes; `voted_up` numerator and 100-row denominator |

## Recommendation

Recommended candidate: **100 reviews**.

It is the smallest candidate that spans three distinct UTC dates in the current local population. Twenty and fifty reviews span only two dates and would technically exercise the reconciliation code, but provide weaker temporal coverage for validating multiple daily buckets. One hundred reviews therefore gives the smallest meaningful temporal acceptance scope.

Estimated provider-call budget: **78 review classifications**.

This is an estimate, not a measured spend. The estimator reports `cached_reviews=0`, `identity_mismatch=100`, and 78 reviews requiring provider classification; 22 are short/rule-handled. No provider call has been made.

## Acceptance checks for the eventual fresh run

The run should be accepted only if all of the following are observed after completion:

1. `analysis_population_count = 100`.
2. `metadata.population_provenance.complete = true`.
3. `metadata.population_provenance.population_count = 100`.
4. Exactly 100 unique provenance rows exist, each with `review_id`, integer `timestamp_created`, and boolean `voted_up`.
5. The daily volume point counts sum to 100.
6. The daily recommendation point `review_count` values sum to 100.
7. The daily recommendation `recommended_count` sum equals the count of provenance rows where `voted_up == true`.
8. The projection result is unchanged if app-wide reviews grow after the run.
9. The UI renders the three daily UTC buckets without fabricated values.

## Stop condition

**STOP before calling the provider.** This document records the recommended count and estimated provider budget only. No fresh run, provider request, database write, or integration change was started.
