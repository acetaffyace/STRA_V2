# STRA Stage 4C — Presentation API, Dashboard UI & Visual Acceptance

## Baseline and scope

- Repository: `acetaffyace/STRA_V2`
- Branch: `integration/research-pipeline-v1`
- Baseline SHA: `770e6f445147e830a8ee65cc73ce652b4eb0438d`
- Migration: 24 (unchanged)
- Scope: read-side dashboard presentation only; no research algorithm, taxonomy, or migration changes.

## Presentation contract

`GET /analysis/{app_id}/dashboard` remains the only dashboard API. It now exposes a typed `dashboard-presentation-v1` projection with run identity, Research Core snapshot, semantic qualification, player voice groups, discovery sidecar, evidence provenance, limitations, and technical provenance. The legacy fields remain in the response for older screens.

Metric ownership is explicit: recommendation metrics come from the persisted Research Core report; topic, issue, request, primary-topic, denominator, and coverage metrics come from `SemanticMeasurementResult`; discovery counts come from the persisted semantic discovery sidecar; ordering, labels, grouping, and layout belong to the presentation layer. No official metric is recomputed in React.

## Dashboard behavior

The dashboard now leads with game/run identity, observed recommendation rate, sample scope, and semantic qualification. `PROVISIONAL` is a prominent badge and explains that production classification is complete but formal classifier validation has not passed. Topic, issue, and request rows state “of classified reviews”; `other/*` is kept in Context / Other and cannot become an actionable card. Discovery is labelled as a secondary signal and never expressed as player prevalence. Quantitative-only runs render Research Snapshot with a nonblocking semantic-unavailable state; partial coverage preserves the classified denominator.

Evidence is run-aware when `?run=<run_id>` is present. It reads the immutable Research Population and frozen ClassificationMaterialization. Verified quotes and Source Reviews are separate; when the verifier returns zero quotes the UI explicitly says “No verified quote available. Showing source reviews instead.”

## Real acceptance run

The reviewed production semantic sample is `b92ba25b9f9b4230945d8eb6f92126ff` for HELLDIVERS 2 / 553850. Canonical acceptance values are 80 reviews, 70 recommended, 10 not recommended, 87.50% observed recommendation rate, PROVISIONAL, 80/80 classified, 100% coverage, `other/meme` 23/80 (28.75%), and `other/general` 15/80 (18.75%). Discovery displays 2 dense regions, 0 rare regions, 48 outlier reviews, and `BLOCKED_PROVIDER_TIMEOUT` as a nonblocking 3C status.

The original run database was intentionally not retained in the repository. Browser validation used an untracked local presentation fixture seeded with the reviewed aggregate result and synthetic frozen source-review payloads; no real Steam review text, prompt dump, credential, database, or model file was written to Git. The fixture preserves the run ID and canonical aggregate values for UI acceptance, while its local population fingerprint is explicitly not asserted as the historical production fingerprint.

## Visual QA

The browser bridge supplied by the primary browser skill was unavailable in this desktop environment, so the required local in-app browser was opened through the safe CUA fallback. Three render → screenshot → inspect loops were completed on the real acceptance URL.

### Loop 1 — structural review

Confirmed the first screen showed HELLDIVERS 2, scope, recommendation rate, PROVISIONAL status, coverage, and actionable topics without grid collapse. The initial fixture omitted four request-only rows; the fixture was corrected so the Requests panel displays the five R2 request categories.

### Loop 2 — information hierarchy review

Inspected the lower view. Context / Other was visually separate from Actionable Topics, Issues and Requests were distinct cards, and Discovery was labelled secondary. A long 3C timeout token was clipped in the first lower screenshot; the status cell was changed to a wrapping, titled value.

### Loop 3 — polish review

Re-rendered and re-inspected the polished view. The timeout status now wraps without hiding the metric, labels use ellipsis where appropriate, keyboard-focusable topic buttons have visible focus rings, and Source Reviews visibly distinguishes the no-verified-quote fallback.

The fallback browser renderer exposed one default desktop viewport; it did not expose the primary skill’s viewport override or console-log API. The visual artifact was inspected at that renderer size. 1440×900, 1366×768, and 1024×768 raster artifacts could not be independently produced in this environment and are recorded as an environment limitation rather than claimed as passed.

## Tests and known limitations

