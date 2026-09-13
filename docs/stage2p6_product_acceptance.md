# Stage 2P.6 Product Acceptance

Stage 2P.6 seals the deterministic snapshot product path. The acceptance
tests exercise the production `analyze` request/background job, first-class
latest and immutable persistence, the dashboard contract, and read-side
freshness behavior using isolated SQLite databases and deterministic Steam/LLM
boundary fakes.

## Acceptance matrix

| Scenario | Automated / Manual | Expected | Observed | Evidence |
|---|---|---|---|---|
| A. No provider | Automated | Completed quantitative run; Research Report persisted; semantic unavailable/no_provider; no semantic/DataFrame calls | PASS | `test_no_provider_full_chain_exact_report_and_quantitative_dashboard` |
| B. Missing API key | Automated | Completed Research Core; semantic unavailable/no_api_key; no HTTP preflight failure | PASS | `test_semantic_unavailable_configurations_still_complete_research` |
| C. Invalid semantic configuration | Automated | Completed Research Core; semantic unavailable/invalid_configuration | PASS | Same parametrized acceptance test |
| D. Semantic success | Automated | Research Report and legacy insights both persisted; both readiness layers ready | PASS | `test_semantic_success_keeps_exact_research_report_and_full_dashboard_readiness` |
| E. Semantic runtime failure | Automated | Run completed; Research Report preserved; semantic status failed/runtime_error | PASS | `test_semantic_runtime_failure_preserves_completed_research_product` |
| F. Research Core failure | Automated | Run failed; no immutable completed result; semantic layer not invoked | PASS | `test_research_core_failure_is_terminal_and_not_research_ready` |
| G. Empty population | Automated | Completed Research Report with review_count 0; recommendation rate null; no semantic run | PASS | `test_empty_population_is_completed_without_fake_recommendation_or_semantics` |
| H. Max-review truncation | Automated | Truncation provenance preserved; inference remains limited | PASS | `test_limited_acquisition_provenance_is_preserved_without_completeness_upgrade` |
| I. Incomplete acquisition | Automated | Non-cap acquisition failure remains limited and observable | PASS | Same parametrized acceptance test |
| J. Duplicate denominator | Automated | Duplicate diagnostics annotate the population; raw and recommendation denominators retain all rows | PASS | No-provider full-chain denominator assertions |
| K. Stale review pool | Automated | Stored report returned unchanged; stale=true; no recomputation | PASS | `test_stale_read_and_repeated_get_are_side_effect_free` |
| L. Repeated GET | Automated | Repeated reads are structurally identical and analytically side-effect free | PASS | Same stale/repeated-read test |
| M. Re-analysis of one app | Automated | New run clears prior report while running; latest points to B; A remains immutable | PASS | `test_reanalysis_clears_previous_report_and_run_specific_results_remain_immutable` |
| N. Run-specific retrieval | Automated | `run_id=A` and `run_id=B` return their own immutable Research Reports | PASS | Same re-analysis test |
| O. Historical semantic-only result | Automated | Semantic dashboard remains usable; research_ready=false; no fabricated report | PASS | `test_historical_semantic_only_result_remains_usable_without_fabricated_research_report` |
| P. Research-only readiness | Automated | research_ready=true; semantic_ready=false | PASS | No-provider dashboard assertions |
| Q. Full Research + Semantic readiness | Automated | research_ready=true; semantic_ready=true | PASS | Semantic-success dashboard assertions |
| R. Failed Research readiness | Automated | Failed Research Core never reports research_ready=true | PASS | Research-Core-failure dashboard assertion |
| Frontend quantitative-only smoke | Manual / CI build | Research Core READY, semantic notice, no fake semantic zeros; progress is Fetch → Research → Save | Covered by typed render path and production build | `npm run typecheck`, `npm run build` |
| Frontend semantic/stale smoke | Manual / CI build | Semantic success/failure and stale notices preserve Research Overview | Covered by typed render paths and production build | `npm run typecheck`, `npm run lint`, `npm run build` |

The automated matrix is implemented in
`tests/integration/test_stage2p6_product_acceptance.py` (12 collected tests,
including parametrized configuration and acquisition cases). No live Steam or
paid LLM provider is required.

## Accepted invariants

- A valid acquired population plus successful Research Core is a valid
  quantitative product, independent of semantic-provider availability.
- The production Research Report is structurally equal to a direct
  `build_snapshot_research_report` call over the exact run population and
  metadata payload.
- Latest compatibility results and immutable run results contain the same
  Research Report and semantic status immediately after finalization.
- Steam `voted_up` is presented as Recommended / Not Recommended, not as
  general sentiment or player satisfaction.
- Wilson intervals and activity diagnostics are backend-authoritative; this
  acceptance layer introduces no client/server statistical recalculation.
- Duplicate text, near-copy, coordinated expression, and activity spikes are
  descriptive diagnostics. They do not establish spam, bots, review bombing,
  or intent, and they do not remove rows from the Research Core denominator.
- `/analyze` remains snapshot mode. Comparison, standardization, and lifecycle
  window sections are explicitly unavailable because they require a second
  population.
- Snapshot Research Core is observational and descriptive. It does not prove
  causal version effects and does not represent all players.

## Verification evidence

The final acceptance commit and its GitHub Actions run are recorded in the
final delivery report. Required evidence is:

- targeted acceptance pytest: 12 passed;
- full backend pytest with an isolated temporary base directory;
- dashboard typecheck, lint, and production build;
- GitHub Actions backend and frontend jobs both successful.

No credentials, provider secrets, raw Steam downloads, or local database files
are part of the acceptance artifacts.

## Deterministic Core Acceptance Status

**PASS** — The Stage 1–2P deterministic snapshot-analysis path is accepted for
its documented assumptions and limitations. STRA can acquire a contracted
Steam review population, preserve acquisition provenance, generate deterministic
quantitative Research Core results, persist immutable run-specific reports,
expose them independently from semantic results, and render quantitative-only
analyses in the Dashboard.

This PASS does not validate semantic classifier quality, establish all-player
representativeness, or claim causal version impact. Deferred work remains:

- Stage 2F external event timeline;
- Stage 3A semantic sampling;
- classifier validation and classifier-error uncertainty;
- comparison/version frontend integration where not yet migrated.
