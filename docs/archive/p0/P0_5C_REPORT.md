# P0.5c Baseline Evaluation Report

## Decision

P0.5c reproducibility preparation is complete. The real production baseline is
**NO-GO pending provider execution** because no LLM provider or API key is
configured in the current environment. No fixture predictions were used, no
classification score was manufactured, and P0.6 was not started.

## Gold freeze

Input: `P0_5B_gold_verified.jsonl`

- records: 150;
- SHA-256: `24f34e35936c2d8944908edecc0a5d42eb98a2b4e5efce384195b055131061c3`;
- taxonomy: `sentinext-taxonomy-v1`;
- guideline: `p0.5a-guidelines-v1`;
- provenance: `human_review_of_model_assisted_labels`;
- verified by: `project_owner`;
- independent double-human annotation: false;
- taxonomy-gap records: 4.

Gold labels were not modified during P0.5c. The user-verified provenance and
the original model-assisted source metadata remain auditable in each record.

## Frozen split

Split command:

```powershell
python tooling/evals/player_voice/split_dataset.py `
  --input P0_5B_gold_verified.jsonl `
  --dev-output P0_5C_dev.jsonl `
  --holdout-output P0_5C_holdout.jsonl `
  --holdout-fraction 0.25 `
  --salt p0.5c-gold-v1
```

- Dev: 112;
- Holdout: 38;
- Holdout ratio: 25.33%;
- Dev SHA-256: `3384ab1d0599c9ea992f3b9201abec3f89497d302b8697207152253f2bbd0000`;
- Holdout SHA-256: `5a4d28b43cb4a82ac50a2612395372c19ff8ddc57000d84ca4adcc1fc77d167b`;
- salt: `p0.5c-gold-v1`.

The split is deterministic and stratifies by Core/Challenge, language, and
major taxonomy family where available. Holdout membership is now frozen.

## Classifier identity and provider status

The current production identity is available from the existing path:

- taxonomy: `sentinext-taxonomy-v1`;
- prompt: `steam_review_insights_v16_basic_labels`;
- normalization/classifier path: `llm.classify_reviews_batch` and production
  normalization;
- classification-input identity: production `classification_identity` logic;
- provider/model: not available in this environment;
- preprocessing/truncation: not executed;
- evaluation timestamp: recorded in `P0_5C_BASELINE.json`.

Provider audit returned no active provider and no configured DeepSeek, xAI,
Gemini, or OpenAI key. Therefore `run_predictions.py` was not run and no
prediction artifact exists. This avoids paid/unavailable calls and preserves
the baseline's validity.

## Metrics and error analysis

Dev/Holdout classification metrics are pending provider execution. There are
no valid accuracy, F1, confusion, issue/request, multi-label, evidence,
language-slice, operational, or Core-versus-Challenge degradation numbers to
report yet.

The evaluator was updated and is ready to report:

- sentiment accuracy, macro F1, confusion and per-class support;
- binary issue and feature-request precision/recall/F1;
- multi-label micro/macro and per-label metrics;
- evidence quote exactness and evidence support where annotated;
- Core, Challenge, language, and overall groups with support;
- operational validity, fallback, retry, latency, and token totals.

Taxonomy-gap handling is explicit: the four user-confirmed gap records remain
eligible for higher-level `issue_present`/`request_present` detection, but are
excluded from subcategory scoring so a model is not penalized for failing to
predict a nonexistent production label. The gap count is reported separately.

No error sample report was invented without predictions. After provider
execution, the first baseline should classify false positives/negatives,
sentiment confusion, boundary errors, omissions, Challenge failures,
long-input failures, and taxonomy-gap behavior before any model change.

## Reproducibility artifacts

- `P0_5C_BASELINE.json`: machine-readable readiness baseline, schema-compatible;
- `P0_5C_SPLIT_MANIFEST.json`: dataset/split hashes, counts, composition and
  taxonomy-gap count;
- `P0_5C_dev.jsonl`;
- `P0_5C_holdout.jsonl`;
- `P0_5B_gold_verified.jsonl` (frozen Gold input).

`P0_5C_BASELINE.json` uses status `NO-GO_NO_PROVIDER` and the explicit marker
`prediction_hash=not-generated:no-provider`; it does not claim a score.

## Verification

Passed:

- Gold validation: PASS;
- Dev validation: PASS;
- Holdout validation: PASS;
- split determinism: PASS;
- baseline required-schema check: PASS;
- evaluator tests: 6 passed;
- full pytest suite: passed with the existing intentional P0.6 xfail;
- compileall: PASS;
- import smoke: PASS.

## Future regression gates

No thresholds are proposed before observing the first real baseline. After
provider execution, propose gates from observed baseline/support, especially
technical-issue precision/recall, feature-request recall, major issue-family
recall, sentiment macro F1, and Core-versus-Challenge degradation. Tiny
language slices must remain descriptive only.

## Final recommendation for P0.6

**NO-GO for P0.6 until the explicit production-provider baseline run is
completed and reviewed.** P0.6 cost-ledger work must not begin automatically.
