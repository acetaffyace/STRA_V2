# Provenance Acceptance Run Execution

Date: 2026-08-26  
Branch: `presentation/projections-v1`  
Runtime: isolated `agent-a` profile, backend `8101`  
Database: `data/runtime/agent-a/sentinext.db`  
Integration DB modified: **No**  
Provider call status: **Completed on final replacement run**

## Bounded workload

- Game: `STEINS;GATE RE:BOOT`
- App ID: `4012810`
- Requested population: `100`
- Preflight estimated unique provider classifications: `78`
- Runtime re-estimate at run admission: `80` (hard expected budget exceeded by 2)
- Automatic population expansion: disabled by task scope
- Second acceptance run: not permitted

## Pre-call configuration

- Provider: `deepseek`
- Model: `deepseek-v4-flash`
- Prompt version: `steam_review_insights_v16_basic_labels`
- Pricing source: application pricing registry, `p0.6-pricing-v1`
- Input price: `$0.14 / 1M tokens`
- Output price: `$0.28 / 1M tokens`
- Cached input price: `$0.014 / 1M tokens`

## Pre-call estimate

The dry-run estimator reported 78 provider-required reviews, 22 short/rule-handled reviews, and 0 cache hits. A prompt-length estimate over the 100-review candidate produced approximately 135,224 input tokens; using a 100-token-per-classification output budget gives approximately 10,000 output tokens. This is an estimate only; the durable `llm_calls` ledger is authoritative after execution.

Estimated upper-bound cost using the configured registry:

`135,224 / 1,000,000 × $0.14 + 10,000 / 1,000,000 × $0.28 = $0.02173136`

The actual workload was lower than the pre-call upper-bound because the run was stopped after the runtime estimate exceeded the hard expected budget. The durable `llm_calls` ledger is authoritative.

## Execution record

## Execution history

Two earlier starts did not produce acceptance evidence:

1. `76914ab9a4504f4c96eb950363d588e8` was cancelled after runtime admission reported 80 required classifications against the original expected 78.
2. `d33461e538734b1e8b6b16ca02f35729` was immediately cancelled by a stale `progress.cancelled` flag and produced no provider calls.

After the user explicitly accepted the two-review variance, the stale isolated progress row was cleared and one final bounded run was started.

## Final observed execution

- run ID: `178d75eeebc848c1a5917ad18e35fb42`
- status: `completed`
- requested / retrieved / deduplicated / analysis population: `100 / 100 / 100 / 100`
- semantic sample / classified / fallback: `100 / 80 / 0 recorded fallback`
- cached / provider-required: `0 / 80`
- physical provider calls: `52`
- logical classification requests recorded in ledger: `52`
- retries: `0`
- failed calls: `0`
- successful provider calls: `52`
- input / output / total tokens: `98,217 / 28,830 / 127,047`
- cached input tokens: `896`
- recorded cost: `$0.021709884`
- latency: min `1,417.353 ms`, max `14,329.817 ms`, average `3,635.570 ms`, total `189,049.652 ms`
- immutable provenance: `complete=true`, `population_count=100`, `rows=100`, schema `general-population-temporal-v1`
- UTC buckets: `2026-08-24`, `2026-08-25`, `2026-08-26`
- daily volume: `44 + 45 + 11 = 100`
- daily recommendation denominator: `44 + 45 + 11 = 100`
- daily recommendation numerator: `39 + 42 + 10 = 91`
- persisted provenance `voted_up=true` numerator: `91`
- per-bucket formula: PASS
- app-wide access immutability proof: PASS; projection remained available with `storage.load_reviews` disabled
- UI screenshot: `artifacts/screenshots/provenance-acceptance-game-analysis.png`

## Stop reason

The final run used the user-approved variance of 80 provider-required reviews. It completed without retries or failed provider calls. The earlier cancelled runs remain recorded for auditability and are not used as acceptance evidence.

This preflight record is superseded by the completed final run above. No additional provider call is authorized for integration closure.
