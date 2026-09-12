# P0.5cV Gold / Production Issue-Semantics Audit

## Decision

P0.5cE provider execution remains valid: DeepSeek predictions are frozen and
were not rerun. P0.5c quality interpretation is **not closed** because the
current Gold issue semantics contain 16 positive-sentiment records with
`issue_present=true`. P0.6 remains **NO-GO**.

No Gold labels, split files, prediction artifacts, or production code were
mutated in this audit.

## Production contract

The current first-pass production prompt in
`apps/api/senti_next/llm.py` explicitly defines:

- `subcategories`: all relevant taxonomy aspects, 1–6 labels;
- `issue_subcategories`: only problems/complaints, and a subset of
  `subcategories`;
- `request_subcategories`: only explicit requests, and a subset of
  `subcategories`.

The structured schema repeats the same subset definitions. Production
`normalize_taxonomy_payload` preserves the three separate arrays. Therefore
production semantics are model A:

`aspect/subcategory mention != problem/issue mention`.

`metric_provenance.py` calculates `technical_issue_rate` and category issue
rates from the presence of non-empty `llm_issue_subcategories`; insights and
Dashboard copy call these “issue-tagged reviews”, “issues”, “complaints”, and
“technical issue rate”. This makes issue metrics problem-oriented, not generic
topic-mention rates.

The production prompt is not the primary defect: it already states the needed
distinction. The current Gold/evaluator alignment is the defect under review.

## Gold audit

Against `P0_5B_gold_verified.jsonl`:

- Gold records: 150;
- `issue_present=true`: 54;
- positive-sentiment issue candidates: 16;
- taxonomy-gap records: 4.

The complete candidate list is in
`P0_5CV_ISSUE_SEMANTIC_AUDIT.json`. Each candidate preserves sample ID,
source review, current Gold labels/evidence, reason, recommended
interpretation, and `requires_human_review=true`.

Representative candidates include:

- “running ranked till a +400 game = goated gameloop” →
  `gameplay/mechanics`;
- “so much fun prices are so low” → `monetization_value/pricing`;
- “best deck builder out there ... still discovering combos and synergies” →
  `gameplay/mechanics`;
- “神的审美” → `presentation/visuals_art_style`.

These may be aspect mentions or praise rather than player problems. They must
not be silently changed because the supplied Gold was explicitly user-verified.

## Required conceptual model

The intended aligned model should be:

- “The visuals are beautiful.” → aspect `presentation/visuals_art_style`,
  issue false;
- “The visuals are blurry and broken.” → same aspect, issue true;
- “The gameplay is excellent.” → aspect `gameplay/mechanics`, issue false;
- “Combat controls constantly fail.” → issue true with
  `gameplay/controls`.

The current Gold schema has fields for `subcategories` and `issue_labels`, but
the audit shows they were sometimes treated as equivalent. The evaluator's
mapping of production `issue_subcategories` to Gold `issue_present` is
mechanically correct only if Gold follows this problem-oriented definition.

## Baseline interpretation impact

The frozen taxonomy overprediction pattern remains valid and independent of
the binary issue semantic concern:

- Dev subcategory micro precision 0.244, recall 0.667, F1 0.358;
- Holdout subcategory micro precision 0.237, recall 0.700, F1 0.354.

This consistently indicates broad topic detection with substantial
overprediction. The reported issue F1 values (Dev 0.779, Holdout 0.833) must
not currently be presented as reliable player-problem detection quality until
the 16 candidates and related Gold semantics are resolved.

Holdout Challenge issue F1 0.154 is a warning signal only: Challenge has N=11
and only 2 positive issue records. It is not a stable population estimate.

## Sentiment contract

The unchanged production first-pass schema intentionally excludes sentiment;
it outputs taxonomy, issue subcategories, request subcategories, and no
sentiment score. Product recommendation/negative-review signals remain based
on Steam `voted_up` and deterministic metrics in the existing product path.
No sentiment field was added and no sentiment score was fabricated in this
audit.

## Re-score and Gold revision decision

Deterministic re-score without Gold mutation is **not sufficient**: the issue
binary task itself is semantically ambiguous. The existing prediction files
remain frozen historical `p0.5c-gold-verified-v1` artifacts. No new metrics are
promoted as the final quality conclusion.

Required next step is explicit human review of the 16 candidates and any
related records. If approved corrections are made, create
`p0.5c-gold-verified-v2` with a new dataset hash, correction provenance, and
old-to-new diff; then re-score the same frozen predictions deterministically.

## Tests and artifacts

- `P0_5CV_ISSUE_SEMANTIC_AUDIT.json` generated with 16 candidates;
- Gold validator: PASS;
- frozen prediction hashes were preserved;
- no live provider calls;
- no Gold mutation;
- P0.5cV audit tests plus backend suite: **65 passed, 1 existing xfail**;
  no new regressions;
- `compileall`: PASS;
- import smoke: PASS;
- Gold validator: PASS (`{"valid": true}`);
- `git diff --check`: PASS (only Git LF/CRLF normalization warnings);
- frozen Gold, split, and Dev/Holdout prediction SHA-256 hashes: unchanged.

## Final recommendation for P0.6

**NO-GO.** Resolve and explicitly approve the Gold issue-semantics audit,
then create a new Gold version and deterministic re-score before starting the
production cost ledger.
