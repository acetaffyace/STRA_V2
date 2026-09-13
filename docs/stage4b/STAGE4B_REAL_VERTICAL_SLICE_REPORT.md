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

At the original Stage 4B baseline, this change added a redacted HTTP harness, its offline contract test, documentation, and a machine-readable summary; application schema remained at Migration 23. The R1 repair below adds Migration 24 without changing Research Core methodology.

Remote GitHub Actions run `34766673591` for the first pushed Stage 4B commit completed successfully: backend `success`, frontend `success`, overall `success`. URL: https://github.com/acetaffyace/STRA_V2/actions/runs/34766673591

## Recommended next path

**Path C — Backend Repair.** First make a real Production provider/model available and ensure quantitative-only completed runs preserve the immutable population fingerprint and full frozen review payload needed by the exact-run Stage 3A contract. Re-run the same 80-review slice before considering Presentation/UI or taxonomy convergence.


### Scope and original blockers

This repair is limited to the three backend blockers exposed by the original Run A:

- `IMMUTABLE_RUN_POPULATION_UNAVAILABLE` — a completed quantitative-only run had no independent exact population snapshot, so Stage 3A correctly refused to use it.
- `DEFAULT_LOCAL_DB_FTS_INTEGRITY_DRIFT` — startup repair did not restore the canonical `reviews.review_text` projection before rebuilding postings.
- `REAL_SEMANTIC_PROVIDER_UNAVAILABLE` remains an external prerequisite. No credential was added, no fake classifier was used, and no hybrid result was promoted as semantic success.

### Fixes

Migration 24 adds additive, idempotent `analysis_run_populations` and `analysis_run_population_items` tables. `/analyze` freezes the final sampled `all_reviews` before background Research Core work, including a complete canonical review payload for every item. The shared population fingerprint remains the Stage 4A-compatible sorted `(review_id, sha256(raw review text))` contract. Re-freezing the same run with the same population is idempotent; a changed population raises `research_population_snapshot_conflict` and cannot replace the old rows.

`build_semantic_index_for_run()` now reads only the immutable run snapshot. It does not fall back to mutable app reviews, presentation samples, or latest result payloads. Classification materialization verifies agreement with the same snapshot fingerprint and fails closed on mismatch. Historical runs created before Migration 24 remain unavailable rather than being backfilled from mutable data.

The runtime now rotates only a system-style provisional bootstrap bundle when it has no validation run, uses the baseline taxonomy, and carries the `not_formally_validated` limitation. A later provider/model identity change creates and activates an identity-specific provisional bundle, deactivates the old bundle, and preserves the activation event. Validated bundles, validation-bound bundles, explicit no-active state, and retired bundles are never auto-rotated or resurrected.

FTS repair now restores `reviews.review_text` from `reviews.data.$.review`, rebuilds the external-content FTS5 postings, verifies projection/posting integrity, and recreates only the derived index if a damaged segment rejects the canonical rebuild command. Startup remains fail-closed if repair cannot verify; it never deletes review data.

### Repaired real run

The new isolated file-backed runtime completed a real HTTP `/analyze` run:

- run: `99e9c86337f04134962c4dece037e9b2`
- target: HELLDIVERS 2 / `553850`
- request: 80 recent English reviews, `persist=true`, output language `zh`
- status: `completed`
- population snapshot: 80 reviews, fingerprint `27bc6aeafc7a27ad102c75874785390ced59d23f89011e656f31626363d9ce9f`
- restart persistence: verified against the file-backed SQLite database
- Research Core: 80 valid observations, 70 recommended, 10 not recommended, rate `0.875`; coverage incomplete because `max_reviews_reached`; the persisted report remains authoritative
- Unified quantitative result: persisted and equal to the exact Research Core report

The same-parameter estimate was also executed. It reported 80 considered, 0 cached, 80 needing refresh, and 80 LLM candidates with `missing_label: 80`. This is expected for a provider-unavailable run and is not presented as a cache identity failure.

