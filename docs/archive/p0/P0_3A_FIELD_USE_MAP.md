# P0.3a review_labels field/use map

## Existing storage

`review_labels` has one mutable row per `(app_id, review_id)` with:

| Field | Current use | P0.3a treatment |
|---|---|---|
| `app_id`, `review_id` | label joins and app-scoped cache lookup | unchanged |
| `model` | legacy/current model identity read by cache code | preserve; populate with canonical provider:model for new LLM labels |
| `prompt_version` | partial cache invalidation and label metadata | preserve; exact identity match required |
| `review_hash` | hash of stripped raw review text | preserve; continue to represent source review text |
| `payload` | analytical label JSON consumed by insights, review APIs, chat and Version Review | shape preserved; only underscore runtime metadata may be added |
| `updated_at` | write timestamp | unchanged |

`upsert_review_label()` and `bulk_upsert_review_labels()` are the only
storage writers. They are called by `ensure_review_labels()` for empty/short
labels, normal LLM success, fallback, cache normalization, and aspect
enrichment. `load_review_labels()` is the only storage reader and is used by
general analysis, estimate/progress paths, review APIs, chat, miscellaneous
insights, and Version Review metrics.

## Classification input audit

Normal batch classification receives, per review:

- sanitized review text (`_sanitize_review_text`, max 3000 characters);
- review language;
- reviewer playtime converted to rounded hours;
- voted-up recommendation;
- shared game name/type/genres/categories (first five)/short description
  (first 200 characters);
- the batch classification mode and current structured-output schema.

Single-review enrichment uses the same semantic fields but a different prompt
template and therefore a distinct classification mode. The raw `review_hash`
does not capture these processed-input changes.

## P0.3a fields

Migration v6 adds nullable provenance fields: `label_origin`, `validated`,
`taxonomy_version`, `provider`, `model_id`, `classification_input_hash`,
`was_truncated`, `original_char_count`, `processed_char_count`, and
`generated_at`. Existing `model` remains for compatibility. Existing rows are
marked `label_origin='legacy'` only; unknown identity and validation remain
unknown, making them cache misses.

`label_origin` answers how a label was generated (`llm`, `rule_fallback`, or
`legacy`). `resolution_source` is runtime-only (`generated` or `cache_hit`)
and is attached to the returned payload without being persisted as label
origin.

`validated=true` means the machine output passed the existing taxonomy/schema
normalization and is eligible for automated analytics. It does not mean human
review, factual correctness, or Golden Set verification.

## Central cache rule

`label_cache_eligible(label, current_identity)` requires validated LLM origin,
exact review hash, classification-input hash, taxonomy, prompt, provider and
canonical model identity matches. Legacy, fallback, invalid, incomplete, or
otherwise mismatched rows are cache misses. The review-label table remains a
latest single-row cache; historical reproducibility continues to rely on
immutable analysis run results, not label history.

