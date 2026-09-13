# STRA Stage 4A.1 Implementation Report

## 1. Baseline

- Source branch: `refactor/semantic-sampling-v1`
- Source SHA: `e234998f08acb0f7536efa7a07c3fc8783d20a61`
- Archive branch: `archive/semantic-3e-pre-integration-20260913`
- Checkpoint tag: `checkpoint-3e-pre-integration-20260913`
- Integration branch: `integration/research-pipeline-v1`
- Checkpoint commit: `6ceaf13 chore: checkpoint stage 3e before pipeline integration`

The source worktree was clean before work began. The archive branch and tag
were created at the required Stage 3E SHA and pushed before implementation.

## 2. What was implemented

Stage 4A.1 now has this executable contract:

```text
Gold Validation Dataset
  → explicit ClassifierTaxonomyContract
  → existing production llm.classify_reviews(..., taxonomy_contract=...)
  → existing deterministic evaluate_classifier_fixture()
  → versioned gate
  → immutable ClassifierValidationRun
```

The runtime is separate from the provider-free scorer. The default runner
uses the production classifier path; tests inject a fake classifier through the
same taxonomy-contract boundary and never call an external API.

The new bundle service stores and activates the separate measurement
configuration contract. It does not modify `/analyze`, Topic Metrics,
Classification Materialization, UI, or Research Core calculations.

## 3. Files changed

- `apps/api/senti_next/classifier_validation_runtime.py` — dataset identity,
  classifier identity, production-compatible execution, and run assembly.
- `apps/api/senti_next/classifier_validation_policy.py` — centralized,
  versioned `classifier-validation-policy-v1` gate.
- `apps/api/senti_next/semantic_measurement_schema.py` — additive migration 20.
- `apps/api/senti_next/semantic_measurement_bundle.py` — validation-run
  persistence and bundle create/list/get/activate/retire/bootstrap services.
- `apps/api/senti_next/migrations.py` and `apps/api/senti_next/db.py` — registry
  and idempotent migration wiring.
- `docs/stage4a/PRE_STAGE4A_CHECKPOINT.md` — pre-integration status and
  limitations.
- `tests/unit/test_stage4a_validation_runtime.py` — runtime, identity, and
  gate coverage.
- `tests/integration/test_stage4a_measurement_bundle.py` — migration and
  bundle lifecycle coverage.
- Existing migration-version assertions were updated from 19 to 20 because
  migration 20 is now the latest schema contract.

## 4. DB migration

Migration 20 is additive and forward-only:

- `classifier_validation_runs`
- `semantic_measurement_bundles`
- `semantic_measurement_activation_events`

Metrics, gate reasons, limitations, and scorer provenance are JSON columns;
identity and lifecycle fields remain queryable columns. A partial unique index
ensures at most one active measurement bundle. Existing rows and migrations
18/19 are not rewritten. File-backed startup uses the existing backup and
restore-on-error migration wrapper; in-memory startup applies the same helper
idempotently.

## 5. Validation runtime design

`run_classifier_validation()` accepts an explicit taxonomy contract and builds
the prediction through `llm.classify_reviews`, which is the same production
batch classifier path used by existing analysis code. It then calls
`evaluate_classifier_fixture()` unchanged. The scorer's report remains
provider-free and retains its scorer-only limitations.

The final run record separately describes execution provenance. A real default
production execution does not claim `not_real_model_validation`; injected test
execution is labeled as injected/simulation in the run limitations.

## 6. Validation identity/provenance

Dataset identity is a canonical SHA-256 over sorted benchmark rows containing
review ID, review-text hash, gold topic/issue/request labels, primary label,
language, and dataset schema version. It does not use file path, time, object
identity, or random UUID. The record includes dataset ID, fingerprint, item
count, and language scope.

Classifier identity reuses the current provider configuration, active prompt
version, and `CLASSIFICATION_SCHEMA_VERSION`; it also records model ID,
taxonomy snapshot/version/fingerprint, and classifier taxonomy-contract
fingerprint. The content-addressed validation run ID changes when any of these
inputs or the scored result changes.

## 7. Gate policy

`classifier-validation-policy-v1` centralizes provisional engineering gates:

