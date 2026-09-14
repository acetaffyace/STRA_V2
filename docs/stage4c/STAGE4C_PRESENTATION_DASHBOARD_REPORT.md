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

Remote CI verification for commit `6664525cd1dbea3378b2a0490b5fd26af96049b4`: GitHub Actions run `34798443462` completed successfully; `backend=success`, `frontend=success`, overall workflow `success`.

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

## Stage 4C-R2 — User-facing Product Simplification & Interaction Seal

### Product-facing projection

The existing dashboard endpoint remains the only presentation endpoint and Migration remains 24. The primary dashboard now uses ordinary user language: 评论概览, 分析状态, 玩家关注, 主要问题, 玩家需求, and 其他内容. Technical research terms, run UUIDs, provider/model identity, taxonomy version, fingerprints, methodology copy, and provenance IDs are no longer rendered in the normal dashboard. The persisted API projection still carries the technical provenance needed by Settings/diagnostics and exact historical reads; no canonical metric ownership or calculation was moved into React.

The duplicate ResearchOverview block was removed from the canonical dashboard path while the existing Health Overview, trend, segmentation, review drill-down, navigation, reports, compare, Version Review, database, and Settings capabilities remain available through the existing AnalysisResults and global navigation. Discovery is now hidden unless a stable user-relevant potential-gap signal exists; a provider timeout is therefore nonblocking and does not create a technical card for ordinary users.

### Sampling Setup

The existing Analysis Queue is reused. The user-facing 采集评论 dialog now supports custom/max review counts, all/7/30/90-day/custom time scope, true multi-language checkbox selection, recommendation status, purchase source, collection order, and off-topic activity. The preview is written as 预计采集范围, and the exact `sampling` contract is submitted with `start_time`, `end_time`, `languages`, `review_type`, `purchase_type`, `collection_order`, `include_offtopic_activity`, and `max_reviews`. Update Analysis opens the same dialog with the current Run scope inherited; the browser check verified a 30-day + English/Japanese + custom 80-review state without submitting a new run.

### Exact historical Review Explorer

`GET /analysis/{app_id}/reviews?run=...` remains exact-run and now permits quantitative-only runs to browse the frozen population with empty semantic labels and an explicit `semantic_available=false`. It never falls back to `game.sample` or the mutable latest cache. The frontend has loading, exact success, and friendly error states, and uses 50-review pages with previous/next controls; the regression test covers 235 reviews as 1–100, 101–200, and 201–235. Topic, issue, request, and other-content links retain metric-specific filtering. Empty evidence no longer renders a misleading empty evidence block; available snippets are labelled 分析依据 while the underlying review remains 原评论.

### Visual QA and browser acceptance

Three fresh real-Chromium QA loops were completed after the R2 polish:

1. Simplification — confirmed ordinary user labels, no primary Methodology/Provenance block, no technical IDs, no duplicated canonical ResearchOverview metrics, and visible scope/暂定结果/80 of 80 coverage.
2. Operation — opened the existing Update Analysis control, exercised multi-language, time scope, custom count preview, exact-run topic navigation, back navigation, and review pagination without submitting an analysis or triggering a research-side effect.
3. Polish — inspected 1440×900, 1366×768, and 1024×768 Dashboard/Reviews renders plus the Sampling Setup modal; fixed the remaining internal `tracked` label and removed empty no-evidence UI. The historical unavailable state was also rendered and confirmed fail-closed with no sample fallback.

Final screenshots are in `docs/stage4c/screenshots/r2/`: Dashboard at 1440×900, 1366×768, and 1024×768; Sampling Setup; Reviews; and historical Reviews unavailable. Main acceptance routes reported zero console errors, page errors, and 4xx/5xx responses. The intentionally missing historical-run route returns the expected 404 API response and shows the user-facing unavailable state.

### Verification

- Backend: `pytest -v --basetemp .pytest_stage4c_full4` — 525 passed, 2 skipped, 47 warnings; the two pre-existing test logging paths were temporarily redirected to a workspace-local log file for collection and restored afterward.
- Frontend: `npm ci`, `npm run typecheck`, and `npm run build` — passed. `npm ci` reported existing dependency audit findings (16 vulnerabilities); dependency versions were not changed.
- Browser: real Chromium Playwright runner, three viewports, three loops, exact-run pagination, Sampling Setup interaction, and historical unavailable state — passed with no main-path console/page errors.
- Migration: still 24; no schema changes.

Known limitations: the dedicated Developer Mode toggle is not introduced in this pass; technical provenance remains available through the read-side presentation contract and existing Settings diagnostics rather than the ordinary Dashboard. The screenshots use the existing local synthetic fixture for review text, while reviewed aggregate values remain 80 reviews, 87.50% recommendation rate, 80/80 semantic coverage, and other/meme 23/80 / other/general 15/80.

Deferred work remains Stage 4D: Version / Compare / Agent / Reports convergence.
