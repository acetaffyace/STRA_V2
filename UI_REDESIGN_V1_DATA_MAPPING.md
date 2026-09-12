# SentiNext UI Redesign V1 — Data Mapping Plan

Status: `PLAN_UPDATED — STOP BEFORE IMPLEMENTATION`  
Classification: **Visual Redesign + Read-Only Deterministic Presentation Projections**  
Authority: `UI_DATA_CAPABILITY_AUDIT.md`  
Scope: Phase 1 current API capabilities; Phase 2 projection identification only.

This document is the implementation/data boundary for UI Redesign V1. It maps rendered components to current response fields and preserves the frozen analytical contract. It does not implement UI changes, API changes, database changes, or presentation projections.

## Non-negotiable product boundaries

The redesign must:

- preserve Steam `voted_up` / recommendation semantics;
- call the metric **Recommendation Rate**, never “Average Sentiment”;
- show raw population, semantic sample, classified population and evidence population as different concepts;
- preserve exact reopening by `app_id + run_id`, using the `run` URL parameter;
- show unknown/unavailable states rather than inventing zeros;
- preserve coverage, denominator and evidence limitations;
- keep Version Review windows to **3 / 7 / 14 days**;
- treat verified quotes as verified source evidence, not proof of semantic accuracy or causality.

The mockup elements explicitly removed/deferred are:

- `Games Monitored`;
- `Alerts`;
- `Average Sentiment`;
- real-time monitoring widgets;
- custom Version Review windows;
- report export history.

## Authoritative current API inputs

| API | Current response used by V1 |
|---|---|
| `GET /analysis/{app_id}/dashboard?run=...` | `readiness`, `metadata`, `insights`, `reviews`, `error` |
| `GET /analysis-runs/recent` | exact run history for Overview and Recent History |
| `GET /analysis-runs/active` | durable active queue projection |
| `GET /progress/{app_id}` | general-analysis progress and ETA |
| `GET /version-events?app_id=...` | event catalog and event metadata |
| `POST /version-review/plan` | deterministic event/window/population plan |
| `POST /version-review/start` | run identity and selected plan |
| `GET /runs/{run_id}` | exact Version Review run and metrics |
| `GET /runs/{run_id}/comparison?window_days=3|7|14` | V2 A/B comparison for approved windows |
| `GET /runs/{run_id}/evidence` | Version Review evidence cards |
| `GET /runs/{run_id}/emerging-topics` | candidate topics requiring human review |
| `GET /reports/available-months/{app_id}` | report month selector and raw review counts |
| `GET /reports/executive-summary/{app_id}` | existing monthly PDF export; no export-history contract |
| Steam context endpoints | artwork, news/update context, price, achievements and player count; context only, not monitoring metrics |

## Phase 1 — current API only

### 1. Overview