- `pytest -q tests/unit/test_dashboard_presentation.py`: passed.
- `npm run typecheck`: passed.
- Full backend suite and production build are run in the final verification pass.
- The UI fixture uses synthetic source review text because the original R2 SQLite runtime was not retained.
- Browser console and exact multi-viewport checks remain environment-blocked by the unavailable primary browser bridge; no browser-side error was observed in the inspected CUA accessibility state.

Deferred work remains Stage 4D: Version / Compare / Agent / Reports convergence.

## Stage 4C-R1 — Full Product Integration, Sampling UI & Visual Seal

### Canonical projection repair

The first Stage 4C projection used pre-`research-report-v1` paths. R1 now reads `recommendation.population.recommendation_rate`, `population.collection_complete`, `population.truncated_by_max_reviews`, `population.stop_reason`, `population.coverage_*`, and the explicit `population.sampling_contract`. Collection state is three-valued: `complete`, `limited`, or `unknown`; unknown is never presented as complete. The contract test now builds its source report through `build_snapshot_research_report()` and asserts the 80/70/10/0.875 canonical values.

### Existing capability inventory

Preserved: global navigation, game search, analysis queue, run history, game header/Steam image, current-player context, quick and advanced review filters, Health Overview, recommendation/review trends, issue/request/topic views, player/language/playtime/purchase/activity segmentation, review drill-down, Reports, Compare, Version Review, Database, and Settings. Improved: the canonical research layer, exact-run evidence, and metric-specific review links. Intentionally deferred: Stage 4D convergence work. No legacy capability was removed; the existing ResearchOverview and AnalysisResults continue to render alongside the canonical layer.

### Sampling and Review Explorer

The Analysis Setup modal exposes max reviews, language, review type, purchase type, collection order, and off-topic activity, shows a scope preview, and submits the explicit `sampling` object while reusing the existing Analysis Queue. Canonical Player Voice links to `/reviews?appId=...&run=...&metric_type=topic|issue|request&taxonomy_key=...`. Run-aware review reads use the immutable population plus frozen materialization and do not fall back to the mutable latest sample. Evidence remains distinct from Source Reviews; metric type is now applied to topic/issue/request filtering.

### Visual convergence and QA

The canonical workspace no longer creates a duplicate game header when embedded and its surfaces use restrained STRA borders/surfaces rather than the earlier gradient/shadow-heavy treatment. Three QA loops remain required for the final local browser run: structural capability review, information hierarchy review, and polish review. The previous bridge limitation remains recorded above; R1's implementation adds the exact viewport/run-aware paths needed for the authorized Playwright acceptance pass.

### R1 verification

- `pytest -q tests/unit/test_dashboard_presentation.py`: passed after the real-schema projection fix.
- `npm run typecheck`: passed after SamplingContract and run-aware Reviews integration.
- Migration remains 24; no schema change was introduced.
- Completed in R1: full backend suite, production build, independent Chromium screenshots at 1440×900, 1366×768, and 1024×768, console/network audit. Remote CI is run after push.

### R1 final browser acceptance

The authorized local Playwright/Chromium path was used after the primary browser bridge was unavailable. The runner rendered independent 1440×900, 1366×768, and 1024×768 viewports and executed three render → screenshot → inspect loops. Loop 1 checked structure and legacy Research Core continuity; Loop 2 checked hierarchy, scope, `PROVISIONAL`, 80/80 coverage, Context / Other, and secondary Discovery; Loop 3 checked polish, the Sampling Setup modal, long status wrapping, Review Explorer density, and exact-run navigation. The final artifacts are in `docs/stage4c/screenshots/`.

The browser console and page-error audit returned zero errors, and the recorded responses had no 404/500 failures. The exact-run Review Explorer returned 11 frozen topic reviews for the synthetic acceptance fixture and displayed the raw review and frozen labels; source review evidence remained separate and empty rather than being mislabeled as verified evidence. Opening the dashboard caused only read-side requests; the analysis modal was not submitted during QA, so no classification/research/discovery side effect was triggered.

The local acceptance fixture is synthetic and untracked; it preserves the reviewed aggregate acceptance values (80 population, 70/10 recommendation split, 87.5%, 80/80 semantic coverage, Context / Other 23 and 15) without committing real Steam text or credentials.
