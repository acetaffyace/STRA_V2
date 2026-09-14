# STRA Stage 4D.1-R1 — Canonical Comparison Fail-Closed Repair

## Baseline and scope

- Baseline: `587880521778d5bb1f6229a7097efe31681facab`
- Repair implementation commit: `91593b4`
- Branch: `integration/research-pipeline-v1`
- Migration: `24` (no Migration 25)
- Scope: four P1 integrity repairs only; Agent and Reports migration remains deferred to Stage 4D.2.

## P1-A — Compare official metric fallback

Before, Compare could resolve an official recommendation through the exact-run comparison, then fall back to a legacy insight and finally zero.

After, the comparison projection is the only source for the official value. If it is unavailable, the value is nullable and the UI shows an explicit unavailable warning. Filtered review/category values remain available only as descriptive views and are labelled accordingly.

## P1-B — Version Review fallback

Before, a failed `/runs/{run_id}/comparison` request could replace the canonical response with the embedded `version_review_v2` payload, allowing legacy values to appear as official metrics.

After, Version Review tracks the V2 compatibility payload and canonical comparison separately. A canonical fetch failure leaves official population, recommendation rate, and delta unavailable (`—`) while retaining legacy window observations, topic comparisons, paired evidence, and sensitivity content as descriptive material.

## P1-C — Version-window exact counts

Before, the adapter fabricated `recommended_n` and `not_recommended_n` using rounded `rate × reviews` arithmetic.

After:

- `population_n`: exact persisted window review count
- `valid_n`: exact window denominator, because V2 computes the persisted rate over every review in that window
- `recommendation_rate`: exact persisted observation
- `recommended_n`: `null` unless explicitly persisted upstream
- `not_recommended_n`: `null` unless explicitly persisted upstream

Optional factual counts now preserve unknown as `null`; parsing no longer converts missing values to zero. Normal `analysis_run` sides continue to preserve exact Research Core counts.

## P1-D — Complete semantic identity gate

Semantic delta now requires both sides to have non-empty values for:

`measurement_bundle_id`, `taxonomy_snapshot_id`, `taxonomy_fingerprint`, `provider`, `model_id`, `prompt_version`, `schema_version`, `measurement_status`, `claim_status`, and `validation_status`.

The canonical 3F contract provides both taxonomy snapshot identity and taxonomy fingerprint, so both are required. Missing identity produces explicit `semantic_identity_incomplete_<field>` reasons and no delta. Complete equal identity still permits comparison, including matching `PROVISIONAL` qualifications; different identity remains side-by-side only. Version Review V2 windows intentionally lack modern 3F identity and therefore remain fail-closed for semantic delta.

## Regression coverage

Added tests cover:

- version-window `3 / 0.666667` without fabricated positive/negative counts
- missing optional counts remain `null`, not zero
- exact Research Core counts remain exact
- missing identity cannot establish compatibility
- complete equal identity permits semantic delta
- bundle, taxonomy, provider, model, prompt, schema, and qualification mismatches disable delta
- exact left/right isolation remains independent of mutable/latest results

## Browser QA

Focused standalone Chromium QA used the isolated synthetic comparison fixture and checked `/compare` and `/version-review` at `1440×900`, `1366×768`, and `1024×768`.

- Canonical success: exact canonical values rendered; Version Review showed `+5.0pp`.
- Canonical failure: Compare showed an unavailable warning and no legacy official value; Version Review showed `推荐率：—`, `推荐率变化：—`, while legacy window observations remained visible.
- Semantic incompatibility/incompleteness: backend projection returned `semantic_delta_comparable = false` and `semantic.delta = null`.
- Exact side isolation: left and right source IDs remained the requested run IDs.
- Horizontal overflow: none.
- Page errors: none.
- Unexpected console errors: none. Expected `ERR_FAILED` noise from intentionally aborted comparison requests was excluded from the failure-injection case only.
- Screenshots and machine-readable QA output were generated and inspected under the ignored local directory `.stage4d_runtime2/r1-qa/`; temporary QA artifacts were removed after inspection and are not committed.

The in-app browser bridge was unavailable in this environment, so the project’s standalone Playwright/Chromium runner was used after attempting the bridge.

## Validation status

- Targeted comparison tests: passed.
- Full backend suite: `539 collected, 537 passed, 2 skipped`.
- Frontend: `npm ci`, `npm run typecheck`, and `npm run build` passed. `npm ci` reported the existing audit baseline of 16 vulnerabilities; no audit remediation was attempted in this scoped repair.
- Remote CI: pending push of the repair commits.

## Remaining issues

- P0: none identified.
- P1: none identified after the repair and focused QA.
- P2: historical Version Review V2 windows do not persist complete modern 3F identity, so semantic delta remains intentionally unavailable; descriptive filtered comparison helpers remain legacy/non-canonical; the legacy AI summary endpoint remains a bounded descriptive consumer.
- P3: npm audit and Developer Mode remain deferred; in-app browser bridge is unavailable on this host.

## Downstream status

The Agent and Reports dependency inventories from Stage 4D.1 are preserved. With this repair, `research-comparison-v1` is safe for downstream read-only consumption. Stage 4D.2 has not started.
