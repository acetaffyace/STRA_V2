# STRA Stage 4D.1 — Canonical Comparison Foundation

## Baseline and scope

- Baseline SHA: `04fcaee27e45fd26f95e59f8c58f755ed520bbe9`
- Branch: `integration/research-pipeline-v1`
- Migration: `24` (unchanged)
- Scope: shared read-side comparison projection, Version Review official metric convergence, Game Compare official recommendation convergence, regression coverage, and browser QA.
- Deferred: Agent and Reports migration; no taxonomy, Research Core, embedding, HDBSCAN, or schema changes.

## Whole-project audit and truth ownership

| Module | Current state | Canonical source | Status |
|---|---|---|---|
| Research Core | authoritative | `research-report-v1` | SEALED |
| Semantic | authoritative | `SemanticMeasurementResult` / 3F | SEALED |
| Discovery | sidecar | 3A/3B/3C persisted materialization | SEALED |
| Dashboard | canonical consumer | Unified / 3F presentation projection | SEALED |
| Reviews | exact-run consumer | frozen population + materialization | SEALED |
| Version Review | comparison consumer | `research-comparison-v1` adapter | THIS STAGE |
| Game Compare | comparison consumer | `research-comparison-v1` for exact runs | THIS STAGE |
| Game Agent | downstream consumer | canonical results + comparison | D2 inventory only |
| Reports | output consumer | canonical results | D2 inventory only |
| Desktop / Package | distribution | full product | 4E |

The comparison foundation exists in `apps/api/senti_next/research_comparison.py`. It is read-only: it does not fetch Steam data, call an LLM, execute Research Core, embed, cluster, mutate taxonomy, rotate bundles, or refresh cache.

## `research-comparison-v1`

The contract contains:

- exact `left` and `right` `ComparisonSide` objects;
- `source_kind` (`analysis_run` or `version_window`), `source_id`, and `app_id`;
- quantitative values taken from `research_report.recommendation.population` and the explicit sampling contract;
- semantic side values taken from persisted 3F rows, including side-specific classified denominators;
- internal provenance for population, measurement, taxonomy, provider/model, prompt, schema, qualification, and semantic fingerprint;
- compatibility gates for quantitative, sampling method, scope, semantic side-by-side, and semantic delta comparison;
- percentage-point recommendation and semantic deltas only when the relevant compatibility gate passes.

`recommendation_rate_delta_pp` is `right - left`, expressed in percentage points. Semantic deltas use each side's `classified_n`; a total population denominator is never substituted.

### Compatibility rules

Sampling equivalence compares languages, review type, purchase type, collection order, off-topic activity, and max review scope. Different before/after time windows are recorded as `time_window_different_by_design` when the method is otherwise equivalent. Semantic delta requires matching measurement bundle, taxonomy identity, provider/model, prompt, schema, measurement status, claim status, and validation status. A missing semantic side remains a valid quantitative comparison but disables semantic delta.

## Version Review convergence

`GET /runs/{run_id}/comparison` now attaches the shared projection as `comparison.canonical_comparison` while retaining `version-review-v2` as a compatibility payload for the existing UI, events, paired evidence, sensitivity, and narrative cards. Official A/B population, recommendation values, and recommendation delta are read from the shared projection. Incompatible or unavailable semantic identities do not receive an official semantic delta; the UI keeps side-by-side compatibility wording.

Existing Version Review planning, event selection, lifecycle window controls, coverage gate, evidence cards, recommendations, and sensitivity UI remain in place.

## Game Compare convergence

The Compare workspace resolves the exact run IDs from persisted metric provenance and calls `GET /comparison?left_run=...&right_run=...`. Official recommendation values no longer depend on the filtered raw sample. Existing filters, category cards, subcategory cards, trend view, AI summary, and selection controls remain available; filtered category/subcategory values are explicitly descriptive. Subcategory review links now carry the exact run and taxonomy key to the existing Reviews workspace.

## Agent dependency inventory (D2)

