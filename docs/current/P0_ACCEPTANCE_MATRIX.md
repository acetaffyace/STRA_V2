# P0 Acceptance Matrix

Status vocabulary: `PASS` means the contract is implemented and covered;
`PASS_WITH_LIMITATION` means the contract is truthful but has a documented
local-first boundary; `FAIL` would be a release blocker.

| Area | Acceptance item | Status | Evidence |
|---|---|---|---|
| P0.1/1V | Canonical review text projection | PASS | `reviews.review_text`, `fts.py`, `test_p0_1_fts.py` |
| P0.1/1V | External-content FTS and trigger insert/update/delete sync | PASS | `apps/api/senti_next/fts.py`, P0.1 report, P0 contract tests |
| P0.1/1V | Inverted-index integrity, rebuild/repair, drift detection | PASS_WITH_LIMITATION | `verify_fts_integrity()` and `rebuild_fts()`; explicit/admin path, not hot startup path |
| P0.2a | Generalized `analysis_runs` schema | PASS | `run_schema.py`, `test_p0_2a_run_schema.py` |
| P0.2b/bV | Queued/running/failed/cancelled lifecycle, cancellation and recovery | PASS_WITH_LIMITATION | lifecycle tests and `recover_interrupted_general_runs()`; process workers are not durable |
| P0.2b | Started-at truth, overlap guard, restart semantics | PASS | `test_p0_2b_lifecycle.py` |
| P0.2c | Immutable successful general-analysis result | PASS | `analysis_run_results`, `test_p0_2c_results.py` |
| P0.2c | Latest/current compatibility state separated from immutable history | PASS | result schema/report and P0.2c tests |
| P0.3a | Label origin, validated and fallback semantics | PASS | `label_schema.py`, provenance tests |
| P0.3a | Cache identity includes taxonomy/prompt/provider/model/input identity | PASS | `llm.py`, `test_p0_3a_provenance.py` |
| P0.3b | Metric numerator/denominator/population/coverage provenance | PASS | `metric_provenance.py`, `test_p0_3b_metric_provenance.py` |
| P0.3b/c | Unavailable is distinct from zero; formal KPI vs display sample | PASS | metric contract tests and frontend adoption map |
| P0.3c/cV | Frontend adoption/typecheck/lint/build | PASS_WITH_LIMITATION | Typecheck/lint/build PASS; lint has 3 non-blocking existing warnings |
| P0.4 | Exact source-grounded quotes and invalid-quote gate | PASS | `evidence.py`, `test_p0_4_evidence.py` |
| P0.4 | Current vs immutable historical evidence snapshots | PASS | evidence schema and persistence tests |
| P0.4 | Chat/Version Review/report evidence gates | PASS | chat/run routes and evidence tests |
| P0.5 | Human-verified Gold v2 and v1→v2 provenance | PASS | `P0_5CW_REPORT.md`, Gold diff and hashes |
| P0.5 | Frozen Dev/Holdout and real DeepSeek baseline | PASS | frozen prediction hashes and baseline artifacts |
| P0.5 | Issue semantic correction retained genuine positive-review complaints | PASS | v2 diff and deterministic rescore |
| P0.5 | Taxonomy overprediction and sentiment-unavailable truth retained | PASS_WITH_LIMITATION | v2 baseline: subcategory precision ≈0.24; sentiment unavailable |
| P0.6 | One physical ledger row per provider attempt | PASS | `cost_ledger.py`, provider adapters, P0.6 tests |
| P0.6 | Retry/fallback accounting and rule-fallback exclusion | PASS | ledger tests and adapter boundary instrumentation |
| P0.6 | Historical pricing snapshot and missing-usage semantics | PASS | pricing registry, `test_p0_6_cost_ledger.py` |
| P0.6 | Run linkage and non-Run Chat behavior | PASS_WITH_LIMITATION | run context captured; ad-hoc Chat legitimately permits nullable run_id |
| P0.6 | Production/evaluation workload separation | PASS | summary defaults to `production`; explicit `workload_type=evaluation` filter |
| P0.6 | Deterministic cost aggregation and read-only API | PASS | `/runs/{run_id}/llm-cost`, `/llm-cost/summary` |

## Source-of-truth map

| Artifact | Role | Ownership class |
|---|---|---|
| `reviews.review_text` | canonical searchable review projection | canonical content projection |
| `reviews.data` | raw/canonical review payload as stored | canonical/raw payload |
| `reviews_fts` | searchable inverted index | derived, repairable |
| `review_labels` | latest reusable label computation cache | mutable cache |
| `analysis_runs` | execution and lifecycle truth | durable operational history |
| `analysis_run_results` | successful general-analysis snapshot | immutable history |
| `analysis_results` | latest/current compatibility state | mutable operational compatibility state |
| `metric_provenance` | formal KPI calculation contract embedded in outputs | derived contract/output |
| verified evidence snapshot | historical direct-quote grounding | immutable evidence history |
| `llm_calls` | physical provider-call usage/cost ledger | append-only persisted telemetry |

## Release gate

Migration 1→8, canonical tests, frontend build, contract xfail closure,
source ownership, run/result/evidence/cost provenance, and known-limitations
documentation all pass. No user-facing P0 blocker remains.
