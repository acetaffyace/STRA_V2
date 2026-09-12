# P0.5a Evaluation Engineering Scaffold Report

## Decision

P0.5a is complete. Recommendation: **GO for the human P0.5b annotation
gate**, subject to human review of the guidelines/schema and a legitimate
review export. P0.5b and P0.5c were not started.

No human labels were created. The two records under
`tooling/evals/player_voice/fixtures/` are deterministic unit-test fixtures
only; they are explicitly not Golden Set ground truth.

## Audit findings

The existing `tooling/benchmarks/` suite is a generic provider/LLM benchmark.
Its provider adapters, request plumbing, configuration, timing and cost
patterns are reusable references. Its synthetic/reference/rendered datasets
and reference labels are not human player-voice gold and were not used as
evaluation truth. See [P0_5A_EVAL_AUDIT.md](P0_5A_EVAL_AUDIT.md).

The production semantic path is `apps/api/senti_next/llm.py`: production
taxonomy/normalization plus `classify_reviews_batch`. The scaffold reuses that
path for explicit predictions, while deliberately avoiding the
cache-writing `ensure_review_labels` path. Prediction artifacts retain
taxonomy, prompt, provider/model, classification-input hash, schema-invalid,
fallback, retry, latency and token fields where available.

## Delivered scaffold

- `golden_set.schema.json`: source/provenance-preserving schema with Core and
  Challenge strata, annotation uncertainty, multi-annotator and adjudication
  fields, and `sentinext-taxonomy-v1`.
- `annotation_guidelines.md`: sentiment, issue/request, multi-label,
  evidence-span, ambiguity and taxonomy-boundary guidance.
- `annotation_template.jsonl`: pending, unlabeled template.
- `select_samples.py`: deterministic selection from an existing real JSONL
  export; raw-text Challenge signals are candidate reasons only, not labels.
- `validate_annotations.py`: identity/hash/taxonomy/status/label/evidence
  validation.
- `split_dataset.py`: deterministic language/stratum-aware Dev/Holdout split,
  refusing pending/unlabeled records and enforcing a 20–30% requested range.
- `run_predictions.py`: production-faithful, cache-isolated batch prediction
  runner; normal tests never call a paid provider.
- `evaluate.py`: sentiment, multi-label, evidence quote exactness/evidence
  support, confusion, operational metrics, and Core/Challenge/language slices
  with support counts. No pass thresholds are defined.
- `baseline.schema.json` and fixture documentation for later baseline
  recording.

## Verification

Passed:

- `pytest tooling/evals/player_voice/tests -q`: 6 passed.
- `pytest -q`: full backend/repository suite passed; one pre-existing,
  intentional future-P0 xfail remains (P0.6 threshold gate).
- annotation fixture validation: `{"valid": true}`.
- fixture evaluator CLI: labeled support 2; all/Core/Challenge/language
  groups emitted.
- `python -m compileall -q apps/api/senti_next tooling/evals/player_voice`.
- import smoke for production API and all P0.5a evaluation modules.
- `git diff --check`: no whitespace errors; only existing Git LF/CRLF
  normalization warnings were reported.

The full run emitted existing Pydantic deprecation warnings in the analysis
route tests; no new failure or regression was observed.

Frontend files and frontend dependencies were not touched or tested because
P0.5a is backend/evaluation tooling scope.

## Known limits and next gate

The scaffold has not selected a production sample population, performed human
annotation, adjudicated disagreements, frozen a final Dev/Holdout split, or
set quality thresholds. Those are deliberate P0.5b decisions. The next
authorized step is therefore the human annotation gate only; do not start
P0.5c automatically.
