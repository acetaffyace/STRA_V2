# SentiNext UI Data Capability Audit

Status: `UI_DATA_CAPABILITY_AUDIT_COMPLETE`  
Task class: `L2 — inspection-only`  
Audit date: 2026-08-26  
Frozen baseline: `sentinext-mvp-v1` / `SENTINEXT_MVP_FROZEN`

## Scope and method

This is a code/data-grounded audit of the current implementation. It does not propose or implement UI, API, schema, taxonomy, prompt, sampling, Evidence Grade, Version Review, or lifecycle changes.

The audit inspected:

- Canonical schema and migrations: `apps/api/senti_next/db.py`, `run_schema.py`, `result_schema.py`, `adaptive_schema.py`, `cost_ledger.py`.
- Read paths: `apps/api/senti_next/storage.py`, `web_contract.py`.
- Current API routes: `apps/api/senti_next/routes/analysis.py`, `runs.py`, `misc.py`, `reviews.py`, `games.py`, `cost.py`.
- Frontend contracts and consumption: `apps/dashboard/src/lib/api.ts`, `src/types/index.ts`, `src/app/dashboard/page.tsx`, `src/app/version-review/page.tsx`, `src/app/reports/page.tsx`, `src/contexts/AnalysisContext.tsx`.
- Canonical integration database: `data/runtime/integration/sentinext.db` (read-only inspection; no writes).

Observed integration DB inventory at audit time: `reviews` 20,404 rows; `review_labels` 2,916; `analysis_results` 2; `analysis_runs` 12; `analysis_run_results` 6; `analysis_designs` 6; `version_events` 25; `llm_calls` 1,022; `progress` 2; `starred_games` 2. These counts are environment evidence, not product guarantees.

## Decision vocabulary

| Decision | Meaning |
|---|---|
| `DIRECTLY_SUPPORTED` | Existing canonical response contains the required value with an adequate current contract. |
| `SUPPORTED_WITH_FRONTEND_REFORMAT` | Existing response contains the value; UI can reshape/present it without a new backend contract. |
| `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` | Canonical data is sufficient, but a read-only response projection is needed for a clean or efficient UI contract. |
| `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` | Technically available, but denominator, coverage, sampling, or interpretation must be shown. |
| `NOT_SUPPORTED` | Current canonical data/API cannot support the requested visual faithfully. |
| `SHOULD_NOT_IMPLEMENT` | The visual implies a product/business contract that does not exist or conflicts with frozen semantics. |

## Canonical source and contract map

| Source | Current authoritative fields / payload |
|---|---|
| `reviews` | `app_id`, `review_id`, `data`, `timestamp_created`, `timestamp_updated`, `review_text`, developer-response and Steam-purchase enrichment fields. Raw `data` includes Steam review metadata such as language, `voted_up`, votes, author playtime and timestamps. |
| `review_labels` | `app_id`, `review_id`, `payload`, `label_origin`, `validated`, `taxonomy_version`, `provider`, `model_id`, `prompt_version`, input hash and truncation metadata. Payload carries taxonomy labels, issue/request flags and evidence snippets. |
| `analysis_results` | Compatibility/latest app snapshot: `status`, `run_id`, `metadata`, `insights`, `reviews`, stale/error fields. |
| `analysis_runs` | Durable run identity and lifecycle: `run_id`, `target_app_id`, `run_type`, `config`, `status`, `phase`, timestamps, requested/retrieved/deduplicated/population/classified/fallback/enriched counts, window fields, taxonomy/prompt/provider/model provenance. |
| `analysis_run_results` | Immutable general-analysis result keyed by exact `run_id`, with `metadata`, `insights`, `reviews`, hashes and completion time. |
| `analysis_designs` | Immutable `AnalysisDesign` snapshot keyed by `run_id`, including window, population rules, metrics, sensitivity and minimum-support rules. |
| `version_events` | `event_id`, `app_id`, title/date/type, description/source/URL, verification, published/effective date and range, anchor precision, source quality, event status and concurrent-event group. |
| `llm_calls` | Physical-call ledger: provider/model, purpose/phase, timestamps/latency, token counts, cache/retry/fallback/status/cost and workload/run identifiers. It is not a product metric source. |
| Dashboard API | `GET /analysis/{app_id}/dashboard?run=...` returns `readiness`, `metadata`, `insights`, `reviews`, `error`. Readiness explicitly separates raw reviews from validated semantic results. |
| General history/queue API | `GET /analysis-runs/recent`, `GET /analysis-runs/active`; backed by `storage.list_analysis_history`, exact `run_id` and durable `analysis_runs`. |
| Version Review API | `GET /version-events`, `POST /version-review/plan`, `POST /version-review/start`, `GET /runs/{run_id}`, `/result`, `/comparison`, `/analysis-design`, `/issues`, `/evidence`, `/recommendations`, `/emerging-topics`. |
| Reports API | `GET /reports/available-months/{app_id}`, `GET /reports/executive-summary/{app_id}`. Current report generation is a monthly export path, not a persisted report-history store. |

