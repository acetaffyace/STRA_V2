# P0.6 LLM Call-Path Audit

## Boundary finding

Production provider calls are centralized in `apps/api/senti_next/providers/`:
`OpenAICompatProvider` covers DeepSeek/OpenAI/Ollama, `GeminiProvider` covers
Google, and `XAIProvider` covers xAI. Classification, enrichment/summary,
report generation, Version Review, Chat Agent, simple Chat, and tool calls all
resolve a provider through `senti_next.llm` or the Chat Agent and therefore now
cross the durable ledger boundary.

The previous `llm_usage` table was best-effort aggregate token logging. It did
not persist a physical call id, retry attempt, run id, pricing snapshot,
latency, terminal status, or unknown-usage state. It remains for compatibility;
P0.6 uses `llm_calls` as the authoritative physical-call ledger.

## Call-path inventory

| Business operation | Caller | Provider boundary | Run linkage | Usage before P0.6 | Retry/fallback | P0.6 ledger behavior |
|---|---|---|---|---|---|---|
| Batch review classification | `llm.classify_reviews_batch` → `generate` | OpenAI-compatible/Gemini/xAI adapter | General analysis `run_id`; Version Review `run_id` | Adapter usage only, best-effort | Provider retries; batch failure can fall back to one call per review | One row per physical batch attempt; fallback calls are separate rows |
| Single/basic classification | `classify_review_single`, `classify_review_basic_single` | Same | Inherited context where caller has one | Same | Provider retries; rule/default fallback has no provider row | Each provider attempt is durable; rule fallback creates none |
| Label enrichment/cache refresh | `ensure_review_labels` | Same | General/Version run where wrapped | Same | Batch-to-single fallback | Physical rows retain operation and requested batch context |
| Health/report/summary generation | `generate_health_overview`, summarize helpers, news/report helpers | Same | General run where wrapped; otherwise nullable | Same | Adapter retries | One row per physical attempt |
| Version Review | `routes/runs.py` → `ensure_review_labels` | Same | Durable Version `run_id` | Same | Provider and classifier fallback | Run-linked attempts |
| Chat Agent/tool calls | `call_llm_with_tools` → `generate_with_tools` | Async provider boundary | No fabricated run id; app/session context where available | Partial adapter usage | Provider retries | One row per tool-call attempt, `purpose=chat_agent` |
| Simple/insight Chat | `run_chat_completion` | Same | No run id; session/app context | Partial adapter usage | Route retry plus provider retry | Route retries and provider attempts remain separate physical rows |
| Translation/other helpers | `_run_llm` / `translate_text` | Same | Nullable unless caller supplies context | Same | Provider retries | `purpose` from context or `unknown` |

## Data semantics

- `operation_id` identifies one logical operation; `call_id` identifies one
  physical attempt. Retry attempt 1 and attempt 2 share `operation_id`.
- `started → completed/failed` is the only lifecycle update. Terminal rows are
  not repriced or rewritten by later configuration.
- Usage is `available` only when provider response fields exist. Missing usage
  stays NULL with `usage_status=unavailable` and `cost_source=unavailable`.
- Rule/default fallback is not an LLM call and creates no ledger row.
- P0.5 evaluation artifacts are historical and are not backfilled into the
  ledger. Future evaluation traffic can set `workload_type=evaluation` via the
  existing context mechanism.

## Known limitations

Provider-reported billed cost is not currently returned by the supported
production adapters, so P0.6 records deterministic token estimates only.
Reasoning-token fields exist in the schema but remain NULL unless an adapter
exposes them. No raw prompt, response, API key, or authorization header is
stored; only an input hash and prompt/taxonomy identity are retained.