### Provider state

Production semantic provider/model: unavailable / unconfigured. The run recorded `semantic_status=unavailable` with reason `no_provider`. Semantic classification, materialization, 3F, frozen taxonomy label mapping, taxonomy audit, and 3C interpretation therefore remain honestly blocked. No API key, credential, fake provider, or fake semantic output was used.

### Real 3A and 3B results

The fixed local ONNX model was ready:

- model: `intfloat/multilingual-e5-small`
- immutable revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- artifact SHA-256: `ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665`

Stage 3A then succeeded directly from the frozen Run population:

- index: `ccf4d8203324ff5e9aa4a702283849b93d4a17b120e406c6d540457daebf16c8`
- population/index fingerprint: `27bc6aeafc7a27ad102c75874785390ced59d23f89011e656f31626363d9ce9f`
- population: 80; indexed reviews: 80
- semantic units: 85; unique embeddings: 84
- embedding cache hits/misses: 85 / 0
- index fingerprint: `8310341c7daf0175490f1cef937123bc3fdb07bad7392c144b21b87aa1b7d90a`

Real HDBSCAN Stage 3B also succeeded without LLM labels:

- discovery run: `77844c128ea4572be4375bd88ee7694c0af44b2ee329ce6bcee2248ccd5119b9`
- dense regions: 2; rare regions: 0; outlier reviews: 48
- clustered review share: 0.4; unclustered review share: 0.6
- stability: 39 stable, 11 moderate
- taxonomy audit: unavailable without frozen classifier labels; no candidate was generated

These are discovery support/geometry results, not 3F topic prevalence and not player percentages. No taxonomy was changed, promoted, or activated. 3C was not run because no eligible taxonomy-labeled materialization existed.

### Regression and migration coverage

Added regression coverage for immutable snapshot idempotence/conflict, mutable-store isolation, restart persistence, quantitative-only-to-Stage-3A, shared fingerprint compatibility, materialization agreement, provisional identity rotation, no-active non-resurrection, validated non-rotation, FTS projection repair, FTS posting repair, file-backed startup recovery, Migration 24 table/FK/idempotence behavior, and retained result rows. The runner also received an offline import-path contract fix and still contains no secret or fake runtime path.

Exact validation commands:

```powershell
$tmp='D:\project\STRA_V2\.pytest_tmp_full3'; New-Item -ItemType Directory -Force -Path $tmp
$env:TEMP=$tmp; $env:TMP=$tmp; .venv\Scripts\python.exe -m pytest -q -rA
npm ci
npx tsc --noEmit
npm run build
```

The first full backend pass after implementation found only two stale tests asserting Migration 23; both were updated to assert Migration 24. The final test and CI results are recorded after push.

### Updated readiness and blockers

| Module | Status | Reason |
|---|---|---|
| Steam Acquisition | PASS | Real 553850 acquisition through `/analyze` completed. |
| Research Core | PASS_WITH_LIMITATION | Exact 80-review quantitative report persisted; recent max-review truncation limits coverage. |
| Measurement Bundle | PASS_WITH_LIMITATION | Provisional baseline and runtime-identity rotation are implemented; no provider is configured. |
| LLM Classification | BLOCKED | `REAL_SEMANTIC_PROVIDER_UNAVAILABLE` remains external. |
| Classification Materialization | BLOCKED | Requires semantic labels from the unavailable provider. |
| 3F | BLOCKED | No semantic measurement result exists without classification. |
| Unified Research Result | PASS_WITH_LIMITATION | Quantitative payload is exact and persisted; semantic payload is null by contract. |
| 3A Embedding | PASS | Real immutable ONNX model indexed the frozen 80-review population. |
| 3B Discovery | PASS_WITH_LIMITATION | Real HDBSCAN completed context-free; taxonomy audit is unavailable without frozen labels. |
| Taxonomy Audit | BLOCKED | No frozen taxonomy label map exists in a provider-unavailable run. |
| 3C Interpretation | BLOCKED | No eligible discovery materialization/evidence package exists. |

