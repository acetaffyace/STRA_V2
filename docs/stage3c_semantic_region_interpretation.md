# Stage 3C — Semantic Region Interpretation & Taxonomy Candidate Review

Stage 3C is a downstream, review-oriented layer over a **completed Stage 3B
materialization**. It packages bounded evidence for semantic regions and, when
an explicitly configured provider is available, asks the existing structured
LLM provider for a constrained interpretation. The result is a candidate or
audit proposal, not a validated topic and not a taxonomy mutation.

## Boundaries

The Research Core denominator, Sampling Contract, Recommendation Rate,
uncertainty, acquisition provenance, Stage 2E diagnostics, Stage 3A vectors,
Stage 3B structure, existing review labels, and `sentinext-taxonomy-v1` are
read-only inputs. A region's support is not prevalence. `voted_up` remains
Recommend/Not Recommend, not sentiment. Similarity is not coordinated
expression, and an outlier is not invalidity or severity.

The evidence contract is `semantic-region-evidence-v1`. Evidence is bounded to
five centroid reviews, eight semantic units, two units per review, and two
dense-region boundary reviews (with 1,600/800 character limits). Unit evidence
is selected by centroid similarity with deterministic ID tie breaks; boundary
evidence is selected by weakest membership. Original review text is preferred;
derived semantic-unit text is explicitly marked as a fallback.

## Interpretation contract

The interpreter uses `semantic-region-interpretation-v1` and
`semantic-region-interpreter-prompt-v1`, temperature zero, English output, and
the existing `LLMProvider.generate_structured` abstraction. Prompts contain
discovery support, cohesion/stability, taxonomy coverage and bounded evidence;
they do not contain recommendation distributions, all-population data, raw
embeddings, credentials, or database details. Review text is untrusted and
delimited. Output recommendations are limited to `no_change`,
`candidate_child_topic`, `candidate_new_topic`, `taxonomy_boundary_review`,
`defer_insufficient_evidence`, and `reject_non_actionable`.

Outliers and unstable regions are deferred without an LLM call. Stable or
moderate well-covered regions receive a deterministic `covered_no_change`
disposition. Other eligible dense/rare regions are bounded by the default
25-call budget (or an explicit larger value). The budget is checked before the
first provider call. A completed run is cached by materialization, evidence,
interpreter contract, prompt, provider, and model identity.

Human decisions are append-only (`approve`, `reject`, `defer`, or
`request_revision`). Approval is a governance gate only: it does not change
taxonomy labels, prompts, training data, or Research Core metrics.

## Persistence and tooling

Migration **17** adds independent evidence-package, interpretation-run,
candidate, and append-only decision tables. It is additive and idempotent.
`tooling/run_semantic_region_interpretation.py` supports evidence-only dry runs,
region subsets, and bounded provider execution. Human review is recorded with
`tooling/review_semantic_candidate.py`.

## Limitations and deferred work

The review-level mean used by Stage 3B may blur multi-topic reviews, so Stage
3C retains unit-level evidence. Candidate names are not final topics and no
numeric LLM confidence is accepted. No prevalence, causality, severity, public
opinion, or taxonomy accuracy claim follows from this stage. Topic validation,
controlled taxonomy evolution, semantic sampling, and frontend presentation
remain later stages.
