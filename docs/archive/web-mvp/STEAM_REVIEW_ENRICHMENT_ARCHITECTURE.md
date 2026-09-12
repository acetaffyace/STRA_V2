# Steam Review Enrichment v1 — Architecture

`raw Steam payload → canonical nullable SQL fields → derived informational API context`.

Canonical fields live on `reviews` and are backfilled only when the exact JSON key exists. Upserts preserve known values when a later partial payload omits a field. Derived labels are computed in `steam_enrichment.py` and are never stored as analytical facts.

API review-detail/list serialization exposes `steam_context`, a separate `developer_response` object, and Steam provenance. Coverage counters are completeness diagnostics only. The migration is version 11 and uses the existing backup/restore migration framework.

These fields are currently stored for future analysis and contextual inspection only. They do not currently affect analytical conclusions.
