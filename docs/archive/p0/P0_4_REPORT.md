# P0.4 Report — Evidence / Citation Verification

Status: **GO for P0.5 review**. P0.5 Golden Set was not started.

## Outcome

Direct player quotes are now blocking-verified against the exact source review text used by the execution. Invalid quotes are removed before user-facing serialization; the system never silently accepts paraphrase or semantic similarity as a direct quote.

The complete pre-change path audit is in [P0_4_EVIDENCE_AUDIT.md](P0_4_EVIDENCE_AUDIT.md). The architectural decision is in [ADR_P0_4_EVIDENCE_ARCHITECTURE.md](ADR_P0_4_EVIDENCE_ARCHITECTURE.md).

## Contract and verifier

`apps/api/senti_next/evidence.py` provides the shared `verify_evidence()` service and compatibility `verify_quote()` function.

Verified evidence contains:

- `run_id` where applicable;
- `app_id` and `review_id`;
- exact source-sliced `quote`;
- `quote_start` / `quote_end`;
- `source_review_hash`;
- `verification_status` and `verification_method`;
- immutable `source_review_text` when verified.

Exact substring matching is preferred. NFKC/whitespace normalization is used only to locate the range; the output is re-sliced from the original source. Altered wording, wrong review/app, missing source, out-of-Run review, and semantic overlap are rejected.

## Current versus historical evidence

P0.2c already stores the full immutable review payload in `analysis_run_results.reviews`. General Run insight evidence now stores the selected source text and verification metadata inside the immutable insight payload. Version Review evidence stores the same snapshot in `analysis_runs.metrics`.

Chat assistant messages now persist verified evidence JSON in the additive `chat_messages.evidence` column. Schema migration version 7 uses the existing backup/restore migration framework. A source hash is retained for integrity, but never used as a substitute for source text.

Later edits/deletions of canonical `reviews` therefore do not invalidate Run A or persisted Chat evidence. A new Run verifies against its new source text.

## Enforcement

- General insight `issue_snippets` / `request_snippets` are emitted only from verified source slices and include structured evidence arrays.
- Version Review evidence cards are verified before persistence and retain the existing `snippet` field for compatibility.
- Monthly reports use the same verifier; report snippets are never accepted independently.
- `/chat` uses the same verifier for LLM citations and only serializes verified citations.
- `/chat/simple` gates the final Agent answer. Invalid direct quotes become `[unverified direct quote removed]`; quotation marks are not retained.
- Chat citation cards are serialized with verification metadata and only verified direct evidence is returned as citations.
- Frontend remains presentation-only; it performs no semantic verification and no broad UI redesign was made.

The evidence-ID architecture was compared in the ADR. P0.4 uses the smaller blocking final verifier, while the structured evidence objects leave a path toward stable evidence IDs without a broad Agent redesign.

## Required behavior tests

Added `apps/api/tests/test_p0_4_evidence.py` covering:

- exact and partial exact quotes;
- normalized source location with original source slice output;
- fabricated and altered wording rejection;
- wrong review, wrong app, and outside-Run rejection;
- missing source rejection;
- invalid Chat quote removal;
- historical source snapshot after canonical edit;
- persisted Chat evidence snapshot;
- insight serialization of verified evidence only.

The existing P0.4 xfail is now a normal passing test. Only the intentional future P0.6 cost-ledger xfail remains.

## Verification and performance

- P0.4 targeted tests: **6 passed**.
- Backend full pytest: **96 passed, 1 intentional xfailed**.
- Backend compileall: **PASS**.
- Backend import smoke: **PASS**.
- Deterministic benchmark: **200 evidence verifications in 1.402 ms**, 200 verified, no LLM calls.
- Frontend was not modified in P0.4; no frontend rebuild was required by the scope. P0.3cV already established TypeScript, lint, and production build PASS.
- `git diff --check`: **PASS**.

The full backend suite retains only existing Pydantic deprecation warnings; no unexpected regressions remain.

## Schema and storage impact

- New migration version: **7** — `chat_messages.evidence TEXT`.
- General Run and Version Review evidence snapshots are bounded to selected evidence items; no full duplicate Run source table was added.
- No FTS, Run lifecycle, metric formula, label cache, ingestion, worker, or frontend information architecture changes were made.

## Files changed

- `apps/api/senti_next/evidence.py`
- `apps/api/senti_next/evidence_schema.py`
- `apps/api/senti_next/migrations.py`
- `apps/api/senti_next/db.py`
- `apps/api/senti_next/storage.py`
- `apps/api/senti_next/chat.py`
- `apps/api/senti_next/chat_agent.py`
- `apps/api/senti_next/chat_tools.py`
- `apps/api/senti_next/routes/chat.py`
- `apps/api/senti_next/insights.py`
- `apps/api/senti_next/version_analysis.py`
- `apps/api/senti_next/reports.py`
- `apps/api/senti_next/routes/runs.py`
- `apps/api/tests/test_p0_4_evidence.py`
- compatibility test updates in `test_p0_contracts.py`, `test_p0_2a_run_schema.py`, `test_p0_migration.py`, and `test_version_runs.py`
- `P0_4_EVIDENCE_AUDIT.md`
- `ADR_P0_4_EVIDENCE_ARCHITECTURE.md`
- `P0_4_REPORT.md`

## Known risks

The current Chat Agent still lets the LLM write prose and citations freely; P0.4 blocks invalid final quotes, while stable evidence-ID-only generation remains a future hardening option. Historical Chat evidence is persisted for verified quoted spans, not every review returned by a search tool.

Verified means “the text exists in the cited source.” It does not mean the claim is true, representative, causal, or correctly classified.

## Recommendation

**GO for P0.5 review.** Stop after P0.4; do not start P0.5 automatically.
