# Dynamic Batch Planner V2

## Scope

V2 changes only how preprocessed representative reviews are packed and how batch responses are recovered. Prompts, taxonomy, model selection, historical cache, near-duplicate logic, and semantic filtering are unchanged.

## Architecture

```text
ReviewPreprocessor
  -> same-app representatives
  -> DynamicBatchPlanner (optional)
  -> provider batch call
  -> per-review validation
  -> targeted retry / structural split
  -> existing duplicate fan-out
  -> existing review_labels persistence
```

## Defaults

`SENTINEXT_DYNAMIC_BATCH_ENABLED=false`; therefore the existing batch slicing remains the default.

| Setting | Default |
|---|---:|
| SHORT max chars | 80 |
| MEDIUM max chars | 300 |
| LONG max chars | 1200 |
| SHORT / MEDIUM / LONG / VERY_LONG max reviews | 100 / 80 / 40 / 15 |
| max total processed chars | 32,000 |
| max retry attempts | 2 |
| minimum split size | 2 |

All values can be overridden through the `SENTINEXT_BATCH_*` variables defined in `batch_planner.py`.

## Response recovery

`validate_batch_results()` distinguishes valid, invalid, missing, duplicate-return, and unexpected IDs. With dynamic mode enabled, valid results are persisted immediately; only failed IDs are retried. Whole response/provider failures are handled separately: structural failures may halve-split up to the retry ceiling, while provider errors are never split.

## Real-data dry-run

The read-only script `tools/validate_dynamic_batch_planner.py` uses active-like preprocessing and does not call an LLM. Results by app:

| App | Representatives | Planned batches | SHORT / MEDIUM / LONG / VERY_LONG batches | Max chars | Old fixed estimate |
|---:|---:|---:|---:|---:|---:|
| 1172470 | 6,069 | 73 | 48 / 13 / 7 / 5 | 31,654 | 66 |
| 2584270 | 977 | 24 | 5 / 4 / 6 / 9 | 31,442 | 18 |
| 2868840 | 1,815 | 24 | 13 / 5 / 4 / 2 | 25,181 | 21 |
| 4162040 | 952 | 16 | 7 / 3 / 3 / 3 | 30,328 | 12 |

Lane isolation increases the theoretical request count in this initial configuration; real provider success/latency telemetry should guide later tuning.

## Verification

The repository test suite passes with `.venv311` using `pytest -q --basetemp .pytest-tmp`. New planner, validation, preprocessor integration, and existing regression tests all pass. Existing deprecation warnings are unrelated to V2.

## Not implemented

Persistent duplicate cache, near-duplicate reuse, complexity scoring, prompt/taxonomy/model optimization, semantic short-text filtering, meme detection, and new LLM call types remain out of scope.
