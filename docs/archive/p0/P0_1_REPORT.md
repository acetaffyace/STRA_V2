# P0.1 Report — FTS Integrity Migration

Status: **P0.1 complete. Recommended GO for P0.2a.** P0.2a was not started.

## Canonical storage discovery

The current `reviews` table had `id`, `app_id`, globally unique `review_id`,
serialized `data`, timestamps, and no dedicated review-text column. The
canonical searchable value was `data.review`, extracted during ingestion as
`str(review.get("review") or "")`.

The legacy `reviews_fts` table was a standalone FTS5 table with columns
`review_id` and `review_text`. `storage.upsert_reviews()` inserted a new FTS
row on every upsert, including updates. Review deletion paths removed rows
from `reviews` but did not remove FTS rows. The dialect searched and ranked by
FTS `review_id`. No other review fields were indexed.

The full decision record is in [ADR_P0_1_FTS_ARCHITECTURE.md](ADR_P0_1_FTS_ARCHITECTURE.md).

## Architecture selected

P0.1 adds `reviews.review_text TEXT NOT NULL DEFAULT ''` and backfills it from
`json_extract(data, '$.review')`. The new FTS table is:

```sql
CREATE VIRTUAL TABLE reviews_fts USING fts5(
  review_text,
  content='reviews',
  content_rowid='id',
  tokenize='unicode61'
)
```

This is the smallest design that exposes canonical text cleanly to SQLite
FTS5, preserves `review_id` semantics, and avoids a second deterministic row-id
mapping. JSON-only trigger parsing and contentless FTS were rejected because
they add maintenance and corruption risk without improving correctness.

## Migration and maintenance

- Migration version: **2**, `canonical external-content review FTS`.
- P0.0A backup/restore and version ledger are used before any destructive FTS
  change. File databases receive a `.p0_1.bak` backup and failed migrations
  restore it. The migration verifies integrity before the version is recorded.
- The legacy FTS table is dropped only after the backup has succeeded, then
  rebuilt from canonical `reviews` rows.
- `reviews_fts_ai`, `reviews_fts_au`, and `reviews_fts_ad` maintain insert,
  text-update, and delete behavior respectively.
- `storage.upsert_reviews()` now writes `review_text` in the same canonical
  upsert. The manual duplicate-producing FTS insert was removed.
- `enforce_review_limit()`, `delete_all_game_data()`, and
  `clear_entire_database()` now benefit from the delete trigger; no review
  deletion path requires a separate FTS delete.
- `rebuild_fts()` is explicit and is never called on normal startup.
- `verify_fts_integrity()` reports canonical/indexed counts, duplicate rowids,
  missing rows, and orphaned rows. External-content rowids make duplicate
  logical documents structurally impossible after migration; legacy duplicates
  are repaired during rebuild.

## Tests

The new P0.1 tests cover:

- one insert and 100 repeated upserts => exactly one indexed row;
- text update removes old search results and exposes new results;
- deletion, explicit rebuild, and two app IDs;
- legacy duplicate and orphan repair;
- repeated migration idempotence;
- migration failure with backup restore preserving canonical reviews.

Validation results:

```text
full backend pytest: 53 passed, 6 xfailed
compileall apps tooling: PASS
import smoke: PASS
```

The six xfails remain unrelated future-P0 contracts. The former FTS trigger
contract is now passing. The existing SQLite compatibility tests were updated
to exercise canonical review writes and trigger-maintained FTS.

## Performance check

On a local in-memory fixture of 1,000 reviews:

| Operation | Result |
|---|---:|
| Initial 1,000-review upsert | 0.063 s |
| Same review upsert 100 times | 0.009 s |
| Search 100 times | 6.137 s |
| Rebuild 1,000 reviews | 0.001 s |

The legacy direct-write reproduction produced 100 FTS rows for 100 repeated
writes; the new mechanism remained at one row. The trigger work is one indexed
row maintenance operation per canonical insert/update/delete and did not
materially change the repeated-write cost in this local check. The search
timing includes the application/SQLAlchemy call path; it is not presented as a
cross-runtime benchmark against the old direct SQLite microbenchmark.

## Files changed

- `apps/api/senti_next/fts.py` — migration, triggers, rebuild, integrity check.
- `apps/api/senti_next/db.py` — version-2 startup migration integration.
- `apps/api/senti_next/migrations.py` — schema version advanced to 2.
- `apps/api/senti_next/storage.py` — canonical text upsert; manual FTS append removed.
- `apps/api/senti_next/dialect.py` — FTS rowid joins through `reviews.id`.
- `apps/api/tests/test_p0_1_fts.py` and `test_sqlite_compat.py` — P0.1 coverage.
- `ADR_P0_1_FTS_ARCHITECTURE.md` — discovery and design decision.

P0.0A/P0.0B files remain in the working tree as earlier gated work. No
dashboard/API semantics, analysis runs, label provenance, ingestion model,
database technology, or review-id key semantics were changed.

## Rollback and known risks

Rollback is automatic for file migration failure through the P0.0A backup
runner. The backup is retained at the database-adjacent `.p0_1.bak` path for
operator recovery. The main compatibility risk is an externally modified
database whose `reviews.data` contains invalid JSON; the migration expects the
existing canonical JSON contract. Such a failure is detected before the
version is recorded and is restored from backup.

## Gate recommendation

**GO for P0.2a**, subject to the normal human gate. P0.1 is complete and this
task stops here.
