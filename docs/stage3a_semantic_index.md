# Stage 3A — Full-Population Semantic Index

Stage 3A adds a derived semantic representation beside the frozen Research
Core.  It is infrastructure for later semantic sampling and discovery; it is
not topic modeling, taxonomy classification, or an LLM feature.

```text
Research Population (frozen)
       ├── Research Core → Research Report (authoritative quantitative result)
       └── Semantic Index → text-eligible units → cached embeddings
```

The index never changes the Research Population denominator, Recommendation
Rate, acquisition provenance, Research Report, or Stage 2E diagnostics.  Exact
duplicates remain members of the population; only identical embedding work is
reused.

## Contract

The contract is `semantic-index-contract-v1` with:

- model: `intfloat/multilingual-e5-small`;
- pinned Hugging Face revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`;
- provider: optional local ONNX Runtime;
- 384 dimensions, `float32`, attention-mask mean pooling and L2 normalization;
- fixed E5 input policy: `query: <semantic text>`;
- text preprocessing `semantic-text-v1`: Unicode NFKC, line-ending
  normalization, repeated-whitespace collapse and trimming;
- deterministic tokenizer-derived `semantic-chunk-v1`: 448-token chunks with
  64-token overlap.

Each eligible review has one or more `SemanticUnit` records.  Units retain the
review ID, unit position, semantic-text hash, token boundaries and cache key.
Empty/whitespace text is retained as an ineligible population member with an
explicit `empty_text` reason.  No language, recommendation, playtime,
taxonomy, or game metadata is injected into embedding text.

## Model distribution and availability

ONNX Runtime, `tokenizers`, and `huggingface_hub` are pinned in
`apps/api/requirements.txt`.  The model is **not** committed to Git and is not
bundled in the desktop installer.  It is downloaded only by the explicit
`tooling/build_semantic_index.py --install-model` action into the platformdirs
user cache.  Normal `/analyze` requests do not download or build an index.
The cache contains a small `model_manifest.json` with the pinned revision,
artifact filename and SHA-256; a mismatch is reported as `load_failed`.

If the model is not installed, cannot be loaded, or fails checksum validation,
the optional semantic-index operation reports `embedding_model_unavailable` or
`load_failed`.  Research Core remains valid and existing semantic/LLM behavior
is unchanged.

## Cache and identity

The SQLite `semantic_embedding_cache` key includes semantic text hash, model
ID/revision, artifact SHA-256, preprocessing/chunking versions, prefix,
pooling, normalization and dimensions.  Batch size and device are not part of
identity.  Model or contract changes therefore miss the cache rather than
reusing stale vectors.  Vectors are binary `float32` BLOBs, not JSON arrays.

`semantic_index_runs` binds an index to one immutable `research_run_id` and
`population_fingerprint`.  Members and units live in
`semantic_index_members` and `semantic_index_units`.  Migration 14 is additive
and idempotent.  Re-running the same run/fingerprint/contract reuses the
completed index identity; a different population cannot be attached merely by
matching `app_id`.

## Non-interference and limitations

The index is provider-independent infrastructure, but the default local E5
backend is optional and its model-quality smoke is not a broad validation
study.  Inference can vary by hardware at tiny floating-point levels; the
immutable contract, artifact checksum and cache identity provide reproducible
meaning and reuse.

Stage 2E duplicate/near-copy/coordinated-expression signals remain descriptive
and are never replaced by embedding similarity.  Duplicate text is not proof
of spam, coordinated expression is not proof of manipulation, and activity
spikes are not automatically review bombing.  Semantic units do not imply
topics or labels.

## Usage

Use `build_semantic_index(reviews, research_run_id=..., population_fingerprint=...,
contract=..., backend=...)` with raw Steam-style mappings.  The higher-level
`build_semantic_index_for_run` helper is intentionally not wired into `/analyze`
until this infrastructure is accepted.  Use `--fake` for deterministic offline
fixture checks.  The opt-in real-model smoke is guarded by
`STRA_RUN_REAL_EMBEDDING_SMOKE=1`.

Stage 3B may consume this index plus Research metadata to study clusters,
outliers and taxonomy blind spots.  It must preserve the distinction:

```text
Research Population N != Semantic Sample N
```

No Stage 3B sampling or interpretation is implemented here.
