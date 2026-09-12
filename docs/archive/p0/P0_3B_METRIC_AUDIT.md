# P0.3b Metric Production Audit

## Population contract

- `population`: valid reviews in the current general-analysis run frame after
  `build_reviews_dataframe()`; the frame is built from `all_reviews` before
  display sampling.
- `validated_classified`: population rows whose joined review label has
  `label_origin='llm'` and `validated=true`.
- `evidence_population`: validated rows with aspect/evidence enrichment data;
  this is a selected, non-representative subset when enrichment is limited.
- `display_sample`: the bounded `reviews_payload` saved for presentation. It
  is never a formal KPI denominator.

## Current metric/use map

| Metric/family | Current formula/source | Labels? | Current risk | P0.3b contract |
|---|---|---:|---|---|
| `total_reviews` / review count | `len(df)` / Steam review rows | no | low; population semantics implicit | `raw_steam`, denominator `population` |
| recommendation/share positive/negative | `voted_up` mean/count in `summarize_sentiment()` and `recommendation_rate()` | no | display/sample confusion outside backend | `raw_steam`, population denominator |
| playtime/language/purchase/platform segments | deterministic aggregations in `analysis.py` | no | nested outputs lack source/coverage metadata | raw/deterministic, subgroup population denominator |
| `issue_rate` | mean of non-empty `llm_issue_subcategories` over all `df` | yes | fallback/legacy rows can be treated as no issue | `llm_derived`, validated classified denominator |
| `feature_request_rate` | mean of non-empty `llm_request_subcategories` over all `df` | yes | same denominator ambiguity | `llm_derived`, validated classified denominator |
| `coverage_rate` | rows with any structured payload | yes | not equivalent to validated coverage | `classification_coverage`, population denominator |
| category breakdown/issue counts | exploded label arrays in `prepare_insights()` | yes | current path can include untrusted labels | validated classified population |
| category recommendation rates | `voted_up` mean within label category | yes | category membership and denominator not provenance-aware | validated classified category cohort |
| evidence/subcategory snippets | selected snippets from `aggregate_subcategory_insights()` | yes | evidence subset is not full population | evidence population; sampled semantics |
| Health/market/refund/core-fan outputs | deterministic calculations in `analysis.py` over derived fields | mixed | formulas are heuristic/derived, not a single objective KPI | registry as `heuristic` where exposed |
| Version Review periods/categories | `version_analysis.calculate_version_metrics()` over event-window rows and labels | yes | existing response contract and proxy semantics | audit/document; no broad rewrite in P0.3b |

## Frontend audit

`apps/dashboard/src/app/dashboard/page.tsx` and
`apps/dashboard/src/app/compare/page.tsx` contain local recommendation-rate
calculations from arrays returned for display. `useAnalysisViewModel.ts` also
formats backend insight fields. These are frontend adoption issues for P0.3c;
P0.3b does not redesign the components. The backend provenance observations
are the replacement source of truth.

## Decision

Implement a code registry and serializer in `metric_provenance.py`. Keep
legacy numeric fields in `insights` for compatibility, but correct LLM-derived
denominators and add `metric_provenance` observations with explicit null/
unavailable semantics. Version Review keeps its existing response shape and
is not forced into the general-analysis serializer in this phase.

