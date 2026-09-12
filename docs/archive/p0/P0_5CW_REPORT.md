# P0.5cW — Human-approved Gold v2 and Deterministic Re-score

## Decision

Human review of all 16 P0.5cV candidates is recorded. Gold v1 is preserved;
Gold v2 was created by a deterministic local transformation. No DeepSeek or
other provider call was made, and the frozen prediction artifacts were not
changed or rerun.

P0.5 is now **GO for final review**. P0.6 remains **NO-GO until that final
review explicitly accepts the revised baseline and its limitations**.

## Gold versioning and corrections

- v1: `P0_5B_gold_verified.jsonl`
- v1 SHA-256: `24f34e35936c2d8944908edecc0a5d42eb98a2b4e5efce384195b055131061c3`
- v2: `P0_5B_gold_verified_v2.jsonl`
- v2 SHA-256: `5b7aa442b9f70ec27f3ddee76a11ca0aab6c5cc110022da7e9c3da0f29eab50d`
- records: 150 → 150
- reviewed candidates: 16
- changed records: 15
- unchanged reviewed boundary case: `pv-2868840-233307187`

The exact field-level diff is in [P0_5CW_GOLD_DIFF.json](P0_5CW_GOLD_DIFF.json).
Changed records are:

`pv-1172470-231768442`, `pv-4162040-232740798`,
`pv-4162040-232989490`, `pv-1172470-232155751`,
`pv-4162040-233002020`, `pv-2868840-232792409`,
`pv-2584270-233573481`, `pv-4162040-232942889`,
`pv-2584270-233528988`, `pv-4162040-233306549`,
`pv-2868840-233323994`, `pv-4162040-232967794`,
`pv-1172470-233023949`, `pv-2868840-232996219`,
`pv-1172470-232959876`.

Semantic actions:

- 13 clear praise/aspect records now retain normal `subcategories` but have
  `issue_present=false` and empty `issue_labels`.
- Watcher omission retains a real narrative-character complaint and request;
  issue/request labels were narrowed to `content_design/narrative_characters`.
- The German review's concrete technical labels were removed because the text
  explicitly denies bugs/performance problems and leaves the minor problems
  unspecified; it is not treated as a taxonomy-specific issue.
- The card-accumulation boundary case was retained as a mild issue without
  broadening its labels.

Every changed record carries `correction_reason`, `correction_source`, and
`previous_gold_version`; original source text, source hashes, sampling data,
and annotation provenance are preserved.

## Deterministic re-score

The original frozen Dev/Holdout split membership was reused. New metrics are:

| Split | Group | Issue detection F1 v1 → v2 | Issue-label micro F1 v1 → v2 | Subcategory micro F1 v1 → v2 |
|---|---|---:|---:|---:|
| Dev | All | 0.779 → 0.892 | 0.493 → 0.530 | 0.358 → 0.358 |
| Dev | Core | 0.554 → 0.642 | 0.435 → 0.500 | 0.324 → 0.324 |
| Dev | Challenge | 0.500 → 0.500 | 0.554 → 0.554 | 0.408 → 0.408 |
| Holdout | All | 0.833 → 0.909 | 0.439 → 0.462 | 0.354 → 0.354 |
| Holdout | Core | 0.818 → 0.857 | 0.444 → 0.457 | 0.381 → 0.381 |
| Holdout | Challenge | 0.154 → 0.167 | 0.400 → 0.500 | 0.250 → 0.250 |

Request detection and macro metrics are included in the machine-readable
metric files. Topic/subcategory metrics remain unchanged because only issue
semantics were corrected; issue metrics move because the binary and issue-label
targets were corrected. Sentiment remains explicitly unavailable because the
production first-pass classifier does not emit sentiment.

Artifacts:

- [P0_5CW_BASELINE.json](P0_5CW_BASELINE.json)
- [P0_5CW_dev_metrics.json](P0_5CW_dev_metrics.json)
- [P0_5CW_holdout_metrics.json](P0_5CW_holdout_metrics.json)
- [P0_5CW_dev_error_analysis.json](P0_5CW_dev_error_analysis.json)
- [P0_5CW_holdout_error_analysis.json](P0_5CW_holdout_error_analysis.json)

## Frozen predictions and cost

- Dev prediction SHA-256: `356d25e02201c183076615923a57dbd626b02753bfc28f29dd38be3fa82445f0`
- Holdout prediction SHA-256: `3ea1cc3a608b3e99484e2371672194ca2648bac8dc4ca3656dc1ab9bcf5085f5`
- Provider calls in P0.5cW: **0**
- Prediction rerun: **false**

## Validation

- Gold v2 validator: PASS; 150 records, unique IDs, source hashes and evidence
  spans valid, taxonomy labels valid, issue/request subset contracts valid.
- Canonical repository pytest from root (`pytest.ini`): **101 passed, 1
  xfailed, 0 xpassed**, 10 warnings.
- compileall: PASS.
- import smoke: PASS.
- `git diff --check`: PASS; only Git LF/CRLF normalization warnings.
- Frozen prediction hashes: unchanged.

## Remaining quality limitation

Taxonomy overprediction remains a separate issue and is not hidden by improved
issue F1: Dev subcategory micro precision remains approximately 0.244 and
Holdout approximately 0.237 from the baseline analysis. Sentiment remains
unavailable. These limitations must remain visible in any P0.6 decision.

## Final recommendation for P0.6

**NO-GO pending final P0.5 review.** The human-approved Gold v2 and zero-cost
deterministic rescore are complete. Start P0.6 only after accepting this
versioned baseline, the unchanged taxonomy precision limitation, and the
sentiment-unavailable contract.
