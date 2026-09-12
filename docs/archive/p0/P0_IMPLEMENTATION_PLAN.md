# P0 Implementation Plan

Status: revised audit-derived plan; application code was not modified in this pass.

This revision incorporates `P0_BASELINE.md`. No destructive FTS/schema operation may occur before the migration/backup foundation is tested.

## Executive conclusion

P0 should be implemented as a sequence of compatible, test-led changes around the existing SQLite/storage/LLM paths. Do not replace SQLite, FastAPI, the provider abstraction, or the existing version-review slice. The first dependency is a preserved baseline plus a tested migration/backup foundation; only then may destructive FTS work begin. Whole-run incremental analysis and incremental ingestion remain P1.

## Audit matrix

| P0 requirement | Status | Direct evidence | Gap / implication |
|---|---|---|---|
| FTS canonical one-to-one index | **implemented differently** | `apps/api/senti_next/db.py:133-140`; `apps/api/senti_next/storage.py:128-180` | Standalone FTS rows are appended on every upsert; no triggers, repair command, or duplicate invariant test. |
| Immutable `analysis_runs` | **partially implemented / implemented differently** | `apps/api/senti_next/db.py:372-393`; `apps/api/senti_next/routes/runs.py:246-300`; `apps/api/senti_next/storage.py:1514-1620` | Exists only for version events; schema lacks general run scope, counts, cutoff, fingerprints, provenance, phase timings, and cost. Metrics/status are updated after creation. General Analyze still overwrites `analysis_results` (`storage.py:1290-1345`). |
| Population / classified population / priority evidence separation | **partially implemented** | `apps/api/senti_next/routes/analysis.py:244-265`; `apps/api/senti_next/insights.py:285+`; `apps/api/senti_next/routes/runs.py:450-509` | Sample payloads and metrics exist, but there is no shared metric registry/contract exposing numerator, denominator, population count, classified count, source type, run ID, and sampling flag. |
| Label provenance | **partially implemented** | `apps/api/senti_next/db.py:144-155`; `apps/api/senti_next/llm.py:1637-1920` | Hash/model/prompt and internal `_label_source` exist; `validated`, taxonomy, retry, latency, token counts, and explicit allowed KPI sources are not persisted as a uniform contract. Fallback terminology is also not normalized to the spec values. |
| Evidence verification | **partially implemented / implemented differently** | `apps/api/senti_next/llm.py:265-292`; `apps/api/senti_next/chat_tools.py:2268-2343`; `apps/api/tests/test_version_runs.py:62-80` | Prompt asks for exact quotes and Chat has a checker, but verification is not a blocking, shared service for Chat, Evidence cards, and run metrics. No regression test proves a fabricated quote is rejected. |
| Golden Set | **partially implemented** | `tooling/benchmarks/`; `apps/api/evaluate_labeling.py` | Existing benchmark/evaluation tooling is not the required player-voice Golden Set package with annotation guideline, stratified human labels, required metrics, and baseline artifact. |
| LLM cost ledger | **partially implemented** | `apps/api/senti_next/db.py:247-270`; `apps/api/senti_next/llm.py:55-110`; `tooling/benchmarks/pricing.py` | Usage tokens are best-effort and aggregate-oriented; no durable per-call ledger with feature/model/prompt/status/retry/latency/estimated cost. |

## Dependency-ordered implementation

### P0.0A. Baseline / migration / backup foundation

Execution order inside P0.0A is strict:

```text
baseline snapshot
  -> P0 contract tests
  -> migration + backup foundation
```

The migration work below must not start until the contract-test gate passes.

Files to add/modify:

- `P0_BASELINE.md` — record branch, HEAD, status, tracked diff, and untracked files before implementation.
- migration runner files selected after verifying desktop packaging constraints; do not assume Alembic before checking footprint.
- `apps/api/tests/test_p0_migration.py` — migration smoke, backup, rollback, and idempotency tests.
- existing SQLite fixtures as needed.

Required discovery before writing migration SQL:

- verify that `reviews` retains a normal SQLite `rowid`;
- verify the current upsert semantics in `apps/api/senti_next/storage.py:128-180` and confirm whether any path uses `INSERT OR REPLACE`;
- audit cross-app collisions with:

