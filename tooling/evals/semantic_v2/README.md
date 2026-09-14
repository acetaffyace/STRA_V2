# Semantic Engine V2 human-in-the-loop benchmark preparation

This directory contains preparation contracts and fail-closed validation
only. It does not create, infer, or promote human labels. The final assets
must be produced by a human annotation workflow and remain two separate
datasets:

- Boundary Regression Suite: 200–500 difficult/confusing examples for
  repeated development regression. Each record carries `boundary_metadata`
  with a category, confusion topics and policy edge cases.
- Evaluation Holdout: 300–600 independently sampled and human-labeled
  examples. Its manifest requires `evaluation_only: true` and
  `allowed_for_calibration_training: false`; it must not tune prototypes,
  thresholds, calibration, assignment policy or adjudication behavior.

Both assets bind exactly to `stra-core-taxonomy-v2`. Records preserve source
system/app/review identity, immutable UTF-8 source-content hash, language,
human annotator provenance, first-pass labels, final labels, disagreement or
adjudication state, explicit `resolved`/`unresolved`/`semantically_invalid`
status, Core Topic IDs, optional Game/Archetype secondary IDs, and canonical
`issue`/`request`/`praise` signals. Resolved labels use one Core Topic per
`semantic_mentions` entry; unresolved records must not contain a catch-all
topic and must include `unresolved_reason`.

## Human annotation workflow

1. Start from immutable real-review input and export candidates. The exporter
   writes `UNLABELED` records with no `gold`, first-pass label, or final label:

   ```powershell
   py tooling/evals/semantic_v2/export_candidates.py `
     --input reviews.jsonl `
     --output boundary_candidates.jsonl `
     --manifest boundary_candidates.manifest.json `
     --asset-type boundary_regression --seed boundary-v1 --count 250
   ```

   Run a separate export for the holdout. Use an independently sampled source
   collection and do not feed holdout candidates into calibration or training.

2. Human annotators fill `annotation_provenance.first_pass` and `gold` using
   the V2 guidelines. A second human may fill the final label and reviewer
   fields when there is disagreement. Models may assist with triage only; a
   model-generated label is not gold and is rejected by the validator.

3. Preserve the exact source text and recompute its SHA-256 after annotation.
   Resolve each mention to an exact source substring. Mark ambiguous or
   semantically invalid cases explicitly rather than inventing a Core Topic.

4. Create a final manifest containing real dataset identity, source-collection
   hash, guideline/protocol version, evaluation commit, asset SHA-256 and
   sample bounds. Use the separate examples as templates:
   `boundary_manifest.example.json` and `holdout_manifest.example.json`.

5. Validate each manifest and then validate both together to catch duplicate
   sample IDs or immutable source-content hashes:

   ```powershell
   py tooling/evals/semantic_v2/validate_assets.py `
     boundary.manifest.json holdout.manifest.json
   ```

   Validation is intentionally fail-closed. Missing assets, old taxonomy,
   wrong provenance, malformed signals, source-hash drift, cross-split overlap,
   insufficient sample bounds, or holdout calibration use are errors.

Record schemas are in `schemas/boundary_record.schema.json` and
`schemas/holdout_record.schema.json`. The checked-in `bench_v2` fixture remains
an unlabeled smoke dataset and is not a §12 release asset.

