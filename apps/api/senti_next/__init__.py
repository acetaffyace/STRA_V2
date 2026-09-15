"""SentiNext - Steam review sentiment MVP package."""

from .analysis import (
    build_reviews_dataframe,

    core_fan_disappointment,
    early_access_vs_release_sentiment,
    free_vs_paid_sentiment,
    helpfulness_summary,
    keyword_summary_by_label,
    market_quality_signal,
    patch_impact_index,
    playtime_segment_sentiment,
    recommended_share_over_time,
    recommendation_rate,
    reviewer_influence_sentiment,
    refund_risk_index,
    summarize_playtime,
    summarize_sentiment,
    top_keywords,
    veteran_benchmarking,
    experience_level_issues,
    purchase_type_insights,
    engagement_based_topics,
    activity_based_feedback,
    platform_segment_insights,
    language_segment_insights,
    quality_weighted_insights,
    cross_segment_analysis,
)
from .insights import prepare_insights
from . import storage
from . import ingest
from .sampling import ReviewQuery, SamplingContract
from .acquisition_provenance import derive_acquisition_coverage
from .population_validity import build_population_comparability_report, compare_populations
from .rate_inference import (
    build_rate_inference_report,
    build_recommendation_rate_report,
    calculate_recommendation_rate,
    compare_recommendation_rates,
)
from .standardization import (
    SUPPORTED_VARIABLES,
    build_composition_standardization_report,
    build_single_dimension_sensitivity,
    standardize_populations,
)
from .window_robustness import (
    DEFAULT_WINDOWS_DAYS,
    WINDOW_SENSITIVITY_THRESHOLDS,
    build_window_robustness_report,
    matched_window_robustness,
)
from .activity_diagnostics import (
    COORDINATION_SIMILARITY_CONFIG,
    SPIKE_CONFIG,
    analyze_review_activity,
    build_activity_diagnostics,
    normalize_review_text,
    normalized_text_hash,
)
from .ingest import (
    SOURCE_DISCORD,
    SOURCE_REDDIT,
    SOURCE_STEAM_FORUM,
    SOURCE_STEAM_REVIEW,
    collect_feedback,
    dedupe_feedback,
    fetch_discord_feedback,
    fetch_reddit_feedback,
    fetch_steam_forum_feedback,
    normalize_feedback_item,
    normalize_steam_reviews,
)
from .steam_api import (
    AUTHOR_METADATA_FIELDS,
    REVIEW_METADATA_FIELDS,
    STEAM_LANGUAGES,
    SteamAPIError,
    fetch_reviews as _steam_fetch_reviews,
    fetch_reviews_multi_language as _steam_fetch_reviews_multi_language,
    iter_author_fields,
    iter_review_fields,
    resolve_app_id,
    search_applications,
)


def _analysis_acquisition_enabled(sampling_contract, progress_callback, stats_callback) -> bool:
    """Return whether this call is a real acquisition stage rather than preview.

    `/analyze` supplies progress/stat callbacks, while estimate/utility callers
    do not.  Keeping preview calls on the raw Steam functions preserves their
    current no-cache-mutation semantics without changing the public function
    signature used across older modules.
    """
    return sampling_contract is not None and (progress_callback is not None or stats_callback is not None)


def fetch_reviews(
    app_id: int,
    count: int = 100,
    language: str = "english",
    filter_type: str = "recent",
    day_range=None,
    include_review_bombs: bool = False,
    stop_before_timestamp=None,
    progress_callback=None,
    stats_callback=None,
    sampling_contract=None,
):
    """Compatibility fetch entrypoint with cache reuse for real analysis runs."""
    if _analysis_acquisition_enabled(sampling_contract, progress_callback, stats_callback):
        from .analysis_acquisition import ensure_reviews

        result = ensure_reviews(sampling_contract, progress_callback=progress_callback)
        if stats_callback is not None:
            stats_callback(result.stats)
        return result.reviews
    return _steam_fetch_reviews(
        app_id,
        count=count,
        language=language,
        filter_type=filter_type,
        day_range=day_range,
        include_review_bombs=include_review_bombs,
        stop_before_timestamp=stop_before_timestamp,
        progress_callback=progress_callback,
        stats_callback=stats_callback,
        sampling_contract=sampling_contract,
    )