## A. Overview audit

The current Overview/Dashboard consumes `fetchDashboardPayload`, `fetchRecentAnalysisRuns`, starred games, and Steam context widgets. It does not have a canonical monitoring registry or alert contract.

| Component | Visual / business meaning | Required fields and current source/API | Exists / derivable / semantic or projection note | Decision |
|---|---|---|---|---|
| Recently analyzed games | Compact card/list | `app_id`, title, `run_id`, completed time, artwork; `GET /analysis-runs/recent`, joined `starred_games.name`, dashboard metadata | Mostly exists and is exposed; title/artwork can be missing for runs not synced to `starred_games`; exact reopen must use `app_id + run_id` | `DIRECTLY_SUPPORTED` |
| Completed analyses | KPI/count | completed general runs from `analysis_runs.status`, history endpoint | Exists durably; current history endpoint is limited/paginated but no aggregate count is returned | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |
| New reviews since previous run | Delta metric | current/previous run population or review fingerprints, exact run timestamps and review IDs | Raw reviews and run counts exist, but no current API exposes a previous-run delta contract; derivable only if two exact runs and populations are compared | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |
| Games needing attention | Alert/list | canonical alert rule, severity, source metric, acknowledged state | No alert table, alert rule, severity contract, or acknowledged state | `SHOULD_NOT_IMPLEMENT` |
| Notable topic shifts | Delta cards | comparable time/run populations, semantic labels, denominator, support and state | Version Review V2 has topic comparisons; general Overview has no cross-run topic-shift endpoint. Must not be inferred as alerts | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Recent analyses table | Table | history fields, status, run type, counts, exact link | `GET /analysis-runs/recent` directly exposes the core fields; result link can use `buildDashboardRunUrl` | `DIRECTLY_SUPPORTED` |
| Recent version reviews | Table/cards | completed version-review run, `run_id`, app, event, status, counts, exact link | History deliberately filters incomplete/empty version runs and exposes `metrics`; exact links are supported | `DIRECTLY_SUPPORTED` |
| Game cover/artwork | Header/card image | `metadata.header_image` or Steam details/header image | Dashboard metadata includes `header_image`; starred-game metadata may contain it; external Steam fallback is a presentation dependency | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Recommendation rate | KPI | `insights.recommendation` plus metric provenance | Exists; authoritative meaning is Steam `voted_up` share, not generic sentiment; `metric_provenance.recommendation_rate` records numerator/denominator | `DIRECTLY_SUPPORTED` |
| Last analyzed time | Metadata | immutable result `completed_at` or run `completed_at` | Run/history exposes completed time; app-level compatibility row has `updated_at`, which is not necessarily analysis completion time | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Games Monitored | KPI | monitored-game registry, monitoring cadence/last poll/status | Product stores/analyzes games; no monitoring semantics or cadence | `SHOULD_NOT_IMPLEMENT` |
| Alerts | Alert widget | alert contract and lifecycle | No canonical alert source | `SHOULD_NOT_IMPLEMENT` |
| Average Sentiment | KPI | defined sentiment metric and denominator | Existing `average_compound` is a Steam thumbs-up/down transform, while recommendation rate is separately defined; renaming/replacing with “average sentiment” would create semantic ambiguity | `SHOULD_NOT_IMPLEMENT` |
| Real-time monitoring widgets | live chart/status | polling/streaming monitoring source, freshness and alert semantics | Steam player/news endpoints are live context, not monitored review or product health state | `SHOULD_NOT_IMPLEMENT` |

## B. Game Analysis audit

The current Game Analysis page is fed primarily by `GET /analysis/{app_id}/dashboard?run=...`. The backend constructs `insights` in `prepare_insights`; the frontend also derives filtered review views and some segment displays. `Trend data` is already present as weekly records when timestamps are available, but it is not a general-purpose arbitrary time-series API.

