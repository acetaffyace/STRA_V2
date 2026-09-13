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
