# Semantic Runtime Staged Test Report

Target: STEINS;GATE RE:BOOT (`4012810`). Provider: `deepseek:deepseek-v4-flash`. Thinking: disabled for structured semantic output. Enrichment was disabled during staged classification to avoid extra calls.

| Stage | Validated | Coverage | Batch calls | Failed | Retries | Fallback | Result |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1/1 | 100% | 1 | 0 | 0 | 0 | PASS after transport fix |
| 10 | 10/10 | 100% | 2 | 0 | 0 | 0 | PASS |
| 50 | 50/50 | 100% | 10 | 0 | 0 | 0 | PASS |
| 100 | 100/100 | 100% | 19 | 0 | 0 | 0 | PASS |

Initial Stage 1 failed because DeepSeek thinking consumed the structured completion budget and returned empty content with `finish_reason=length`. After defaulting structured calls to `thinking=disabled`, Stage 1 passed with a validated taxonomy label and input hash.

Token/cost deltas were recorded in `llm_calls`; no API key was persisted by the smoke scripts. No uncontrolled retry fan-out occurred in the passing stages.
