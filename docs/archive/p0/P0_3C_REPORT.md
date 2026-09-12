# P0.3c Report — Frontend Metric Provenance Adoption

Status: **GO for P0.4 review** (P0.4 was not started by this change).

## Scope and audit

The frontend audit is recorded in [P0_3C_FRONTEND_METRIC_MAP.md](P0_3C_FRONTEND_METRIC_MAP.md). Before this phase, formal Dashboard and Compare recommendation/LLM rates could be recomputed from the currently displayed review sample. That made a filtered or truncated sample look like a run-level metric.

P0.3c changes only frontend metric sourcing and the single stale P0.1 xfail marker. It does not change API semantics, analysis execution, run schemas, labels, dashboard widgets, or ingestion.

## Adopted contract

`apps/dashboard/src/types/index.ts` now models the backend `MetricObservation` fields: metric identity, value, numerator/denominator, population/classified counts, coverage, source and denominator types, sampling semantics, run ID, formula version, status, and unavailable reason.

`apps/dashboard/src/lib/metricProvenance.ts` provides reusable presentation helpers:

- modern results read `metric_provenance` and never fall back to display-sample arithmetic;
- legacy numeric fields are used only when the provenance object is absent;
- unavailable/null values render as unavailable (`—` through existing formatters), not `0%`;
- run mismatch is rejected;
- comparison compatibility checks include metric ID, formula version, source, denominator, sampled status, and sampling semantics;
- secondary labels expose numerator/denominator and LLM coverage, and mark sampled evidence as selected/non-representative.

## Adoption

- Dashboard hero recommendation uses `recommendation_rate`.
- Dashboard hero issue/request rates use `technical_issue_rate` and `feature_request_rate`.
- Dashboard favorite and recent-analysis cards use the backend recommendation observation.
- Compare selection preview, Compare overview recommendation, and AI comparison payloads use the backend recommendation observation.
- Filtered Dashboard/Compare states remain sample-derived only as explicit interactive views and are labeled accordingly.
- Backend trend remains authoritative when filters are inactive. Review-derived trend fallback is limited to active filters.
- Existing cohort, category, segment, and heuristic surfaces without equivalent backend observations were not given invented denominators. They remain documented legacy/interactive surfaces pending a later contract.

## Legacy and mismatch behavior

Old records without `metric_provenance` remain displayable through their existing numeric insight fields. Modern records with missing or run-incompatible observations show unavailable rather than merging a different run or recalculating from the sample.

## Tests and validation

- Backend full pytest: **89 passed, 2 intentional xfailed**.
- Backend `compileall`: passed.
- Backend import smoke: passed.
- Frontend TypeScript `npx tsc --noEmit`: passed.
- Frontend lint: blocked by incomplete local dependencies (`language-subtag-registry/data/json/index.json` missing from installed `node_modules`).
- Frontend build: blocked by incomplete local dependencies (`caniuse-lite/dist/data/browsers` missing from installed `node_modules`). No dependency files were changed.
- `git diff --check`: passed.

The only xfail cleanup in this phase was removal of the stale P0.1 FTS marker. The two unrelated future-P0 xfails remain unchanged.

## Files changed

- `P0_3C_FRONTEND_METRIC_MAP.md`
- `P0_3C_REPORT.md`
- `apps/dashboard/src/types/index.ts`
- `apps/dashboard/src/lib/metricProvenance.ts`
- `apps/dashboard/src/hooks/useAnalysisViewModel.ts`
- `apps/dashboard/src/app/dashboard/page.tsx`
- `apps/dashboard/src/app/compare/page.tsx`
- `apps/dashboard/src/components/compare/OverviewComparisonCard.tsx`
- `apps/api/tests/test_p0_contracts.py` (P0.1 stale xfail marker only)

## Known risks

The existing category/cohort panels still contain legacy sample-derived calculations because P0.3b does not publish matching cohort observations. They are not silently promoted to formal run metrics in this phase. Reinstalling the dashboard dependencies is required before lint/build can be independently rerun.

## Recommendation

**GO for P0.4 review**, subject to rerunning frontend lint/build after dependency repair. Stop here; P0.4 was not implemented.