| Rendered component | Exact API field / source | Business meaning | Denominator | Fallback / unknown behavior |
|---|---|---|---|---|
| Page readiness state | `dashboard.readiness.state` | Whether reviews, analysis, running state or incompatible result is available | State, not a metric | Render the explicit readiness state; never convert absent analysis to zero |
| Recently analyzed game card | `/analysis-runs/recent[]`: `app_id`, `run_id`, `app_name`, `run_type`, `analysis_mode`, `status`, `completed_at`, `result_available` | A saved exact analysis result available to reopen | One history row per exact run | If `app_name` is missing, display app ID; if no result, show unavailable/reopen disabled |
| Recent analyses table | Same history fields plus `requested_review_count`, `analysis_population_count`, `classified_count` | Recent durable analysis activity | Per run; fields have distinct scopes | Label each count explicitly; null means unknown, not zero |
| Recent Version Review table | History rows where `run_type = version_review`, `status = completed`, `result_available = true` | Completed evidence-backed version reviews | Per exact Version Review run | Follow backend filtering; do not display incomplete/empty rows as completed |
| Completed analyses count | Current API has rows, not an aggregate field; count completed eligible rows from `/analysis-runs/recent` only within returned scope | Number of completed runs in the displayed history scope | Completed eligible history rows | If pagination/scope is not explicit, label as “shown recent completed runs”; a global KPI is Phase 2 projection |
| Game artwork | `dashboard.metadata.header_image`; fallback Steam details `header_image`; history has no artwork field | Steam game header artwork | N/A | If missing, use neutral artwork placeholder; never block analytical content |
| Recommendation Rate | `dashboard.insights.recommendation`; authoritative `dashboard.insights.metric_provenance.recommendation_rate` | Share of raw review population with Steam `voted_up = true` | Raw analysis population; provenance provides numerator/denominator | If value or provenance is absent, show `—` and “unavailable”; do not call it sentiment |
| Last analyzed time | `/analysis-runs/recent[].completed_at`; exact run preferred | Completion time of that run | Per exact run | If null, show “Completion time unavailable”; do not substitute current time or compatibility `updated_at` silently |
| Coverage strip | `dashboard.readiness.review_count`, `classified_count`, `classification_coverage`; `insights.metric_provenance.classification_coverage` | Difference between raw population and validated semantic classification | `classified / population` | Show “coverage”, never “accuracy”; preserve unknown status |
| Games Monitored | **No field** | Unsupported monitoring concept | N/A | Remove/defer entirely |
| Alerts | **No field/contract** | Unsupported alert lifecycle | N/A | Remove/defer entirely |
| Average Sentiment | **No approved field under this label** | Would misname recommendation semantics | N/A | Remove/defer; use Recommendation Rate only |
| Real-time monitoring widgets | Steam live context only, no monitoring contract | Unsupported product-health monitoring | N/A | Remove/defer entirely |

### 2. Game Analysis

| Rendered component | Exact API field / source | Business meaning | Denominator | Fallback / unknown behavior |
|---|---|---|---|---|
| Game header/title | `dashboard.metadata.app_id`, `dashboard.metadata.header_image`; Steam details `name` | Identity of analyzed Steam game | N/A | App ID remains visible if title unavailable; artwork placeholder if image unavailable |
| Run/provenance header | `dashboard.metadata.run_id`, `mode`, `source`, `window_start`, `window_end`, `data_cutoff`, `classification_population`, `evidence_population`, `dashboard.readiness.result_source` | Scope and origin of displayed result | Per exact run | Missing provenance renders as “Unknown”, not inferred from current runtime |
| Current Recommendation Rate card | `insights.recommendation`; `metric_provenance.recommendation_rate.{numerator,denominator,value}` | Steam recommendation share | Raw analysis population | Show value plus numerator/denominator when available; `—` if missing |
| Review population card | `metadata.requested`, `retrieved`, `retrieved_count`, `deduplicated_count`, `analysis_population_count`; readiness review count | Requested/retrieved/deduplicated/analysis populations | Field-specific; never merge labels | Present separate labeled rows; unknown fields remain `—` |
| Weekly recommendation trend | `insights.trend[].period`, `recommendation_rate`, `reviews` | Weekly Steam recommendation share over observed review buckets | Reviews in each weekly bucket | Current API uses weekly `W-SUN`; show bucket review count; empty series gets “Trend unavailable” |
| Weekly review-volume trend | `insights.trend[].period`, `reviews` | Weekly count of observed reviews | Raw reviews in each bucket | Show counts, not player volume; empty series gets “Trend unavailable” |
| Language distribution | `insights.player_segments.language.languages[].language`, `count`, `recommendation_rate`, `issue_count`; `total_languages` | Distribution and recommendation rate by review language | Reviews in each language segment; semantic issue count uses classified labels | Show top-15 scope if returned; missing language is unknown, not a language bucket invented by UI |
| Player/cohort distribution | `insights.player_segments.experience_level`, `purchase_type`, `engagement_topics`, `activity_status`, `platform` | Deterministic cohorts based on stored playtime/purchase/platform fields | Segment review population; each segment has its own count | Missing playtime/purchase/platform fields are shown as unavailable; do not imply population coverage beyond returned data |
| Topic ranking | `insights.subcategory_insights[].subcategory`, `count`, `recommendation_rate` | Ranked taxonomy topics mentioned in labeled reviews | Semantic labeled population for topic count; multi-label | Show “mentions/support” wording and coverage; never imply mutually exclusive topics |
| Issue ranking | `insights.subcategory_insights[].issue_count`, `count`, `issue_snippets`, `issue_evidence` | Ranked taxonomy issues | Validated/classified semantic population; exact denominator from metric provenance where available | If no classified population, render unavailable; do not divide by raw reviews silently |
| Request ranking | `insights.subcategory_insights[].request_count`, `count`, `request_snippets`, `request_evidence` | Ranked player requests | Validated/classified semantic population | Same missing/coverage behavior as issue ranking |
| Positive-topic ranking | `insights.subcategory_insights[].recommendation_rate` plus `count` | Topics with observed recommendation share, not a separate positive-topic ontology | Labeled topic-support population | Label as topic recommendation rate or positive signal only if copy preserves the existing contract; otherwise defer |
| Verified evidence block | `insights.subcategory_insights[].issue_evidence/request_evidence`; optionally `GET /analysis/{app_id}/evidence` fields `items[].review_id`, `review`, `evidence`, `verified_evidence_count` | Verified source quotes attached to taxonomy signals | Evidence-selected subset; not representative by default | If no verified quote, show “No verified evidence available”; do not synthesize replacement quotes |
| Developer response context | Review row `developer_response`, `timestamp_dev_responded`; database review response fields | Stored developer response attached to reviews | Reviews containing response data | Missing response is “No response recorded”, not “developer ignored issue” |
| Update/news context | Steam news/context endpoint fields `news_items`, event metadata where applicable | External update context around observed feedback | N/A; contextual source | If Steam endpoint fails, show “Update context unavailable”; do not infer causality |
| Topic/issue/request filters | Current `reviews[]`: `language`, `created_at`, `voted_up`, playtime, `llm_*` fields; frontend filters | Restrict displayed review/evidence population | Filtered review sample; semantic metrics must retain their own denominator | If a filter would invalidate a metric’s denominator, show filtered review view only and do not relabel aggregate KPI |
| Source/run detail drawer | `metadata`, `readiness`, run identity and metric provenance | Explain what was observed and classified | Field-specific | Render absent fields as unknown and preserve observed/inferred/needed distinctions |

