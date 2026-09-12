# zh-CN Localization Audit — Portfolio Release V1.1

Date: 2026-08-26  
Scope: packaged desktop UI after historical-data migration

## Result

`ZH_CN_LOCALIZATION_AUDIT = PARTIAL — FINAL SURFACE PASS APPLIED`

The default language is zh-CN and the primary navigation/common labels are translated. The migrated historical data is displayed correctly. This pass translated additional user-facing chrome in Reports, month selection, player progression, achievement states, and PDF actions through the existing language state. The audit still finds hard-coded English in other secondary and analytical surfaces, so it does not claim full localization completion.

## Rules

| Text class | Treatment |
|---|---|
| Product navigation, buttons, loading, errors, empty states | SHOULD_TRANSLATE |
| Recommendation semantics, taxonomy IDs, provider/model names, Steam/game names, run IDs | KEEP_CANONICAL or PROPER_NOUN |
| API route, runtime profile, migration version, hashes, diagnostic payloads | TECHNICAL_DETAIL_ONLY |
| Stored review text and evidence quotes | KEEP_SOURCE_TEXT; do not silently translate provenance |

## Observed coverage

| Surface | Observed state | Classification | Action |
|---|---|---|---|
| App navigation and common actions | Chinese translations exist in `LanguageContext` | PASS | Keep |
| Overview primary labels | Mostly Chinese; some direct JSX fallback text remains | PARTIAL | Translate user-facing fallback labels |
| Game Analysis metrics | Recommendation semantics preserved as 推荐率; several analytical helper/status strings remain English | PARTIAL | Translate UI chrome only; preserve metric meaning |
| Version Review | Chinese comparative labels coexist with English technical/status text | PARTIAL | Translate user-facing controls/statuses; retain IDs and provider names |
| Reports | Chinese page structure with possible English empty/error/status strings | PARTIAL | Translate user-facing states; keep evidence source text |
| Settings and diagnostics | Mixed Chinese/English | PARTIAL | Translate controls and status prose; retain technical payload values |
| Onboarding | English copy is still present when onboarding is shown | OPEN | Translate or remove only under a separately approved UI change |

## Follow-up pass changes

- `AchievementsWidget`: player progression, unavailable state, completion, achievement counts, and expand/collapse labels now follow zh-CN.
- `MonthSelector`: loading, selection, empty state, and review count labels now follow zh-CN.
- `ReportsPage`: loading, empty state, PDF generation/download, and last-generated labels now follow zh-CN.
- Existing source values and stored content were not mutated.

## Semantic guardrails

- Steam recommendation semantics remain recommendation semantics. Do not rename `recommendation_rate` to sentiment.
- Do not translate or mutate taxonomy keys, stored evidence, game titles, provider/model names, run IDs, hashes, or API/runtime diagnostics.
- Missing values must remain empty, unavailable, or hidden; no localization change may add fallback data.

## Closure status

The data migration is accepted. Full zh-CN closure is not asserted by this audit because the repository still contains user-facing hard-coded English outside the existing translation map. The required screen-first packaged recheck for the latest source changes was blocked by unavailable browser connection in this session; no visual PASS is claimed. Any follow-up localization pass must not modify database or analytical behavior.
