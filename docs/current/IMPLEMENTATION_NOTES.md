# Implementation Notes — Audit Pass

This file records observed deviations between `PRODUCT_OPTIMIZATION_SPEC.md` and the current source tree. It is an audit artifact only; no application code was changed during this pass.

## Observed facts

- The repository already contains a version-review vertical slice: `analysis_runs` in `apps/api/senti_next/db.py:372-393`, persistence in `apps/api/senti_next/storage.py:1514-1620`, and APIs in `apps/api/senti_next/routes/runs.py:246-510`.
- The general Analyze path still persists one latest result per `(user_id, app_id)` through `analysis_results` in `apps/api/senti_next/storage.py:1290-1345`; its `run_id` is a reference field, not the immutable run object required by the specification.
- SQLite schema creation remains embedded in `init_db()` and uses `CREATE TABLE IF NOT EXISTS`; `apps/api/README.md:33-35` explicitly says no migrations are needed. No Alembic directory or migration files were found.
- `reviews_fts` is a standalone FTS5 table in `apps/api/senti_next/db.py:133-140`. `storage.upsert_reviews()` appends one FTS row per upsert in `apps/api/senti_next/storage.py:128-180`; there are no external-content declarations or INSERT/UPDATE/DELETE triggers.
- `reviews.review_id` is globally unique (`apps/api/senti_next/db.py:119-127`), while the specification requires uniqueness by `(app_id, recommendation_id)`.
- Review-label cache invalidation currently compares only the stored review hash in `apps/api/senti_next/llm.py:1637-1775`; the database has `model`, `prompt_version`, and `review_hash`, but no first-class `label_source`, `validated`, retry, latency, token, or taxonomy fields (`apps/api/senti_next/db.py:144-155`).
- LLM usage is recorded in `llm_usage` via a best-effort logger (`apps/api/senti_next/llm.py:55-110`, `apps/api/senti_next/storage.py:79-125`), but the schema has no per-call `feature`, prompt version, estimated cost, latency, status, retry, or error fields required for the P0 cost ledger.
- Quote prompts request verbatim evidence (`apps/api/senti_next/llm.py:265-292`), and chat has a validator (`apps/api/senti_next/chat_tools.py:2268-2343`), but the validator returns suspicious quotes/warnings and is not a single enforced gate for all Chat/Evidence/run outputs. Existing version-run tests seed evidence without verification (`tests/regression/test_version_runs.py:62-80`).
- Benchmark infrastructure exists under `tooling/benchmarks/`, including cached token/latency data and synthetic/reference datasets, and `apps/api/evaluate_labeling.py` exists. The required `tooling/evals/player_voice/` Golden Set package, annotation guidelines, 300–500 human-reviewed records, and required precision/recall/F1 baseline report are not present.

## Baseline cautions

The working tree contained extensive pre-existing modifications and untracked feature files before this audit. They were not reverted or interpreted as authored by this audit. The plan therefore treats the current working tree as the observed baseline and calls for tests before implementation.

The revised plan now makes migration/backup a prerequisite to FTS work, retains the global `review_id` model pending collision evidence, keeps whole-run incremental behavior in P1, splits Run/Provenance and Golden Set work into independently rollbackable sub-phases, and forbids synthetic labels from being presented as human ground truth.
