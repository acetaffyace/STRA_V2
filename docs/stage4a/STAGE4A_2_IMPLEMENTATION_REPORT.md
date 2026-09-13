# STRA Stage 4A.2 — Production Classification Binding & Frozen Materialization

## Baseline

- Branch: `integration/research-pipeline-v1`
- Required baseline SHA: `542c3bbadd574d965a6d7297e6608bf9c8d52298`
- Feature commit: `76a17fd` (`feat: bind and freeze production semantic classification`)
- Scope remains limited to Stage 4A.2. Stage 4A.3 and 3F are explicitly deferred.

## Migration 22

Added `classification_materialization_schema.py` and migration registry version 22:

- `classification_materializations` is the immutable run-level parent record.
- `classification_materialization_items` stores one frozen item per review in the current Research Population.
- `analysis_runs` receives nullable direct references for measurement bundle, materialization, taxonomy, measurement status, and validation status.
- Migration is additive and idempotent; existing validation, measurement bundle, analysis run, and label rows are preserved.

## Measurement Runtime Resolver

`semantic_measurement_runtime.resolve_measurement_context()` is the single Production Analyze resolver.

- If no measurement bundle exists, it creates and activates an auditable `PROVISIONAL` baseline with activation reason `initial_product_bootstrap`.
- If bundles exist but no bundle is active, it returns `no_active_measurement_bundle` and does not resurrect a retired bundle.
- It loads the exact taxonomy contract from the active bundle and verifies snapshot ID, version, and fingerprint.
- It verifies provider, model, prompt, and schema identity against the current runtime.
- `VALIDATED` bundles re-check the authoritative persisted validation run, including production execution mode and actual execution identity.
- Resolver failures preserve Research Core and finalize a quantitative-only result.

## Strict cache and Analyze integration

Production classification now passes the resolved taxonomy contract directly to `ensure_review_labels(..., strict_taxonomy_identity=True)`. Strict mode requires exact taxonomy snapshot/fingerprint/version, provider, model, prompt, and classification-input identity; legacy NULL taxonomy provenance becomes a cache miss and is refreshed.

The background `/analyze` job now follows:

```text
Research Core
  -> resolve active measurement context
  -> bind bundle provenance to analysis_runs
  -> strict classification with exact taxonomy contract
  -> create immutable ClassificationMaterialization
  -> bind materialization to analysis_runs
  -> load frozen labels
  -> legacy apply_review_labels / prepare_insights
```

Provider-unavailable behavior remains backward compatible: Research Core completes as quantitative-only with the existing semantic reason. Semantic failures after Research Core also preserve the quantitative result.

Run metadata and semantic status retain explicit `PROVISIONAL` / `VALIDATED` and validation provenance. Legacy `status` / `reason` consumers remain supported; the new provenance is additive.

## Classification Materialization

`classification_materialization.py` provides:

- `create_classification_materialization()`
- `get_classification_materialization()`
- `get_materialization_for_run()`
- `load_materialized_review_labels()`
- measurement/materialization run-binding helpers

Materialization covers exactly the `all_reviews` population passed to the run, not all app-level cached labels. Population identity is deterministic over sorted `(review_id, review_hash)` pairs. The materialization fingerprint includes run ID, bundle identity, population fingerprint, and every item payload/provenance field.

Items use only `classified`, `fallback`, or `missing`:

- `classified` requires `label_origin == llm`, `validated == true`, and exact bundle identity.
- `fallback` freezes an existing non-validated label while preserving exact bundle taxonomy identity.
- `missing` records a population review with no usable cache label.

The same run and same content is idempotent. The same run with changed content raises `classification_materialization_conflict`. Different runs always receive separate materializations. Payloads are copied into the item table, so later mutable `review_labels` updates cannot change historical results.

## Tests

Exact local full-suite command:

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-temp-stage4a2-full2
```

Result: **499 collected, 497 passed, 2 skipped**.

Stage 4A.2 focused command:

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-temp-stage4a2 tests/integration/test_stage4a2_classification_materialization.py
```

Coverage includes migration/idempotency, fresh bootstrap, no-active non-resurrection, strict legacy cache rejection, runtime identity behavior, exact population isolation, same-run idempotency/conflict, cross-run separation, historical payload immutability, restart persistence, and `/analyze` bundle/materialization binding.

## Known limitations

- The existing app-level `review_labels` table remains a mutable operational cache; frozen materializations are the historical source of truth for completed Production Analyze runs.
- The baseline bundle is intentionally `PROVISIONAL` until a persisted production classifier validation PASS is available.
- Existing legacy routes outside Production Analyze retain their prior cache and taxonomy behavior.
- The resolver does not add new UI/admin surfaces in this stage.

## Explicit deferrals

Stage 4A.3 remains deferred. This commit does not add 3F topic metrics, issue/request formal measurement gates, unified research results, version/compare convergence, embedding/taxonomy convergence, dashboard redesign, agent/report rewrites, or new semantic metrics.

## Remote CI

To be filled after pushing the feature and report commits to `integration/research-pipeline-v1`:

- GitHub Actions run ID: pending
- Backend: pending
- Frontend: pending
- Overall: pending
