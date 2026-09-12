# V1/P1 Acceptance Matrix

| Area | Result | Evidence |
|---|---|---|
| Startup uses validated local environment | PASS | `runtime_diagnostics.py`, `run_backend_local.ps1` |
| SOCKS dependency is reproducible | PASS | declared `socksio`, diagnostic test |
| Unknown pricing cannot crash telemetry | PASS | cost ledger test |
| Systemic provider failure cannot fan out unbounded calls | PASS | typed failures + operation circuit tests |
| Restart recovery converges active runs | PASS | P0 lifecycle/recovery tests |
| No paid API required for development | PASS | offline runner and zero `llm_calls` assertion |
| What changed? | PASS | `five_questions.what_changed`, unavailable when baseline absent |
| Why? | PASS | positive/problem/request observations and coverage |
| Who? | PASS | language/cohort observations with denominator note |
| What matters? | PASS | transparent heuristic components |
| What should we do? | PASS | FIX/IMPROVE/BUILD/AMPLIFY action records |
| Run provenance | PASS | existing P0 run/result contracts |
| Label provenance | PASS | offline fixture origin explicit |
| Metric provenance | PASS | existing P0.3b observations retained |
| Evidence verification | PASS | exact-substring evidence path |
| Immutable results | PASS | existing P0.2c contracts + offline runner |
| Cost ledger | PASS | unknown price unavailable; fixture writes no provider row |
| Gold v2 preserved | PASS | no Gold files modified |
| Primary Dashboard workflow | PASS | five-question summary added to Dashboard |
| Explainable priorities | PASS | score components, action class, caveats |
| Recoverable failures | PASS | cancellation, stale cleanup, startup recovery |
| Mode/quality limitations visible | PASS | offline mode label, coverage, heuristic warning |
| Frontend typecheck | PASS | `npm run typecheck` |
| Frontend lint | PASS | 0 errors, 3 warnings |
| Frontend production build | PASS | `npm run build` |

Final decision: **V1_P1_READY_OFFLINE**.

