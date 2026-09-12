# Player Voice Golden Set Annotation Guidelines

Version: `p0.5a-guidelines-v1`  
Production taxonomy: `sentinext-taxonomy-v1`

This document defines the annotation contract scaffold. P0.5a does not label any review. Human annotators must work from `source_review_text` and relevant raw Steam context, never from existing model labels.

## Annotation status and disagreement

Use `pending` before annotation, `labeled` when the annotator is confident, `ambiguous` when the text cannot support a stable label, `needs_adjudication` when annotators disagree, and `exclude` only when the source is unusable or outside scope. Ambiguous/excluded records are not ordinary negatives.

For calibration, preserve two independent `annotations` entries, each with an `annotator_id`; record the final decision in `gold` only after adjudication. `adjudication_status` records whether agreement or adjudication occurred.

## General rules

- Label what the player wrote, not what an analyst infers.
- Multi-label freely when distinct aspects are present; do not force one “main” topic to erase another.
- A positive and negative statement in one review is `mixed` sentiment when both materially matter.
- General dislike is not automatically an issue.
- A feature request requires an explicit desired change, request, wish, or actionable “should/add/fix” construction. A complaint alone is not an inferred request.
- Evidence spans must be verbatim substrings of `source_review_text`.

## Taxonomy boundaries

The validator imports the current production taxonomy directly from `apps/api/senti_next/llm.py`; no parallel taxonomy is defined here. For every chosen subcategory, annotators should record the narrowest production label supported by the text.

- Gameplay vs Content/Design: gameplay is interaction, controls, mechanics, difficulty, AI, or moment-to-moment play; content/design is levels, quests, modes, variety, writing, or authored material.
- Technical vs UI/UX: technical covers crashes, bugs, performance, networking, compatibility, installation, saves; UI/UX covers readability, navigation, controls-as-interface, accessibility, and quality-of-life presentation.
- Technical vs Platform: platform-specific behavior belongs to technical/compatibility when the complaint is compatibility or execution; do not use platform as a generic category for any player device mention.
- Onboarding vs UI/UX: onboarding is first-use/tutorial/accessibility-to-entry friction; UI/UX is ongoing interface or interaction quality.
- Praise plus issue: assign both the supported positive topic and issue topic; do not let praise cancel an explicit defect.
- Sarcasm: annotate the intended player stance only when the wording provides sufficient evidence; otherwise use `uncertain`/`ambiguous` rather than inventing certainty.
- Short, multilingual, and code-switching reviews: annotate only what the source actually supports; use `needs_adjudication` when translation/context is insufficient.

## Gold fields

`sentiment` is one of `positive`, `negative`, `mixed`, `neutral`, or `uncertain`. `subcategories`, `issue_labels`, and `request_labels` are production taxonomy keys. `issue_present` and `request_present` must agree with their corresponding label arrays when not null. `evidence_spans` are optional until the task requires them, but every supplied span must be exact source text.

Core and Challenge scores are reported separately. Challenge oversampling is not evidence of production traffic prevalence and must not be merged into an unweighted overall claim.
