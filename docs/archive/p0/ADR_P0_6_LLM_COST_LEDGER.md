# ADR P0.6: Durable LLM Cost Ledger

## Status

Accepted for P0.6.

## Decision

Add an append-only SQLite `llm_calls` table and instrument the shared provider
adapters. Each provider attempt receives a UUID `call_id`; retries share a
logical `operation_id`. Context variables carry `run_id`, app, purpose, phase,
prompt/taxonomy identity, and workload type from business callers.

Pricing is a small in-process versioned registry. The selected unit prices,
currency, pricing version, source, and timestamp are copied into each call row.
Historical reads therefore never depend on current pricing configuration.

## Alternatives rejected

- Read-time pricing from today's config: changes historical cost.
- One row per logical operation: hides retry/fallback spend.
- Reusing `llm_usage`: lacks identity, lifecycle, run linkage, pricing
  provenance, and explicit unknown usage.
- Prompt/response persistence: unnecessary sensitive-data retention.
- External billing service/warehouse: outside local-first P0 scope.

## Failure policy

Ledger writes are best-effort but logged with stack traces. A telemetry failure
does not discard a provider result or turn it into a fake zero-cost record.
Migration uses the existing backup/restore framework and is version 8.

## Scope boundary

P0.6 adds read-only cost aggregation endpoints and no frontend redesign,
routing, model selection, prompt optimization, quality changes, or budget
enforcement.