### 3. Version Review

| Rendered component | Exact API field / source | Business meaning | Denominator | Fallback / unknown behavior |
|---|---|---|---|---|
| Event selector | `GET /version-events[]`: `event_id`, `event_name`, `event_date`, `event_type`, `source`, `source_url`, `manual_verified`, `resolution_status`, `analysis_safety` | Select an event anchor | N/A | Show unresolved/conflicted status; do not silently start a causal comparison |
| Previous/current event header | V2 `event_a_id`, `event_b_id`; run metrics `version_a.event`, `version_b.event`; event fields | Identify comparison sides and dates | N/A | If comparison event is absent, show “No comparable previous event” |
| Effective date/range | Event `effective_at`, `effective_at_range`, `anchor_precision` | Precision of event timing | N/A | Show unresolved/date-only status explicitly |
| Window filter | UI values `3`, `7`, `14`; `/runs/{run_id}/comparison?window_days=` | Approved post-event comparison window | Exact selected window | Reject/defer custom values; preserve backend validation |
| Raw review count A/B | V2 `raw_metrics_a.reviews`, `raw_metrics_b.reviews` | Observed raw reviews in each lifecycle window | Raw reviews in A/B window | Show coverage status beside counts; `null`/missing => `—` |
| Reviews/day A/B | V2 `raw_metrics_a/b.reviews_per_day` | Raw review volume normalized by window days | Raw reviews / window days | Show selected window; do not call this player activity |
| Recommendation Rate A/B | V2 `raw_metrics_a/b.recommendation_rate` | Steam recommendation share in each window | Raw reviews in each A/B window | Keep label Recommendation Rate; `null` => `—` |
| Recommendation delta | V2 `raw_metric_deltas.recommendation_rate_pp` | A/B percentage-point change | Difference between A/B raw recommendation rates | Render `—` if either side unavailable; use “pp” |
| Semantic sample strip | V2 `a_semantic_sample_count`, `b_semantic_sample_count`; run `population_contract` | Number sampled for semantic comparison | Semantic sample per side | Label as semantic sample, not all reviews analyzed |
| Classified count strip | V2 `a_classified_count`, `b_classified_count`; run population contract | Number with classification result | Classified population per side | If current response returns zero/default without provenance, show unknown/insufficient rather than infer |
| Coverage status | V2 `a_coverage_status`, `b_coverage_status`, `coverage_gate.status`, `coverage_gate.reason` | Whether temporal populations are adequate for comparison | Coverage contract per side | Preserve `BLOCKED`, `INSUFFICIENT` and reasons prominently |
| Topic delta table/chart | V2 `topic_comparisons[]`: `topic_id`, `display_name`, `family`, `a_support`, `a_rate`, `b_support`, `b_rate`, `delta_pp`, `state`, `direction` | Change in semantic topic support | Classified semantic population per side | Show support and denominator context; no all-player wording |
| Request delta | V2 `request_comparisons[]` with same fields | Change in request signals | Classified semantic population per side | Same semantic caution as topic delta |
| Positive-signal delta | V2 `positive_comparisons[]` with same fields | Change in positive taxonomy signals | Classified semantic population per side | Preserve observed signal wording; do not turn into causal impact |
| State badges | comparison `state` | `NEW`, `INCREASED`, `DECREASED`, `PERSISTENT`, `STABLE`, `INSUFFICIENT` | Derived by frozen V2 rules | Render unknown/unrecognized states as raw value; never coerce insufficient to stable |
| Paired evidence | V2 `paired_evidence[].topic_id`, `a[]`, `b[]` with evidence/review IDs/snippets | Side-by-side source evidence | Selected verified evidence subset | If one side lacks evidence, show “No paired evidence”; no generated quote |
| Window sensitivity | V2 `window_sensitivity[]`: `window_days`, `coverage_status`, raw counts, rate delta, volume delta | Robustness across approved windows | Each selected window’s raw/coverage population | Plot only returned 3/7/14 values; do not interpolate/customize |
| Robustness/evidence status | V2 `comparison_status`, `coverage_gate`; run `adaptive_analysis.evidence_grade`, design minimum support | Status of observational evidence and robustness | Rules in immutable AnalysisDesign | Preserve grade/limitations; never expose confidence as accuracy |
| Emerging topics | `/runs/{run_id}/emerging-topics`: `topics`, `human_review_required` | Candidate topics for human review | Candidate support as returned by run | Mark candidates as pending human review; do not display as confirmed findings |
| Methodology/provenance disclosure | `/runs/{run_id}/analysis-design`; run `config`, `taxonomy_version`, `prompt_version`, provider/model and population fields | Explain event, window, sample, taxonomy and method | Exact run/design | Missing design is unavailable; do not reconstruct from UI state |

