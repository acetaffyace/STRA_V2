# STRA Stage 4D.2 — Game Agent & Reports Canonical Convergence

## Baseline and scope

- Baseline: `b4079ff8634ae6005a5701a18e2852e171f52e42`
- Implementation final SHA: `3f0bc6a520effcd13e246ba026d7f04d4efcddf6`
- Branch: `integration/research-pipeline-v1`
- Migration: `24`; no schema change was required.
- Scope: downstream read-side convergence for Game Agent and Reports only. Research Core, 3F, Discovery, comparison, Dashboard, Version Review, and Compare remain upstream sealed contracts.

No Agent or Report path invokes Steam acquisition, Research Core, classification, measurement rotation, embedding, HDBSCAN, or taxonomy mutation.

## Agent convergence

Agent context now carries `run_ids_by_app`. A supplied run is resolved first and is used for every tool call in the turn. Without an explicit run, the resolver selects one latest completed `general_analysis` run once, then pins it in context. The cache context includes the pinned run map, so `(app_id, run_id)` cannot collide with another run.

Canonical tool mapping:

| Tool capability | Canonical source |
|---|---|
| Overview, population, recommendation, scope | exact Research Core / Unified quantitative result |
| Topics, issues, requests, coverage, qualification | exact persisted SemanticMeasurementResult / 3F |
| Review search and metric membership | frozen ResearchPopulationSnapshot + frozen ClassificationMaterialization |
| Evidence distinction | exact-run evidence fields; source review is never promoted to verified evidence |
| Game comparison | `research-comparison-v1` shared comparison builder |
| Discovery context | persisted Discovery sidecar, never official prevalence |

Exact overview values preserve `population_n`, `valid_n`, `recommended_n`, `not_recommended_n`, `recommendation_rate`, sampling scope, collection status, truncation, and stop reason. Missing exact values remain unavailable; no `rate × n` reconstruction is used. Semantic results retain `classified_n`, `population_n`, coverage, claim status, measurement status, and the classified-review denominator. `PROVISIONAL` remains visible to the model context and is not presented as validated. Quantitative-only runs continue to answer quantitative questions while semantic questions report unavailable.

Keyword and descriptive filters operate only over the exact frozen run population. They do not become prevalence calculations. `other/*` remains separate from actionable topics. Comparison uses the canonical compatibility gate; incompatible semantic identities are side-by-side only and never receive a locally calculated delta.

## Reports convergence

The principal report projection is `report-presentation-v1`, built by `build_canonical_report(run_id)`. It is pinned to one completed exact run and contains:

- run identity and provenance;
- Research Core quantitative snapshot and sampling limitations;
- exact 3F semantic qualification, coverage, topics, issues, requests, and context/other;
- exact-run evidence/source-review counts;
- optional Discovery sidecar and limitations;
- a provenance appendix without raw review text.

The Reports page accepts `?game=<app_id>&run=<run_id>` and the canonical export uses that same run. Missing canonical runs fail closed instead of falling back to a legacy monthly report. The old monthly endpoint remains available only as a bounded compatibility/descriptive path when no exact run is requested; it is not used by the canonical report.

Canonical HTML/PDF values are selected from the projection. The PDF renderer uses WeasyPrint when available and a deterministic ReportLab fallback when native WeasyPrint libraries are unavailable. The fallback was hardened to retain scope, classified denominator, semantic qualification, topics/issues/requests, context/other, and provenance rather than invoking the legacy monthly renderer.

## Ownership matrix

| Workspace | Official source |
|---|---|
| Dashboard | Unified Research Result / 3F |
| Reviews | frozen run population + frozen materialization |
| Version Review | `research-comparison-v1` |
| Game Compare | `research-comparison-v1` |
| Game Agent | canonical run + 3F + exact evidence + comparison |
| Reports | canonical run + 3F + exact evidence |
| Database | storage/exploration only; not official research measurement |

## Cross-workspace and isolation checks

