# P0 Known Limitations

| Limitation | Classification | Trigger / next action |
|---|---|---|
| Steam reviews are self-selected and do not represent all players | accepted P0 limitation | P1 research/measurement if broader population inference is needed |
| Subcategory overprediction; baseline precision ≈0.244 Dev / 0.237 Holdout | accepted P0 limitation; P1 candidate | Improve taxonomy calibration/precision before high-stakes automation |
| First-pass LLM sentiment is unavailable | accepted P0 limitation | Add a separately evaluated sentiment contract only when needed |
| Golden Set is small for rare labels and languages | accepted P0 limitation | Expand human set when decisions require rare-language confidence |
| Challenge Holdout is small-N and descriptive only | accepted P0 limitation | Increase challenge sampling before population claims |
| FastAPI BackgroundTasks are not durable workers across restart | accepted P0 limitation | Durable task infrastructure becomes a scale/P1 trigger |
| `llm_calls` is best-effort observability, not exactly-once billing ledger | accepted P0 limitation | Billing-grade guarantees require a different deployment scope |
| Provider cost is token-estimated unless provider reports billing | accepted P0 limitation | Persist provider-reported billing if a provider exposes it |
| Frontend has no dedicated test runner; typecheck/lint/build are the closure checks | accepted P0 limitation | Add browser/component tests when UI complexity justifies it |
| FTS full integrity verification is explicit/admin path, not hot path | accepted P0 limitation | Run repair when diagnostics detect drift |
| `review_labels` is latest reusable cache, not label version history | accepted P0 limitation | Add label history only if reproducibility requires it |
| SQLite/local-first concurrency has single-host limits | accepted P0 limitation | PostgreSQL/queue infrastructure is a scale trigger, not P0 |

## Product-claim guardrails

P0 can legitimately claim that the system analyzes Steam review data, computes
formal metrics with provenance, separates problem/request/topic signals,
provides source-grounded evidence, preserves run-level reproducibility,
contains a human-verified classifier baseline, and tracks provider usage/cost
estimates.

P0 must not claim that Steam reviewers represent all players, observational
review changes prove causality, LLM confidence means factual accuracy,
taxonomy labels are high precision for every subcategory, cost estimates equal
provider invoices, or Challenge small-N metrics are population estimates.