### 4. Reports

| Rendered component | Exact API field / source | Business meaning | Denominator | Fallback / unknown behavior |
|---|---|---|---|---|
| Report game selector | Starred game `app_id`, `name`, `metadata.header_image` | Select an analyzed game | N/A | Empty state if no analyzed games; app ID fallback if name missing |
| Current analysis summary | `fetchAnalysisResult`: `metadata.retrieved`, `run_id`, `insights.five_questions.current_snapshot.note` | Current single-run decision snapshot | Run-specific | If no result, show no analysis state; do not synthesize summary |
| Recommended action | `insights.five_questions.recommended_actions[0].title` plus rationale/validation/evidence | Existing action contract | Signal/evidence-specific | If absent, show “No action available”; do not generate a new call |
| Verified evidence | Analysis evidence fields / run evidence endpoint | Source-backed evidence for report | Evidence-selected subset | Missing evidence remains unavailable |
| Recommendation trend | `insights.trend[]` | Existing weekly recommendation trend | Raw reviews per weekly bucket | Preserve weekly scope and recommendation label |
| Monthly report selector | `/reports/available-months/{app_id}`: `months[].year`, `month`, `label`, `review_count` | Select existing monthly raw-review window | Raw reviews in month | Empty months state; no invented month |
| Monthly report metadata | Selected month fields plus analysis `metadata`/`run_id` | Report scope and source | Selected month/run | Distinguish generated PDF time from analysis completion time |
| PDF export action | `/reports/executive-summary/{app_id}?year&month&format=pdf&output_language=` | Existing export action | Selected month raw/cached review scope | Show server error explicitly; no export-history card |
| Topic-delta summary | Only when exact Version Review V2 result is loaded: `topic_comparisons` | Existing A/B semantic change summary | Classified semantic populations A/B | Hide or mark unavailable for general reports without V2 result |
| Export history | **No field/endpoint** | Unsupported persistence concept | N/A | Remove/defer entirely |

