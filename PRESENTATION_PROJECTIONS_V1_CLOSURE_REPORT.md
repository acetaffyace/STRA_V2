# Presentation Projections V1 Population Provenance Closure Report

Date: 2026-08-26  
Branch: `chore/agent-governance-layout` (fast-forwarded from `presentation/projections-v1`)

## Closure changes

- Added new-run immutable `metadata.population_provenance` with exact population count and minimal temporal source rows.
- Explicitly persisted `analysis_population_count = len(all_reviews)` at general-run completion.
- Changed daily projections to consume only the new immutable provenance contract.
- Kept historical runs without provenance unavailable; no backfill or immutable-result rewrite was performed.
- Added seven focused projection tests covering future provenance, historical unavailability, incomplete membership, zero buckets, reconciliation, isolation, and Version Review compatibility.

## Verification

- Projection/provenance unit tests: `9 passed`
- API Python compileall: PASS
- No database migration executed.
- No additional provider/LLM call was made for integration closure. The completed bounded real run and its ledger remain the authoritative acceptance evidence.
- No P2 projection implemented.

## Remaining gates

The full frontend build passed. After the user accepted the two-review variance and the stale isolated progress flag was cleared, the final bounded run `178d75eeebc848c1a5917ad18e35fb42` completed. It persisted 100 provenance rows, produced three UTC buckets, reconciled volume to 100 and recommendation numerator to 91, and rendered the daily projection in the UI without browser console errors. Exact ledger and screenshot evidence are recorded in `PROVENANCE_ACCEPTANCE_RUN_EXECUTION.md`.

Integration closure completed on the canonical integration runtime without copying the isolated `agent-a` database, logs, or temporary artifacts. The integration database remained at migration version 12 and passed SQLite integrity check.

The full frontend production build now exits successfully under the controlled elevated build environment. The earlier non-elevated `spawn EPERM` was an environment/process-spawn restriction, not an application compile failure.

The final integration report is `PRESENTATION_PROJECTIONS_V1_INTEGRATION_REPORT.md`.
