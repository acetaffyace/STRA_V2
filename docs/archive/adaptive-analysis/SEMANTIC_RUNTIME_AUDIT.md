# Semantic Runtime Audit

Target runtime: Web `POST /analyze` → `_run_analysis_job` → `llm.ensure_review_labels` → `classify_reviews_batch` → active provider → `review_labels`.

Supported modes found in the repository:

| Mode | Arbitrary fresh game | Status |
|---|---:|---|
| `live_provider` | Yes, when provider/model/runtime prerequisites pass | Real runtime path |
| `local_provider` / Ollama | Potentially, when a reachable local endpoint and model exist | Adapter exists; endpoint/model must be smoke-tested |
| `cached_labels` | No | Reuses identity-compatible labels only |
| `codex_offline_fixture` | No | Deterministic development fixture, not a general semantic engine |

Findings:

- DeepSeek live models accepted for new calls are `deepseek-v4-flash` and `deepseek-v4-pro`; legacy `deepseek-chat` is rejected.
- DeepSeek thinking was defaulting to `enabled`; the transport diagnostic showed it could consume a 32-token structured completion and return empty content with `finish_reason=length`. Semantic structured calls now default to `thinking=disabled`; the setting remains explicitly overridable.
- Batch provider failures are classified as systemic and are converted to bounded fallback labels without per-review fan-out. Non-systemic batch shape failures can still single-review retry and therefore require staged observation.
- The second-pass aspect enrichment can issue additional single-review calls; staged runs must account for this separately.
- Cost ledger records physical calls, attempts, usage and pricing snapshots. Live providers without a pricing snapshot are now rejected before workload creation.
- A live current-snapshot `AnalysisDesign` is now persisted after ingestion and before semantic classification.

Release interpretation: only `live_provider` or a verified local provider can satisfy fresh-game semantic runtime. Offline fixture success cannot.
