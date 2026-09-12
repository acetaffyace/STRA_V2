# P0.5b Human Annotation Preparation Report

## Decision

P0.5b preparation is complete and **GO for human annotation**. The runtime
database was identified through `DATABASE_URL` and a blind candidate package
was generated from real reviews. No synthetic, benchmark, reference,
model-labeled, or inferred review was inserted.

P0.5c was not started. No gold labels, predictions, adjudication, or
Dev/Holdout split were created.

## Review source audit

The initial default platformdirs database was empty. The configured runtime
source is:

`D:\reviews\SentiNext\source\data\sentinext.db`

It passed SQLite integrity check. Its `reviews` table contains canonical
fields `app_id`, `review_id`, `data`, `timestamp_created`, and
`timestamp_updated`:

- total reviews: 11,669;
- app IDs: 1,172,470 (7,669), 2,868,840 (2,000), 4,162,040 (1,000),
  2,584,270 (1,000);
- recommendation distribution: positive 8,144; negative 3,525;
- languages: English 4,862; Simplified Chinese 3,336; Russian 1,082;
  Spanish 345; Traditional Chinese 331; remaining languages 1,713;
- review length: minimum 0 characters, median 20, maximum 8,000;
- weak raw-text candidate signals: issue terms 475; request terms 528.

Signal counts are selection diagnostics only. They are not labels and are not
included as model predictions in annotator-facing files.

Repository inspection found no other legitimate local review export. The
existing `tooling/benchmarks` datasets were excluded because their synthetic
and reference data are not human Golden Set source material.

## Candidate and calibration packages

The generated target is 150 records: 100 Core and 50 Challenge. The
calibration subset contains 30 records: 15 Core and 15 Challenge. Sampled
languages are Simplified Chinese 57, English 50, Russian 14, French 5,
German/Latin-American Spanish 4 each, and 16 records in remaining languages.

Generated files contain no labels or model answers:

- `P0_5B_annotation_batch.jsonl`;
- `P0_5B_calibration_batch.jsonl`.

Supporting workflow files:

- `P0_5B_annotation_instructions.md`;
- `P0_5B_annotation_checklist.md`;
- `P0_5B_START_ANNOTATION.ps1`: one-command local launcher;
- `tooling/evals/player_voice/annotation_guidelines.md`;
- `tooling/evals/player_voice/golden_set.schema.json`.

The source pool is `P0_5B_source_pool.jsonl`: 11,669 records with minimum
non-identifying review/classification context. It does not contain `author`,
hardware, review labels, or model predictions. All 150 candidate records have
`gold: null`, `annotation_status: pending`, and empty annotation fields.

## Blindness and validation

Blindness inspection passed: annotator-facing files contain no model answers
or prior labels. Both candidate files passed `validate_annotations.py`,
including duplicate-ID, source-hash, pending-status, taxonomy-version, and
source/evidence validation. No final split was run.

## Manual procedure

1. Independently annotate the 30-record calibration subset twice without
   exposing prior/model output.
2. Review disagreements against the guideline; only a human may adjudicate or
   revise/freeze the guideline.
3. Annotate the remaining 120 records.
4. Run `validate_annotations.py` after labels are complete.
5. Only after annotation, disagreement review, adjudication, and guideline
   freeze, run `split_dataset.py` to create Dev/Holdout.

## How to start

From the repository root, run:

```powershell
.\P0_5B_START_ANNOTATION.ps1
```

Then open `http://127.0.0.1:8765/`. The UI saves human work to
`P0_5B_annotation_batch.annotated.jsonl` and does not overwrite the original
pending package. Stop the server with `Ctrl+C`.

## Final recommendation

**GO for human P0.5b annotation.** The package is ready for manual work;
P0.5c remains explicitly out of scope.