- coverage: 0.95 target, 0.80 hard floor;
- topic micro F1: 0.80; topic macro F1: 0.70;
- primary accuracy: 0.80;
- issue/request micro F1 when those gold labels are available: 0.65;
- invalid predictions and zero-gold-support false positives: 0 allowed;
- topic support below 5 is limited/insufficient rather than being accepted
  solely because its F1 is high.

The policy returns `PASS`, `PASS_WITH_LIMITATIONS`, or `FAIL`, with explicit
failure and limitation reasons. These thresholds are provisional engineering
admission criteria, not universal statistical claims.

## 8. Measurement Bundle semantics

`semantic_measurement_bundles` stores taxonomy identity, classifier identity,
validation run ID/status, measurement status, limitations, and lifecycle times.
The service exposes:

```text
create_measurement_bundle()
get_measurement_bundle()
list_measurement_bundles()
get_active_measurement_bundle()
activate_measurement_bundle()
retire_measurement_bundle()
```

Activation is separate from taxonomy activation. A retired bundle cannot be
activated, and activation writes an auditable event while preserving prior
bundles.

## 9. PROVISIONAL vs VALIDATED behavior

- `PASS` validation may create a `VALIDATED` bundle.
- `PASS_WITH_LIMITATIONS` defaults to `PROVISIONAL` and preserves all
  limitations.
- `FAIL` validation cannot create or activate a `VALIDATED` bundle.
- A no-run baseline is created as `PROVISIONAL` with
  `not_formally_validated` and `legacy_baseline_for_engineering_integration`.
- Explicit provisional activation is allowed for engineering/product
  integration and remains permanently identifiable as provisional.

No UI, route, or boolean bypass was added.

## 10. Tests added

- Production-compatible runtime receives the exact taxonomy contract.
- Dataset fingerprint is stable under row ordering and changes when content
  changes.
- Gate PASS, PASS_WITH_LIMITATIONS, FAIL, invalid labels, coverage, rare
  support, and zero-gold false positives.
- Migration 20 is idempotent and retains prior schema history.
- Provisional and validated activation, uniqueness of active bundle, retirement,
  and failed-validation admission rules.

## 11. Exact commands executed and results

Backend commands from `.github/workflows/ci.yml` were adapted only to use the
repository's Python 3.11 virtual environment and a workspace-local pytest
temporary directory because the default Windows temp root was inaccessible:

- `\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-temp-stage4a-run2`
  — **484 passed, 2 skipped** out of 486 collected.
- `\.venv\Scripts\python.exe -m py_compile apps/api/main.py` — passed.
- `\.venv\Scripts\python.exe -m py_compile` on the unchanged scorer and all
  new Stage 4A.1 modules — passed.
- Focused command `\.venv\Scripts\python.exe -m pytest -q tests/unit/test_classifier_validation.py tests/unit/test_stage4a_validation_runtime.py tests/integration/test_stage4a_measurement_bundle.py` — **18 passed**.
- `git diff --check` — no whitespace errors; only normal Windows LF/CRLF
  warnings.

Frontend checks were attempted exactly as required, but could not complete due
  the environment:

- `npm ci` in `apps/dashboard` — stalled with no output both in the sandbox
  and in a permitted retry; it was interrupted after the registry/cache
  operation did not complete. This left no usable local `node_modules`.
- `npx tsc --noEmit` — failed before TypeScript execution with npm
  `ENOTCACHED` while trying to resolve `tsc` from the unavailable registry.
- `npm run build` — failed with `'next' is not recognized` because the locked
  frontend dependencies could not be installed.

These frontend results are environment-related and not represented as a code
pass. The frontend was not changed by this stage.

## 12. Test counts/results

Backend: 486 collected, 484 passed, 2 skipped. The skipped tests are the
repository's existing real-provider/real-embedding smoke cases. The first
default-temp run also exposed Windows permission denial on
`C:\Users\liuqi\AppData\Local\Temp\pytest-of-liuqi`; rerunning with the
workspace-local basetemp completed the backend suite.

## 13. Existing behavior intentionally left unchanged

- `classifier_validation.py` scoring formulas and scorer limitations.
- Research Core Stage 2A–2E statistical semantics.
- Stage 3A semantic index, Stage 3B discovery, Stage 3C interpretation, and
  Stage 3D taxonomy governance behavior.