Blocker severity after R1: P0 `REAL_SEMANTIC_PROVIDER_UNAVAILABLE` remains open; the prior P1 immutable-population and P2 FTS blockers are repaired and regression-tested. No new P1/P2/P3 blocker was found.

The pushed R1 HEAD was validated by GitHub Actions run `34768743389`: backend `success`, frontend `success`, overall `success`. URL: https://github.com/acetaffyace/STRA_V2/actions/runs/34768743389

### Recommended next action

Remain on **Path C — Backend Repair**, but the remaining action is operational: configure an approved Production LLM provider/model without committing or exposing credentials, then rerun the same 80-review slice to exercise classification, frozen materialization, 3F, taxonomy audit, and optional 3C. Do not start UI or taxonomy convergence until that semantic branch is available and reviewed.

## Stage 4B-R2 Real Production Semantic Slice

### Scope and runtime safety

R2 used the existing HTTP `/analyze` orchestration for HELLDIVERS 2 (`553850`), with 80 recent English reviews, `persist=true`, and output language `zh`. The run used the user-configured Production DeepSeek runtime. Only the provider name, effective model identifier, prompt version, and runtime availability are recorded here; no key, header, credential file, raw prompt dump, database, model file, or full Steam review text was written to Git.

- baseline: `583c7ffed295b861e2ec4564874988375529c3a6`
- provider: `deepseek`
- model: `deepseek-v4-flash`
- prompt: `steam_review_insights_v16_basic_labels`
- classifier schema: `review-classification-schema-v1`
- taxonomy: `sentinext-taxonomy-v1`
- migration: `24`

### Production run and measurement binding

- run: `b92ba25b9f9b4230945d8eb6f92126ff`
- population: 80 reviews
- population fingerprint: `27bc6aeafc7a27ad102c75874785390ced59d23f89011e656f31626363d9ce9f`
- snapshot status: frozen; exact population was read back from the immutable snapshot
- measurement bundle: `measurement_bundle_afa0fd5e732d8b6476d3457df3447143`
- bundle status: `PROVISIONAL`
- validation run/status: `null` / `UNAVAILABLE`
- taxonomy snapshot/fingerprint: `snapshot_13190aadeede17d62ea387efc0efb7e3` / `418f27caf82290b258ded444a3f1eec8b7975a0f0989e248965e7279adb71b7d`
- materialization: `classification_materialization_cabf47ee4e9129b162d71a47e8207bca`
- materialization fingerprint: `657d6b79d5798ddb3031be6b801a809dfd9268830af8a3bf61eb0131423473c8`

The earlier unconfigured bootstrap bundle remained persisted and inactive; the DeepSeek-specific provisional bundle became active and an identity-rotation activation event was recorded. The old bundle was not retired. This is a real Production classification run, but its measurement qualification remains PROVISIONAL until formal classifier validation passes.

Classification materialization was complete: `population_n=80`, `materialized_n=80`, `validated_llm_n=80`, `fallback_n=0`, `missing_n=0`. The materialization population fingerprint exactly matched the immutable research population fingerprint.

### Research Core and 3F

The authoritative Research Core report remained the canonical quantitative payload. It reported 80 valid observations, 70 recommended, 10 not recommended, recommendation rate `0.875`, Wilson 95% interval `[0.7849719790084033, 0.9306644238399513]`, English distribution `80`, and incomplete acquisition because `max_reviews_reached` / `truncated_by_max_reviews=true`.

The persisted semantic result was:

- semantic fingerprint: `350a102670a0e9bc43adf5b16cf05fc9e60d606d0e48f8824cc1957f74af1695`
- population/classified/materialized: `80 / 80 / 80`
- classification coverage: `1.0` (`FULL`)
- claim status: `PROVISIONAL`
- unified result fingerprint: `8871964458deadb096e82aee7c1a668ac811a0483524f004c46cecf531ec5fd3`

