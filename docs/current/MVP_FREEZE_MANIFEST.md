# SentiNext MVP Freeze Manifest

Status: `SENTINEXT_MVP_FROZEN` candidate, Phase A, 2026-08-26.

## Identity

- Release branch: `release/mvp-v1`
- Release tag: `sentinext-mvp-v1`
- Source baseline commit: the commit resolved by tag `sentinext-mvp-v1` (`git rev-parse sentinext-mvp-v1^{}`)
- Pre-freeze working-tree HEAD: `7ec4adcb7cb17e69ae997310e108d7ec6688d291`
- API contract: `unified-analysis-v1`
- Runtime profile: `integration`
- Backend/frontend ports: `8000` / `3000`
- Canonical database: `data/runtime/integration/sentinext.db`
- Database instance: integration runtime SQLite instance
- Schema migration version: `12`
- Canonical DB integrity: `ok`
- Frozen DB backup: `backups/mvp-v1/sentinext-mvp-v1.db`
- Backup SHA-256: `6707B02911275C52B988D6DF7E16A249F8BFB014AE8DC0D7AA80DC3AFA2ED4B`

## Analytical identity

- Taxonomy version: `sentinext-taxonomy-v1`
- Classification schema: `review-classification-schema-v1`
- Active prompt version: `steam_review_insights_v16_basic_labels`
- Gold/Holdout identities are recorded by SHA-256 in the release report; source files remain in the repository.
- Provider/model configuration: runtime-configured through environment/settings; secrets are intentionally not copied into this manifest. The checked-in `.env.example` is the configuration template.

## Preserved evidence

Source/runtime, migration modules, tests, Gold/Dev/Holdout artifacts, taxonomy/prompt/schema contracts, metric/evidence provenance, AnalysisDesign/Version Review contracts, MVP release/acceptance/runbook documents, canonical DB and backup, and portfolio materials are retained.

Superseded process material is indexed under `docs/archive/`. Disposable caches, build output, runtime logs, and stale locks were removed only from the explicit cleanup manifest.

## Freeze contract

The release branch is frozen for normal feature work. Allowed changes are critical bug, security, data-loss, or compatibility fixes required to keep the product runnable. API cost work must use a separate branch and preserve this analytical contract.

## Verification status

See `MVP_FREEZE_RELEASE_REPORT.md` for exact regression results and the browser-smoke environment limitation.