| Component | Visual / business meaning | Required fields and current source/API | Exists / derivable / semantic or projection note | Decision |
|---|---|---|---|---|
| Current recommendation rate | Metric | `voted_up` numerator/denominator, provenance | `insights.recommendation` and `metric_provenance.recommendation_rate` are exposed; denominator is raw analysis population | `DIRECTLY_SUPPORTED` |
| Total review count | Metric | requested/retrieved/deduplicated/analysis population counts | `metadata`, `readiness`, and run fields expose several distinct counts; UI must label which one | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Review volume by day | Line/bar chart | `reviews.timestamp_created`, exact population/window, day bucket | Timestamp is canonical and deterministic; current `insights.trend` is weekly, not daily; daily endpoint/projection is absent | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |
| Recommendation rate by day | Line chart | daily `voted_up` numerator/denominator | Deterministically derivable from raw reviews; current API only exposes weekly trend and frontend type `TrendPoint` | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |
| Language distribution | Bar/donut | `language`, count, recommendation numerator/denominator | `insights.player_segments.language` exposes top 15 and total language count; raw sample also carries language; counts may describe returned/sample population | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Playtime/cohort distribution | Bar/table | author playtime, bucket rule, count and recommendation rate | `insights.player_segments.experience_level`, `purchase_type`, `engagement_topics`, and `playtime` expose deterministic buckets; zero/missing playtime is a caveat | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Topic ranking | Ranked bar/list | semantic subcategory labels and support count | `insights.subcategory_insights` and `category_breakdown` expose topic counts; labels are model-derived and may be multi-label | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Issue ranking | Ranked bar/list | issue labels, classified denominator, support | `subcategory_insights.issue_count`, `llm_issue_subcategories`, metric provenance support it; must use validated classified population, not all raw reviews | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Request ranking | Ranked bar/list | request labels, classified denominator, support | `subcategory_insights.request_count` and request labels exist; same coverage/multi-label caveat | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Positive-topic ranking | Ranked bar/list | positive topic definition, labels, denominator | General taxonomy labels and recommendation rates exist, but “positive topic” is not a separate canonical contract; deriving it from recommended reviews is a presentation choice | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Topic prevalence by day/week | Stacked/line chart | timestamp + semantic label + semantic denominator | Technically derivable from `reviews` + `review_labels`; current API lacks series. Denominator must be classified semantic population and must not be called all-player prevalence | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |
| Recommendation trend | Line chart | weekly/daily raw recommendation numerator/denominator | `insights.trend` is exposed from `recommended_share_over_time`, currently weekly `W-SUN`; safe if period and denominator are shown | `DIRECTLY_SUPPORTED` |
| Review-volume trend | Line/bar chart | trend period and review count | `insights.trend[].reviews` exists; currently weekly and can be reformatted directly | `DIRECTLY_SUPPORTED` |
| Evidence quotes | Evidence block | quote, review ID, taxonomy key, verification status, source | `insights.subcategory_insights.*_evidence` is verified through `build_evidence`; dedicated `GET /analysis/{app_id}/evidence` also exposes paged verified evidence | `DIRECTLY_SUPPORTED` |
| Developer/update context | Context/header/news block | developer response, Steam news, event/date/source | Review enrichment fields and Steam news/context endpoints exist; update context is external/live and not automatically causal | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Game artwork/header | Header/artwork | `metadata.header_image`, Steam details | Exposed in analysis metadata and Steam details response | `DIRECTLY_SUPPORTED` |
| Source/run/provenance details | Evidence/provenance block | `run_id`, source/mode, window, cutoff, provider/model, taxonomy/prompt, hashes, coverage | Metadata/readiness and `analysis_runs` contain most fields; dashboard response does not expose every run column in one response, so detail projection may be useful | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |

### Game Analysis time-series rules

| Series | Raw source | Bucket | Denominator | Minimum support / caveat | Current API |
|---|---|---|---|---|---|
| Review volume | `reviews.timestamp_created` / immutable result population | Day or current weekly `W-SUN` | Number of raw reviews in the bucket | Display actual counts; avoid interpreting volume as player population | Weekly `insights.trend[].reviews` only |
| Recommendation rate | `reviews.voted_up` | Day/week | `count(voted_up=true) / count(reviews)` in bucket | Show bucket count; small buckets should be suppressed/flagged | Weekly `insights.trend[].recommendation_rate` |
| Topic prevalence | `reviews.timestamp_created` joined to `review_labels.payload` | Day/week | Topic-supporting classified reviews / classified semantic population in bucket | Require labels with compatible taxonomy/version; multi-label means topic rates can sum above 100%; not all-player prevalence | No current series endpoint |
| Issue/request rate | `review_labels` issue/request fields joined to review population | Day/week | Validated classified reviews containing issue/request / validated classified population | State coverage and fallback/label origin; do not use raw review denominator silently | Aggregate rates exist; no time series |

## C. Version Review audit

Version Review V2 is the strongest current source for comparison UI. Immutable configuration is stored in `analysis_runs.config`; immutable `AnalysisDesign` is stored in `analysis_designs`; V2 metrics are stored in `analysis_runs.metrics` and returned by `/runs/{run_id}/comparison`.

