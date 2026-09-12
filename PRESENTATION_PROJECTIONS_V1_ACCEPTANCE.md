# Presentation Projections V1 Acceptance

Date: 2026-08-26  
Branch: `chore/agent-governance-layout` (fast-forwarded from `presentation/projections-v1`)

## Gates

| Gate | Status | Evidence |
|---|---|---|
| `P1_RAW_TEMPORAL_PROJECTIONS` | PASS | Fresh completed run `178d75eeebc848c1a5917ad18e35fb42` persisted 100 exact provenance rows; volume reconciled to 100 and recommendation numerator reconciled to 91 across 3 UTC buckets. |
| `P1_RECENT_SUMMARY` | PASS | Exact history/run/result identity, nullable optional fields, and exact `app_id + run_id` reopen URL implemented; live read-only check returned 6 completed items. |
| `P1_VERSION_POPULATION_STRIP` | PASS | V2 run `3a738a76f94c4e6894e67bb171225d67` returned READY with complete A/B coverage and existing metrics. |
| `P1_PROVENANCE_STRIP` | PASS | Exact run/config/result/design provenance fields exposed with null-safe optional values. |
| `FULL_FRONTEND_BUILD` | PASS | `npm run build` exited successfully under the controlled elevated build environment; static pages and route optimization completed. |
| `REAL_GENERAL_RUN_ACCEPTANCE` | PASS | Fresh real run `178d75eeebc848c1a5917ad18e35fb42` completed with exact provenance, daily reconciliation, immutable-source proof, ledger evidence, and UI screenshot. |
| `P2_WEEKLY_TOPIC_PREVALENCE` | DEFERRED | Denominator and label-origin provenance are not yet contract-safe. |
| `INTEGRATION_ACCEPTANCE` | PASS | Canonical integration runtime handshake, API contracts, historical-unavailable behavior, frontend gates, and four-page browser smoke all passed on ports 8000/3000. |

## Quality checks

- No fake or mock product fallback data was added.
- Steam recommendation rate remains recommendation rate; it is not renamed to sentiment.
- Missing capability renders an unavailable state or remains absent; it is never converted to zero.
- Version Review methodology and the valid V2 comparison run were not changed.

## Final status

`SENTINEXT_PRESENTATION_PROJECTIONS_V1_READY`

All required V1 integration gates are complete. P2 weekly topic prevalence remains explicitly deferred; no new provider call or P2 projection was started.
