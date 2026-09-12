# WEB MVP UX Polish Audit

Date: 2026-08-25

Scope: `WEB_MVP_UX_POLISH_FIX_SPEC.md`. This round is limited to Web MVP sample-count truthfulness, authoritative run progress, ETA presentation, Decision Summary copy, localized AI widget output, taxonomy localization, and provenance.

Implemented findings:

- Run metadata now distinguishes requested, available, retrieved, deduplicated, analysis-population, and classified counts. Dashboard completion and primary sample displays use `analysis_population_count` with compatibility fallbacks for older runs.
- Lifecycle and completion are backend-authoritative. Immutable result persistence and exact-run dashboard linkage are required before `COMPLETED` is presented as ready.
- ETA is persisted by the backend from recent batch throughput and exposed only after sufficient observations; the browser no longer estimates from a wall-clock timer and the UI uses coarse language.
- The queue and Decision Summary copy is productized in Chinese, with the cohort caveat placed at module level.
- Widget summaries receive an explicit output-language contract, have one bounded repair attempt, and return requested/actual language, provider, model, run ID, and generation timestamp.
- Taxonomy keys remain canonical machine keys; UI labels use the centralized taxonomy localization map.

No Adaptive Analysis methodology, taxonomy semantics, scoring rules, or unrelated feature behavior was changed.

Known compatibility behavior: legacy runs without the new population columns fall back to their existing metadata until a new run is created.
