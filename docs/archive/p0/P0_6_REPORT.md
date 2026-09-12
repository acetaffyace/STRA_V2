# P0.6 — Durable LLM Cost Ledger

## Outcome

P0.6 is implemented and verified. Every provider adapter now records one
durable row per physical provider attempt in SQLite `llm_calls`; retries share
an `operation_id` but retain separate `call_id` rows. P0.7/P1 work was not
started.

## Call-path audit

The audit is documented in [P0_6_LLM_CALL_AUDIT.md](P0_6_LLM_CALL_AUDIT.md).
The shared boundaries cover DeepSeek/OpenAI/Ollama, Gemini, and xAI for batch
classification, single classification, enrichment, summaries/reports,
Version Review, Chat Agent/tool calls, simple Chat, and translation helpers.
Existing `llm_usage` remains compatibility telemetry; `llm_calls` is the
authoritative physical-call ledger.

## Schema and migration

- Migration version: **8**
- Table: `llm_calls`
- Stable identity: `call_id` physical attempt; `operation_id` logical operation
- Run linkage: nullable `run_id`, captured from execution context; no latest-run
  inference
- Indexes: run, created time, provider/model, purpose
- Migration uses the existing backup/restore framework and is idempotent.
- No historical rows were fabricated or backfilled.

The schema records provider/model, purpose/phase, app/user/run context,
timestamps/latency, attempt/status/error, token fields, cached/reasoning
fields, pricing snapshot, cost source, prompt/taxonomy identity, input hash,
workload type, and batch counts where available.

## Cost semantics

`cost_source` is explicitly one of `token_estimate` or `unavailable` in the
current adapters; the schema also reserves `provider_reported` for a provider
that returns actual billed cost. Missing usage remains NULL with
`usage_status=unavailable` and `estimated_cost=NULL`; it is never converted to
zero.

Pricing is centralized in `cost_ledger.py`, versioned as `p0.6-pricing-v1`,
and snapshots currency, input/output/cache unit prices, source, version, and
timestamp into each call row. Historical reads never apply current pricing to
old calls. Canonical storage currency is USD; no historical RMB conversion is
persisted.

## Retry, fallback, and evaluation behavior

- Provider retry attempt 1 and attempt 2 are two physical rows with one
  logical `operation_id`.
- Provider/model fallback calls are independently recorded when the adapter is
  used; rule/default fallback creates no fake row.
- A batch request classifying N reviews remains one physical provider row.
- `run_id` is captured for general analysis and Version Review contexts.
- Ad-hoc Chat uses nullable `run_id` and retains purpose/app/session context;
  no synthetic Run architecture was added.
- Historical P0.5 evaluation spend was not fabricated into production history.
  Future evaluation callers can mark `workload_type=evaluation`.
- No API key, authorization header, raw prompt, raw review text, or raw
  response is stored. Only a SHA-256 input hash is retained.

## API and aggregation

Read-only endpoints:

- `GET /runs/{run_id}/llm-cost`
- `GET /llm-cost/summary?operation_type=&provider=&since=`

The deterministic summary returns physical call count, input/output/cache
tokens, retry count, failed-call count, estimated cost, and currency. Detailed
rows are available for a run endpoint. No Dashboard redesign was added.

## Performance

Synthetic local SQLite benchmark, 1,000 rows:

- 1,000 inserts: **15.799 ms**
- one run aggregation: **0.309 ms**
- daily aggregation: **0.644 ms**

This is negligible relative to provider latency; no speculative warehouse or
external service was introduced.

## Validation

- Canonical root pytest: **102 passed, 0 xfailed, 0 xpassed**
- P0 migration, P0.2 run, P0.3 provenance, P0.4 evidence, and P0.5 evaluator
  regressions: included in the full suite and PASS
- New P0.6 ledger tests: PASS
- `compileall`: PASS
- import smoke: PASS
- `git diff --check`: PASS, apart from normal Git LF/CRLF normalization
  warnings

The former intentional P0.6 contract xfail now passes.

## Preserved P0.5 quality truth

Accepted baseline remains Gold `p0.5c-gold-verified-v2`, SHA-256
`5b7aa442b9f70ec27f3ddee76a11ca0aab6c5cc110022da7e9c3da0f29eab50d`, with
DeepSeek `deepseek-v4-flash` frozen predictions. Subcategory precision remains
approximately 0.244 Dev and 0.237 Holdout with overprediction unresolved;
Holdout Challenge issue F1 is small-N and unstable; production first-pass
sentiment remains unavailable. P0.6 does not calculate a quality-per-dollar
score or imply a quality improvement.

## Known risks

Provider adapters currently expose token usage but not actual billed cost, so
the ledger is estimated where usage is available. Telemetry persistence is
best-effort and emits observable error logs so a provider result is not lost
when local telemetry is unavailable. Pricing updates require an explicit
versioned code/config change.

## Final recommendation

**GO for P0 closure review.** P0.6 is complete. Stop here; do not begin P1
automatically.