def fetch_reviews_multi_language(
    app_id: int,
    count: int = 100,
    languages=None,
    filter_type: str = "recent",
    day_range=None,
    include_review_bombs: bool = False,
    progress_callback=None,
    stats_callback=None,
    sampling_contract=None,
):
    """Multi-language compatibility entrypoint with shared acquisition cache."""
    if _analysis_acquisition_enabled(sampling_contract, progress_callback, stats_callback):
        from .analysis_acquisition import ensure_reviews

        result = ensure_reviews(sampling_contract, progress_callback=progress_callback)
        if stats_callback is not None:
            stats_callback(result.stats)
        return result.reviews
    return _steam_fetch_reviews_multi_language(
        app_id,
        count=count,
        languages=languages,
        filter_type=filter_type,
        day_range=day_range,
        include_review_bombs=include_review_bombs,
        progress_callback=progress_callback,
        stats_callback=stats_callback,
        sampling_contract=sampling_contract,
    )


def __getattr__(name: str):
    """Load the optional semantic/LLM layer only when explicitly requested.

    Deterministic Research Core imports therefore do not import provider code
    merely because they use the ``senti_next`` package namespace.  Existing
    ``from senti_next import llm`` callers retain their compatibility path.
    """
    if name == "llm":
        from importlib import import_module

        module = import_module(".llm", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AUTHOR_METADATA_FIELDS",
    "REVIEW_METADATA_FIELDS",
    "STEAM_LANGUAGES",
    "SteamAPIError",
    "SamplingContract",
    "ReviewQuery",
    "derive_acquisition_coverage",
    "compare_populations",
    "build_population_comparability_report",
    "calculate_recommendation_rate",
    "compare_recommendation_rates",
    "build_rate_inference_report",
    "build_recommendation_rate_report",
    "SUPPORTED_VARIABLES",
    "standardize_populations",
    "build_composition_standardization_report",
    "build_single_dimension_sensitivity",
    "DEFAULT_WINDOWS_DAYS",
    "WINDOW_SENSITIVITY_THRESHOLDS",
    "matched_window_robustness",
    "build_window_robustness_report",
    "COORDINATION_SIMILARITY_CONFIG",
    "SPIKE_CONFIG",
    "analyze_review_activity",
    "build_activity_diagnostics",
    "normalize_review_text",
    "normalized_text_hash",
    "fetch_reviews_multi_language",
    "build_reviews_dataframe",

    "core_fan_disappointment",
    "early_access_vs_release_sentiment",
    "fetch_reviews",
    "free_vs_paid_sentiment",
    "helpfulness_summary",
    "iter_author_fields",
    "iter_review_fields",
    "keyword_summary_by_label",
    "market_quality_signal",
    "patch_impact_index",
    "playtime_segment_sentiment",
    "recommended_share_over_time",
    "recommendation_rate",
    "reviewer_influence_sentiment",
    "refund_risk_index",
    "resolve_app_id",
    "search_applications",
    "summarize_playtime",
    "summarize_sentiment",
    "top_keywords",
    "prepare_insights",
    "veteran_benchmarking",
    "experience_level_issues",
    "purchase_type_insights",
    "engagement_based_topics",
    "activity_based_feedback",
    "platform_segment_insights",
    "language_segment_insights",
    "quality_weighted_insights",
    "cross_segment_analysis",
    "storage",
    "llm",
    "ingest",
    "collect_feedback",
    "normalize_feedback_item",
    "normalize_steam_reviews",
    "dedupe_feedback",
    "fetch_reddit_feedback",
    "fetch_discord_feedback",
    "fetch_steam_forum_feedback",
    "SOURCE_STEAM_REVIEW",
    "SOURCE_REDDIT",
    "SOURCE_DISCORD",
    "SOURCE_STEAM_FORUM",
]