| Component | Visual / business meaning | Required fields and current source/API | Exists / derivable / semantic or projection note | Decision |
|---|---|---|---|---|
| Previous Version vs Current Version | Comparison header/table | event A/B IDs, names, dates, ordering, status | `version_events`, run config, `version_review_v2.event_a_id/event_b_id` and frontend types expose it | `DIRECTLY_SUPPORTED` |
| Event titles | Header/labels | `event_name` | `version_events` and `VersionEventResponse` expose it | `DIRECTLY_SUPPORTED` |
| Effective dates | Timeline/header | effective/published date or range, anchor precision | Schema and API include `effective_at`, range, `anchor_precision`; may be unresolved/null | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| 3/7/14 day filter | Filter control | window selection and recomputed comparison | Frontend offers 3/7/14; `/runs/{run_id}/comparison?window_days=` validates and deterministically rebuilds V2 result | `DIRECTLY_SUPPORTED` |
| Custom window | Filter control | arbitrary window and coverage recalculation | Current API intentionally accepts only 3, 7, 14 for V2 comparison; custom window is not exposed as a stable current contract | `NOT_SUPPORTED` |
| Raw review count A/B | Comparison metric | `raw_metrics_a/b.reviews` | V2 immutable/result response exposes it | `DIRECTLY_SUPPORTED` |
| Reviews/day A/B | Comparison metric | `raw_metrics_a/b.reviews_per_day` | V2 response exposes it | `DIRECTLY_SUPPORTED` |
| Recommendation rate A/B | Comparison metric | `raw_metrics_a/b.recommendation_rate` | V2 response exposes it; raw Steam recommendation semantics | `DIRECTLY_SUPPORTED` |
| Recommendation delta | Delta visualization | `raw_metric_deltas.recommendation_rate_pp` | V2 response exposes percentage-point delta | `DIRECTLY_SUPPORTED` |
| Semantic sample A/B | Population strip | `a_semantic_sample_count`, `b_semantic_sample_count` | V2 response exposes counts; sample method/seed also in `population_contract`/design | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Classified count A/B | Coverage metric | `a_classified_count`, `b_classified_count` | V2 response includes fields, but current builder initializes them to 0 in the shown comparison path; run population contract may contain related counts | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Topic delta | Delta table/chart | `topic_comparisons` support/rate/delta/state/direction | V2 response directly exposes it; topic is semantic and multi-label | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Request delta | Delta table/chart | `request_comparisons` | V2 response directly exposes it with same denominator caveat | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Positive-signal delta | Delta table/chart | `positive_comparisons` | V2 response directly exposes it; positive signal semantics must be retained | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| NEW / INCREASED / DECREASED / PERSISTENT / STABLE / INSUFFICIENT | State badges | `topic_comparisons[].state`, coverage/support rules | `state` is in V2 result; UI must preserve `INSUFFICIENT` and coverage gate instead of forcing a direction | `DIRECTLY_SUPPORTED` |
| Paired evidence | Two-column evidence block | topic ID, evidence ID, review ID, snippet A/B | `paired_evidence` exists in V2 result; direct quote existence is not semantic accuracy | `DIRECTLY_SUPPORTED` |
| Window sensitivity chart | Multi-line/table | `window_sensitivity` by 3/7/14 with coverage and deltas | V2 result exposes it; safe as robustness display, not as a new conclusion | `DIRECTLY_SUPPORTED` |
| Robustness status | Status card | coverage gate, comparison status, sensitivity and evidence grade | `coverage_gate`, `comparison_status`, `adaptive_analysis.evidence_grade`, design rules exist across metrics/design | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Emerging topic candidates | Candidate list | candidate, growth/support, review status, human review flag | `/runs/{run_id}/emerging-topics` returns candidates and `human_review_required`; candidates are not approved findings | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Coverage status | Coverage badge | A/B coverage status, raw/semantic/classified counts | `a_coverage_status`, `b_coverage_status`, `coverage_gate`, population contract exist | `DIRECTLY_SUPPORTED` |
| Methodology/provenance disclosure | Disclosure block | schema/algorithm/design, event source, population rules, taxonomy/prompt, run | `analysis_designs`, run config and run provenance expose these; may need read-only detail projection for one compact response | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |

### Version Review V2 immutable-result boundary

Already part of the V2 result contract: A/B raw metrics, raw deltas, semantic sample counts, topic/request/positive comparisons, paired evidence, window sensitivity, emerging candidates, coverage statuses and coverage gate. The run/config/design contract separately preserves event identity, windows, semantic limit, taxonomy, prompt, population rules and minimum support.

Still requiring aggregation or projection for a polished UI: compact event metadata joined from `version_events`; a single provenance/coverage strip; normalized classified counts when the current V2 builder leaves them at zero; and any arbitrary/custom-window series. These are presentation projections only if they preserve the immutable result and do not rewrite its semantics.

## D. Reports audit

Reports currently select a starred game, fetch its analysis result, show a five-question snapshot/action/source card, enumerate available review months, and download a generated monthly PDF. The report endpoint can optionally include an LLM summary, but the UI does not need a new call for the listed deterministic modules.

| Component | Visual / business meaning | Required fields and current source/API | Exists / derivable / semantic or projection note | Decision |
|---|---|---|---|---|
| Executive summary | Summary block | `five_questions.current_snapshot`, actions, risks, evidence | Current analysis result exposes `insights.five_questions`, risk and evidence; report UI consumes snapshot/action/source | `DIRECTLY_SUPPORTED` |
| Key changes | Summary/list | current snapshot/what changed signals or report insights | Five Questions includes `what_changed`, `what_matters`, snapshot; report endpoint also builds monthly insights | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Verified evidence | Evidence block | verified quote/source/review ID | Analysis insights and evidence endpoint provide verified evidence; report generator can consume labels/evidence | `DIRECTLY_SUPPORTED` |
| Action recommendations | Action list | action class/title/rationale/validation plan/evidence | `five_questions.recommended_actions` and Version Review recommendations exist | `DIRECTLY_SUPPORTED` |
| Report metadata | Metadata table | app, run, window/month, counts, source/mode | analysis metadata and report month response provide core values; generated report metadata is not a separate persisted object | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Recommendation trend | Chart | trend series and denominator | `insights.trend` is exposed and report generator can derive monthly view from raw reviews | `DIRECTLY_SUPPORTED` |
| Topic-delta summary | Delta list | V2 topic comparisons or aggregate topic signals | Available for Version Review run; not guaranteed for every general report | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |
| Export history | List/table | persisted report ID, generated time, format, path/status | No report-history table or endpoint; `lastGeneratedAt` is frontend session state only | `NOT_SUPPORTED` |
| Generated-at/provider/model/run provenance | Metadata/provenance | immutable generated time, provider/model, run ID, prompt/taxonomy | Run fields and metadata contain provenance; PDF generation time is not durably stored as an export record | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |

