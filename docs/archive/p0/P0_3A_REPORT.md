# P0.3a Report — Label Provenance and Cache Identity

## Outcome

P0.3a is complete. Review labels now carry enough machine provenance to
distinguish generation origin, validation state, and the semantic identity of
the input/model configuration used. Cache reuse is centralized and requires a
complete identity match. P0.3b was not started.

## Existing `review_labels` audit

The table was a latest single-row cache keyed by `(app_id, review_id)` with
`model`, `prompt_version`, `review_hash`, `payload`, and `updated_at`.
`upsert_review_label()` handles empty/short labels and aspect enrichment;
`bulk_upsert_review_labels()` handles normal batch success and fallback.
`load_review_labels()` feeds general analysis, estimate/progress, review APIs,
chat, miscellaneous analysis, and Version Review metrics. Analytical payload
shape and joins remain unchanged.

The current table still overwrites prior label versions when identity changes.
Older versions are not inspectable through `review_labels`; reproducible
completed analyses rely on immutable P0.2c run results. P0.3a intentionally did
not create a label-history architecture.

The field/use map is recorded in
[P0_3A_FIELD_USE_MAP.md](P0_3A_FIELD_USE_MAP.md).

## Provenance semantics

`label_origin` is persisted and means how the label was generated:

- `llm`: successful structured classification and enrichment;
- `rule_fallback`: deterministic continuity/fallback output, not a trusted LLM label;
- `legacy`: pre-v6 row with unknown provenance.

`resolution_source` is runtime-only and is attached to returned payloads as
`_resolution_source`: `generated` or `cache_hit`. Reusing an LLM label does
not change its `label_origin`.

`validated=true` means the existing schema/taxonomy normalization succeeded
and the label is eligible for future automated analytics. It does not mean
human-reviewed, factually correct, or Golden Set verified. Fallback and legacy
rows are not validated.

## Final semantic cache identity

The centralized `label_cache_eligible()` requires all of:

- `label_origin == 'llm'`;
- `validated == true`;
- exact `review_hash`;
- exact `classification_input_hash`;
- exact taxonomy version;
- exact prompt version;
- exact provider;
- exact canonical model identity.

The current taxonomy constant is `sentinext-taxonomy-v1`. Provider model IDs
are already namespaced by the provider layer (`provider:model`), for example
`openai:gpt-x`; provider is also persisted separately to make the decision
explicit.

`classification_input_hash` is SHA-256 over the normalized semantic input:

- sanitized final review text;
- classification mode (`batch` or `single_enrichment`);
- language;
- rounded playtime hours;
- voted-up recommendation;
- game name/type;
- all game genres;
- first five game categories;
- first 200 characters of game description;
- structured classifier schema version.

The raw `review_hash` remains the identity of the stripped source review.
Thus changing source text and changing preprocessing/context are distinct
cache invalidation causes.

## Truncation and metadata

v6 persists `was_truncated`, `original_char_count`, and
`processed_char_count`. Current classification sanitizes/truncates at 3,000
characters; the hash is computed from the final sanitized text actually sent
to the classifier plus the other semantic inputs.

## Migration and legacy behavior

Migration v6 uses the existing backup/restore framework and adds nullable:

`label_origin`, `validated`, `taxonomy_version`, `provider`, `model_id`,
`classification_input_hash`, `was_truncated`, `original_char_count`,
`processed_char_count`, and `generated_at`.

Existing `model` remains for compatibility. Existing rows are marked
`label_origin='legacy'` only; unknown taxonomy, validation, provider/model
identity, and input identity are not fabricated. Therefore legacy rows remain
readable but cannot silently satisfy the current cache.

## Fallback and failure behavior

The current batch/single retry workflow is preserved. Default continuity
fallbacks are persisted as `rule_fallback` with `validated=false` and no LLM
provider/model claim. They are distinguishable and eligible for retry on a
later run. A failed generation does not become a valid cached LLM label.

## Tests

Added `test_p0_3a_provenance.py` for:

- processed-input/truncation identity;
- taxonomy, prompt, provider, and model invalidation;
- generated provenance persistence;
- cache hit without a classification call;
- fallback and legacy cache exclusion.

Validation:

- backend pytest: **71 passed, 5 intentional xfails**, with the P0.3a cache
  identity contract now PASS;
- P0 migration and P0.2 suites: passed;
- compileall: passed;
- import smoke: passed;
- existing insights, review API, chat, dashboard-facing storage consumers,
  and Version Review paths remained compatible.

## Performance and expected LLM cost

The centralized identity/eligibility check measured **12.60 ms for 1,000
identity plus eligibility checks** on the local SQLite/Python environment.
This is negligible compared with an LLM call. Matching validated labels avoid
classification calls as before, now with stricter correctness. Legacy and
fallback rows may cause a one-time increase in LLM calls because they are no
longer normal cache hits; valid current LLM rows retain cache reuse. No
per-call cost ledger was added.

## Files changed

- `apps/api/senti_next/label_schema.py`
- `apps/api/senti_next/db.py`
- `apps/api/senti_next/migrations.py`
- `apps/api/senti_next/storage.py`
- `apps/api/senti_next/llm.py`
- `apps/api/tests/test_p0_3a_provenance.py`
- existing migration/contract test expectations
- `P0_3A_FIELD_USE_MAP.md`

## Rollback and known risks

File databases are backed up before v6 and restored on migration failure via
the existing `.p0_3a.bak` path. Runtime label writes remain ordinary atomic
single-row/bulk transactions.

Known risks:

- the latest-row label model still cannot inspect older label versions;
- game context changes intentionally invalidate cache identity;
- fallback rows may be retried repeatedly until a valid LLM result is
  available;
- adding semantic identity fields increases row size modestly.

## Recommendation for P0.3b

**GO for P0.3b**, subject to human review. P0.3a stops here.
