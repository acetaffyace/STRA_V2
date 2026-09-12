# ADR P0.1 — Canonical review FTS architecture

## Discovery finding

The canonical `reviews` table currently stores `review_id`, `app_id`, and the
serialized review in `data`; it has no dedicated review-text column. The
canonical text is the JSON field `data.review`, represented in ingestion by
`str(review.get("review") or "")`. The legacy `reviews_fts` table is a
standalone FTS5 table with two indexed columns, `review_id` and
`review_text`. `storage.upsert_reviews()` appends one FTS row for every upsert,
including updates, while the review deletion paths delete only from
`reviews`. The dialect searches and ranks by the FTS `review_id` column. No
other review fields are indexed.

## Decision

P0.1 adds `reviews.review_text` and makes it the canonical, maintained copy of
`data.review`. `reviews_fts` is rebuilt as an FTS5 external-content table with
`content='reviews'`, `content_rowid='id'`, and one indexed column,
`review_text`. Insert, update, and delete triggers maintain the FTS table.
Queries join FTS rowids to `reviews.id` and return the unchanged
`reviews.review_id`.

## Alternatives rejected

- **Keep JSON-only content with triggers:** SQLite triggers would need to parse
  JSON on every write and the current standalone FTS row identity would remain
  easy to corrupt.
- **Contentless FTS with a deterministic mapping:** this adds a second row-id
  mapping and custom delete/update handling without improving correctness over
  the existing integer primary key.
- **Keep manual writes:** this is the source of duplicate documents and leaves
  deletion paths incomplete.

The selected design exposes the searchable value in the content table, gives
FTS one stable row per canonical review, remains SQLite-native and desktop
compatible, and keeps schema complexity limited to one column, one FTS table,
and three triggers.