## E. Global Analysis Queue audit

The queue is a projection of durable state. `analysis_runs` is authoritative for saved runs; `progress` is the current app-level progress source for general analysis. Frontend `AnalysisContext` also maintains an in-memory queue for newly submitted work, so reload-safe display must be based on the active-history endpoint rather than that memory alone.

| Component | Visual / business meaning | Required fields and current source/API | Exists / derivable / semantic or projection note | Decision |
|---|---|---|---|---|
| Run type | Queue label | `analysis_runs.run_type` | History and run response expose general/version type | `DIRECTLY_SUPPORTED` |
| Game | Queue identity | `target_app_id`, title | `analysis_runs.target_app_id`; history joins `starred_games.name`; unknown names may fall back to app ID | `DIRECTLY_SUPPORTED` |
| Phase | Progress step | `analysis_runs.phase` or `progress.phase` | Both exist; they are different lifecycle layers and should not be conflated | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Progress current/total | Progress bar | `progress.processed/total`, `fetched_count`; run counts | Current progress endpoint exposes current/total for app-level general work; version lifecycle counts are in run fields/metrics | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| ETA | Progress estimate | `progress.eta_seconds` | Exists for general progress; can be null; no reliable version-review ETA contract | `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` |
| Status | Badge/state | durable run status and error | `analysis_runs.status`, `error`, readiness states, active-history endpoint | `DIRECTLY_SUPPORTED` |
| Exact result link | Action/link | `app_id + run_id`, `run` URL parameter | `buildDashboardRunUrl` and `buildVersionReviewRunUrl` use exact identity | `DIRECTLY_SUPPORTED` |
| Persisted/reload-safe state | Queue/history behavior | durable run plus result availability | `analysis_runs` and immutable result table support this; in-memory queue alone does not, so UI must prefer API after reload | `SUPPORTED_WITH_FRONTEND_REFORMAT` |

## F. Recent Analysis / Recent Version Review audit

Current source is `GET /analysis-runs/recent`, backed by `storage.list_analysis_history`. The endpoint intentionally hides incomplete/empty Version Review records and reports exact run identity.

| Component | Visual / business meaning | Required fields and current source/API | Exists / derivable / semantic or projection note | Decision |
|---|---|---|---|---|
| Exact `app_id + run_id` | Reopen identity | both IDs | Directly returned and required by governance; use `run` URL parameter | `DIRECTLY_SUPPORTED` |
| Game cover/title | Compact card | title/artwork | Title is joined from starred games; artwork is not returned by history and needs metadata lookup/projection | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |
| Run type | Card badge | `run_type` | Directly returned | `DIRECTLY_SUPPORTED` |
| Analysis mode | Card metadata | `analysis_mode` | Derived from immutable config and returned | `DIRECTLY_SUPPORTED` |
| Completed time | Card metadata | `completed_at` | Returned for run history; absent for active runs by design | `DIRECTLY_SUPPORTED` |
| Review/sample/classified counts | Compact metrics | requested/population/classified; version population contract | History returns requested/population/classified; version metrics may expose raw/semantic/classified counts; labels must distinguish them | `SUPPORTED_WITH_FRONTEND_REFORMAT` |
| Recommendation rate | Compact metric | raw rate from result/metrics | General history does not return recommendation rate; Version Review metrics may contain it; needs projection or detail fetch | `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` |
| Exact reopen link | Card action | exact run URL | Supported by dashboard/version-review URL builders | `DIRECTLY_SUPPORTED` |

Safe compact-card fields: `app_id`, `run_id`, title, run type, analysis mode, completed time, status, result availability, population/classified counts with explicit labels, and exact reopen link. Keep detailed evidence, provider cost, taxonomy/prompt, window sensitivity and semantic caveats in the detail view rather than compact cards.

## G. Data-source and semantic safety findings

