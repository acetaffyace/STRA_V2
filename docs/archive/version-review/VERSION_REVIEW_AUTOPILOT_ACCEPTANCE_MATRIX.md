# Version Review Autopilot Acceptance Matrix

| Requirement | Evidence | Status |
|---|---|---|
| Manual verification no longer blocks start | `/runs` no longer rejects `manual_verified=false`; regression updated | PASS |
| Automatic event resolution | `version_review_autopilot.resolve_event` and event response provenance | PASS |
| Previous comparable event | Comparable-type selector skips hotfix/balance events | PASS |
| Lifecycle-matched comparison | Day 0–7 interval planner | PASS |
| Cache-first historical plan | required/cached/missing interval response | PASS |
| Raw versus semantic populations | `population_contract` and UI population card | PASS |
| Bounded deterministic sampling | stable SHA-256 seeded sampler | PASS |
| Provider-free plan | `/version-review/plan` planner path has no LLM call | PASS |
| Existing methodology preserved | Adaptive Analysis and Evidence modules reused | PASS |
| Full regression/build | pytest, typecheck, lint, build | PASS |
| Real/manual browser smoke | Bridge unavailable | NOT RUN |
