# STRA Stage 4B — Real Steam Vertical Slice Report

## Verdict

**BLOCKED for a complete semantic vertical slice.** The product path successfully acquired real Steam data and completed Research Core, but no active Production LLM provider/model was configured. The backend correctly finalized the run as quantitative-only; no fake classifier, fake semantic result, or fake embedding result was presented as success.

The next stage is **Path C — Backend Repair**, limited to the blockers below. Do not start Dashboard/UI convergence or taxonomy work from this run.

## Baseline and scope

- Repository: `acetaffyace/STRA_V2`
- Branch: `integration/research-pipeline-v1`
- Baseline SHA: `5a4716654e5e17fce1d09e274dde5726dfdab5db`
- Migration latest known: `23`; no Migration 24 added.
- Target: HELLDIVERS 2 (`553850`)
- Request: `80`, `english`, `recent`, `persist=true`, output `zh`
- Run A: `143aaf6e722141c4a445499fcad2b16e`

The repository's default local database also failed application initialization because existing FTS integrity drift remained after the automatic rebuild. The slice therefore used a fresh, untracked Stage 4B SQLite runtime database. The existing default database was not overwritten or repaired.

## Provider and Measurement Bundle preflight

The active provider preflight returned no configured provider and no configured model. The available immutable local embedding model was unrelated to LLM provider availability.

The isolated product runtime resolved the honest baseline bundle:

| Field | Value |
|---|---|
| Bundle | `measurement_bundle_4b151375c7a873b57016196163072ccb` |
| Status | `PROVISIONAL` |
| Validation run | none |
| Validation status | `UNAVAILABLE` |
| Taxonomy snapshot | `snapshot_13190aadeede17d62ea387efc0efb7e3` |
| Taxonomy version | `sentinext-taxonomy-v1` |
| Taxonomy fingerprint | `418f27caf82290b258ded444a3f1eec8b7975a0f0989e248965e7279adb71b7d` |
| Classifier provider | `unconfigured` |
| Classifier model | `unconfigured` |
| Prompt version | `steam_review_insights_v16_basic_labels` |
| Schema version | `review-classification-schema-v1` |

Semantic measurement is therefore **PROVISIONAL, not formally validated**. Because the runtime provider preflight was unavailable, this bundle was not bound to Run A and did not produce a classification materialization.

## Steam acquisition and Research Core

The real `POST /analyze` path returned `202`, and the lifecycle reached `completed`.

| Metric | Result |
|---|---:|
| Population | 80 |
| Valid recommendation outcomes | 80 |
| Recommended | 70 |
| Not recommended | 10 |
| Recommendation rate | 0.875 |
| 95% Wilson interval | 0.78497–0.93066 |
| Language | English: 80 |
| Collection complete | false |
| Truncated by max reviews | true |
| Stop reason | `max_reviews_reached` |
| Acquisition coverage | `incomplete` |
| Available matching reviews | 821,512 |

The quantitative result is exact for the observed 80 reviews, not a population-of-players estimate. The Research Core report also records reviewer self-selection and the assumption-sensitive, non-design-based interval limitation.

Stage 2E activity diagnostics in the persisted report: no activity spike, no coordinated expression, 2 exact duplicate short-text reviews, exact duplicate share 0.025. No alternate Stage 2E run was created.

## Measurement, materialization, 3F, and Unified Result

The completed immutable run was read through `get_analysis_run_result(run_id)`.

- `semantic_measurement_result`: `null`
- `classification_materialization_id`: `null`
- `measurement_bundle_id`: `null` in the run provenance
- semantic status: `unavailable`, reason `no_provider`
- persisted Unified Research Result fingerprint: `7e42efd3321211a43beb0680305d5378e466534c45169bd326c9a378789db0ad`
- `UnifiedResearchResult.quantitative == research_report`: **true**
- `UnifiedResearchResult.semantic`: **null**

Consequently there are no authoritative 3F Top Topics, Issues, Requests, Primary Topics, validation qualifications, or `other/general` measurement values for this run. They are intentionally reported as unavailable rather than inferred from mutable labels or raw text.

## Cache reuse probe

The same-parameter `/analyze/estimate` endpoint was executed immediately after Run A:

```json
{
  "reviews_considered": 80,
  "cached_reviews": 0,
  "needs_refresh_reviews": 80,
  "llm_reviews": 80,
  "empty_reviews": 0,
  "short_reviews": 29,
  "reasons": {"missing_label": 80}
}
```

This is a measured result, but it is not a cache-quality conclusion: there were no prior semantic labels because the provider was unavailable. No identity-mismatch contradiction was observed.

## Stage 3A, 3B, taxonomy audit, and 3C

`inspect_local_model()` returned `ready` for the fixed, immutable revision:

