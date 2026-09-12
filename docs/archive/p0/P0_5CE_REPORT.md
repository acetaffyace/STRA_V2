# P0.5cE Real Production Provider Baseline Report

## Decision

The first real production baseline completed with the user-authorized
configuration:

- provider: DeepSeek;
- model: `deepseek-v4-flash`;
- thinking: disabled;
- structured output: JSON Output;
- taxonomy: `sentinext-taxonomy-v1`;
- prompt: `steam_review_insights_v16_basic_labels`.

No prompt, taxonomy, normalization, truncation, or model tuning was performed
between Dev and Holdout. P0.6 was not started.

## Frozen identities

- Gold SHA-256:
  `24f34e35936c2d8944908edecc0a5d42eb98a2b4e5efce384195b055131061c3`;
- Dev split SHA-256:
  `3384ab1d0599c9ea992f3b9201abec3f89497d302b8697207152253f2bbd0000`;
- Holdout split SHA-256:
  `5a4d28b43cb4a82ac50a2612395372c19ff8ddc57000d84ca4adcc1fc77d167b`;
- Dev predictions SHA-256:
  `356d25e02201c183076615923a57dbd626b02753bfc28f29dd38be3fa82445f0`;
- Holdout predictions SHA-256:
  `3ea1cc3a608b3e99484e2371672194ca2648bac8dc4ca3656dc1ab9bcf5085f5`.

The three frozen input hashes were verified before paid calls and remain
unchanged. Gold provenance remains
`human_review_of_model_assisted_labels`; it is not represented as independent
double-human annotation.

## Budget preflight and cost

The 10-record preflight used the exact production configuration, then its
predictions were reused without reclassification. Preflight usage was 1,514
input and 504 output tokens in one request, with zero schema-invalid results.

Actual evaluation usage:

| Split | Records | Requests | Input | Cached input | Output | Est. RMB* |
|---|---:|---:|---:|---:|---:|---:|
| Dev | 112 | 12 | 18,986 | 7,680 | 4,849 | 0.0237 |
| Holdout | 38 | 4 | 5,849 | 3,072 | 1,657 | 0.0069 |
| Total | 150 | 16 | 24,835 | 10,752 | 6,506 | 0.0306 |

\* Estimate uses DeepSeek V4 Flash published rates at execution time and a
transparent 8 RMB/USD conversion assumption. This is evaluation-run cost
only, not the P0.6 production ledger. The run remained far below the RMB 4
execution ceiling and RMB 5 available balance.

## Production output contract limitation

The unchanged current production first-pass classifier emits taxonomy,
`issue_subcategories`, and `request_subcategories`; it does not emit a
sentiment field. Therefore sentiment accuracy/macro-F1 is explicitly
**not evaluable**, rather than reported as zero. The Gold sentiment support is
still recorded, but no sentiment prediction was invented.

The evaluator maps production fields as follows:

- issue detection: `bool(issue_subcategories)`;
- request detection: `bool(request_subcategories)`;
- issue/request multi-label: corresponding production arrays;
- taxonomy multi-label: production `subcategories`;
- evidence: no score unless the production prediction contains evidence.

## Quality results

### Development, N=112

- issue detection: Precision 0.833, Recall 0.732, F1 0.779, positive N=41;
- feature request detection: Precision 0.714, Recall 1.000, F1 0.833,
  positive N=5;
- taxonomy subcategory micro F1: 0.358, support 66;
- taxonomy subcategory macro F1: 0.240;
- issue-label micro F1: 0.493, support 66;
- request-label micro F1: 0.462, support 6;
- Core issue F1: 0.554, N=73, positive N=29;
- Challenge issue F1: 0.500, N=39, positive N=12;
- sentiment: not evaluable under current production contract.

### Frozen Holdout, N=38

Holdout composition is Core 27 and Challenge 11. The small Challenge and
request supports are descriptive only.

- issue detection: Precision 0.909, Recall 0.769, F1 0.833, positive N=13;
- feature request detection: Precision 1.000, Recall 0.500, F1 0.667,
  positive N=2;
- taxonomy subcategory micro F1: 0.354, support 20;
- taxonomy subcategory macro F1: 0.304;
- issue-label micro F1: 0.439, support 20;
- request-label micro F1: 0.000, support 2;
- Core issue F1: 0.818, N=27, positive N=11;
- Challenge issue F1: 0.154, N=11, positive N=2;
- sentiment: not evaluable under current production contract.

Observed Holdout minus Dev issue F1 is +0.054 overall; Core is +0.264 and
Challenge is -0.346. This is an observed split difference, not a causal claim.

## Taxonomy gaps and slices

The four user-confirmed taxonomy-gap records were not forced into invented
subcategories. They remain eligible for higher-level presence metrics and are
excluded from nonexistent Gold subcategory scoring. The split-specific gap
count is 2 in Dev and 2 in Holdout.

Language slices are included in the machine-readable metric files with support.
Slices with N=1–2 are unstable/descriptive only; even N=4–5 should not be
treated as population estimates. Simplified Chinese and English have the
largest supports, while rare language slices are not decision-grade.

## Structured error analysis

Bounded examples are in:

- `P0_5C_dev_error_analysis.json`;
- `P0_5C_holdout_error_analysis.json`.

The baseline shows:

- issue false positives and false negatives in both splits;
- request false positives in Dev and one request false negative in Holdout;
- multi-label omissions and category-family boundary mismatches;
- materially more Challenge failures than Core failures in Holdout;
- one long/truncation candidate in Dev;
- explicit taxonomy-gap examples;
- sentiment error analysis unavailable because the production contract emits no
  sentiment prediction.

No classifier changes were made after observing these errors.

## Business-critical interpretation

Technical issue and feature-request performance should be read through the
reported support counts. The current first-pass classifier has useful issue
presence signal on this sample, but taxonomy precision is much weaker than
presence precision. Request Holdout support is only N=2, and request-label
micro F1 is descriptive, not a stable release metric. Sentiment macro F1 is a
missing-contract metric, not a failed score.

Candidate future regression gates should be proposed only after reviewing this
baseline and adding coverage for the missing sentiment contract. Do not use
arbitrary round thresholds or treat rare-label results as stable targets.

## Artifacts and validation

- `P0_5C_BASELINE.json` completed machine-readable baseline;
- `predictions/P0_5C_dev_deepseek_v4_flash.jsonl`;
- `predictions/P0_5C_holdout_deepseek_v4_flash.jsonl`;
- `P0_5C_dev_metrics.json` and `P0_5C_holdout_metrics.json`;
- bounded Dev/Holdout error-analysis JSON files.

Passed:

- Gold and frozen-hash verification;
- prediction uniqueness: Dev 112/112, Holdout 38/38;
- schema-invalid rate: 0 for both splits;
- evaluator tests: 6 passed;
- baseline completed artifact generation;
- full pytest: passed with the existing intentional P0.6 xfail;
- compileall/import smoke;
- `git diff --check` with only existing LF/CRLF normalization warnings.

## Final recommendation for P0.6

**NO-GO for P0.6 pending human review of this completed baseline.** The real
provider baseline is now recorded, but the production classifier's missing
sentiment output and weak/low-support taxonomy slices should be reviewed before
cost-ledger work begins.