1. `voted_up` is the current recommendation signal. The code defines `recommendation_rate` as Steam recommended reviews share (`metric_provenance.py`), so it must not be relabeled as generic “sentiment”.
2. Raw review count, retrieved count, deduplicated count, analysis population, semantic sample and classified count are separate concepts. The UI should never collapse them into “reviews analyzed”.
3. Topic, issue and request metrics are multi-label semantic observations. Their denominators are classified/validated populations, not automatically all raw reviews. Topic percentages may sum above 100%.
4. `review_labels.label_origin`, `validated`, taxonomy/prompt/model and input hashes preserve provenance. Fallback or legacy labels require explicit treatment and must not silently become validated KPI population.
5. Review timestamps support deterministic temporal aggregation. A temporal topic chart is technically possible, but its denominator and minimum-support rule must be visible.
6. Version Review event identity is not equivalent to a causal intervention. `version_events` has source quality, event status and anchor precision specifically because event timing may be unresolved or confounded.
7. Verified evidence means the quote exists in the source review and passes deterministic verification. It does not prove classification accuracy or causality.
8. Steam player count, Steam news, achievements and price endpoints are live context endpoints. They are not a canonical “monitoring” or “alert” data model.

## H. Recommended Read-Only Presentation Projections

These are candidates only. None is implemented by this audit.

| Projection | Input sources | Exact formula / response shape | Cacheability / cost | Caveat |
|---|---|---|---|---|
| `daily_review_volume` | Immutable general result reviews or canonical `reviews.timestamp_created`, plus run population/window | `{run_id, bucket: "day", points:[{period, reviews, population_scope}]}`; `reviews = count(review.timestamp_created in day)` | Deterministic, cache by `run_id + filter`; low/medium CPU depending on population size | Counts are review observations, not players; preserve exact run scope and timezone/bucket definition |
| `daily_recommendation_rate` | Same reviews with `voted_up` | `{period, recommended, reviews, recommendation_rate}` where `rate = recommended / reviews` | Deterministic and cacheable by run/filter | Show bucket denominator and suppress/flag low support; this is recommendation, not average sentiment |
| `weekly_topic_prevalence` | Reviews joined to `review_labels.payload`, compatible taxonomy/prompt, label provenance | `{period, topic_id, support_count, classified_denominator, rate, label_scope}` where `rate = topic-supporting classified reviews / classified reviews in bucket` | Deterministic; cache by exact run and taxonomy/provenance | Multi-label rates are not mutually exclusive and do not represent all-player prevalence |
| `recent_analysis_summary` | `analysis_runs`, `analysis_run_results`, `starred_games`, result metadata/insights | `{app_id, run_id, title, artwork, run_type, mode, completed_at, population, classified, recommendation_rate, exact_url}` | Deterministic join; cache by latest run IDs; low cost | Must not use “latest” as an approximate reopen identity; retain exact `run_id` |
| `version_comparison_population_strip` | `analysis_runs.config`, `analysis_runs.metrics.version_review_v2`, `analysis_designs`, `version_events` | `{run_id, event_a, event_b, raw_count_a/b, semantic_sample_a/b, classified_a/b, coverage_a/b, window_days, gate}` | Deterministic; cache by run/window; low cost | If a field is absent or zero because current builder did not populate it, display unknown/insufficient rather than infer |
| `completed_analysis_count` | `analysis_runs` | `{scope, completed_general, completed_version_review, generated_at}` | Deterministic aggregate; cache briefly | Define whether duplicate/legacy/hidden version runs count; endpoint currently has no aggregate contract |
| `new_reviews_since_previous_run` | Two exact immutable result populations/review IDs and run timestamps | `{current_run_id, previous_run_id, new_review_count, changed_review_count, population_rule}` | Deterministic but potentially medium cost; cache by run pair | Requires an explicit previous-run selection rule; not “new since last API fetch” |
| `provenance_strip` | `analysis_runs`, `analysis_designs`, immutable result metadata, `review_labels` provenance | `{run_id, source, mode, window, counts, taxonomy, prompt, provider, model, design_id, hashes}` | Deterministic, highly cacheable | This is disclosure, not a quality score; never imply provider/model proves accuracy |

Projection boundary: all candidates above are read-only, deterministic and do not require an LLM call or schema migration. They must not alter the immutable result or analytical denominator.

## I. Final matrix

The matrix contains 50 audited components. “DB support” refers to canonical data existence; “API support” refers to a current response contract, not merely an internal helper.