- Production `/analyze` orchestration, materialization, Topic Metrics,
  embedding/HDBSCAN behavior, version review, compare, agent, reports, and
  dashboard/UI.

## 14. Known limitations

- No independent human gold dataset was invented or promoted; the current
  baseline remains provisional.
- The gate numbers are provisional and need governance review against a real
  benchmark before formal admission.
- Frontend typecheck/build remain unverified locally because npm dependencies
  could not be installed in this environment.
- Stage 4A.1 stores the contract only; production `/analyze` consumption is
  explicitly deferred.

## 15. Explicitly deferred to Stage 4A.2

- Make Production Analyze read the active semantic measurement bundle.
- Classification materialization.
- Stage 3F Topic/Issue/Request metrics and unified research result.
- Taxonomy-gap classifier fields, embedding prototype convergence, version
  convergence, and all dashboard/database/report/UI work.

## 16. Final commit SHA(s)

- `6ceaf13` — `chore: checkpoint stage 3e before pipeline integration`
- `5314b2e5a7397c4a7c3f95d170ea4eff7e88b492` — `feat: add validated semantic measurement contracts`

## Stage 4A.1-R1 Review Fix — Validation Integrity Hardening

This section is appended as a review correction; the historical Stage 4A.1
record above is intentionally preserved.

### Review findings corrected

1. An injected/fake classifier could previously produce a metric PASS and then
   be admitted as a `VALIDATED` bundle. `run_classifier_validation()` now marks
   callback execution as `injected_classifier`; only the no-callback production
   path can produce `production_classifier` provenance. A fake run can create
   metrics and a provisional bundle, never a validated one.
2. The scorer previously omitted taxonomy topics with zero gold support from
   the visible per-topic audit. It now reports all active topics, including
   `taxonomy_topic_n`, covered count/rate, zero-support topic IDs, and complete
   `topic_support_status`. Macro F1 remains calculated only over gold-supported
   topics. Any zero-support or limited-support topic forces at least
   `PASS_WITH_LIMITATIONS`.
3. Production execution now preserves the `model_used` returned by
   `llm.classify_reviews()` in `ClassifierExecutionResult.actual_model_id`.
   Production callers cannot override provider/model/prompt/schema identity.
   Injected execution requires an explicit test identity, and the run identity
   includes execution mode, actual model identity, execution fingerprint, and
   full gate-policy content.
4. Bundle admission reloads `validation_run_id` from the database. The stored
   record, not a caller mapping, controls gate status, execution mode, and
   actual identity. Activation repeats the production-run referential checks.
   Baseline provisional bootstrap now matches the complete current classifier
   identity; provider/model/prompt/schema changes create a new bundle.
5. `.github/workflows/ci.yml` now includes `integration/**` in the push
   trigger; other CI semantics are unchanged.

### Migration 21

Migration 21, `classifier validation execution provenance hardening`, is
additive and idempotent. It adds nullable historical-safe fields to
`classifier_validation_runs`:

```text
execution_mode
actual_model_id
execution_identity_fingerprint
actual_provider
gate_policy_json
```

Existing Migration 20 rows remain readable with null actual-execution fields;
new formal runs require complete execution provenance before persistence.
Tests cover 20→21 upgrade, fresh latest initialization, repeated init, and
preservation of an existing validation row.

### R1 tests and remote CI

- Focused R1 tests: **25 passed**.
- Full backend suite: **493 collected, 491 passed, 2 skipped** using
  `\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-temp-stage4a-r1-full2`.
- Syntax/import compilation for `main.py` and all changed validation/database
  modules: passed.
- GitHub Actions run: **34759874689**
  ([run page](https://github.com/acetaffyace/STRA_V2/actions/runs/34759874689))
  for commit `56b84864a0ebcb71bd143fc4ff772789f07b8d22`.
  - backend: `success`
  - frontend (`npm ci`, `npx tsc --noEmit`, `npm run build`): `success`
  - overall: `success`

R1 core commit:

- `56b84864a0ebcb71bd143fc4ff772789f07b8d22` — `fix: harden semantic measurement admission`

R1 explicitly remains limited to validation-integrity hardening, Migration 21,
tests, and the integration-branch CI trigger. Stage 4A.2, `/analyze`,
Classification Materialization, 3F, Version Review, Compare, Agent, Reports,
and UI remain deferred.
