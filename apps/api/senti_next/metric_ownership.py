"""Machine-readable ownership map for the research-core migration.

This module is an audit artifact, not a second analytical implementation.  The
entries describe where a metric is calculated today and which Stage 2 contract
will own it in the future.  Production callers continue to use their existing
functions until the later orchestrator stages are implemented.
"""
from __future__ import annotations

from copy import deepcopy
import importlib
from typing import Any, Mapping


RESEARCH_CORE = "RESEARCH_CORE"
SEMANTIC_LAYER = "SEMANTIC_LAYER"
LEGACY_COMPAT = "LEGACY_COMPAT"
DEPRECATED_CANDIDATE = "DEPRECATED_CANDIDATE"
PRESENTATION_ONLY = "PRESENTATION_ONLY"

_REQUIRED_FIELDS = {
    "metric_id",
    "current_source",
    "future_owner",
    "status",
    "canonical_name",
    "semantic_definition",
    "notes",
}


def _entry(
    metric_id: str,
    current_source: str,
    future_owner: str,
    status: str,
    canonical_name: str,
    semantic_definition: str,
    *,
    replacement_metric: str | None = None,
    notes: str = "",
    formula: str | None = None,
    inputs: tuple[str, ...] = (),
    empirical_validation: str = "not yet performed",
) -> dict[str, Any]:
    """Create a stable, JSON-serialisable ownership record."""
    record: dict[str, Any] = {
        "metric_id": metric_id,
        "current_source": current_source,
        "future_owner": future_owner,
        "status": status,
        "canonical_name": canonical_name,
        "semantic_definition": semantic_definition,
        "replacement_metric": replacement_metric,
        "notes": notes,
    }
    if formula is not None:
        record["formula"] = formula
        record["inputs"] = list(inputs)
        record["empirical_validation"] = empirical_validation
    return record


