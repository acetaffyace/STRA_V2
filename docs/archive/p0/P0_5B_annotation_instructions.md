# P0.5b Human Annotation Instructions

This file is a blank annotation workflow for real review records. It must be
used together with `tooling/evals/player_voice/annotation_guidelines.md`.
Annotators must not see model predictions, prior labels, confidence values, or
benchmark reference labels.

For each review, independently record:

- sentiment: positive, negative, mixed, neutral, or uncertain;
- whether an issue is present, then all applicable issue category/subcategory
  labels;
- whether a feature request is explicit, then all applicable request
  category/subcategory labels;
- exact evidence spans copied from the source review when a claim requires
  evidence;
- ambiguity, `needs_adjudication`, or `exclude` when the guideline does not
  support a confident decision.

Do not infer a request merely from dissatisfaction. Do not force a category at
a taxonomy boundary. Preserve the exact source text and source hash. Complete
the calibration subset independently before comparing decisions. Disagreements
must be recorded for later human adjudication; annotators must not resolve them
by looking at model output.

The prepared package contains only real reviews from the configured local
database. Do not replace or supplement it with synthetic, benchmark, or
model-generated text.