```sql
SELECT review_id, COUNT(DISTINCT app_id)
FROM reviews
GROUP BY review_id
HAVING COUNT(DISTINCT app_id) > 1;
```

Do not change the current globally unique `review_id` model unless source/data evidence proves it unsafe. If the collision query is empty and joins/cache/evidence rely on the current key, retain it and record an ADR.

Definition of Done:

- migration applies to fresh and existing fixtures;
- migration is idempotent;
- backup is created before destructive operations and restore is tested;
- rollback criteria and restore procedure are documented;
- migration tests pass before any FTS schema migration.

Rollback criteria: any backup failure, migration exception, integrity mismatch, or failed restore test blocks P0.1; restore the pre-migration backup and leave application schema untouched.

### 0. Baseline and compatibility harness

Files to add/modify:

- `apps/api/tests/test_p0_contracts.py` — new failing tests for the invariants below.
- `apps/api/tests/conftest.py` or existing SQLite fixtures — isolated in-memory/file fixtures as needed.
- `IMPLEMENTATION_NOTES.md` — keep observed schema and compatibility decisions current.

Tests first:

- duplicate FTS IDs are zero after one insert, 100 identical upserts, text update, delete, and rebuild;
- label cache identity uses review hash + taxonomy + prompt + model;
- a metric exposes numerator/denominator/coverage and excludes invalid fallback labels;
- fabricated evidence is rejected;
- an LLM call writes one ledger record.

This section is the P0.0A contract-test gate; the unchanged whole-Analyze/zero-LLM behavior is intentionally excluded because it belongs to P1 incremental analysis.

### 1. FTS integrity (P0.1; only after P0.0A passes)

Files to modify:

- `apps/api/senti_next/db.py`
- `apps/api/senti_next/storage.py`
- `apps/api/senti_next/dialect.py` only if the shared FTS expression needs adjustment
- `apps/api/tests/test_sqlite_compat.py` and/or `apps/api/tests/test_p0_contracts.py`

Design:

- Preserve existing `reviews` and `review_labels` callers.
- After P0.0A confirms rowid/upsert behavior, migrate `reviews_fts` to external-content FTS5 keyed by canonical `reviews.rowid`, with INSERT/UPDATE/DELETE triggers.
- Add `rebuild_fts()` and `verify_fts_integrity()` storage operations.
- Make review upsert update the canonical `reviews` row only; remove manual FTS appends after migration.
- Do not introduce a composite key merely to match the specification. Retain the current global key if the collision and join audits support it; document the decision in an ADR.

Migration/rollback:

- Use the migration/backup mechanism established in P0.0A; do not create a second ad hoc mechanism here.
- Back up the local DB before migration; create the new FTS table/triggers, rebuild from `reviews`, then verify counts and searchable text.
- Rollback restores the backup or drops only newly-created FTS objects; never delete source reviews.

Definition of Done:

```text
insert once       -> 1 FTS document
same upsert x100  -> still 1 FTS document
text update       -> old text absent, new text searchable
review delete     -> no FTS result
rebuild           -> reviews and FTS consistent
duplicate IDs     -> 0
```

Rollback criteria: any duplicate, trigger mismatch, failed rebuild, or search regression blocks rollout; restore the P0.0A backup and leave canonical reviews intact.

### 2. Run/provenance contract (split P0.2a–P0.3c)

#### P0.2a Run schema

Files: `apps/api/senti_next/db.py`, migration files, schema tests.

Only establish the general analysis-run data model and indexes. Do not change frontend behavior or rewrite the analysis pipeline in this sub-phase.

Definition of Done: fresh and upgraded DBs expose the required nullable run fields, indexes, and schema version; rollback is backup restore.

#### P0.2b Run lifecycle

Files: `apps/api/senti_next/routes/analysis.py`, run storage helpers, lifecycle tests.

Only wire Analyze to create a run and move through controlled queued/running/completed/failed/cancelled states. Do not redesign metrics or dashboard payloads.

Definition of Done: every new Analyze has a run ID; terminal transitions are deterministic; failures/cancellation are observable. Rollback disables new run creation and preserves legacy reads.

#### P0.2c Result linkage / compatibility

Files: `apps/api/senti_next/storage.py`, `apps/api/senti_next/routes/analysis.py`, response models, compatibility tests.

Link `analysis_results` to the latest completed general run while retaining `/analysis/{app_id}` response compatibility. Preserve old records as legacy; do not invent provenance.