# Keep this tuple ordered by research layer and then by metric id.  Stable order
# makes audit diffs and compatibility tests deterministic.
METRIC_OWNERSHIP_REGISTRY: tuple[dict[str, Any], ...] = (
    # Stage 2B: recommendation is the observable Steam outcome.  It is not
    # linguistic sentiment, even though older payloads used that label.
    _entry("stage2b.valid_n", "rate_inference.calculate_recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "valid_n", "Reviews with a valid Steam voted_up value.", notes="Recommendation denominator; missing values are excluded."),
    _entry("stage2b.recommended_n", "rate_inference.calculate_recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "recommended_n", "Valid reviews whose Steam voted_up value is true.", notes="Count only; no text sentiment interpretation."),
    _entry("stage2b.not_recommended_n", "rate_inference.calculate_recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "not_recommended_n", "Valid reviews whose Steam voted_up value is false.", notes="Count only; no text sentiment interpretation."),
    _entry("stage2b.not_recommended_rate", "rate_inference.calculate_recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "not_recommended_rate", "Share of valid Steam reviews with voted_up=false.", formula="not_recommended_n / valid_n (equivalently 1 - recommendation_rate for a binary valid denominator)", inputs=("not_recommended_n", "valid_n"), notes="Canonical deterministic Research Core rate; not textual negative sentiment."),
    _entry("stage2b.recommendation_rate", "rate_inference.calculate_recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate", "recommended_n divided by valid_n for Steam recommendation outcomes.", formula="recommended_n / valid_n", inputs=("voted_up",), notes="Canonical Recommendation Rate."),
    _entry("stage2b.wilson_interval", "rate_inference.calculate_recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate_wilson_interval", "Wilson interval for the recommendation proportion.", formula="Wilson score interval", inputs=("recommended_n", "valid_n"), notes="Uncertainty for a single population window."),
    _entry("stage2b.difference", "rate_inference.compare_recommendation_rates", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate_difference", "Difference between two population recommendation rates.", formula="rate_b - rate_a", inputs=("recommendation_rate_a", "recommendation_rate_b"), notes="Descriptive comparison only."),
    _entry("stage2b.newcombe_interval", "rate_inference.compare_recommendation_rates", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate_difference_newcombe_interval", "Newcombe interval for a difference in independent recommendation proportions.", formula="Newcombe hybrid score interval", inputs=("recommended_n_a", "valid_n_a", "recommended_n_b", "valid_n_b"), notes="Comparison uncertainty; not a causal estimate."),
    _entry("stage2b.interval_contains_zero", "rate_inference.compare_recommendation_rates", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate_difference_interval_contains_zero", "Whether the comparison interval includes no observed difference.", formula="lower <= 0 <= upper", inputs=("newcombe_interval",), notes="Descriptive interval interpretation."),

    # Stage 2A: descriptive population composition and acquisition coverage.
    _entry("stage2a.population_count", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "population_review_count", "Reviews satisfying the acquired SamplingContract scope."),
    _entry("stage2a.language_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "language_composition", "Counts and shares by raw Steam review language."),
    _entry("stage2a.playtime_at_review_composition", "population_validity.PLAYTIME_COHORTS", RESEARCH_CORE, RESEARCH_CORE, "playtime_at_review_cohort_composition", "Counts and shares using the playtime already accumulated when the player wrote the review: 0–2h, 2–10h, 10–30h, 30–100h, 100h+.", notes="This is the canonical comparison/composition variable; it must not be substituted with playtime_forever."),
    _entry("stage2a.playtime_cohort", "population_validity.PLAYTIME_COHORTS", RESEARCH_CORE, LEGACY_COMPAT, "playtime_cohort_composition", "Compatibility name for the canonical at-review playtime composition variable.", replacement_metric="stage2a.playtime_at_review_composition", notes="The old <2h/2–20h/20h+ and 30h+ buckets remain compatibility outputs only."),
    _entry("stage2a.purchase_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "purchase_composition", "Counts and shares by Steam purchase-source metadata."),
    _entry("stage2a.free_copy_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "free_copy_composition", "Counts and shares by received_for_free."),
    _entry("stage2a.early_access_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "early_access_composition", "Counts and shares by written_during_early_access."),
    _entry("stage2a.deck_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "steam_deck_composition", "Counts and shares by primarily_steam_deck."),
    _entry("stage2a.metadata_missingness", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "metadata_missingness", "Missing-value counts and rates for descriptive Steam metadata.", notes="Missing is not silently converted into a substantive category."),

    # Stage 2C–2E are already implemented as deterministic diagnostics.
    _entry("stage2c.composition_standardization", "standardization.standardize_populations", RESEARCH_CORE, RESEARCH_CORE, "composition_standardization", "Sensitivity of an observed recommendation difference under a shared observed composition.", notes="Descriptive sensitivity, not causal adjustment or bias removal."),
    _entry("stage2d.window_robustness", "window_robustness.matched_window_robustness", RESEARCH_CORE, RESEARCH_CORE, "window_robustness", "Sensitivity of a lifecycle comparison to matched window lengths.", notes="Research Core Stage 2D; no fabricated comparison in a snapshot."),
    _entry("stage2e.review_activity", "activity_diagnostics.analyze_review_activity", RESEARCH_CORE, RESEARCH_CORE, "review_activity", "Review volume, reviews/day, bins, and unusual activity spikes in the acquired population.", notes="Descriptive activity signals; not intent or causality."),
    _entry("stage2e.coordinated_expression", "activity_diagnostics.analyze_review_activity", RESEARCH_CORE, RESEARCH_CORE, "coordinated_expression", "Near-duplicate expression and temporal concentration diagnostics without removing reviews.", notes="Does not label spam, bots, review bombing, or intent."),

    # Existing names retained for compatibility but not canonical ownership.
    _entry("legacy.recommendation_rate", "analysis.recommendation_rate / metric_provenance", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_rate", "Legacy recommendation proportion calculated from the current DataFrame.", replacement_metric="stage2b.recommendation_rate", notes="Must not overwrite a Research Core Stage 2B value."),
    _entry("legacy.share_positive", "analysis.summarize_sentiment", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_rate", "Legacy alias for Steam voted_up=true share, not text sentiment.", replacement_metric="stage2b.recommendation_rate", notes="Compatibility alias; display should call this Recommendation, not sentiment."),
    _entry("legacy.share_negative", "analysis.summarize_sentiment", LEGACY_COMPAT, LEGACY_COMPAT, "not_recommended_rate", "Legacy alias for the share of valid Steam reviews with voted_up=false, not textual negative sentiment.", replacement_metric="stage2b.not_recommended_rate", notes="Compatibility alias; preserve rate units and Stage 2B denominator semantics."),
    _entry("legacy.summarize_sentiment", "analysis.summarize_sentiment", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_summary_legacy", "Legacy aggregate whose positive/negative fields are derived from Steam recommendation outcomes.", notes="Do not interpret voted_up as linguistic sentiment; individual share fields have their own rate mappings."),
    _entry("legacy.sentiment_counts", "insights.prepare_insights", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_counts_legacy", "Legacy positive/negative count distribution derived from voted_up.", notes="Kept for API consumers until the report contract migration; do not replace this distribution with one scalar count."),
    _entry("legacy.playtime_buckets", "analysis.playtime_segment_sentiment / version_analysis", LEGACY_COMPAT, LEGACY_COMPAT, "playtime_cohort_legacy", "Legacy <2h, 2–20h, 20h+ or 30h+ buckets.", replacement_metric="stage2a.playtime_at_review_composition", notes="Incompatible with the canonical Stage 2A cohorts; do not delete yet."),
    _entry("legacy.trend_chart", "analysis.recommended_share_over_time", PRESENTATION_ONLY, PRESENTATION_ONLY, "review_activity_trend_legacy", "Legacy chart projection of recommendation share over time.", replacement_metric="stage2e.review_activity", notes="Presentation compatibility only; empty periods currently fill rate with zero and are a deprecated candidate."),
    _entry("legacy.empty_period_rate_zero", "analysis.recommended_share_over_time(fill_missing=True)", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "empty_period_rate", "A missing activity period represented as recommendation_rate=0.", replacement_metric="stage2e.review_activity", notes="Zero is not an observed recommendation outcome; no UI fix in this audit."),

    # Explicitly audited heuristic indicators.  They remain callable but have
    # no empirical validation and cannot be presented as research findings.
    _entry("heuristic.refund_risk_index", "analysis.refund_risk_index", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "refund_risk_index", "Share of non-recommended reviews from authors with under 2h playtime.", formula="count(voted_up=false and playtime_forever<120) / count(voted_up=false)", inputs=("voted_up", "author_playtime_forever"), notes="Descriptive heuristic; not refund behavior or causal risk. No empirical validation.", empirical_validation="none; requires refund-linked ground truth"),
    _entry("heuristic.core_fan_disappointment", "analysis.core_fan_disappointment", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "core_fan_disappointment", "Share of non-recommended reviews from authors with more than 50h playtime.", formula="count(voted_up=false and playtime_forever>3000) / count(voted_up=false)", inputs=("voted_up", "author_playtime_forever"), notes="Descriptive heuristic; not a validated fan identity or disappointment construct. No empirical validation.", empirical_validation="none; requires validated player-segment ground truth"),
    _entry("heuristic.market_quality_signal", "analysis.market_quality_signal", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "market_quality_signal", "Placeholder/legacy market-quality segment output.", formula="currently returns an empty compatibility frame", inputs=("review frame",), notes="No operational signal or empirical validation; candidate for removal after consumers migrate.", empirical_validation="none"),
    _entry("heuristic.reviewer_influence_sentiment", "analysis.reviewer_influence_sentiment", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "reviewer_influence_legacy", "Recommendation and legacy sentiment fields for the top 10% reviewer-count segment.", formula="quantile(author_num_reviews, .9), minimum threshold 10", inputs=("author_num_reviews", "voted_up"), notes="Reviewer volume is not influence; descriptive segmentation only. No empirical validation.", empirical_validation="none"),
    _entry("heuristic.veteran_benchmarking", "analysis.veteran_benchmarking", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "veteran_benchmarking_legacy", "Recommendation and legacy sentiment fields for the top 10% games-owned segment.", formula="quantile(author_num_games_owned, .9), minimum threshold 100", inputs=("author_num_games_owned", "voted_up"), notes="Games owned is not a validated veteran construct. No empirical validation.", empirical_validation="none"),
    _entry("heuristic.quality_weighted_insights", "analysis.quality_weighted_insights", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "quality_weighted_recommendation", "Review recommendation rate weighted by author/review quality proxies.", formula="weighted_sum(voted_up, author/review weights) / total_weight", inputs=("voted_up", "author_num_reviews", "votes_up", "weighted_vote_score"), notes="Weights are heuristic and can change composition; not Research Core population metrics. No empirical validation.", empirical_validation="none"),
    _entry("heuristic.cross_segment_analysis", "analysis.cross_segment_analysis", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "cross_segment_recommendation", "Recommendation differences across legacy player segments.", formula="segment recommendation rate minus overall rate", inputs=("voted_up", "playtime", "language", "purchase metadata"), notes="Descriptive exploratory output; no multiplicity or causal interpretation. No empirical validation.", empirical_validation="none"),

    # Semantic ownership is deliberately separate from population metrics.
    _entry("semantic.topic", "insights.category_breakdown / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "topic", "LLM/taxonomy-derived topic or category mentions in a future semantic sample.", notes="Must use validated classified reviews and retain evidence provenance."),
    _entry("semantic.issue", "insights.subcategory_insights / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "issue", "Semantic issue mentions and evidence spans selected from the population.", notes="Not a population count unless explicitly defined with a denominator."),
    _entry("semantic.issue_count", "insights.subcategory_insights / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "issue_count", "Count of semantic issue labels within a validated classified or semantic sample.", notes="Not a Research Core population count."),
    _entry("semantic.request", "insights.subcategory_insights / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "request", "Semantic feature/request mentions and evidence spans.", notes="Future semantic sample; never silently replaces population composition."),
    _entry("semantic.top_issues", "insights.subcategory_insights / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "top_issues", "Ranked semantic issue labels or issue cards.", notes="Ranking is semantic/presentation output, not a population metric."),
    _entry("semantic.aspect_sentiment", "version_analysis.calculate_version_metrics", SEMANTIC_LAYER, SEMANTIC_LAYER, "aspect_sentiment", "Model-derived sentiment attached to a reviewed aspect/evidence span.", notes="Separate from Steam voted_up recommendation outcome."),
    _entry("semantic.evidence", "evidence.build_evidence / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "evidence", "Verified quote and provenance for a semantic claim.", notes="Evidence supports interpretation; it does not change research denominators."),

    # Top-level insight payload fields are audited explicitly so future report
    # assembly can enforce precedence instead of merging by accident.
    _entry("presentation.metrics", "insights.prepare_insights.metrics", PRESENTATION_ONLY, PRESENTATION_ONLY, "metrics_projection", "Legacy dashboard metrics projection.", notes="This container contains multiple metrics; individual quantitative fields must be populated from Research Core first."),
    _entry("presentation.llm", "insights.prepare_insights.llm", SEMANTIC_LAYER, SEMANTIC_LAYER, "semantic_coverage_projection", "Validated semantic classification coverage and request/issue rates.", notes="Semantic denominator is validated classified sample, not the full population."),
    _entry("presentation.category_breakdown", "insights.prepare_insights.category_breakdown", SEMANTIC_LAYER, SEMANTIC_LAYER, "topic_breakdown", "Taxonomy category counts for classified reviews."),
    _entry("presentation.category_recommendation_rates", "insights.prepare_insights.category_recommendation_rates", SEMANTIC_LAYER, SEMANTIC_LAYER, "topic_recommendation_association", "Recommendation outcomes within a semantic topic subset.", notes="Semantic association; overall Recommendation Rate remains Research Core."),
    _entry("presentation.category_trend", "insights.category_trend_over_time", PRESENTATION_ONLY, PRESENTATION_ONLY, "topic_trend_projection", "Presentation trend of semantic category mentions."),
    _entry("presentation.version_insights", "insights.version_based_insights / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "version_semantic_insights", "Version/event semantic issue, request, topic, and evidence outputs.", notes="Raw period metrics should be sourced from Research Core Stage 2A–2E."),
    _entry("legacy.playtime_forever_summary", "analysis.summarize_playtime", RESEARCH_CORE, LEGACY_COMPAT, "playtime_forever_descriptive_summary", "Descriptive lifetime playtime reported by Steam at acquisition time.", notes="Retain as supplementary lifetime-playtime metadata. Do not substitute it for Stage 2A playtime_at_review composition."),
    _entry("presentation.playtime", "analysis.summarize_playtime", RESEARCH_CORE, LEGACY_COMPAT, "playtime_summary", "Legacy projection of Steam lifetime playtime metadata; canonical cohorts belong to Stage 2A.", notes="Retain as supplementary lifetime-playtime metadata. Current summarize_playtime uses playtime_forever, not playtime_at_review; no replacement mapping is implied."),
    _entry("presentation.helpful", "analysis.helpfulness_summary", RESEARCH_CORE, RESEARCH_CORE, "helpfulness_summary", "Descriptive Steam helpful-vote metadata."),
    _entry("presentation.recommendation", "analysis.recommendation_rate", RESEARCH_CORE, LEGACY_COMPAT, "recommendation_summary", "Legacy projection of Steam recommendation outcomes.", replacement_metric="stage2b.recommendation_rate", notes="Stage 2B has precedence."),
    _entry("presentation.sentiment_counts", "insights.prepare_insights.sentiment_counts", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_counts_legacy", "Positive/negative count distribution projected from voted_up.", notes="Do not call this text sentiment or replace the distribution with one scalar count."),
    _entry("presentation.trend", "insights.prepare_insights.trend", PRESENTATION_ONLY, PRESENTATION_ONLY, "activity_trend_projection", "Legacy time-series chart projection."),
    _entry("presentation.segments", "insights.prepare_insights.segments", RESEARCH_CORE, LEGACY_COMPAT, "population_segments", "Legacy descriptive composition segment projection.", notes="The current container includes multiple dimensions and legacy playtime buckets; migrate each dimension to its own canonical Research Core contract."),
    _entry("presentation.audience", "insights.prepare_insights.audience", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "audience_heuristics", "Legacy reviewer/audience heuristic projections.", notes="No validated influence or veteran interpretation; no direct canonical replacement is implied."),
    _entry("presentation.risk", "insights.prepare_insights.risk", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "risk_heuristics", "Legacy refund/core-fan heuristic projections.", notes="Not a Research Core risk estimate; no direct population-count replacement is implied."),
    _entry("presentation.subcategory_insights", "insights.aggregate_subcategory_insights", SEMANTIC_LAYER, SEMANTIC_LAYER, "semantic_subcategory_insights", "Validated semantic issue/request evidence cards."),
    _entry("presentation.player_segments.population_counts", "insights.experience_level_issues / purchase_type_insights / activity_based_feedback / platform_segment_insights / language_segment_insights", RESEARCH_CORE, LEGACY_COMPAT, "player_segment_population_counts", "Deterministic counts of reviews in descriptive player segments.", notes="Current helpers are legacy projections; future Research Core output must retain explicit segment denominators."),
    _entry("presentation.player_segments.recommendation_rates", "insights.experience_level_issues / purchase_type_insights / activity_based_feedback / platform_segment_insights / language_segment_insights", RESEARCH_CORE, LEGACY_COMPAT, "player_segment_recommendation_rates", "Steam voted_up recommendation rates within descriptive player segments.", notes="Segment rates are descriptive Research Core projections and must not be confused with semantic issue rates or replaced by the overall rate."),
    _entry("presentation.player_segments.issue_counts", "insights.engagement_based_topics / activity_based_feedback / platform_segment_insights / language_segment_insights", SEMANTIC_LAYER, LEGACY_COMPAT, "player_segment_issue_counts", "Issue counts attached to semantic labels within a player segment.", notes="Consumes llm_issue_subcategories or top_issues; denominator is the classified segment, not the full population."),
    _entry("presentation.player_segments.top_issues", "insights.engagement_based_topics / activity_based_feedback / platform_segment_insights / language_segment_insights", SEMANTIC_LAYER, LEGACY_COMPAT, "player_segment_top_issues", "Top semantic issues associated with a player segment.", notes="Semantic topic/issue output; not a Research Core population metric."),
    _entry("presentation.quality_weighted", "analysis.quality_weighted_insights", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "quality_weighted_legacy", "Legacy quality-weighted projection.", replacement_metric="stage2b.recommendation_rate", notes="Must not replace unweighted population metrics."),
    _entry("presentation.cross_segment", "analysis.cross_segment_analysis", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "cross_segment_legacy", "Legacy exploratory cross-segment projection."),
    _entry("presentation.theme", "insights.derive_theme", PRESENTATION_ONLY, PRESENTATION_ONLY, "visual_theme", "Color/presentation theme derived from legacy metrics."),
    _entry("presentation.metric_provenance", "metric_provenance.build_metric_provenance", RESEARCH_CORE, RESEARCH_CORE, "metric_provenance", "Denominator-safe source, numerator, denominator, and coverage metadata.", notes="Future report should expose Research Core provenance without overwriting it."),
    _entry("presentation.five_questions", "five_questions.build_five_question_contract", SEMANTIC_LAYER, SEMANTIC_LAYER, "decision_contract", "Presentation decision structure built from owned observations and semantic evidence.", notes="Heuristic ranking remains explicitly labeled; no causal claims."),

    # Version analysis overlap is explicit: raw metrics map to Research Core;
    # semantic outputs remain in the semantic/version layer.
    _entry("version.period_assignment", "version_analysis.assign_period", RESEARCH_CORE, LEGACY_COMPAT, "version_window_assignment_legacy", "Legacy calendar-date assignment to pre/event_day/post windows.", replacement_metric="stage2d.window_robustness", notes="Not the validated matched lifecycle contract: anchor <= timestamp_created < anchor + window_days*86400 for 3d/7d/14d windows."),
    _entry("version.recommendation_rate", "version_analysis._review_summary", RESEARCH_CORE, LEGACY_COMPAT, "version_recommendation_rate_legacy", "Legacy recommendation outcome by calendar period.", replacement_metric="stage2b.recommendation_rate", notes="Future orchestrator supplies the canonical rate and uncertainty."),
    _entry("version.playtime_buckets", "version_analysis._playtime_bucket", RESEARCH_CORE, LEGACY_COMPAT, "version_playtime_cohort", "Version-period playtime composition from the legacy helper.", replacement_metric="stage2a.playtime_at_review_composition", notes="Current 0–2h/2–10h/10–30h/30h+ output is transitional and incomplete versus canonical 30–100h/100h+; status is legacy, future owner is Research Core."),
    _entry("version.purchase_segmentation", "version_analysis._purchase_bucket", RESEARCH_CORE, LEGACY_COMPAT, "version_purchase_composition", "Version-period purchase metadata composition from the legacy helper.", replacement_metric="stage2a.purchase_composition", notes="Current helper returns unknown and needs future wiring; status is legacy, future owner is Research Core."),
    _entry("version.daily_review_volume", "version_analysis.calculate_version_metrics", RESEARCH_CORE, LEGACY_COMPAT, "version_review_activity_legacy", "Legacy daily review volume and post/pre volume index from calendar periods.", replacement_metric="stage2e.review_activity", notes="Transitional output; canonical activity uses Research Core Stage 2A/2E contracts and does not inherit legacy period semantics."),
    _entry("version.priority_score", "version_analysis._build_priority_and_evidence", DEPRECATED_CANDIDATE, SEMANTIC_LAYER, "semantic_priority_proxy", "Heuristic issue-card priority score combining reach, severity, deterioration, actionability, and confidence multiplier.", formula="100*(.30*reach+.30*severity+.20*deterioration+.20*actionability)*multiplier", inputs=("mention_rate", "negative_rate_or_issue_rate", "delta_rates", "taxonomy_actionability", "sample_size", "label_confidence"), notes="Proxy only; requires empirical validation before product prioritization.", empirical_validation="none"),
    _entry("version.actionability", "version_analysis._actionability", DEPRECATED_CANDIDATE, SEMANTIC_LAYER, "semantic_actionability_proxy", "Hand-authored taxonomy actionability weight used in the issue-card proxy.", formula="fixed taxonomy lookup", inputs=("subcategory",), notes="Not a product priority fact; requires stakeholder/empirical review.", empirical_validation="none"),
    _entry("version.confidence", "version_analysis._confidence", DEPRECATED_CANDIDATE, SEMANTIC_LAYER, "semantic_confidence_proxy", "Sample-size label and multiplier for semantic issue cards.", formula="low<min_sample, medium<50, high otherwise", inputs=("mentions", "min_sample_size"), notes="Not a statistical confidence interval.", empirical_validation="none"),
    _entry("version.emerging_topics", "version_analysis._discover_emerging_topics", SEMANTIC_LAYER, SEMANTIC_LAYER, "emerging_topic_candidates", "Lexical candidates from negative reviews classified as other."),
    _entry("version.evidence", "version_analysis._build_priority_and_evidence", SEMANTIC_LAYER, SEMANTIC_LAYER, "version_evidence", "Verified semantic evidence cards attached to version-period topics/issues."),
)


# Small explicit integrity maps. Values are (importable module, attribute).
# ``CANONICAL_SOURCE_CHECKS`` contains current canonical implementations;
# ``TRANSITIONAL_SOURCE_CHECKS`` covers legacy helpers whose concepts migrate
# to Research Core. Constants such as PLAYTIME_COHORTS are checked for
# existence; callable functions are checked for callability as well. Keeping
# the maps explicit avoids a fragile reflection framework.
CANONICAL_SOURCE_CHECKS: dict[str, tuple[str, str]] = {
    "stage2b.valid_n": ("apps.api.senti_next.rate_inference", "calculate_recommendation_rate"),
    "stage2b.recommended_n": ("apps.api.senti_next.rate_inference", "calculate_recommendation_rate"),
    "stage2b.not_recommended_n": ("apps.api.senti_next.rate_inference", "calculate_recommendation_rate"),
    "stage2b.not_recommended_rate": ("apps.api.senti_next.rate_inference", "calculate_recommendation_rate"),
    "stage2b.recommendation_rate": ("apps.api.senti_next.rate_inference", "calculate_recommendation_rate"),
    "stage2b.wilson_interval": ("apps.api.senti_next.rate_inference", "calculate_recommendation_rate"),
    "stage2b.difference": ("apps.api.senti_next.rate_inference", "compare_recommendation_rates"),
    "stage2b.newcombe_interval": ("apps.api.senti_next.rate_inference", "compare_recommendation_rates"),
    "stage2b.interval_contains_zero": ("apps.api.senti_next.rate_inference", "compare_recommendation_rates"),
    "stage2a.population_count": ("apps.api.senti_next.population_validity", "compare_populations"),
    "stage2a.language_composition": ("apps.api.senti_next.population_validity", "compare_populations"),
    "stage2a.playtime_at_review_composition": ("apps.api.senti_next.population_validity", "PLAYTIME_COHORTS"),
    "stage2a.purchase_composition": ("apps.api.senti_next.population_validity", "compare_populations"),
    "stage2a.free_copy_composition": ("apps.api.senti_next.population_validity", "compare_populations"),
    "stage2a.early_access_composition": ("apps.api.senti_next.population_validity", "compare_populations"),
    "stage2a.deck_composition": ("apps.api.senti_next.population_validity", "compare_populations"),
    "stage2a.metadata_missingness": ("apps.api.senti_next.population_validity", "compare_populations"),
    "stage2c.composition_standardization": ("apps.api.senti_next.standardization", "standardize_populations"),
    "stage2d.window_robustness": ("apps.api.senti_next.window_robustness", "matched_window_robustness"),
    "stage2e.review_activity": ("apps.api.senti_next.activity_diagnostics", "analyze_review_activity"),
    "stage2e.coordinated_expression": ("apps.api.senti_next.activity_diagnostics", "analyze_review_activity"),
    "presentation.metric_provenance": ("apps.api.senti_next.metric_provenance", "build_metric_provenance"),
}


TRANSITIONAL_SOURCE_CHECKS: dict[str, tuple[str, str]] = {
    "stage2a.playtime_cohort": ("apps.api.senti_next.population_validity", "PLAYTIME_COHORTS"),
    "legacy.playtime_forever_summary": ("apps.api.senti_next.analysis", "summarize_playtime"),
    "presentation.playtime": ("apps.api.senti_next.analysis", "summarize_playtime"),
    "presentation.helpful": ("apps.api.senti_next.analysis", "helpfulness_summary"),
    "presentation.recommendation": ("apps.api.senti_next.analysis", "recommendation_rate"),
    "presentation.player_segments.population_counts": ("apps.api.senti_next.insights", "experience_level_issues"),
    "presentation.player_segments.recommendation_rates": ("apps.api.senti_next.insights", "experience_level_issues"),
    "presentation.segments": ("apps.api.senti_next.insights", "prepare_insights"),
    "version.period_assignment": ("apps.api.senti_next.version_analysis", "assign_period"),
    "version.recommendation_rate": ("apps.api.senti_next.version_analysis", "_review_summary"),
    "version.playtime_buckets": ("apps.api.senti_next.version_analysis", "_playtime_bucket"),
    "version.purchase_segmentation": ("apps.api.senti_next.version_analysis", "_purchase_bucket"),
    "version.daily_review_volume": ("apps.api.senti_next.version_analysis", "calculate_version_metrics"),
}


def validate_canonical_sources(
    registry: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = METRIC_OWNERSHIP_REGISTRY,
) -> list[str]:
    """Verify source objects resolve and registry sources agree with the maps."""
    errors: list[str] = []
    entries = {str(entry.get("metric_id")): entry for entry in registry}
    source_maps = (CANONICAL_SOURCE_CHECKS, TRANSITIONAL_SOURCE_CHECKS)
    checked: set[str] = set()
    for source_map in source_maps:
        for metric_id, (module_name, attribute_name) in source_map.items():
            checked.add(metric_id)
            if metric_id not in entries:
                errors.append(f"source check has no registry entry: {metric_id}")
                continue
            expected_source = _expected_registry_source(module_name, attribute_name)
            registry_source = str(entries[metric_id].get("current_source") or "")
            if expected_source not in registry_source:
                errors.append(
                    f"{metric_id} registry source mismatch: expected {expected_source}, got {registry_source}"
                )
                continue
            try:
                module = importlib.import_module(module_name)
                attribute = getattr(module, attribute_name)
            except (ImportError, AttributeError) as exc:
                errors.append(f"{metric_id} source does not resolve: {module_name}.{attribute_name} ({exc})")
                continue
            if callable(attribute) or attribute_name == "PLAYTIME_COHORTS":
                continue
            errors.append(f"{metric_id} source is neither callable nor an approved constant: {module_name}.{attribute_name}")
    for entry in registry:
        if entry.get("future_owner") == RESEARCH_CORE and entry.get("current_source") and entry.get("metric_id") not in checked:
            errors.append(f"missing canonical source check: {entry.get('metric_id')}")
    return errors


def _expected_registry_source(module_name: str, attribute_name: str) -> str:
    """Normalize a fully qualified check to the repository source notation."""
    short_module = module_name.rsplit(".", 1)[-1]
    return f"{short_module}.{attribute_name}"


RESEARCH_REPORT_CONTRACT: dict[str, Any] = {
    "schema_version": "research-report-v2-preview",
    "snapshot": {
        "required": ["population", "recommendation", "activity", "limitations"],
        "forbidden_inference": "No comparison, change, or causal claim without a second compatible population.",
    },
    "comparison": {
        "required": ["population", "recommendation", "activity", "comparability", "standardization", "window_robustness", "limitations"],
        "descriptive_observed_population": "Raw recommendation rates and observed differences may be reported from available rows when provenance is incomplete, but must be explicitly marked limited.",
        "coverage_dependent": "Matched-window robustness and coverage-complete lifecycle claims require sufficient verified temporal/acquisition coverage.",
        "incomplete_provenance": "Incomplete acquisition must never be silently treated as complete.",
    },
    "precedence": [
        "Research Core owns quantitative population metrics and uncertainty.",
        "Semantic Layer owns topics, issues, requests, aspects, and evidence.",
        "Presentation fields are projections and cannot overwrite either owner.",
    ],
}


MIGRATION_ROADMAP: tuple[dict[str, str], ...] = (
    {"stage": "Stage2P.1", "deliverable": "Audit and ownership registry", "status": "this task"},
    {"stage": "Stage2P.2", "deliverable": "Research Core snapshot/comparison orchestrator", "status": "future"},
    {"stage": "Stage2P.3", "deliverable": "Production /analyze integration", "status": "future"},
    {"stage": "Stage2P.4", "deliverable": "Persistence and API contract", "status": "future"},
    {"stage": "Stage2P.5", "deliverable": "Frontend consumption migration", "status": "future"},
    {"stage": "Stage3A", "deliverable": "Semantic sampling from the Research Core population", "status": "future"},
)


def get_metric_ownership_registry() -> list[dict[str, Any]]:
    """Return a defensive copy suitable for JSON serialisation."""
    return deepcopy(list(METRIC_OWNERSHIP_REGISTRY))


def ownership_by_id() -> dict[str, dict[str, Any]]:
    return {entry["metric_id"]: deepcopy(entry) for entry in METRIC_OWNERSHIP_REGISTRY}


def validate_ownership_registry(registry: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = METRIC_OWNERSHIP_REGISTRY) -> list[str]:
    """Return validation errors; an empty list means the audit is well formed."""
    errors: list[str] = []
    seen: set[str] = set()
    allowed_status = {RESEARCH_CORE, SEMANTIC_LAYER, LEGACY_COMPAT, DEPRECATED_CANDIDATE, PRESENTATION_ONLY}
    for index, entry in enumerate(registry):
        missing = _REQUIRED_FIELDS - set(entry)
        if missing:
            errors.append(f"entry {index} missing fields: {sorted(missing)}")
        metric_id = str(entry.get("metric_id", ""))
        if metric_id in seen:
            errors.append(f"duplicate metric_id: {metric_id}")
        seen.add(metric_id)
        if entry.get("future_owner") not in allowed_status:
            errors.append(f"entry {metric_id} has invalid future_owner")
        if entry.get("status") not in allowed_status:
            errors.append(f"entry {metric_id} has invalid status")
    by_id = {str(entry.get("metric_id")): entry for entry in registry}
    expected_migrations = {
        "version.playtime_buckets": (LEGACY_COMPAT, RESEARCH_CORE),
        "version.purchase_segmentation": (LEGACY_COMPAT, RESEARCH_CORE),
    }
    for metric_id, (status, future_owner) in expected_migrations.items():
        entry = by_id.get(metric_id)
        if entry is None:
            errors.append(f"missing required ownership entry: {metric_id}")
            continue
        if entry.get("status") != status or entry.get("future_owner") != future_owner:
            errors.append(f"invalid migration direction for {metric_id}")
    if by_id.get("legacy.share_negative", {}).get("replacement_metric") != "stage2b.not_recommended_rate":
        errors.append("legacy.share_negative must map to stage2b.not_recommended_rate")
    if by_id.get("legacy.playtime_forever_summary", {}).get("replacement_metric") == "stage2a.playtime_at_review_composition":
        errors.append("playtime_forever cannot replace playtime_at_review composition")
    semantic_ids = {
        "semantic.topic",
        "semantic.issue",
        "semantic.issue_count",
        "semantic.request",
        "semantic.top_issues",
        "semantic.aspect_sentiment",
        "semantic.evidence",
        "presentation.player_segments.issue_counts",
        "presentation.player_segments.top_issues",
    }
    for metric_id in semantic_ids:
        entry = by_id.get(metric_id)
        if entry is not None and entry.get("future_owner") != SEMANTIC_LAYER:
            errors.append(f"semantic metric must remain Semantic Layer-owned: {metric_id}")
    errors.extend(validate_canonical_sources(registry))
    return errors


__all__ = [
    "DEPRECATED_CANDIDATE",
    "LEGACY_COMPAT",
    "METRIC_OWNERSHIP_REGISTRY",
    "MIGRATION_ROADMAP",
    "PRESENTATION_ONLY",
    "RESEARCH_CORE",
    "RESEARCH_REPORT_CONTRACT",
    "SEMANTIC_LAYER",
    "CANONICAL_SOURCE_CHECKS",
    "TRANSITIONAL_SOURCE_CHECKS",
    "get_metric_ownership_registry",
    "ownership_by_id",
    "validate_canonical_sources",
    "validate_ownership_registry",
]
