# P0.1V Report — FTS Integrity Verification Hardening

Status: **P0.1V complete. GO for P0.2a.** P0.2a was not started.

## 1. Actual FTS index verification

`verify_fts_integrity()` no longer relies on `COUNT(*) FROM reviews_fts` as
proof of index health. For external-content FTS5, it creates a temporary
`fts5vocab('main', 'reviews_fts', 'instance')` view and reads distinct `doc`
IDs from the actual inverted-index postings.

It then checks:

- `expected_searchable_count`: canonical reviews whose text contains a
  unicode61-compatible probe token;
- `indexed_count`: distinct document IDs present in the actual FTS postings;
- missing document IDs: canonical searchable reviews absent from postings;
- orphan document IDs: postings with no canonical `reviews.id`;
- per-review `MATCH` probe: a token taken from each canonical text must match
  the expected FTS rowid;
- duplicate logical documents: external-content rowids are unique by SQLite
  design, so duplicate rowids are structurally impossible in the selected
  architecture and remain reported as an empty duplicate set;
- projection drift between `data.review` and `review_text`.

The external-content `SELECT` projection is therefore not used as the sole
integrity signal.

## 2. Deliberate corruption regression

The test preserves canonical `reviews`, executes the FTS5 `delete-all` command
to clear the inverted index only, and then verifies:

```text
corrupt actual index
  -> verify_fts_integrity(): FAIL
  -> rebuild_fts()
  -> verify_fts_integrity(): PASS
  -> MATCH search result restored
```

The failure reports both the missing document and the failed MATCH probe,
which demonstrates that an apparently intact external-content table cannot
hide this corruption from the checker.

## 3. Review-text projection contract

The contract is:

```text
reviews.data.review == reviews.review_text
```

where missing/null review values normalize to the empty string. `data` remains
the original serialized Steam payload; `review_text` is its canonical
searchable projection.

Production-path audit found one canonical write path: `storage.upsert_reviews()`.
It now writes `data` and `review_text` together on insert and conflict update.
The other `reviews` references are reads or deletes. No production code path
was found that updates `reviews.data` independently. Test fixtures that insert
raw rows are not production write paths.

The regression tests cover:

- normal insert: projection PASS;
- normal review update: both values change and projection remains PASS;
- deliberate `review_text` drift: integrity FAIL with the affected row ID;
- canonical rewrite through `upsert_reviews()`: projection PASS again.

## 4. Compatibility and performance impact

The hardening adds one temporary `fts5vocab` construction, one actual-posting
document scan, and one MATCH probe per searchable canonical review whenever
integrity verification is explicitly requested or run during migration. Normal
startup does not silently rebuild the FTS index. Normal write/search paths are
unchanged apart from the already-installed triggers and projection column.

Validation:

```text
full backend pytest: 55 passed, 6 xfailed
P0.1V tests: 7 passed
compileall apps tooling: PASS
import smoke: PASS
```

The six xfails remain unrelated future-P0 contracts. No tokenizer, review ID,
migration architecture, API contract, or analysis schema was changed.

## 5. Files changed

- `apps/api/senti_next/fts.py` — actual-posting verification and projection
  drift detection.
- `apps/api/tests/test_p0_1_fts.py` — corruption and projection regression
  tests.
- `P0_1V_REPORT.md` — this verification record.

## Final gate

**GO for P0.2a**, subject to the user’s explicit schema gate. This verification
gate is complete; execution stops here.
