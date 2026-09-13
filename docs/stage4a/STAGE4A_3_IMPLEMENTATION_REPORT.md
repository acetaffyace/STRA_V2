# STRA Stage 4A.3 Implementation Report

## Baseline

- Branch: `integration/research-pipeline-v1`
- Required baseline SHA: `23aa95768dd9d3c04d25abf24f6fff49ffee06fe`
- The baseline was verified against `origin` before implementation; no reset or force push was used.

## Delivered

### Migration 23 and persistence

Migration 23, `canonical semantic measurement and unified research result`, adds nullable `semantic_measurement_result` and `unified_research_result` JSON text columns to both `analysis_run_results` and `analysis_results`. It is additive, forward-only, idempotent, and performs no legacy backfill. Storage reads the fields as dictionaries and preserves `_UNSET` backward-compatible update semantics.

Immutable run finalization is insert-once. A later attempt to finalize an existing run with a different semantic measurement fingerprint raises `semantic_measurement_result_conflict` rather than replacing the historical fact.

### Label estimate correction

Pre-run label estimates now best-effort resolve the active measurement context. When ready, estimates use the exact active taxonomy contract with `strict_taxonomy_identity=True`; when unavailable, the estimate is omitted rather than falling back to legacy cache identity. Background execution still resolves the authoritative context again.

### 3F canonical measurement

`topic_measurement.py` consumes only the frozen `ClassificationMaterialization`, persisted measurement bundle, and persisted validation run. It does not read mutable `review_labels`, Research Core, embeddings, or discovery output.

- `population_n`: full Research Population denominator.
- `materialized_n`: frozen materialized denominator; incomplete materialization fails closed.
- `classified_n`: items with `item_status=classified`, `label_origin=llm`, and `validated=true`.
- Topic, issue, request, and primary shares use `classified_n`.
- Classification coverage uses `classified_n / population_n`.
- Topic, issue, and request counts are multi-label and can sum above 100%; primary topic is mutually exclusive.
- Every active taxonomy topic is emitted in canonical-key order, including zero rows.
- Coverage states are `FULL`, `PARTIAL`, and `NONE`; zero population is `NO_POPULATION` with coverage `0.0`.
- Frozen payload taxonomy membership and issue/request subset integrity are defensively validated.

The result is schema-versioned as `semantic-measurement-result-v1` and has a deterministic `semantic_measurement_result_fingerprint` that excludes timestamps, random IDs, and filesystem paths.

### Validation qualification

`PROVISIONAL` bundles produce descriptive counts but mark all per-topic validation as `UNVALIDATED` with `provisional_measurement_bundle`. `VALIDATED` bundles read the persisted validation run independently for topic, issue, and request metrics. Sufficient, limited, and insufficient gold support map to `VALIDATED`, `LIMITED`, and `INSUFFICIENT`; unavailable issue/request gold remains `UNVALIDATED` with an explicit reason. Issue/request limitations are added only when they actually occur.

### Unified Research Result

`unified_research_result.py` composes `unified-research-result-v1`:

```text
quantitative: exact persisted Research Core report
semantic: SemanticMeasurementResult or null
semantic_status
provenance
limitations
```

Research Core is never recomputed. Quantitative-only runs also persist a unified result with `semantic=null` and the explicit unavailable/failed status. Successful semantic runs persist the semantic result and matching measurement fingerprint, bundle, materialization, taxonomy, classifier, and validation provenance. Legacy `insights` remain intact.

## Tests and verification

Backend:

```text
.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-temp-full3 tests
```

Result: full backend suite passed; the run retained only existing deprecation warnings and the existing two skipped tests.

Focused Stage 4A.3 and Stage 4A.2 regression tests also passed, including denominator semantics, primary-topic exclusivity, coverage states, zero-classification handling, invalid frozen payload rejection, frozen-source route integration, and quantitative-only unified composition.

Frontend:

```text
npm ci
npx tsc --noEmit
npm run build
```

`tsc --noEmit` passed. `npm run build` passed after allowing Next.js worker processes to run under the host environment. `npm ci` reported the repository lockfile's existing audit findings (16 vulnerabilities: 2 low, 3 moderate, 10 high, 1 critical); no dependency changes were made.

## Known limitations

- 3F is a single-run current-snapshot measurement only.
- Shares describe observed validated Steam reviews, not all-player prevalence.
- No significance testing, error correction, taxonomy-gap inference, embedding/discovery prevalence, or causal interpretation is included.
- Dashboard, Version Review, Compare, Agent, Reports, and Presentation API consumers still use their existing contracts; they are not migrated in this stage.

## Deferred

The next integration stage may consume Unified Research Result for Dashboard, Version Review, Compare, Agent, Reports, and presentation projections. Taxonomy-gap convergence and discovery-to-taxonomy mapping remain explicitly deferred.

## Stage 4A.3-R1 Review Hardening

### Historical qualification drift fix

The original 3F builder used the current `semantic_measurement_bundles.measurement_status` for claim and validation qualification. Because bundle retirement changes that lifecycle column to `RETIRED`, an old run could otherwise change meaning after governance action. R1 now accepts only the materialization-frozen status (`PROVISIONAL` or `VALIDATED`) and raises `semantic_measurement_invalid_frozen_measurement_status` for `RETIRED` or unknown frozen values. Claim status, per-topic qualification, limitations, and canonical provenance all use the frozen run-time status. Current bundle status is used only for existence and identity checks, so retirement cannot change the measurement fingerprint.

The validation run is loaded from `materialization.validation_run_id`, then checked against the bundle identity. Frozen `VALIDATED` materializations additionally require an authoritative persisted validation run with `PASS`, `production_classifier`, an actual model, an execution identity fingerprint, and matching taxonomy/classifier identity. Invalid validation provenance raises `semantic_measurement_invalid_validation_provenance`.

### Label estimate identity fix

`estimate_review_labeling` now accepts optional `game_context` and includes it in `classification_identity`, matching `ensure_review_labels`. Its cache eligibility and `identity_mismatch` reason use the same strict taxonomy flag. `/analyze` fetches app details once and reuses that context for the estimate and production classification; `/analyze/estimate` best-effort fetches the same context and returns an explicit unavailable error if it cannot obtain it.

### R1 regression coverage

Added tests for:

- validated topic qualification and unequal issue/request support qualification;
- explicit unavailable issue/request gold qualification;
- provisional bundle retirement invariance;
- invalid frozen status fail-closed behavior;
- exact game-context estimate identity and strict reason accounting;
- additive/idempotent Migration 23 structure and old-row retention;
- file-backed restart persistence for semantic and unified results;
- immutable semantic fingerprint conflict protection.

Focused command:

```text
.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-temp-r1b tests/integration/test_stage4a3_topic_measurement.py
```

Result: 11 passed. The Stage 4A.2, Stage 4A.3, lifecycle, and estimate regression set also passed.

Remote CI result will be appended after the R1 commit is pushed and its GitHub Actions run completes.