| Page | Component | DB support | API support | Derivable | New projection needed | Analytical risk | Final decision |
|---|---|---:|---:|---:|---:|---|---|
| Overview | Recently analyzed games | Yes | Partial | Yes | Sometimes | exact run/title/artwork joins | DIRECTLY_SUPPORTED |
| Overview | Completed analyses | Yes | No aggregate | Yes | Yes | definition of completed scope | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Overview | New reviews since previous run | Yes | No | Yes, exact pair | Yes | previous-run/population rule | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Overview | Games needing attention | No | No | No | No | invented alert contract | SHOULD_NOT_IMPLEMENT |
| Overview | Notable topic shifts | Partial | Version only | Partial | Maybe | semantic denominator/support | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Overview | Recent analyses table | Yes | Yes | Yes | No | explicit count labels | DIRECTLY_SUPPORTED |
| Overview | Recent version reviews | Yes | Yes | Yes | No | incomplete records intentionally hidden | DIRECTLY_SUPPORTED |
| Overview | Game cover/artwork | Partial | Partial | Yes | Sometimes | external Steam fallback | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Overview | Recommendation rate | Yes | Yes | Yes | No | raw recommendation, not sentiment | DIRECTLY_SUPPORTED |
| Overview | Last analyzed time | Yes | Yes | Yes | No | `updated_at` vs `completed_at` | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Overview | Games Monitored | No | No | No | No | false monitoring semantics | SHOULD_NOT_IMPLEMENT |
| Overview | Alerts | No | No | No | No | no alert lifecycle | SHOULD_NOT_IMPLEMENT |
| Overview | Average Sentiment | Partial | Ambiguous | Yes | No | prohibited relabeling | SHOULD_NOT_IMPLEMENT |
| Overview | Real-time monitoring widgets | No | Context only | No | No | live context ≠ monitoring | SHOULD_NOT_IMPLEMENT |
| Game Analysis | Current recommendation rate | Yes | Yes | Yes | No | raw denominator | DIRECTLY_SUPPORTED |
| Game Analysis | Total review count | Yes | Yes | Yes | No | multiple population counts | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Game Analysis | Review volume by day | Yes | No | Yes | Yes | bucket/timezone/player inference | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Game Analysis | Recommendation rate by day | Yes | No | Yes | Yes | low bucket support | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Game Analysis | Language distribution | Yes | Yes | Yes | No | sample/population scope | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Game Analysis | Playtime/cohort distribution | Yes | Yes | Yes | No | missing/zero playtime | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Game Analysis | Topic ranking | Yes | Yes | Yes | No | model-derived multi-label | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Game Analysis | Issue ranking | Yes | Yes | Yes | No | classified denominator | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Game Analysis | Request ranking | Yes | Yes | Yes | No | classified denominator | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Game Analysis | Positive-topic ranking | Partial | Partial | Yes | No | no dedicated positive-topic contract | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Game Analysis | Topic prevalence by day/week | Yes | No | Yes | Yes | semantic denominator/multi-label | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Game Analysis | Recommendation trend | Yes | Yes | Yes | No | weekly bucket denominator | DIRECTLY_SUPPORTED |
| Game Analysis | Review-volume trend | Yes | Yes | Yes | No | review observations only | DIRECTLY_SUPPORTED |
| Game Analysis | Evidence quotes | Yes | Yes | Yes | No | verification ≠ accuracy/causality | DIRECTLY_SUPPORTED |
| Game Analysis | Developer/update context | Partial | Yes | Yes | No | external context/causality | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Game Analysis | Game artwork/header | Yes/Steam | Yes | Yes | No | external availability | DIRECTLY_SUPPORTED |
| Game Analysis | Source/run/provenance | Yes | Partial | Yes | Yes | disclosure completeness | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Version Review | Previous vs current | Yes | Yes | Yes | No | event ordering/status | DIRECTLY_SUPPORTED |
| Version Review | Event titles | Yes | Yes | Yes | No | source quality | DIRECTLY_SUPPORTED |
| Version Review | Effective dates | Yes | Yes | Yes | No | unresolved anchor | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Version Review | 3/7/14 filter | Yes | Yes | Yes | No | coverage recomputation | DIRECTLY_SUPPORTED |
| Version Review | Custom window | Partial | No | No stable contract | No | semantic comparability | NOT_SUPPORTED |
| Version Review | Raw count A/B | Yes | Yes | Yes | No | coverage | DIRECTLY_SUPPORTED |
| Version Review | Reviews/day A/B | Yes | Yes | Yes | No | window definition | DIRECTLY_SUPPORTED |
| Version Review | Recommendation A/B | Yes | Yes | Yes | No | raw recommendation | DIRECTLY_SUPPORTED |
| Version Review | Recommendation delta | Yes | Yes | Yes | No | percentage-point wording | DIRECTLY_SUPPORTED |
| Version Review | Semantic sample A/B | Yes | Yes | Yes | No | sample ≠ classified | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Version Review | Classified count A/B | Partial | Partial | Yes | Maybe | current V2 zero/default path | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Version Review | Topic/request/positive deltas | Yes | Yes | Yes | No | semantic support/denominator | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Version Review | State badges | Yes | Yes | Yes | No | preserve insufficient | DIRECTLY_SUPPORTED |
| Version Review | Paired evidence | Yes | Yes | Yes | No | quote verification limits | DIRECTLY_SUPPORTED |
| Version Review | Window sensitivity | Yes | Yes | Yes | No | robustness not causality | DIRECTLY_SUPPORTED |
| Version Review | Robustness status | Yes | Partial | Yes | Maybe | evidence grade semantics | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Version Review | Emerging candidates | Yes | Yes | Yes | No | human review required | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Version Review | Coverage status | Yes | Yes | Yes | No | coverage ≠ accuracy | DIRECTLY_SUPPORTED |
| Version Review | Methodology/provenance | Yes | Partial | Yes | Yes | immutable contract disclosure | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Reports | Executive summary | Yes | Yes | Yes | No | observed vs inferred | DIRECTLY_SUPPORTED |
| Reports | Key changes | Yes | Partial | Yes | No | scope depends on run/window | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Reports | Verified evidence | Yes | Yes | Yes | No | verified quote limits | DIRECTLY_SUPPORTED |
| Reports | Action recommendations | Yes | Yes | Yes | No | recommendation is not causal proof | DIRECTLY_SUPPORTED |
| Reports | Report metadata | Yes | Partial | Yes | No | generated/export time distinction | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Reports | Recommendation trend | Yes | Yes | Yes | No | raw rate semantics | DIRECTLY_SUPPORTED |
| Reports | Topic-delta summary | Partial | Version only | Yes | Yes | not every general report has V2 comparison | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Reports | Export history | No | No | No | No | no persistence contract | NOT_SUPPORTED |
| Reports | Generated/provider/model/run provenance | Yes | Partial | Yes | Yes | export timestamp not durable | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Global Queue | Run type/game/phase/status | Yes | Yes | Yes | No | lifecycle layer distinction | DIRECTLY_SUPPORTED |
| Global Queue | Progress current/total/ETA | Yes | Partial | Yes | No | ETA can be null/version differs | SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION |
| Global Queue | Exact result link | Yes | Yes | Yes | No | exact identity required | DIRECTLY_SUPPORTED |
| Global Queue | Persisted/reload-safe state | Yes | Yes | Yes | No | in-memory queue must not be authority | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Recent History | Exact identity | Yes | Yes | Yes | No | none if `run` used | DIRECTLY_SUPPORTED |
| Recent History | Cover/title | Partial | Partial | Yes | Yes | join/artwork availability | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Recent History | Type/mode/time | Yes | Yes | Yes | No | completed time may be null | DIRECTLY_SUPPORTED |
| Recent History | Counts | Yes | Yes | Yes | No | requested/raw/semantic/classified labels | SUPPORTED_WITH_FRONTEND_REFORMAT |
| Recent History | Recommendation rate | Partial | Partial | Yes | Yes | history response omits general rate | SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION |
| Recent History | Exact reopen link | Yes | Yes | Yes | No | exact app/run pair | DIRECTLY_SUPPORTED |

