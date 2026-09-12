# P0.5a Player Voice Evaluation Scaffold

This directory is the evaluation-engineering scaffold only. P0.5a does not
create human labels, does not claim a Golden Set, and does not start P0.5b or
P0.5c. The records under `fixtures/` are deterministic scorer tests, not
evaluation evidence or ground truth.

## Workflow

1. Export legitimate review records to JSONL, retaining `app_id`, `review_id`,
   source text, language, and source metadata.
2. Select pending Core and Challenge candidates:

   ```powershell
   py tooling/evals/player_voice/select_samples.py --input reviews.jsonl --output candidates.jsonl --core 200 --challenge 50
   ```

3. Human annotators work from `annotation_guidelines.md`. They preserve the
   source/provenance fields and complete `gold` only during the later human
   annotation gate.
4. Validate annotations:

   ```powershell
   py tooling/evals/player_voice/validate_annotations.py annotations.jsonl
   ```

5. Only after labeled records exist, create deterministic Dev/Holdout files:

   ```powershell
   py tooling/evals/player_voice/split_dataset.py --input annotations.jsonl --dev-output dev.jsonl --holdout-output holdout.jsonl
   ```

6. Run production-faithful predictions explicitly. `run_predictions.py` calls
   the production classifier and writes an isolated prediction artifact; it
   does not call the cache-writing `ensure_review_labels()` path.
7. Evaluate Core, Challenge, and language slices with support counts:

   ```powershell
   py tooling/evals/player_voice/evaluate.py --gold dev.jsonl --predictions predictions.jsonl --output metrics.json
   ```

The final split and thresholds are intentionally deferred. No paid provider
is used by normal unit tests; prediction runs require the repository's normal
provider configuration and credentials.
