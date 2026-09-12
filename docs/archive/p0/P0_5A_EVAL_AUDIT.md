# P0.5a Evaluation Audit

## Scope and outcome

P0.5a establishes an evaluation scaffold only. No human annotation was
performed, no synthetic label was promoted to ground truth, and no P0.5b or
P0.5c work was started.

## Existing benchmark audit

`tooling/benchmarks/` is a generic LLM/provider benchmark suite. Its provider
adapters, request/prompt plumbing, timing/cost collection, and configuration
patterns can be reused as engineering references. Its `synthetic_v1`,
`reference_labels.json`, rendered examples, and other reference datasets are
not human-annotated Golden Set data and are not used as player-voice ground
truth. The benchmark task prompts and judge/reference-label logic are not
reused for the production evaluation contract.

## Production classifier audit

The production semantic path is in `apps/api/senti_next/llm.py`:

- taxonomy: `sentinext-taxonomy-v1`;
- prompt/schema provenance: the active production prompt and classification
  schema versions;
- normalization: `normalize_taxonomy_payload`;
- batch inference: `classify_reviews_batch`;
- cache-writing path: `ensure_review_labels`.

The scaffold imports the production taxonomy and normalization path and calls
`classify_reviews_batch` for explicit prediction runs. It deliberately does
not call `ensure_review_labels`, so evaluation runs do not mutate production
label cache state. Prediction artifacts retain provider/model, prompt and
taxonomy versions, classification input hash, and operational fields.

## Dataset contract

The Golden Set schema retains app/review identity, exact source text and hash,
language, raw metadata, sampling stratum/reason, guideline/taxonomy versions,
annotation status, annotator/adjudication status, labels, and evidence spans.
Core and Challenge are supported. Splitting is deterministic and refuses
pending/unlabeled records; no final split is generated in P0.5a.

The evaluation scaffold reports sentiment, multi-label categories/subcategories,
issue/request labels, exact evidence quote matching, optional evidence
support, confusion, operational validity/fallback/retry/latency/token fields,
and separate Core/Challenge/language slices with support counts. It does not
set pass thresholds.

P0.4 evidence membership verification remains a separate production contract:
this evaluator measures whether a predicted quote matches the annotated source
span, while P0.4 verifies that surfaced evidence belongs to the corresponding
Run's canonical review corpus.

## Real-data boundary

Sample selection requires a legitimate exported review JSONL source. P0.5a
does not create a local Golden Set or invent Steam reviews. The included
fixtures exist only to test validator/scorer mechanics and are explicitly
marked as non-gold.

## Recommendation

GO for the human P0.5b annotation gate, subject to human review of the
guidelines, schema, and a legitimate candidate export. Do not treat the
scorer fixtures or existing generic benchmark references as annotation data.
