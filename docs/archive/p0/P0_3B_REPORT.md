# P0.3b Report — Metric Provenance / Denominator Contract

## Outcome

P0.3b is complete. Backend formal metrics now expose population, numerator,
denominator, eligibility, coverage, source semantics, sampling semantics,
formula version, and `run_id`. Existing numeric insight fields remain for
compatibility, while LLM-derived rates now use validated-classification
denominators. P0.3c frontend adoption was not started.

## Audit summary

The audit is recorded in [P0_3B_METRIC_AUDIT.md](P0_3B_METRIC_AUDIT.md).

`build_reviews_dataframe()` creates the run frame from `all_reviews`; this is
the backend population before the presentation sample is limited. Raw Steam
metrics use fields such as `voted_up`, playtime, language, purchase and
platform directly. Existing `issue_rate` and `feature_request_rate` used to
average label presence across every frame row, while `coverage_rate` meant
“has structured payload”. That allowed fallback/legacy rows to become implicit
negative observations.

The dashboard and compare pages also contain local recommendation-rate
calculations over returned arrays. Those are documented as P0.3c adoption
work; P0.3b does not modify frontend components.

Version Review remains on its existing response and metric architecture. Its
denominator behavior is audited/documented but was not broadly rewritten or
forced into the general-analysis contract.

## Canonical population types

- `population`: valid reviews in the current run frame;
- `validated_classified`: population rows with
  `label_origin='llm' AND validated=true`;
- `evidence_population`: validated rows with aspect/evidence enrichment;
  this is selected and non-representative when enrichment is limited;
- `display_sample`: bounded payload for UI performance only, never a KPI
  denominator.

## Registry and observation contract

`apps/api/senti_next/metric_provenance.py` provides the code-level
`MetricDefinition` registry and `MetricObservation` serializer. Registered
core metrics include:

- `review_count`;
- `recommendation_rate` and `negative_review_rate`;
- `technical_issue_rate`;
- `feature_request_rate`;
- `classification_coverage`;
- `evidence_coverage`.

Each observation includes:

`metric_id`, `value`, `numerator`, `denominator`, `population_count`,
`eligible_count`, `classified_count`, `coverage`, `source_type`,
`denominator_type`, `is_sampled`, `run_id`, `formula_version`,
`sampling_semantics`, `status`, and `unavailable_reason`.

Source vocabulary is stable: `raw_steam`, `deterministic_derived`,
`llm_derived`, and `heuristic`. A deterministic division over LLM labels is
still `llm_derived` because its dependency is LLM classification.

## Denominator corrections

For a run with 10 population reviews, 8 validated LLM labels, 2 fallback or
legacy rows, and 4 technical issues:

```text
technical_issue_rate = 4 / 8 = 0.5
classification_coverage = 8 / 10 = 0.8
```

It is not `4 / 10`. Fallback and legacy labels are not silently treated as
no-issue observations.

Raw recommendation rate remains population-based: 7 recommended out of 10 is
`7 / 10`, independent of classification coverage.

The compatibility `insights.llm.issue_rate`, `insights.llm.feature_request_rate`,
and `insights.llm.coverage_rate` now use the corrected semantics. The new
`insights.metric_provenance` object carries the complete contract.

Category issue metrics are generated against the validated classified
population. Cohort observations use the eligible subgroup denominator rather
than the whole-game denominator.

Zero denominator produces `value=null`, `status='unavailable'`, and
`unavailable_reason='denominator_zero'`; it does not produce a misleading 0%.

## Evidence and heuristic semantics

`evidence_coverage` uses the enriched/aspect subset, exposes its own coverage,
and sets `is_sampled=true` with explicit non-representative sampling semantics.
The evidence subset is not presented as full-population coverage.

Existing Health/market/refund/core-fan outputs remain compatibility payloads;
they are not redefined in this phase. The registry vocabulary permits them to
be registered as `heuristic` when promoted as formal metrics.

## Run linkage and immutability

`prepare_insights(df, run_id=run_id)` creates observations linked to the
current durable general-analysis run. The resulting `metric_provenance` is
inside the P0.2c immutable `analysis_run_results` payload. Run B therefore
cannot rewrite Run A's metric provenance. The completed run's
`classified_count` is also now the validated LLM count rather than total label
payload count.

## Tests

Added `test_p0_3b_metric_provenance.py` covering:

- raw Steam denominator;
- validated LLM denominator with fallback/legacy exclusion;
- subgroup denominator;
- evidence coverage and sampled semantics;
- zero denominator unavailable behavior;
- run-linked compatibility insight payload.

The two P0.3b contract xfails were promoted to normal passing tests:
`build_metric_contract` and fallback denominator exclusion.

Final backend validation:

- **79 passed**;
- **2 intentional xfails** (P0.4 evidence verifier, P0.6 cost ledger);
- **1 existing XPASS** for the already-implemented P0.1 FTS invariant test;
- compileall: passed;
- import smoke: passed;
- P0 migration, P0.2, P0.3a, Version Review and existing API consumer tests:
  passed.

## Performance

On a local 1,000-row pandas fixture, building seven provenance observations
and serializing them took **2.28 ms**. The implementation operates on the
already-loaded DataFrame and label metadata; it performs no per-review
database queries and introduces no N+1 provenance lookups.

## Compatibility and files

Legacy numeric insight fields remain present. `metric_provenance` is additive.
No dashboard, FTS, immutable run lifecycle, label history, Golden Set,
evidence verification, worker, or cost-ledger changes were made.

Files changed include:

- `apps/api/senti_next/metric_provenance.py`;
- `apps/api/senti_next/insights.py`;
- `apps/api/senti_next/llm.py`;
- `apps/api/senti_next/routes/analysis.py`;
- `apps/api/tests/test_p0_3b_metric_provenance.py`;
- `apps/api/tests/test_p0_contracts.py`;
- `P0_3B_METRIC_AUDIT.md`.

## Known risks

- frontend consumers still need P0.3c adoption to stop recalculating formal
  KPIs from display samples;
- Version Review retains its established response semantics;
- not every cosmetic or experimental nested number is registered;
- heuristic outputs remain heuristic and should be explicitly registered
  before being treated as formal decision metrics.

## Recommendation for P0.3c

**GO for P0.3c**, subject to human review. P0.3b stops here.
