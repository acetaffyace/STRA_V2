# ADR P0.2a — Generalized analysis run schema

## Audit finding

The existing `analysis_runs` table is used end-to-end by the Version Review
routes and storage helpers. Its `run_id` is the Version Review execution
identity, `target_app_id` is the game identity, `event_id` anchors a verified
version event, `config` is the immutable configuration snapshot, and
`metrics` is the derived Version Review payload. `status`, `metrics`, `error`,
and `updated_at` are mutable through existing helpers; identity and config are
not updated.

The ordinary `/analyze` flow does not write `analysis_runs`; it writes the
latest app-level `analysis_results` row and its existing `run_id`. P0.2a does
not wire those flows together, change either API, or move result JSON.

## Decision

Use one generalized `analysis_runs` entity. Add `run_type` as ordinary TEXT,
with application constants for `version_review`, `general_analysis`, and
`legacy`. SQLite ENUM-like enforcement is intentionally avoided so future run
types can be added without a table rewrite.

Existing Version Review columns remain and existing run IDs remain unchanged.
`event_id` becomes nullable because a general analysis has no version event;
existing Version Review foreign-key relationships remain valid. `target_app_id`
continues to be the app identity for both run types.

## Field contract

- **Creation/configuration:** `run_id`, `user_id`, `target_app_id`, `event_id`,
  `run_type`, scope fields, counts supplied by execution, and analysis identity
  fields. These are intended to be fixed once execution begins.
- **Lifecycle:** `status`, `created_at`, `started_at`, `completed_at`,
  `updated_at`, and `error`. P0.2a only establishes columns; P0.2b will own
  transition enforcement.
- **Existing result payloads:** `config` and `metrics` remain untouched. No
  new result JSON is added to `analysis_runs`.

All new provenance fields are nullable. Existing rows are classified as
`version_review` because every current `analysis_runs` writer is the Version
Review implementation. No historical counts, fingerprints, model, prompt,
taxonomy, cutoff, or timing values are fabricated.

## Migration consequence

SQLite cannot drop the old `NOT NULL` constraint on `event_id` with an
additive `ALTER TABLE`. Migration v3 therefore uses the P0.0A backup-protected
table-copy pattern, preserves every existing value, makes only `event_id`
nullable, adds the generalized columns, and recreates the existing indexes.
