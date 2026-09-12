# ADR P0.4 — Evidence Architecture

## Decision

Use a shared deterministic verifier and persist a bounded immutable source-text snapshot with each selected evidence item. Reuse the immutable full review payload already stored by P0.2c for general Run context, but do not rely on a hash alone.

Add an additive `chat_messages.evidence` JSON column for historical Chat assistant evidence. Version Review and general Run evidence remain embedded in their existing immutable JSON payloads.

## Alternatives rejected

- A source hash alone cannot re-prove substring membership after the canonical review changes.
- A full run-review membership/source table would duplicate the complete P0.2c general Run review snapshot for no P0.4 benefit.
- A broad evidence-ID Agent redesign is safer long term but materially expands P0.4; the blocking final verifier provides the required safety boundary now.

## Invariants

- Direct quotes are exact slices of source text.
- Normalization can locate a source span but never changes displayed text.
- Review/app/run scope mismatches reject evidence.
- Historical evidence cannot be overwritten by later canonical review edits.
- Evidence verification is deterministic and makes no LLM calls.
