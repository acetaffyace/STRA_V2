# P0.3c Frontend Metric Adoption Map

Audit completed before implementation edits. Scope is limited to Dashboard and Compare metric presentation.

| Surface | Current source | P0.3c disposition | Contract |
|---|---|---|---|
| Dashboard hero recommendation rate | Recomputed from `filteredReviewSample` | Migrate unfiltered/formal view to `insights.metric_provenance.recommendation_rate`; retain local calculation only for active filters | Raw Steam population denominator |
| Dashboard hero issue/request rates | Recomputed from displayed sample | Migrate unfiltered/formal view to `technical_issue_rate` / `feature_request_rate`; filtered view remains explicitly interactive | Validated classified denominator and coverage |
| `useAnalysisViewModel` summary | Legacy `insights.recommendation` and `insights.llm` numeric fields | Prefer metric observations; legacy numeric fields are fallback for old records only | Null/unavailable is presented as `—`, never as 0% |
| Dashboard starred/recent cards | Recomputed from each card sample | Use backend recommendation observation, then legacy insight field | No display-sample recomputation |
| Compare selection preview | Recomputed from preview sample | Use backend recommendation observation, then legacy insight field | No display-sample recomputation |
| Compare overview recommendation | Recomputed from filtered sample for every state | Use backend observation when no filters; local result only for active filters and labeled interactive | No silent sample merge |
| Compare trend | Backend trend when available; sample fallback | Backend trend remains formal; sample trend fallback is limited to active filters | Legacy backend trend remains compatible |
| Dashboard/Compare category and cohort breakdowns | Local sample-derived rates | Not migrated to invented formulas; retain as legacy/interactive until matching cohort observations exist in the backend | Must be documented as non-formal where exposed |
| Dashboard player segments / derived utilities | Local sample-derived segment calculations under filters | Preserve existing interactive behavior; no new denominator contract introduced | Not used as core formal KPI |
| Health/risk/heuristic outputs | Backend insight fields | Preserve; metric provenance does not yet expose equivalent formal observations | Existing heuristic semantics unchanged |

## Adoption rules

Modern results with a `metric_provenance` object use observations as the authority. If an expected observation is absent or has a run mismatch, the UI presents it as unavailable rather than recomputing it from the displayed sample. Legacy numeric fields are used only when the provenance object is absent.

Compare presentation must not silently merge observations from incompatible runs, formula versions, source types, sampling semantics, or denominator types. Sample-derived values are allowed only for an explicitly active interactive filter state.