| Agent tool | Current source | Canonical source needed | D2 action |
|---|---|---|---|
| `research.snapshot` | dashboard / legacy result readers | Unified quantitative projection | migrate in D2 |
| `research.metric` | mixed metric ownership / legacy insight readers | Research Core + 3F | migrate in D2 |
| `taxonomy.aggregate` | legacy label aggregates | 3F semantic rows | migrate in D2 |
| `reviews.search` | mutable review store | exact-run Reviews API when run-scoped | migrate in D2 |
| `reviews.sample` | legacy sample payload | frozen population/materialization | migrate in D2 |
| `reviews.aggregate` | derived legacy aggregates | canonical result or explicitly descriptive filter view | migrate in D2 |
| `reviews.timeseries` | presentation projections | persisted run-scoped descriptive projection | migrate in D2 |
| `themes.overview` | legacy insights | 3F topics/issues/requests | migrate in D2 |
| `themes.timeline` | legacy/version helpers | comparison projection | migrate in D2 |
| `segments.compare` | legacy segment readers | canonical segment contract | migrate in D2 |
| `competitors.compare` | legacy compare path | `research-comparison-v1` | migrate in D2 |
| `version.delta` | Version Review V2 | `research-comparison-v1` | migrate in D2 |
| `hypothesis.check` | legacy evidence/narrative | canonical result + exact evidence | migrate in D2 |

The highest-risk tools are `competitors.compare` and `version.delta`; neither should retain local recommendation or semantic delta formulas after D2.

## Reports dependency inventory (D2)

| Report surface | Current source | Canonical future source |
|---|---|---|
| Decision Evidence Matrix | mixed `analysis.insights` and evidence readers | exact-run 3F + evidence projection |
| `five_questions` | `analysis.insights.five_questions` | Unified Research Result / narrative projection |
| Echo Rate | legacy insights | canonical quantitative/semantic projections where defined |
| Key Themes | legacy insight aggregates | SemanticMeasurementResult |
| recommendation | mixed legacy and Research Core | Research Core quantitative result |
| issues / requests | legacy insight fields in some callers | SemanticMeasurementResult |
| evidence | mutable/legacy evidence readers | exact-run evidence endpoint |
| run identity | app latest result in some callers | pinned ComparisonSide / exact run |

`analysis.insights.five_questions` remains a legacy dependency this stage and is explicitly deferred to D2.

## Tests

Added `tests/unit/test_research_comparison.py` covering:

- exact quantitative sides and 0.70 → 0.75 = +5.0 percentage points;
- raw fixture mutation cannot change official persisted metrics;
- same semantic identity enables delta;
- bundle, taxonomy, provider/model, prompt, schema, and qualification mismatch disables delta;
- one semantic side missing preserves quantitative comparison;
- sampling mismatch vs intentional version time-window difference;
- side-specific classified denominators;
- exact A/B isolation from a changed latest mutable result;
- version-window adapter shape.

Targeted backend result: **16 passed** across comparison, dashboard presentation, and Version Review V2 tests.

Frontend typecheck: **passed**.

## Browser QA

The in-app browser bridge was unavailable in this desktop session, so the required real Chromium validation used the project's installed Playwright/Chromium runtime against the local API and frontend. No fallback renderer was used.

Runner: `tooling/vertical_slice/stage4d_playwright_qa.mjs`

Three independent render → screenshot → inspect loops were run for both pages at 1440×900, 1366×768, and 1024×768. Final screenshots and `qa.json` are under `docs/stage4d/screenshots/`.

- Loop 1 — structure: Compare and Version Review rendered; no horizontal overflow; canonical comparison and Version Review surfaces present.
- Loop 2 — information hierarchy: exact-run comparison cards and Version Review A/B metrics visible; existing navigation and rich workspace preserved.
- Loop 3 — polish: 1024px layout remained usable; no overlap/cropping; existing STRA dark surface, border, spacing, and accent language preserved.
- Browser console errors: 0.
- Page errors: 0.
- Unexpected 4xx/5xx responses: 0.

The first visual pass exposed an official-delta loading defect in Version Review: the page used the embedded compatibility payload without requesting the shared projection. The page now always requests the comparison endpoint when a V2 run exists; the compatibility payload is only retained for legacy display continuity.

## Known limitations and severity

- P2: legacy Version Review V2 windows do not yet persist full 3F identity, so the shared adapter safely keeps semantic delta disabled for those windows while retaining side-by-side topic output.
- P2: Compare's existing filtered category/subcategory visualizations still use legacy sample-derived helpers as descriptive views; official recommendation cards use the exact-run comparison projection.
- P2: the existing AI comparison summary endpoint still consumes its legacy bounded review sample; it is not an official metric source and is deferred with the Reports/Agent migration.
- P3: the in-app browser bridge was unavailable; standalone Chromium/Playwright produced the acceptance evidence.
- P3: `npm audit` and residual Stage 4C Developer Mode work remain deferred.

## D2 plan

Stage 4D.2 should migrate Game Agent tools to canonical research and comparison projections, then migrate Reports to canonical results and narrative/output projections. It should not introduce another comparison builder or allow tools to recompute official metrics.