- backend: `LocalONNXEmbeddingBackend`
- model: `intfloat/multilingual-e5-small`
- revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- artifact SHA-256: `ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665`

The real `build_semantic_index_for_run(run_id)` attempt was made with that backend. It correctly refused to build because the quantitative-only immutable run does not expose `population_fingerprint` (and stores no complete immutable review payload in `analysis_run_results`):

`ValueError: Research run does not expose a population_fingerprint`

No `FakeEmbeddingBackend` was used. No index was persisted. Therefore:

- 3A index: blocked at immutable population contract.
- 3B HDBSCAN discovery: not run; no valid semantic index or frozen taxonomy label map exists.
- Taxonomy Audit: not run; no discovery regions exist.
- 3C evidence dry run: not run; no discovery materialization exists.
- 3C real interpretation: not run; no eligible stable region exists.
- No taxonomy was modified, promoted, or activated.
- No raw Steam review text was saved in repository artifacts.

There is consequently no valid 3F-vs-discovery comparison, no region support numbers, and no candidate IDs.

## Product readiness diagnosis

| Module | Status | Reason |
|---|---|---|
| Steam Acquisition | PASS | Real 553850 recent English reviews were fetched through `/analyze`. |
| Research Core | PASS_WITH_LIMITATION | 80-review quantitative report persisted; recent max-review truncation makes coverage incomplete. |
| Measurement Bundle | PASS_WITH_LIMITATION | Honest provisional baseline resolves in the isolated runtime, but no provider-backed run binding occurred. |
| LLM Classification | BLOCKED | No active Production provider/model was configured. |
| Classification Materialization | BLOCKED | Requires the unavailable semantic classification path. |
| 3F | BLOCKED | No semantic measurement result exists. |
| Unified Research Result | PASS_WITH_LIMITATION | Quantitative payload is exact and persisted; semantic payload is correctly null. |
| 3A Embedding | PASS_WITH_LIMITATION | Fixed ONNX runtime is ready; exact-run builder is blocked by missing immutable population fingerprint/payload. |
| 3B Discovery | BLOCKED | No valid 3A index or frozen labels. |
| Taxonomy Audit | BLOCKED | No discovery regions to audit. |
| 3C Interpretation | BLOCKED | No discovery materialization/evidence packages. |

## Blockers

### P0 — `REAL_SEMANTIC_PROVIDER_UNAVAILABLE`

No active real LLM provider/model was configured. The product correctly completed quantitative-only and recorded `no_provider`; a complete semantic vertical slice cannot be claimed.

### P1 — `IMMUTABLE_RUN_POPULATION_UNAVAILABLE`

The quantitative-only completed run has the population rows in its Research Core provenance, but its immutable result does not expose `population_fingerprint` or a complete immutable review payload. The real Stage 3A entry point therefore rejects the run before embedding. Reusing the mutable app cache would violate the exact-run requirement.

### P2 — `DEFAULT_LOCAL_DB_FTS_INTEGRITY_DRIFT`

The configured default local SQLite database failed startup FTS verification after rebuild. The slice used a fresh untracked runtime database to avoid altering the existing database. This is an environment/data-integrity limitation that should be repaired before relying on the default runtime.

No P3 blocker was identified.

## Exact execution commands

The following commands were used, with the database path isolated outside the committed artifacts:

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git fetch origin
POST http://127.0.0.1:8000/analyze
GET  http://127.0.0.1:8000/analysis/553850
POST http://127.0.0.1:8000/analyze/estimate
inspect_local_model()
build_semantic_index_for_run("143aaf6e722141c4a445499fcad2b16e")
get_analysis_run_result("143aaf6e722141c4a445499fcad2b16e")
```

The reproducible HTTP harness is `tooling/vertical_slice/stage4b_real_steam_slice.py`; it defaults to the same app, 80 reviews, English, and recent ordering. Its offline contract test is `tests/unit/test_stage4b_runner_contract.py`.

No credentials, API keys, raw prompts, raw Steam review text, local database, or model files are included in repository artifacts.

## Tests and CI

This Stage 4B change adds a redacted HTTP harness, its offline contract test, documentation, and a machine-readable summary; it does not modify application schema or Research Core methodology. Migration latest remains 23.

Remote GitHub Actions run `34766673591` for the first pushed Stage 4B commit completed successfully: backend `success`, frontend `success`, overall `success`. URL: https://github.com/acetaffyace/STRA_V2/actions/runs/34766673591

## Recommended next path

**Path C — Backend Repair.** First make a real Production provider/model available and ensure quantitative-only completed runs preserve the immutable population fingerprint and full frozen review payload needed by the exact-run Stage 3A contract. Re-run the same 80-review slice before considering Presentation/UI or taxonomy convergence.
