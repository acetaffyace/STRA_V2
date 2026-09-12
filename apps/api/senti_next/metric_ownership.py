"""Machine-readable ownership map for the research-core migration.

This module is an audit artifact, not a second analytical implementation.  The
entries describe where a metric is calculated today and which Stage 2 contract
will own it in the future.  Production callers continue to use their existing
functions until the later orchestrator stages are implemented.
"""
from __future__ import annotations

from copy import deepcopy
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
    _entry("stage2b.recommendation_rate", "rate_inference.calculate_recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate", "recommended_n divided by valid_n for Steam recommendation outcomes.", formula="recommended_n / valid_n", inputs=("voted_up",), notes="Canonical Recommendation Rate."),
    _entry("stage2b.wilson_interval", "rate_inference.calculate_recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate_wilson_interval", "Wilson interval for the recommendation proportion.", formula="Wilson score interval", inputs=("recommended_n", "valid_n"), notes="Uncertainty for a single population window."),
    _entry("stage2b.difference", "rate_inference.compare_recommendation_rates", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate_difference", "Difference between two population recommendation rates.", formula="rate_b - rate_a", inputs=("recommendation_rate_a", "recommendation_rate_b"), notes="Descriptive comparison only."),
    _entry("stage2b.newcombe_interval", "rate_inference.compare_recommendation_rates", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate_difference_newcombe_interval", "Newcombe interval for a difference in independent recommendation proportions.", formula="Newcombe hybrid score interval", inputs=("recommended_n_a", "valid_n_a", "recommended_n_b", "valid_n_b"), notes="Comparison uncertainty; not a causal estimate."),
    _entry("stage2b.interval_contains_zero", "rate_inference.compare_recommendation_rates", RESEARCH_CORE, RESEARCH_CORE, "recommendation_rate_difference_interval_contains_zero", "Whether the comparison interval includes no observed difference.", formula="lower <= 0 <= upper", inputs=("newcombe_interval",), notes="Descriptive interval interpretation."),

    # Stage 2A: descriptive population composition and acquisition coverage.
    _entry("stage2a.population_count", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "population_review_count", "Reviews satisfying the acquired SamplingContract scope."),
    _entry("stage2a.language_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "language_composition", "Counts and shares by raw Steam review language."),
    _entry("stage2a.playtime_cohort", "population_validity.PLAYTIME_COHORTS", RESEARCH_CORE, RESEARCH_CORE, "playtime_cohort_composition", "Counts and shares using canonical at-review playtime cohorts: 0–2h, 2–10h, 10–30h, 30–100h, 100h+.", notes="The old <2h/2–20h/20h+ and 30h+ buckets remain compatibility outputs only."),
    _entry("stage2a.purchase_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "purchase_composition", "Counts and shares by Steam purchase-source metadata."),
    _entry("stage2a.free_copy_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "free_copy_composition", "Counts and shares by received_for_free."),
    _entry("stage2a.early_access_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "early_access_composition", "Counts and shares by written_during_early_access."),
    _entry("stage2a.deck_composition", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "steam_deck_composition", "Counts and shares by primarily_steam_deck."),
    _entry("stage2a.metadata_missingness", "population_validity.compare_populations", RESEARCH_CORE, RESEARCH_CORE, "metadata_missingness", "Missing-value counts and rates for descriptive Steam metadata.", notes="Missing is not silently converted into a substantive category."),

    # Stage 2C–2E are already implemented as deterministic diagnostics.
    _entry("stage2c.composition_standardization", "standardization.standardize_populations", RESEARCH_CORE, RESEARCH_CORE, "composition_standardization", "Sensitivity of an observed recommendation difference under a shared observed composition.", notes="Descriptive sensitivity, not causal adjustment or bias removal."),
    _entry("stage2d.window_robustness", "window_robustness.analyze_window_robustness", RESEARCH_CORE, RESEARCH_CORE, "window_robustness", "Sensitivity of a lifecycle comparison to matched window lengths.", notes="Research Core Stage 2D; no fabricated comparison in a snapshot."),
    _entry("stage2e.review_activity", "activity_diagnostics.analyze_review_activity", RESEARCH_CORE, RESEARCH_CORE, "review_activity", "Review volume, reviews/day, bins, and unusual activity spikes in the acquired population.", notes="Descriptive activity signals; not intent or causality."),
    _entry("stage2e.coordinated_expression", "activity_diagnostics.analyze_review_activity", RESEARCH_CORE, RESEARCH_CORE, "coordinated_expression", "Near-duplicate expression and temporal concentration diagnostics without removing reviews.", notes="Does not label spam, bots, review bombing, or intent."),

    # Existing names retained for compatibility but not canonical ownership.
    _entry("legacy.recommendation_rate", "analysis.recommendation_rate / metric_provenance", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_rate", "Legacy recommendation proportion calculated from the current DataFrame.", replacement_metric="stage2b.recommendation_rate", notes="Must not overwrite a Research Core Stage 2B value."),
    _entry("legacy.share_positive", "analysis.summarize_sentiment", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_rate", "Legacy alias for Steam voted_up=true share, not text sentiment.", replacement_metric="stage2b.recommendation_rate", notes="Compatibility alias; display should call this Recommendation, not sentiment."),
    _entry("legacy.share_negative", "analysis.summarize_sentiment", LEGACY_COMPAT, LEGACY_COMPAT, "not_recommended_rate", "Legacy alias for Steam voted_up=false share, not text sentiment.", replacement_metric="stage2b.not_recommended_n", notes="Compatibility alias; denominator semantics remain Stage 2B."),
    _entry("legacy.summarize_sentiment", "analysis.summarize_sentiment", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_summary_legacy", "Legacy aggregate whose positive/negative fields are derived from Steam recommendation outcomes.", replacement_metric="stage2b.recommendation_rate", notes="Do not interpret voted_up as linguistic sentiment."),
    _entry("legacy.sentiment_counts", "insights.prepare_insights", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_counts_legacy", "Legacy positive/negative count array derived from voted_up.", replacement_metric="stage2b.recommended_n", notes="Kept for API consumers until the report contract migration."),
    _entry("legacy.playtime_buckets", "analysis.playtime_segment_sentiment / version_analysis", LEGACY_COMPAT, LEGACY_COMPAT, "playtime_cohort_legacy", "Legacy <2h, 2–20h, 20h+ or 30h+ buckets.", replacement_metric="stage2a.playtime_cohort", notes="Incompatible with the canonical Stage 2A cohorts; do not delete yet."),
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
    _entry("semantic.request", "insights.subcategory_insights / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "request", "Semantic feature/request mentions and evidence spans.", notes="Future semantic sample; never silently replaces population composition."),
    _entry("semantic.aspect_sentiment", "version_analysis.calculate_version_metrics", SEMANTIC_LAYER, SEMANTIC_LAYER, "aspect_sentiment", "Model-derived sentiment attached to a reviewed aspect/evidence span.", notes="Separate from Steam voted_up recommendation outcome."),
    _entry("semantic.evidence", "evidence.build_evidence / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "evidence", "Verified quote and provenance for a semantic claim.", notes="Evidence supports interpretation; it does not change research denominators."),

    # Top-level insight payload fields are audited explicitly so future report
    # assembly can enforce precedence instead of merging by accident.
    _entry("presentation.metrics", "insights.prepare_insights.metrics", PRESENTATION_ONLY, PRESENTATION_ONLY, "metrics_projection", "Legacy dashboard metrics projection.", replacement_metric="stage2b.recommendation_rate", notes="Quantitative fields must be populated from Research Core first."),
    _entry("presentation.llm", "insights.prepare_insights.llm", SEMANTIC_LAYER, SEMANTIC_LAYER, "semantic_coverage_projection", "Validated semantic classification coverage and request/issue rates.", notes="Semantic denominator is validated classified sample, not the full population."),
    _entry("presentation.category_breakdown", "insights.prepare_insights.category_breakdown", SEMANTIC_LAYER, SEMANTIC_LAYER, "topic_breakdown", "Taxonomy category counts for classified reviews."),
    _entry("presentation.category_recommendation_rates", "insights.prepare_insights.category_recommendation_rates", SEMANTIC_LAYER, SEMANTIC_LAYER, "topic_recommendation_association", "Recommendation outcomes within a semantic topic subset.", notes="Semantic association; overall Recommendation Rate remains Research Core."),
    _entry("presentation.category_trend", "insights.category_trend_over_time", PRESENTATION_ONLY, PRESENTATION_ONLY, "topic_trend_projection", "Presentation trend of semantic category mentions."),
    _entry("presentation.version_insights", "insights.version_based_insights / version_analysis", SEMANTIC_LAYER, SEMANTIC_LAYER, "version_semantic_insights", "Version/event semantic issue, request, topic, and evidence outputs.", notes="Raw period metrics should be sourced from Research Core Stage 2A–2E."),
    _entry("presentation.playtime", "analysis.summarize_playtime", RESEARCH_CORE, RESEARCH_CORE, "playtime_summary", "Descriptive playtime distribution; canonical cohorts belong to Stage 2A."),
    _entry("presentation.helpful", "analysis.helpfulness_summary", RESEARCH_CORE, RESEARCH_CORE, "helpfulness_summary", "Descriptive Steam helpful-vote metadata."),
    _entry("presentation.recommendation", "analysis.recommendation_rate", RESEARCH_CORE, RESEARCH_CORE, "recommendation_summary", "Legacy projection of Steam recommendation outcomes.", replacement_metric="stage2b.recommendation_rate", notes="Stage 2B has precedence."),
    _entry("presentation.sentiment_counts", "insights.prepare_insights.sentiment_counts", LEGACY_COMPAT, LEGACY_COMPAT, "recommendation_counts_legacy", "Positive/negative labels projected from voted_up.", replacement_metric="stage2b.recommended_n", notes="Do not call this text sentiment."),
    _entry("presentation.trend", "insights.prepare_insights.trend", PRESENTATION_ONLY, PRESENTATION_ONLY, "activity_trend_projection", "Legacy time-series chart projection."),
    _entry("presentation.segments", "insights.prepare_insights.segments", RESEARCH_CORE, RESEARCH_CORE, "population_segments", "Descriptive composition segments; playtime uses Stage 2A cohorts."),
    _entry("presentation.audience", "insights.prepare_insights.audience", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "audience_heuristics", "Legacy reviewer/audience heuristic projections.", replacement_metric="stage2a.metadata_missingness", notes="No validated influence or veteran interpretation."),
    _entry("presentation.risk", "insights.prepare_insights.risk", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "risk_heuristics", "Legacy refund/core-fan heuristic projections.", replacement_metric="stage2a.population_count", notes="Not a Research Core risk estimate."),
    _entry("presentation.subcategory_insights", "insights.aggregate_subcategory_insights", SEMANTIC_LAYER, SEMANTIC_LAYER, "semantic_subcategory_insights", "Validated semantic issue/request evidence cards."),
    _entry("presentation.player_segments", "insights.prepare_insights.player_segments", RESEARCH_CORE, RESEARCH_CORE, "descriptive_player_segments", "Descriptive composition slices with explicit denominators."),
    _entry("presentation.quality_weighted", "analysis.quality_weighted_insights", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "quality_weighted_legacy", "Legacy quality-weighted projection.", replacement_metric="stage2b.recommendation_rate", notes="Must not replace unweighted population metrics."),
    _entry("presentation.cross_segment", "analysis.cross_segment_analysis", DEPRECATED_CANDIDATE, DEPRECATED_CANDIDATE, "cross_segment_legacy", "Legacy exploratory cross-segment projection."),
    _entry("presentation.theme", "insights.derive_theme", PRESENTATION_ONLY, PRESENTATION_ONLY, "visual_theme", "Color/presentation theme derived from legacy metrics."),
    _entry("presentation.metric_provenance", "metric_provenance.build_metric_provenance", RESEARCH_CORE, RESEARCH_CORE, "metric_provenance", "Denominator-safe source, numerator, denominator, and coverage metadata.", notes="Future report should expose Research Core provenance without overwriting it."),
    _entry("presentation.five_questions", "five_questions.build_five_question_contract", SEMANTIC_LAYER, SEMANTIC_LAYER, "decision_contract", "Presentation decision structure built from owned observations and semantic evidence.", notes="Heuristic ranking remains explicitly labeled; no causal claims."),

    # Version analysis overlap is explicit: raw metrics map to Research Core;
    # semantic outputs remain in the semantic/version layer.
    _entry("version.period_assignment", "version_analysis.assign_period", RESEARCH_CORE, RESEARCH_CORE, "version_window_assignment", "Deterministic assignment to pre/event_day/post windows."),
    _entry("version.recommendation_rate", "version_analysis._review_summary", RESEARCH_CORE, RESEARCH_CORE, "version_recommendation_rate", "Recommendation outcome by version period.", replacement_metric="stage2b.recommendation_rate", notes="Future orchestrator supplies the canonical rate and uncertainty."),
    _entry("version.playtime_buckets", "version_analysis._playtime_bucket", LEGACY_COMPAT, RESEARCH_CORE, "version_playtime_cohort", "Version-period playtime composition.", replacement_metric="stage2a.playtime_cohort", notes="Current 0–2h/2–10h/10–30h/30h+ output is incomplete versus canonical 30–100h/100h+."),
    _entry("version.purchase_segmentation", "version_analysis._purchase_bucket", LEGACY_COMPAT, RESEARCH_CORE, "version_purchase_composition", "Version-period purchase metadata composition.", replacement_metric="stage2a.purchase_composition", notes="Current helper returns unknown and needs future wiring."),
    _entry("version.daily_review_volume", "version_analysis.calculate_version_metrics", RESEARCH_CORE, RESEARCH_CORE, "version_review_activity", "Daily review volume and post/pre volume index."),
    _entry("version.priority_score", "version_analysis._build_priority_and_evidence", DEPRECATED_CANDIDATE, SEMANTIC_LAYER, "semantic_priority_proxy", "Heuristic issue-card priority score combining reach, severity, deterioration, actionability, and confidence multiplier.", formula="100*(.30*reach+.30*severity+.20*deterioration+.20*actionability)*multiplier", inputs=("mention_rate", "negative_rate_or_issue_rate", "delta_rates", "taxonomy_actionability", "sample_size", "label_confidence"), notes="Proxy only; requires empirical validation before product prioritization.", empirical_validation="none"),
    _entry("version.actionability", "version_analysis._actionability", DEPRECATED_CANDIDATE, SEMANTIC_LAYER, "semantic_actionability_proxy", "Hand-authored taxonomy actionability weight used in the issue-card proxy.", formula="fixed taxonomy lookup", inputs=("subcategory",), notes="Not a product priority fact; requires stakeholder/empirical review.", empirical_validation="none"),
    _entry("version.confidence", "version_analysis._confidence", DEPRECATED_CANDIDATE, SEMANTIC_LAYER, "semantic_confidence_proxy", "Sample-size label and multiplier for semantic issue cards.", formula="low<min_sample, medium<50, high otherwise", inputs=("mentions", "min_sample_size"), notes="Not a statistical confidence interval.", empirical_validation="none"),
    _entry("version.emerging_topics", "version_analysis._discover_emerging_topics", SEMANTIC_LAYER, SEMANTIC_LAYER, "emerging_topic_candidates", "Lexical candidates from negative reviews classified as other."),
    _entry("version.evidence", "version_analysis._build_priority_and_evidence", SEMANTIC_LAYER, SEMANTIC_LAYER, "version_evidence", "Verified semantic evidence cards attached to version-period topics/issues."),
)


RESEARCH_REPORT_CONTRACT: dict[str, Any] = {
    "schema_version": "research-report-v2-preview",
    "snapshot": {
        "required": ["population", "recommendation", "activity", "limitations"],
        "forbidden_inference": "No comparison, change, or causal claim without a second compatible population.",
    },
    "comparison": {
        "required": ["population", "recommendation", "activity", "comparability", "standardization", "window_robustness", "limitations"],
        "requirement": "Both populations must have compatible SamplingContracts and complete provenance before comparison metrics are reported.",
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
    "get_metric_ownership_registry",
    "ownership_by_id",
    "validate_ownership_registry",
]
