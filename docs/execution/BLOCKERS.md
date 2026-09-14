# Blockers

## M2-BENCH-001 — human review and finalization of the V2 Boundary Suite and independent Evaluation Holdout

- Exact problem: human review and finalization of the V2 Boundary Suite and
  independent Evaluation Holdout remain outstanding. The Master Spec requires
  a 200–500 example Boundary
  Regression Suite and a separate 300–600 example labeled Evaluation Holdout;
  the holdout must have meaningful EN/ZH/JA representation (target at least
  50 per primary language when available). No such V2 assets are present.
- Evidence: `tooling/benchmarks/datasets/bench_v2/manifest.json` declares 60
  English reviews and `reference_labels: 0`; the existing 3000-review
  `bench_v1` manifest is tied to a prior benchmark contract/taxonomy and is
  not a Semantic V2 labeled asset. Running
  `tooling/evals/semantic_v2/validate_assets.py` on the checked-in example
  manifest reports missing boundary/holdout files and zero language support.
- Attempted approaches: inspected all repository benchmark/eval manifests;
  added the fail-closed V2 manifest validator and support-aware evaluator;
  verified that old/unlabeled fixtures are rejected rather than relabeled.
- Affected milestone/item: M2 benchmark assets and §12.3 product-ready gates.
- Consequence of guessing: fabricating or remapping labels would invalidate
  macro F1, boundary precision, unresolved rate, discovery recall and
  multilingual gates, and would violate the reproducibility requirement.
- Precise missing input: complete human review and finalization of the V2
  Boundary Suite and independent Evaluation Holdout, with their labeling
  guideline/version metadata. After that, run the validator and measured
  evaluation report.
- Status: OPEN; implementation of other unblocked M2 contracts continues.