Definition of Done: old API responses remain valid; latest completed linkage is correct. Rollback returns to legacy latest-result reads.

#### P0.3a Label provenance

Files: `apps/api/senti_next/db.py`, `storage.py`, `llm.py`, label tests.

Persist `label_source`, `validated`, taxonomy, provider/model, prompt, review hash, retry, latency, token/truncation metadata. Cache identity is:

```text
review_hash + taxonomy_version + prompt_version + model_id
```

Definition of Done: unchanged identity is a cache hit; each identity component changing causes a miss; fallback labels remain visible but are excluded from formal KPI eligibility. Rollback marks new fields legacy and retains prior labels.

#### P0.3b Metric provenance

Files: `apps/api/senti_next/insights.py`, backend metric serializers, contract tests.

Define a shared metric contract with numerator, denominator, population/classified counts, source type, sampling flag, and run ID. Separate population, classified population, and selected evidence.

Definition of Done: every new LLM-derived KPI exposes denominator and coverage; invalid fallback labels cannot enter the formal denominator. Rollback serves legacy metric payloads with explicit legacy status.

#### P0.3c Frontend adoption

Files, only after backend contract tests pass: `apps/dashboard/src/lib/api.ts`, view models, affected components, frontend tests.

Read and render the backend metric contract; do not recompute KPI values from review samples.

Definition of Done: frontend displays backend values/coverage without changing metric semantics. Rollback leaves legacy rendering available.

Shared design constraints:

- Generalize the existing run object without breaking `/analysis/{app_id}`. The legacy endpoint can remain a compatibility read facade pointing to the latest completed run.
- Add immutable creation-time scope/config fields: app, cutoff/window, language/query parameters, requested/retrieved/valid/classified/fallback/enriched counts, scope/label/analysis fingerprints, taxonomy/prompt/model/provider, and phase timings/cost references.
- Treat status transitions as controlled state changes; freeze scope and provenance after completion. Preserve old run records.
- Formal KPI eligibility is `label_source in ('llm','cache') AND validated = true`.
- Add run summary/metrics/evidence API reads while keeping existing version-run endpoints compatible.

Migration/rollback:

- Add nullable columns/tables first; backfill legacy results with explicit `legacy` provenance and no invented counts.
- Dual-read during rollout; rollback by disabling new run creation while preserving legacy reads. Do not rewrite old completed results.

### 4. Evidence verification (P0.4)

Files to modify:

- `apps/api/senti_next/chat_tools.py`
- `apps/api/senti_next/chat.py`
- `apps/api/senti_next/routes/chat.py`
- `apps/api/senti_next/insights.py`
- `apps/api/senti_next/routes/runs.py`
- `apps/api/tests/test_p0_contracts.py`, `apps/api/tests/test_version_runs.py`

Design:

- Extract a shared verifier that checks quote is an exact substring of the cited review and that review ID/app ID exists in the run scope.
- Make invalid quotes unavailable to response serializers and mark/reject the containing evidence item; do not merely emit a warning.
- Return verification status and source review IDs with every evidence card/citation.
- Add tests for exact quote, altered punctuation, missing review, wrong app, and empty source scope.

### 5. Golden Set and evaluation (split P0.5a–P0.5c)

Files to add/modify:

- `tooling/evals/player_voice/annotation_guidelines.md`
- `tooling/evals/player_voice/golden_set.schema.json`
- `tooling/evals/player_voice/select_samples.py`
- `tooling/evals/player_voice/annotation_template.jsonl`
- `tooling/evals/player_voice/evaluate.py`
- `tooling/evals/player_voice/baseline.json`
- `tooling/evals/player_voice/README.md`
- Reuse/adapt `tooling/benchmarks/hashing.py`, pricing, and provider adapters where compatible.

#### P0.5a Engineering scaffold

Codex may implement the schema, guidelines, sample-selection tooling, annotation template/UI/CSV/JSONL path, evaluator, metrics, CI subset, and baseline runner. It must not manufacture human ground truth.

Definition of Done: a real-review sample can be exported for annotation, re-imported without losing provenance, evaluated, and run in a small CI subset. Rollback is removal/disablement of the new tooling only.

#### P0.5b Human annotation