## Totals and implementation boundary

The 69 matrix rows above are the audited component count. Counts below use the final decision assigned to each row; composite rows are counted once.

| Decision | Count | Share |
|---|---:|---:|
| `DIRECTLY_SUPPORTED` | 29 | 42.03% |
| `SUPPORTED_WITH_FRONTEND_REFORMAT` | 13 | 18.84% |
| `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` | 11 | 15.94% |
| `SUPPORTED_BUT_NEEDS_SEMANTIC_CAUTION` | 9 | 13.04% |
| `NOT_SUPPORTED` | 2 | 2.90% |
| `SHOULD_NOT_IMPLEMENT` | 5 | 7.25% |
| Total | 69 | 100% |

For mutually exclusive implementation planning:

- Current API as-is: `DIRECTLY_SUPPORTED` + `SUPPORTED_WITH_FRONTEND_REFORMAT` = 42/69 = **60.87%**.
- Requires only deterministic presentation projection: `SUPPORTED_WITH_DETERMINISTIC_BACKEND_PROJECTION` = 11/69 = **15.94%**.
- Requires semantic caution but no new analytical contract by itself: 9/69 = **13.04%**.
- Not supported: 2/69 = **2.90%**.
- Should not implement under current product semantics: 5/69 = **7.25%**.
- The implementable surface without changing analytical semantics is therefore 62/69 = **89.86%**, provided semantic-caution components retain coverage/denominator disclosures. The remaining 7.25% is not a recommendation to expand methodology: it is custom-window, export-history, and explicitly unsupported product-contract functionality.

### Mockup ideas to remove or defer

Remove or defer:

- `Games Monitored`, unless a monitoring registry, cadence and freshness contract is introduced.
- `Alerts`, unless alert rules, severity, acknowledgement and lifecycle are introduced.
- `Average Sentiment` as a renamed recommendation metric.
- Real-time review/product-health monitoring widgets; Steam live context is not monitoring.
- Arbitrary custom Version Review windows; current V2 contract is explicitly 3/7/14 days.
- Export history cards; there is no durable export-history source.
- Any topic chart labelled “all-player prevalence” unless the semantic population and support rules justify that wording.

### Classification of the redesign

The redesign should not remain described as purely “visual-only” if it adds daily series, recent-run summary cards, aggregate completed-analysis counts, or provenance/coverage strips. The accurate classification is:

> **visual redesign + read-only deterministic presentation projections**

This remains within the UI boundary only if projections are deterministic, read-only, do not call an LLM, do not change denominator/methodology, and preserve exact run identity and provenance.

## What was not changed

- No source code, API route, response model, database schema, migration, taxonomy, prompt, Evidence Grade, Version Review logic, run lifecycle, or runtime data was changed.
- No presentation projection was implemented.
- No provider or LLM call was made.
- No canonical database row was modified.
