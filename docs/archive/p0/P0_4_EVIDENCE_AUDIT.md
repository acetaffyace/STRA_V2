# P0.4 Evidence / Citation Audit

## Evidence path inventory

| Surface | Origin | review_id | run_id | Validation before P0.4 | Persistence / historical status |
|---|---|---:|---:|---|---|
| General insight subcategory cards | `llm_subcategory_evidence` on the run DataFrame | available from review row | available during general run | none; raw strings were emitted | inside immutable `analysis_run_results.insights`, but without source metadata |
| Version Review evidence cards | label/aspect evidence spans in `version_analysis.py` | available | available in `analysis_runs.metrics` | none; raw spans were emitted | metrics persisted, but no source snapshot |
| Monthly PDF/dashboard reports | `reports.calculate_monthly_insights()` | often available in DataFrame | not attached | none; snippets were copied | report output had no verification metadata |
| `/chat` JSON chat | LLM `citations` matched to `ChatEvidence` | available | not applicable/current query | citation shape check only; no exact blocking verifier | answer/citations returned; no immutable source snapshot |
| `/chat/simple` agent | `search_reviews` tool output and LLM final answer | available in tool output | not applicable/current query | prompt instructed the model; no blocking final gate | chat message content persisted, source evidence was not |
| Dashboard chat citation cards | backend `citations[].snippet` | available | not exposed | frontend rendered returned snippets | frontend is presentation-only |

## P0.4 contract

`apps/api/senti_next/evidence.py` is the single verifier. A verified item contains `run_id` when applicable, `app_id`, `review_id`, the exact source-sliced `quote`, `quote_start`, `quote_end`, `source_review_hash`, `verification_status`, `verification_method`, and an immutable `source_review_text` snapshot.

Exact substring matching is preferred. Unicode normalization and whitespace normalization are used only to locate a source range; the returned quote is always sliced from the original source. Semantic similarity, word overlap, paraphrase, review existence alone, and LLM assertions are rejected.

The verifier also checks review identity, app identity, run identity, and allowed Run review IDs when supplied.

## Historical source decision

P0.2c already persists the full review payload in immutable `analysis_run_results.reviews`. General Run evidence therefore stores the selected source text and verification metadata inside the immutable `insights` payload; a new full run-review membership table is unnecessary.

Version Review metrics are persisted in `analysis_runs.metrics`, so each verified evidence card stores its source text snapshot there as well.

Chat assistant messages did not have an immutable evidence field. P0.4 adds an additive `chat_messages.evidence` JSON column (schema migration 7) and stores verified evidence snapshots with the assistant message. A source hash alone is never used as the historical proof.

## Enforcement points

- Insight aggregation only serializes verified `issue_snippets` / `request_snippets` and keeps structured evidence metadata.
- Version Review evidence cards are filtered through the same verifier.
- Reports use the same verifier and never add unverified snippets to report evidence arrays.
- `/chat` and `/chat/simple` final answers pass through a blocking quote gate. Invalid quoted text is replaced with `[unverified direct quote removed]`; quotation marks are not retained.
- Chat citation cards are serialized only when their evidence status is `verified`.
- Frontend does not perform semantic verification. It renders backend-approved citation/evidence payloads only.

## Evidence IDs architecture comparison

P0.4 implements the smaller blocking final verifier: it avoids a broad Agent redesign while ensuring every returned direct quote is source-grounded. The stronger future architecture is verified tool evidence objects with stable evidence IDs supplied to the LLM, followed by serializer-side source rendering. The current structured evidence records are compatible with that direction, but P0.4 does not introduce a new Agent protocol or Golden Set.

## Analytical distinction

`verification_status=verified` means only that the displayed text exists in the cited source review. It does not establish that the player's claim is true, representative, causal, or correctly classified.