Human annotators label the exported real Steam reviews. The first acceptable milestone is 100–150 high-quality records; scale toward 300–500 only when annotation quality and coverage justify it.

Definition of Done: records are marked human-reviewed with annotator/version metadata and disagreement handling. Synthetic labels or model agreement cannot be marked as human ground truth.

#### P0.5c Baseline evaluation

Codex runs `evaluate.py` against the human-annotated data and stores baseline metrics. No model/prompt upgrade is approved from synthetic-only results.

Definition of Done: required classification, issue/request, sentiment, evidence, schema, fallback, latency, token, and cost metrics are reproducible. Rollback removes only derived reports, not human annotations.

Coverage requirements:

- Start with a stratified, human-reviewed set; do not represent synthetic agreement as ground truth.
- Cover positive/negative/mixed, short/long, sarcasm, technical/gameplay/content/UI/onboarding/monetization, requests, and no-issue/multi-label cases.
- Report category precision/recall/F1/macro-F1, multi-label micro/macro/per-label scores, issue/request precision/recall, sentiment accuracy/confusion matrix, quote exactness/support rate, invalid JSON/schema retry/fallback/latency/tokens/cost.
- Keep small CI subset separate from full Golden Set.

### 6. LLM cost ledger (P0.6)

Files to modify:

- `apps/api/senti_next/db.py`
- `apps/api/senti_next/storage.py`
- `apps/api/senti_next/llm.py`
- provider wrappers under `apps/api/senti_next/providers/`
- `apps/api/tests/test_p0_contracts.py`

Design:

- Add durable `llm_calls` records with run ID, feature, provider, model, prompt/taxonomy version, input/output/cached tokens, estimated cost, latency, status, retry count, error type, and timestamp.
- Centralize instrumentation around provider calls so classification, enrichment, summary, chat, comparison, report, and translation are tagged consistently.
- Keep existing `llm_usage` as a compatibility aggregate until consumers migrate.
- Add pricing lookup with explicit unknown-cost state; local Ollama remains API cost zero while latency/tokens are recorded.
- Add run-level aggregation and budget estimates only after per-call records are reliable.

Ledger write granularity:

- one provider attempt produces one complete short-transaction record after the call;
- never update SQLite per streamed token/event;
- logging failure is non-blocking but observable.

Migration/rollback:

- Add the ledger table nullable/non-blocking; failure to log must not fail an analysis run, but diagnostics must expose missing records.
- Rollback disables new ledger writes and retains old usage data.

## API compatibility impact

- Keep existing `/analysis/{app_id}`, `/analysis/{app_id}/estimate`, `/runs`, and version-review endpoints operational during migration.
- Add fields rather than changing existing field meanings; legacy records should return explicit `provenance_status: "legacy"` where required.
- Do not make frontend code compute formal denominators from review samples. Update frontend only after backend contract tests establish the payload.
- Do not rename or remove `llm_usage` until all existing diagnostics and settings consumers are migrated.

## Performance and cost risks

- FTS rebuild is O(number of stored reviews); run once per migration and expose progress for large local databases.
- Trigger maintenance adds write overhead but removes duplicate manual indexing and makes update/delete correctness deterministic.
- Run/provenance aggregation adds small SQLite writes; avoid copying full review DataFrames into every run record.
- Per-call cost logging must be non-blocking/best effort, but missing ledger rows must be measurable.
- Golden Set full runs may invoke providers; CI should use a small fixed subset by default and require explicit credentials for full runs.

## Minimal delivery order

```text
baseline snapshot
  -> P0 contract tests
  -> migration + backup foundation (P0.0A)
  -> FTS integrity and repair (P0.1)
  -> P0.2a run schema
  -> P0.2b run lifecycle
  -> P0.2c result linkage / compatibility
  -> P0.3a label provenance
  -> P0.3b metric provenance
  -> P0.3c frontend adoption
  -> P0.4 blocking evidence verifier
  -> P0.5a engineering scaffold
  -> P0.5b human annotation
  -> P0.5c baseline evaluation
  -> P0.6 durable LLM cost ledger
```

After this plan is revised, start only with P0.0A. Do not implement FTS until the P0.0A tests pass. Do not bundle dashboard redesign, incremental ingestion, whole-run incremental analysis, architecture replacement, or unrelated frontend refactors into the audit-derived P0 work.
