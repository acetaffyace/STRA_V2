# Presentation Projections V1 Integration Report

Date: 2026-08-26  
Integration branch: `chore/agent-governance-layout`  
Source branch: `presentation/projections-v1`  
Commit: `a5d6cd21e64479da8497b95ba67a1a9539a8da86`

## Integration boundary

The source branch was committed and fast-forwarded into the governed integration branch. Only source, tests, benchmark source, and documentation were merged. The isolated `agent-a` database, provider-run database, logs, backups, locks, and temporary artifacts were not copied or merged.

Canonical runtime:

- frontend: `http://127.0.0.1:3000`
- backend: `http://127.0.0.1:8000`
- runtime profile: `integration`
- database instance: `integration-32fd979b7073`
- migration version: `12`
- API contract: `unified-analysis-v1`
- SQLite `PRAGMA integrity_check`: `ok`

No migration was added or executed by this closure, and no provider call was made.

The first readiness probes during backend startup briefly returned 503 while background initialization was running; subsequent `/health` and `/runtime-info` probes returned 200 and all contract requests completed successfully. The existing integration database also reports a pre-existing FTS verification drift in the backend log; SQLite integrity itself is `ok`, migration remains 12, and no FTS or database repair was performed in this read-only closure.

## Contract smoke

| Contract | Result | Evidence |
|---|---|---|
| `GET /presentation/recent-analysis-summary?limit=20` | PASS | HTTP 200; exact run identity and reopen URLs returned. |
| `GET /presentation/version-comparison-population-strip/3a738a76f94c4e6894e67bb171225d67` | PASS | HTTP 200; valid V2 comparison returned `READY`, complete A/B coverage, and coverage gate `PASS`. |
| `GET /presentation/provenance-strip/3a738a76f94c4e6894e67bb171225d67` | PASS | HTTP 200; nullable fields remained null where the existing V2 result does not provide them. |
| Historical daily projections for `6b8dbe8e073f46b195e9995bfccf8186` | PASS | Both volume and recommendation-rate endpoints returned HTTP 200 with `available=false` and `historical_run_population_provenance_unavailable`. |

## Frontend gates

- `npm run typecheck`: PASS.
- `npm run lint`: PASS with three pre-existing warnings and zero errors.
- `npm run build`: PASS.
- Overview: PASS; HTTP 200, no console/page errors, no NaN/undefined output.
- Historical Game Analysis: PASS; HTTP 200, full existing analysis rendered, daily projection remained explicitly unavailable, no fake values, no console/page errors.
- Version Review V2: PASS; existing run `3a738a76f94c4e6894e67bb171225d67` rendered normally with 3/7/14 controls, complete coverage, and no console/page errors.
- Reports: PASS; HTTP 200, report list rendered, no console/page errors or unexpected 502.

Browser screenshots are in `artifacts/screenshots/integration-overview.png`, `integration-game-analysis-historical.png`, `integration-version-review-v2.png`, and `integration-reports.png`.

## Truthful loading closure

The Game Analysis page's optional Steam game-details request could remain pending indefinitely when Steam was slow or unavailable. The smallest safe frontend change adds a five-second timeout and presents `游戏详情暂时不可用`; it does not synthesize metadata or alter analysis semantics. The final browser smoke showed no persistent `Loading details...` state.

## Final gate

`P1_RAW_TEMPORAL_PROJECTIONS = PASS`  
`P1_RECENT_SUMMARY = PASS`  
`P1_VERSION_POPULATION_STRIP = PASS`  
`P1_PROVENANCE_STRIP = PASS`  
`REAL_GENERAL_RUN_ACCEPTANCE = PASS`  
`INTEGRATION_ACCEPTANCE = PASS`  
`P2_WEEKLY_TOPIC_PREVALENCE = DEFERRED`

`SENTINEXT_PRESENTATION_PROJECTIONS_V1_READY`
