# Stage 3E — Taxonomy-aware classifier contract

Stage 3E makes the classifier consume an explicit immutable taxonomy
snapshot.  The default remains the frozen `sentinext-taxonomy-v1` baseline;
the classifier never follows the active governance snapshot implicitly.

`ClassifierTaxonomyContract` records the snapshot id, taxonomy version,
content fingerprint, complete topic keys, active output keys, and topic count.
Promoted/deprecated topics are therefore auditable, and new output is limited
to active canonical keys.  The prompt and JSON schema are rendered from the
same contract.  Canonical keys may contain deeper paths; their full path is
the identity while the first segment remains the compatibility main category.

The v1 prompt/schema path is byte/structure compatible with the frozen
classifier.  Explicit future snapshots use dynamic schemas and the same
provider abstraction.  Unknown labels are rejected; aliases are only
compatibility mappings when they resolve to an active key.  Rule-based
fallbacks remain v1-only until a future stage explicitly audits new rules.

Review-label cache identity now includes `taxonomy_snapshot_id` and
`taxonomy_fingerprint` (migration 19).  Historical v1 labels with otherwise
matching identity may be reused when those fields are absent.  v2+ labels
must match both fields exactly, so a snapshot or fingerprint change is a
cache miss.

`classifier_validation.py` provides deterministic, offline multilabel topic,
issue, and request metrics.  It validates gold labels against the selected
contract and records invalid predictions rather than silently dropping them.
The report is validation-set performance only: it is not model-quality proof,
population inference, sentiment measurement, or a correction for reviewer
self-selection.

The stage does not change Research Core, the Research Report, Stage 2E
diagnostics, taxonomy governance, or the existing production LLM flow unless
an explicit taxonomy contract is supplied by a caller.