## Phase 2 — projection identification only

The following are the only deterministic presentation projections currently required by the approved visual direction. They are identified, not implemented in the UI worktree or backend.

| Projection candidate | Required by | Inputs | Exact output / denominator | Unknown behavior | Implementation status |
|---|---|---|---|---|---|
| `completed_analysis_count` | Overview KPI | `/analysis-runs/recent` or future read-only aggregate over `analysis_runs` | Count eligible completed runs in explicit scope | Do not label a limited recent page as global count | Identify only |
| `recent_analysis_summary` | Overview and Recent History cards | History row + exact dashboard metadata/artwork | `app_id`, `run_id`, title, artwork, type, mode, completed time, population/classified counts, exact URL | Null fields remain unknown; exact URL requires both IDs | Identify only |
| `daily_review_volume` | Optional Game Analysis daily chart | Exact immutable run reviews with `created_at` | Per-day count of raw reviews in exact run population | Empty/missing timestamp buckets are unknown, not zero unless bucket range is explicitly defined | Identify only |
| `daily_recommendation_rate` | Optional Game Analysis daily chart | Same reviews with `voted_up` | `recommended / raw reviews` per day, with numerator and denominator | Low-support bucket warning; no sentiment label | Identify only |
| `weekly_topic_prevalence` | Optional semantic trend view | Reviews + compatible `review_labels` | `topic-supporting classified reviews / classified reviews` per week | Show coverage, taxonomy, multi-label caveat; no all-player prevalence | Identify only |
| `version_comparison_population_strip` | Version Review compact header | V2 result + run config/design/events | A/B raw, semantic sample, classified, coverage, window and gate | Preserve missing/zero distinction | Identify only |
| `provenance_strip` | All detail pages | Run, immutable result, AnalysisDesign, metadata | Source/mode/window/cutoff/taxonomy/prompt/provider/model/counts/hashes | Missing provenance displayed as unknown | Identify only |

Projection rules:

- deterministic only;
- read-only only;
- no LLM call;
- no denominator or taxonomy changes;
- no schema migration unless separately approved;
- cache by exact `run_id` and relevant filter/window;
- retain the source run and formula version in any future response;
- no implementation begins in this task.

## Explicitly deferred from V1

| Deferred element | Reason |
|---|---|
| Games Monitored | No monitoring registry, cadence or freshness contract. |
| Alerts | No canonical alert rule, severity or acknowledgement lifecycle. |
| Average Sentiment | Conflicts with the existing distinction between Steam Recommendation Rate and sentiment-like derived fields. |
| Real-time monitoring widgets | Steam live context is not a stored monitoring product metric. |
| Custom Version Review window | Current immutable V2 comparison contract supports only 3/7/14 days. |
| Report export history | No durable export-history table or endpoint. |

## Phase gate

Phase 1 may proceed as a visual redesign against the current API mappings above. Phase 2 may document projection contracts, but must not implement them in the UI worktree during this task. Backend presentation projections remain a separate future task and must not alter frozen analytical semantics.

**STOP — no UI or backend implementation performed.**

