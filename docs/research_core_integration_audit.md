# Stage 2P.1 — Research Core integration audit

Status: audit only. This document and the machine-readable registry in
`apps/api/senti_next/metric_ownership.py` do not change the production
`/analyze` route, sampling, taxonomy, LLM prompts, or numerical methodology.

## Scope and current pipeline

The current production path is approximately:

`Steam raw review dictionaries → storage / run result → build_reviews_dataframe → prepare_insights → metric_provenance / five_questions / web_contract → frontend projections`

Version review runs additionally pass stored reviews and labels through
`version_analysis.calculate_version_metrics`. Stage 2A–2E are deterministic
research diagnostics available as separate modules:

`raw population → Stage 2A population_validity → Stage 2B rate_inference → Stage 2C standardization → Stage 2D window_robustness → Stage 2E activity_diagnostics`

The current implementation still has a broad compatibility payload. In
particular, `analysis.summarize_sentiment` and the fields `share_positive`,
`share_negative`, and `sentiment_counts` are calculated from Steam's
`voted_up` flag. That flag is an observed recommendation outcome, not a
linguistic sentiment label. The compatibility names are therefore retained
but explicitly marked as aliases in the registry.

## Future target and ownership rule

The target pipeline is:

`Steam raw → Research Core → optional Semantic Layer → presentation`

Research Core owns population scope, descriptive composition, recommendation
outcomes and uncertainty, review activity, and sensitivity diagnostics. The
Semantic Layer owns topic/issue/request/aspect/evidence outputs from a future
semantic sample. Presentation fields are projections only. If a Research Core
metric exists, a legacy quantitative field must not overwrite it; semantic
outputs must not be used as population denominators.

The registry is intentionally machine-readable and deterministic. Every record
contains `metric_id`, `current_source`, `future_owner`, `status`,
`canonical_name`, `semantic_definition`, and `notes`; formulas, inputs, and
validation status are included for heuristic records.

## Ownership decisions

| Area | Canonical owner | Current/legacy treatment |
| --- | --- | --- |
| Steam `voted_up` and recommendation rate | Research Core Stage 2B | `share_positive`, `share_negative`, `summarize_sentiment`, and `sentiment_counts` are legacy compatibility aliases only |
| `valid_n`, `recommended_n`, `not_recommended_n`, Wilson interval, difference, Newcombe interval, interval-zero flag | Research Core Stage 2B | Canonical uncertainty fields; no silent fallback to a legacy point estimate |
| Language, `playtime_at_review`, purchase, free-copy, early-access, Deck, missingness | Research Core Stage 2A | Descriptive composition of the acquired population |
| Review count, reviews/day, activity bins, spikes, near-duplicate expression | Research Core Stage 2E (with population count in 2A) | Never remove or rebalance population rows |
| Composition standardization | Research Core Stage 2C | Descriptive sensitivity against a shared observed composition |
| Matched-window robustness | Research Core Stage 2D | Comparison-only; unavailable in a snapshot |
| Topics, issues, requests, aspects, evidence | Semantic Layer | Future subset of the Research Core population; evidence retains provenance |
| Theme, chart trends, dashboard projections | Presentation only | Cannot define or replace a Research Core metric |

### Canonical playtime cohorts

Stage 2A is the sole canonical definition for **`author.playtime_at_review`**:

`0–2h`, `2–10h`, `10–30h`, `30–100h`, `100h+`.

This means playtime already accumulated when the player wrote the review. It is
the canonical comparison/composition variable and is not interchangeable with
the separate
**`author.playtime_forever`** field is Steam-reported cumulative lifetime
playtime at acquisition time. The legacy `summarize_playtime()` output uses
`playtime_forever`; it remains descriptive metadata only and must not replace
Stage 2A cohorts.

The older `<2h`, `2–20h`, `20h+`, and `30h+` buckets occur in legacy
`analysis.py` and `version_analysis.py`. They are not deleted in this audit;
they are marked `LEGACY_COMPAT` and must not be merged with canonical cohorts.

## Legacy heuristic audit

The following functions remain callable for compatibility but are not accepted
as research findings:

| Metric | Current formula / inputs | Evidence status | Future status |
| --- | --- | --- | --- |
| `refund_risk_index` | Negative reviews with `playtime_forever < 120` divided by all negative reviews; `voted_up`, playtime | No refund-linked ground truth | Deprecated candidate |
| `core_fan_disappointment` | Negative reviews with `playtime_forever > 3000` divided by all negative reviews; `voted_up`, playtime | No validated “core fan” construct | Deprecated candidate |
| `market_quality_signal` | Currently returns an empty compatibility frame | No operational signal | Deprecated candidate |
| `reviewer_influence_sentiment` | Top 10% `author_num_reviews`, minimum threshold 10; recommendation fields | Reviewer count is not influence | Deprecated candidate |
| `veteran_benchmarking` | Top 10% `author_num_games_owned`, minimum threshold 100; recommendation fields | Games owned is not a validated veteran construct | Deprecated candidate |
| `quality_weighted_insights` | Heuristic author/review weights applied to `voted_up` | No empirical weighting validation | Deprecated candidate |
| `cross_segment_analysis` | Segment rate minus overall rate across legacy dimensions | No multiplicity or causal validation | Deprecated candidate |
| Version `priority_score` | `100*(.30*reach+.30*severity+.20*deterioration+.20*actionability)*multiplier` | Proxy only; no outcome validation | Future semantic review |
| Version `actionability` | Fixed taxonomy lookup by subcategory | No product-outcome validation | Future semantic review |
| Version `confidence` | Sample-size labels (`low`, `medium`, `high`) and multiplier | Not a confidence interval | Future semantic review |

The registry records formula, inputs, and the absence of empirical validation so
future work can review or replace these functions without silently promoting
them to Research Core.

### Counts, rates, and compatibility mappings

Research Core keeps the units explicit:

* `recommended_n`, `not_recommended_n`, and `valid_n` are counts;
* `recommendation_rate = recommended_n / valid_n`;
* `not_recommended_rate = not_recommended_n / valid_n` (equivalently
  `1 - recommendation_rate` for a binary valid denominator).

Therefore the legacy `share_negative` proportion maps to
`stage2b.not_recommended_rate`, not to the count `not_recommended_n`.
Compatibility replacement mappings must preserve metric meaning and unit/type:
a rate cannot directly replace a count, a distribution cannot directly replace
a scalar, and lifetime `playtime_forever` cannot replace at-review
`playtime_at_review` composition.

## `prepare_insights()` field map

Every top-level field is represented in the registry. The short ownership map
is:

| Field | Owner | Notes |
| --- | --- | --- |
| `metrics`, `recommendation`, `metric_provenance` | Research Core projection | Stage 2B takes precedence for quantitative values |
| `playtime`, `segments`, `helpful` | Legacy compatibility → Research Core | `playtime` currently uses lifetime `playtime_forever`; canonical cohorts use `playtime_at_review` |
| `player_segments.population_counts`, `player_segments.recommendation_rates` | Legacy compatibility → Research Core | Deterministic segment counts/rates with explicit denominators |
| `player_segments.issue_counts`, `player_segments.top_issues` | Semantic Layer | These consume `llm_issue_subcategories`, `top_issues`, or related semantic labels; they are not population metrics |
| `llm`, `category_breakdown`, `category_recommendation_rates`, `version_insights`, `subcategory_insights`, `five_questions` | Semantic Layer | Denominators and coverage must be explicit; evidence remains semantic |
| `sentiment_counts` | Legacy compatibility | Rename/display as recommendation counts in future migration |
| `trend`, `category_trend`, `theme` | Presentation only | Charts and visual theme cannot define research metrics |
| `audience`, `risk`, `quality_weighted`, `cross_segment` | Deprecated candidates | Existing heuristic outputs are not deleted in Stage 2P.1 |

`recommended_share_over_time(..., fill_missing=True)` currently fills empty
periods with rate zero. That can manufacture an observed-looking value from no
reviews, so it is recorded as a deprecated candidate. This audit does not alter
that behavior or the frontend.

## Coercion and provenance risks

The current DataFrame construction in `analysis.build_reviews_dataframe` uses
`or 0` for missing playtime and defaults several booleans to `False`. These
coercions can turn “unknown” into a substantive value and must be addressed by
the future Research Core adapter while preserving raw Steam dictionaries. The
same audit applies to:

* treating `voted_up` as sentiment;
* filling empty activity periods with recommendation rate zero;
* using legacy, incompatible playtime buckets;
* treating semantic sample counts as population counts;
* allowing legacy `metrics` fields to overwrite Stage 2B values.

The player-segment container is also mixed ownership: deterministic segment
counts and Steam recommendation rates can become Research Core projections,
while `issue_count`, `top_issues`, and semantic topic fields remain Semantic
Layer outputs with classified-sample denominators.

Missing population information must remain unknown, not zero. Raw metadata
should be retained before normalization so missingness can be measured.

## Version-analysis overlap

`version_analysis.py` currently combines legacy calendar-date period assignment
(`pre`/`event_day`/`post`), recommendation summaries, legacy playtime/purchase
segments, and daily review volume with semantic topic/issue/request/evidence
cards. The calendar-date assignment is not the validated Stage 2D lifecycle
contract (`anchor <= timestamp_created < anchor + window_days*86400` for matched
3d/7d/14d windows), so it is `LEGACY_COMPAT → RESEARCH_CORE`. Legacy version
recommendation and daily-volume fields are likewise transitional; their future
owners are Stage 2B/2E contracts rather than the old implementation. Topic,
issue, request, aspect sentiment, emerging topic candidates, and evidence remain
Semantic Layer outputs. Priority, actionability, and confidence are explicitly
heuristic/proxy fields pending future review; they are not statistical
confidence or product priority facts.

## Future report contract (preview only)

The registry exports `RESEARCH_REPORT_CONTRACT` for later orchestrator work.

* **Snapshot mode** must contain population, recommendation, activity, and
  limitations. It must not fabricate a “change” or comparison without a second
  compatible population.
* **Comparison mode** additionally contains comparability,
  standardization, and window robustness. Raw observed-population rates and
  differences may still be reported when provenance is incomplete, but must be
  marked as limited. Coverage-dependent robustness claims require sufficient
  verified acquisition coverage, and incomplete acquisition must never be
  silently treated as complete.

The registry also exports explicit `CANONICAL_SOURCE_CHECKS`; tests import each
listed module, verify the referenced callable or approved constant exists, and
compare the normalized `module.attribute` with the registry's
`current_source`. Transitional legacy helpers are kept in the separately named
`TRANSITIONAL_SOURCE_CHECKS` map, so their existence does not imply canonical
implementation ownership. This is intentionally a small source-integrity map,
not a general reflection system.

The future orchestrator should be named along the lines of
`build_snapshot_research_report(...)` and
`build_comparison_research_report(...)` (or one explicit mode-based function).
It should call existing Stage 1–2E modules rather than reimplementing metrics.

## Migration order

1. **Stage 2P.1 (this audit):** ownership registry, provenance map, and
   compatibility tests.
2. **Stage 2P.2:** Research Core snapshot/comparison orchestrator using existing
   Stage 1–2E outputs.
3. **Stage 2P.3:** integrate `/analyze` without changing sampling or semantic
   behavior.
4. **Stage 2P.4:** persist and expose the report contract through the API.
5. **Stage 2P.5:** migrate frontend consumers while retaining compatibility
   aliases.
6. **Stage 3A:** select a future semantic sample from the Research Core
   population for expensive LLM coding.

No Stage 2A–2E thresholds, Steam crawling, taxonomy, LLM prompts, statistics,
version algorithms, database schema, or frontend behavior are changed by this
audit.

## Stage 2P.4 result contract

The deterministic Research Core report is now a first-class result rather than
part of the semantic insights namespace.  `analysis_results` and
`analysis_run_results` persist nullable JSON fields named `research_report` and
`semantic_status`; `insights` remains the legacy semantic/presentation
compatibility payload.  The migration copies only exact Stage 2P.3 envelope
keys when they exist and never reconstructs reports from older metrics.

For a completed immutable run, `research_ready` means a recognized
`research-report-v1` report is present. `semantic_ready` remains independent
and requires the existing validated semantic output plus an available semantic
status. Thus a quantitative-only run can be research-ready while semantic
analysis is unavailable. Read endpoints report a changed review fingerprint as
stale and do not silently recompute or mutate either result.