Canonical denominator audit passed: topic, issue, and request shares use `classified_n=80`; classification coverage uses `population_n=80`. All canonical share/count pairs matched the expected count divided by the canonical denominator. The unified quantitative payload was exactly equal to the persisted Research Core report, and unified semantic was exactly equal to the persisted semantic measurement result.

Top observed classified topic share:

1. `other/meme` — 23 (`28.75%`)
2. `other/general` — 15 (`18.75%`)
3. `online_community/multiplayer_experience` — 11 (`13.75%`)
4. `gameplay/mechanics` — 10 (`12.50%`)
5. `gameplay/balance` — 7 (`8.75%`)
6. `technical/bugs` — 6 (`7.50%`)
7. `gameplay/difficulty` — 4 (`5.00%`)
8. `developer_updates/patch_quality` — 3 (`3.75%`)
9. `gameplay/progression` — 3 (`3.75%`)
10. `monetization_value/value_for_money` — 3 (`3.75%`)

Top observed classified issue share:

`gameplay/balance` 7 (`8.75%`), `technical/bugs` 6 (`7.50%`), `content_design/replayability` 2 (`2.50%`), `developer_updates/patch_quality` 2 (`2.50%`), `gameplay/ai` 2 (`2.50%`), and `gameplay/difficulty` 2 (`2.50%`). The remaining top-ten issue entries each had `n=1` (`1.25%`).

Top observed classified request share: `content_design/customization`, `developer_updates/update_frequency`, `online_community/social_features`, `technical/bugs`, and `technical/compatibility`, each `n=1` (`1.25%`).

`other/general` was 15/80 (`18.75%`) and `other/meme` was 23/80 (`28.75%`). This is a material taxonomy-coverage diagnostic, not a reason to mutate the taxonomy in R2. The classifier payloads had no populated evidence quote objects in this run; the spot-check therefore treated label assignments as evidence-limited rather than inventing quotes.

Evidence spot-check records were restricted to review IDs, labels, verdicts, and short reasons. Fifteen frozen reviews across `gameplay/balance`, `gameplay/mechanics`, `online_community/multiplayer_experience`, `other/general`, and `other/meme` were inspected. The verdicts were mostly `reasonable` or `clearly_correct`; the balance cases were marked `reasonable/questionable` where issue assignments could not be supported by a persisted evidence quote. No raw review text was saved.

### Cache reuse

The immediate same-parameter `/analyze/estimate` reported 80 considered, 65 cached, 15 needing refresh, and 15 LLM reviews. The refresh reasons were 10 `identity_mismatch` and 5 `missing_label`. This is substantial cache reuse, but the identity-mismatch subset is a P2 efficiency/reproducibility diagnostic to monitor; it did not alter the completed Run A canonical result. No optional second `/analyze` was run because the first estimate was sufficient for this slice and showed non-zero identity churn.

### Real 3A and 3B

The fixed LocalONNX runtime was ready and used; no fake embedding backend was used.

- model: `intfloat/multilingual-e5-small`
- revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- artifact SHA-256: `ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665`
- 3A index: `7f568d5678a167e7ccb8236992df5bdcd4b1a873ad6f28c544563008a956da30`
- index fingerprint: `8310341c7daf0175490f1cef937123bc3fdb07bad7392c144b21b87aa1b7d90a`
- population/index fingerprint: `27bc6aeafc7a27ad102c75874785390ced59d23f89011e656f31626363d9ce9f`
- indexed reviews: 80; semantic units: 85; unique embeddings: 84; cache hits/misses: 0/84 in the isolated runtime

Real HDBSCAN 3B used frozen Run A review metadata and the frozen `ClassificationMaterialization.items` label map. No mutable `review_labels` source was used.

- discovery materialization: `8981ae13c2e36802dff360a8cf02e4db9ec55d8059f2ffeeeccd97541419518d`
- discovery fingerprint: `e3789e2cf69b6e2dace56a03d12f625cf3c421d39d37c1c71bbaf5bb165154e4`
- dense regions: 2
- rare regions: 0
- outlier reviews: 48
- clustered/unclustered review share: `0.4 / 0.6`
- stability: 39 stable, 11 moderate