The targeted fixtures assert exact equality for canonical recommendation, population, scope, coverage, topic/issue/request rows, and qualification across Dashboard presentation, Agent outputs, and Reports projection. Comparison results are reused by Agent rather than recomputed. Exact-run review membership is shared with the Reviews workspace. Mutation of a mutable/latest review or legacy insight does not alter an already-built Agent or Report projection. Switching from run A to run B changes the cache identity and cannot return A's facts.

## Acceptance data

The sealed HELLDIVERS 2 identity was used for deterministic acceptance:

- run: `b92ba25b9f9b4230945d8eb6f92126ff`
- population: `80`
- recommendation: `70 / 80 = 87.5%`
- semantic claim: `PROVISIONAL`
- semantic coverage: `80 / 80 = 100%`
- context: `other/meme = 23 / 80`, `other/general = 15 / 80`

The local real Steam database was not present for this run; the browser/PDF acceptance used the repository's isolated Stage 4C synthetic fixture with the sealed aggregate values and synthetic review text. No full review corpus or private database was added to Git.

## Browser QA

The in-app browser bridge was attempted but unavailable on this host, so the repository's standalone Playwright/Chromium runner was used. Runner: `tooling/vertical_slice/stage4d2_agent_reports_playwright_qa.mjs`.

`/chat?game=553850&run=b92ba25b9f9b4230945d8eb6f92126ff` and `/reports?game=553850&run=b92ba25b9f9b4230945d8eb6f92126ff` were rendered at `1440×900`, `1366×768`, and `1024×768`. Screenshots are retained under `docs/stage4d/screenshots/`:

- `stage4d2-chat-1440x900.png`, `stage4d2-chat-1366x768.png`, `stage4d2-chat-1024x768.png`
- `stage4d2-reports-1440x900.png`, `stage4d2-reports-1366x768.png`, `stage4d2-reports-1024x768.png`

The first Reports pass exposed optional live Steam widgets making 502 requests in a pinned canonical view. Those widgets are now omitted in the exact-run report path; the canonical report remains read-only and unaffected. The final pass reported zero console errors, zero page errors, zero failed responses, and no horizontal overflow at all three viewports. Chat shows the exact HELLDIVERS 2 run context.

## PDF QA

Two PDFs were generated and rendered with Poppler:

1. FULL/PROVISIONAL canonical run: `80`, `87.5%`, `80 / 80`, `PROVISIONAL`, English/recent/max-80 scope, limitations, topics/issues/requests/context, and provenance.
2. Quantitative-only fixture: `100` population, semantic unavailable, explicit unavailable semantic rows, scope/truncation, and provenance.

Both rendered without clipping or overlap. The canonical fallback is used because WeasyPrint cannot load `libgobject-2.0-0` on this host; this is a renderer environment limitation, not a data fallback.

## Tests and validation

- Targeted Agent/Reports tests: passed (`7 passed`).
- Full backend suite: `542 passed, 2 skipped, 47 warnings`.
- Frontend: `npm ci` passed; `npx tsc --noEmit` passed; `npm run build` passed.
- Browser QA: 6 page/viewport renders passed with clean console/network.
- PDF QA: FULL/PROVISIONAL and quantitative-only outputs rendered and inspected.
- Existing npm audit baseline remains `16 vulnerabilities` (`2 low`, `3 moderate`, `10 high`, `1 critical`); no `npm audit fix --force` was run.

## Remaining limitations

- P0: none identified.
- P1: none identified after exact-run, isolation, browser, and PDF checks.
- P2: historical Version Review V2 windows lack modern 3F identity; bounded legacy descriptive helpers and the monthly compatibility report remain outside the canonical report path; 3C provider timeout remains an auxiliary limitation.
- P3: npm audit remediation, Developer Mode, native WeasyPrint dependency packaging, and desktop release work remain deferred to Stage 4E.

Stage 4D.2 is complete. Stage 4E is the next action; no Stage 4E work was started in this change.
