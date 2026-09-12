# P0.5b Gold Import Report

The supplied `P0_5B_gold_only.jsonl` was checked against the 150-record
candidate batch. All `sample_id`, `app_id`, language, and exact review text
values matched; no record was mismatched or missing.

Per the user's explicit instruction, the supplied annotations are promoted as
user-verified Gold into `P0_5B_gold_verified.jsonl`. The source file remains
unchanged. Each record is marked `annotation_status=labeled`,
`annotator_id=user-verified`, and `adjudication_status=adjudicated`.

The original source metadata is retained for auditability:

- reviewer type: `model_adjudication`;
- reviewer model: `GPT-5.6 Sol`;
- confidence: high 112, medium 35, low 3;
- `taxonomy_gap=true`: 4 records.

The four taxonomy-gap records are accepted without invented subcategories.
The validator explicitly allows a user-confirmed taxonomy gap to preserve
`issue_present` or `request_present` without a production subcategory.

Validation:

- 150 records;
- `validate_annotations.py`: PASS;
- evaluation-tool tests: 6 passed;
- no production review-label cache was modified;
- P0.5c evaluation and Dev/Holdout split were not started.