The taxonomy audit found review-level label coverage for all 80 frozen reviews, but region-level audit found 0 `well_covered`, 2 `mixed_existing_labels`, 0 `potential_gap`, and 48 `insufficient_taxonomy_coverage` outlier regions. One 20-review region had `other/general_share=0.7`. This means the current taxonomy is usable for the official 3F output but not yet strongly supported as a coherent explanation for most discovery geometry. Discovery support remains support, never player prevalence.

### 3C bounded interpretation

Evidence dry-run completed for all 50 regions: 2 dense regions were eligible by stability/type, while 48 outliers were deterministically deferred. There were no stable `potential_gap` regions, so the two stable/mid-stability mixed-existing-label regions were selected for the bounded real interpretation attempt.

The real Production 3C call was started with the frozen evidence packages, frozen review metadata, current provider, and `max_llm_calls=3`. The provider request did not return within the bounded operational wait and was stopped without accepting output. No fake interpretation, candidate, taxonomy approval, taxonomy mutation, or 3D promotion was created. 3C is therefore `BLOCKED` for this run by provider-call responsiveness, while the dry-run evidence gate itself passed.

### Product readiness matrix

| Module | Status | Reason |
|---|---|---|
| Steam Acquisition | PASS | Real 553850 acquisition through `/analyze` completed. |
| Research Core | PASS_WITH_LIMITATION | Exact 80-review report persisted; recent feed is max-review truncated. |
| Research Population Snapshot | PASS | Complete immutable population was persisted and matched all downstream fingerprints. |
| Measurement Bundle | PASS_WITH_LIMITATION | Runtime identity rotated to a provider-specific provisional bundle; formal validation is still unavailable. |
| Production LLM | PASS_WITH_LIMITATION | 80/80 real classifications completed; the separate 3C call did not return within the bounded wait. |
| ClassificationMaterialization | PASS | 80/80 materialized with no fallback or missing items. |
| 3F | PASS_WITH_LIMITATION | Canonical result and denominators are correct; claim remains PROVISIONAL. |
| Unified Research Result | PASS_WITH_LIMITATION | Quantitative and semantic payloads exactly match persisted canonical results. |
| 3A Embedding | PASS | Real fixed-revision ONNX index built from the exact frozen run. |
| 3B Discovery | PASS_WITH_LIMITATION | Real HDBSCAN completed; many outliers and mixed taxonomy coverage limit interpretation. |
| Taxonomy Audit | PASS_WITH_LIMITATION | Audit is available, but no region was well-covered and no potential-gap candidate was stable enough. |
| 3C Interpretation | BLOCKED | Dry-run completed; bounded real provider interpretation did not return. |

### Blockers and recommendation

- P0: none. The canonical semantic pipeline completed without fake provider output.
- P1: none observed in the completed Run A canonical result.
- P2: bounded 3C provider call did not return; 10/80 estimate refreshes were identity mismatches; classifier evidence quote objects were empty; Research Core acquisition was max-review truncated.
- P3: isolated 3A embedding cache was cold; no optional second Analyze was run.

R2 did not modify taxonomy, Research Core methodology, schema beyond Migration 24, or UI architecture. Because the official semantic pipeline is correct and reproducible but formal validation remains provisional and 3C provider responsiveness needs follow-up, the recommended next action is **Backend Repair** focused only on bounded 3C provider-call handling/observability and evidence-output quality. After that review, the product can proceed to **Presentation API + Dashboard convergence**; no UI work was started in R2.

### R2 remote CI

The semantic-slice documentation commit `6cacc06` was validated by GitHub Actions run `34771690536`: backend `success`, frontend `success`, overall `success`. The final report-only commit `a4295ef` was validated by run `34771829572` with backend `success`, frontend `success`, and overall `success`.
