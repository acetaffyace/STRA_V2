"""High-level insight builders for Steam review analysis."""
from __future__ import annotations

import json
from typing import Any, Dict

import pandas as pd

from .analysis import (
    early_access_vs_release_sentiment,
    free_vs_paid_sentiment,
    helpfulness_summary,
    market_quality_signal,
    playtime_segment_sentiment,
    recommended_share_over_time,
    recommendation_rate,
    reviewer_influence_sentiment,
    summarize_playtime,
    summarize_sentiment,
    core_fan_disappointment,
    refund_risk_index,

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
from .metric_provenance import (
    build_metric_provenance,
    build_metric_contract,
    formal_metric_denominator,
)
from .evidence import build_evidence
from .five_questions import build_five_question_contract


def _listify(value: Any) -> list[str]:
    """Normalize a value to a list of strings, filtering non-strings."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _frame_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    return json.loads(
        df.to_json(orient="records", date_format="iso", date_unit="s")
    )


def aggregate_subcategory_insights(
    df: pd.DataFrame, *, max_snippets: int = 6, run_id: str | None = None, app_id: int | None = None
) -> list[dict[str, Any]]:
    """Aggregate evidence snippets for issue/request subcategories.

    Snippets are prioritized from English reviews with the most helpful votes,
    ensuring the UI displays the most relevant evidence first.
    """
    if (
        df is None
        or df.empty
        or "llm_subcategories" not in df.columns
        or "llm_subcategory_evidence" not in df.columns
    ):
        return []

    def _snippets(value: Any) -> list[str]:
        if isinstance(value, list):
            items = value
        elif value is None:
            return []
        else:
            items = [value]
        cleaned = []
        for item in items:
            text = str(item).replace("\n", " ").replace("\r", " ").strip()
            if text and text not in cleaned:
                cleaned.append(text[:160])
        return cleaned

    # Sort DataFrame to prioritize English reviews with most helpful votes
    # This ensures snippets come from most relevant/helpful English reviews first
    df_sorted = df.copy()
    if "language" in df_sorted.columns and "votes_up" in df_sorted.columns:
        # Create sort key: English first (0), then other languages (1)
        df_sorted["_is_english"] = df_sorted["language"].apply(
            lambda x: 0 if str(x).lower() == "english" else 1
        )
        df_sorted = df_sorted.sort_values(
            by=["_is_english", "votes_up"],
            ascending=[True, False]  # English first, then highest votes
        )
    elif "votes_up" in df_sorted.columns:
        df_sorted = df_sorted.sort_values(by="votes_up", ascending=False)

    results: dict[str, dict[str, Any]] = {}
    for _, row in df_sorted.iterrows():
        subcats = _listify(row.get("llm_subcategories"))
        if not subcats:
            continue
        voted_up = row.get("voted_up")
        voted_up_bool = bool(voted_up) if voted_up is not None else True
        issue_subcats = set(_listify(row.get("llm_issue_subcategories")))
        request_subcats = set(_listify(row.get("llm_request_subcategories")))
        evidence = row.get("llm_subcategory_evidence") or {}
        if not isinstance(evidence, dict):
            evidence = {}

        for subcat in subcats:
            entry = results.setdefault(
                subcat,
                {
                    "subcategory": subcat,
                    "count": 0,
                    "recommended": 0,
                    "not_recommended": 0,
                    "issue_count": 0,
                    "request_count": 0,
                    "issue_snippets": [],
                    "request_snippets": [],
                    "issue_evidence": [],
                    "request_evidence": [],
                },
            )
            entry["count"] += 1
            if voted_up_bool:
                entry["recommended"] += 1
            else:
                entry["not_recommended"] += 1
            if subcat in issue_subcats:
                entry["issue_count"] += 1
            if subcat in request_subcats:
                entry["request_count"] += 1

            snippets = _snippets(evidence.get(subcat))
            if not snippets:
                continue
            review_id = row.get("review_id") or row.get("recommendationid")
            source_text = row.get("review")
            allowed_review_ids = {
                str(item) for item in df_sorted.get("review_id", pd.Series(dtype=object)).dropna().tolist()
            }
            if "recommendationid" in df_sorted.columns:
                allowed_review_ids.update(str(item) for item in df_sorted["recommendationid"].dropna().tolist())
            if subcat in issue_subcats:
                for snippet in snippets:
                    item = build_evidence(
                        source_text, snippet, review_id=str(review_id) if review_id is not None else None,
                        app_id=app_id, run_id=run_id, allowed_review_ids=allowed_review_ids,
                        subcategory=subcat, evidence_type="issue",
                    )
                    if item["verification_status"] == "verified" and len(entry["issue_snippets"]) < max_snippets:
                        entry["issue_snippets"].append(item["quote"])
                        entry["issue_evidence"].append(item)
            if subcat in request_subcats:
                for snippet in snippets:
                    item = build_evidence(
                        source_text, snippet, review_id=str(review_id) if review_id is not None else None,
                        app_id=app_id, run_id=run_id, allowed_review_ids=allowed_review_ids,
                        subcategory=subcat, evidence_type="request",
                    )
                    if item["verification_status"] == "verified" and len(entry["request_snippets"]) < max_snippets:
                        entry["request_snippets"].append(item["quote"])
                        entry["request_evidence"].append(item)

    insights_list = list(results.values())
    for entry in insights_list:
        raw = entry.get("subcategory", "")
        if isinstance(raw, str) and "/" in raw:
            main, sub = raw.split("/", 1)
        else:
            main, sub = "other", str(raw)
        entry["main_category"] = main
        entry["sub_category"] = sub
        try:
            count = int(entry.get("count", 0) or 0)
            recommended = int(entry.get("recommended", 0) or 0)
        except Exception:
            count = 0
            recommended = 0
        entry["recommendation_rate"] = float(recommended / count) if count else 0.0

    insights_list.sort(key=lambda item: int(item.get("count", 0) or 0), reverse=True)
    return insights_list


def version_based_insights(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze issues and features by game version (Early Access vs Release).

    Returns insights split by written_during_early_access flag.
    """
    if df is None or df.empty or "written_during_early_access" not in df.columns:
        return {}

    results = {}

    # Split by early access status
    ea_reviews = df[df["written_during_early_access"] == True].copy()  # noqa: E712
    release_reviews = df[df["written_during_early_access"] == False].copy()  # noqa: E712

    for status, reviews_df in [("early_access", ea_reviews), ("release", release_reviews)]:
        if reviews_df.empty:
            continue

        # Basic metrics
        total_reviews = len(reviews_df)
        recommendation_rate = float(reviews_df["voted_up"].mean()) if "voted_up" in reviews_df.columns else 0.0

        # Top subcategories for issues/requests
        top_issue_subcategories = []
        if "llm_issue_subcategories" in reviews_df.columns:
            exploded = reviews_df["llm_issue_subcategories"].explode().dropna()
            if not exploded.empty:
                counts = exploded.value_counts().head(5)
                top_issue_subcategories = [
                    {"subcategory": subcat, "count": int(count)} for subcat, count in counts.items()
                ]

        top_request_subcategories = []
        if "llm_request_subcategories" in reviews_df.columns:
            exploded = reviews_df["llm_request_subcategories"].explode().dropna()
            if not exploded.empty:
                counts = exploded.value_counts().head(5)
                top_request_subcategories = [
                    {"subcategory": subcat, "count": int(count)} for subcat, count in counts.items()
                ]

        # Top categories (main)
        category_counts: dict[str, int] = {}
        if "llm_subcategories" in reviews_df.columns:
            exploded = reviews_df["llm_subcategories"].explode().dropna()
            if not exploded.empty:
                main_counts = exploded.apply(
                    lambda value: str(value).split("/", 1)[0] if "/" in str(value) else str(value)
                )
                category_counts = main_counts.value_counts().head(3).to_dict()
        elif "llm_main_category" in reviews_df.columns:
            category_counts = reviews_df["llm_main_category"].value_counts().head(3).to_dict()

        results[status] = {
            "total_reviews": total_reviews,
            "recommendation_rate": recommendation_rate,
            "top_issue_subcategories": top_issue_subcategories,
            "top_request_subcategories": top_request_subcategories,
            "top_categories": category_counts,
        }

    return results


def category_trend_over_time(df: pd.DataFrame, freq: str = "auto") -> Dict[str, list]:
    """Calculate time series of issue-tagged reviews by main category."""
    if df is None or df.empty or "created_at" not in df.columns or "llm_main_category" not in df.columns:
        return {}

    if "llm_issue_subcategories" not in df.columns:
        return {}

    # Filter to reviews with issues
    df_with_issues = df[df["llm_issue_subcategories"].apply(
        lambda x: isinstance(x, list) and len(x) > 0
    )].copy()

    if df_with_issues.empty:
        return {}

    ts_df = df_with_issues.dropna(subset=["created_at", "llm_main_category"]).copy()
    if ts_df.empty:
        return {}

    # Get date range from first to last review
    min_date = ts_df["created_at"].min()
    max_date = ts_df["created_at"].max()

    # Auto-select frequency based on date range
    if freq == "auto":
        date_span = (max_date - min_date).days
        if date_span <= 14:
            freq = "D"  # Daily for 2 weeks or less
        elif date_span <= 60:
            freq = "W"  # Weekly for 2 months or less
        elif date_span <= 365:
            freq = "2W"  # Bi-weekly for 1 year or less
        else:
            freq = "ME"  # Monthly for more than 1 year

    # Create complete date range
    date_range = pd.date_range(start=min_date, end=max_date, freq=freq)

    category_trends = {}
    for category in ts_df["llm_main_category"].unique():
        cat_df = ts_df[ts_df["llm_main_category"] == category]

        # Group by period and count
        trend = cat_df.set_index("created_at").resample(freq).size()

        # Reindex to include all periods in date range
        trend = trend.reindex(date_range, fill_value=0).reset_index()
        trend.columns = ["period", "count"]
        trend["period"] = trend["period"].dt.strftime("%Y-%m-%d")

        category_trends[category] = json.loads(trend.to_json(orient="records"))

    return category_trends


def prepare_insights(
    df: pd.DataFrame, run_id: str | None = None, app_id: int | None = None
) -> Dict[str, Any]:
    """Build a JSON-serialisable insight payload for the given review frame."""
    if df is None or df.empty:
        default_metrics = {
            "total_reviews": 0,
            "share_positive": 0.0,
            "share_negative": 0.0,
            "feature_request_rate": 0.0,
            "issue_rate": 0.0,
            "coverage_rate": 0.0,
        }
        empty_payload = {
            "metrics": default_metrics,
            "llm": {
                "feature_request_rate": 0.0,
                "issue_rate": 0.0,
                "coverage_rate": 0.0,
            },
            "category_breakdown": {},
            "category_recommendation_rates": {},
            "playtime": {},
            "helpful": {},
            "recommendation": {},
            "sentiment_counts": [],
            "trend": [],
            "segments": {
                "early_access_vs_release": [],
                "free_vs_paid": [],
                "playtime_buckets": [],
            },
            "audience": {
                "reviewer_influence": [],
                "veteran_benchmarking": [],
                "market_quality": [],
            },
            "risk": {
                "refund_risk": 0.0,
                "core_fan_disappointment": 0.0,
            },
            "subcategory_insights": [],
            "theme": derive_theme(default_metrics),
            "metric_provenance": build_metric_provenance(df, run_id),
        }
        empty_payload["five_questions"] = build_five_question_contract(empty_payload, run_id=run_id)
        return empty_payload

    metrics = summarize_sentiment(df)
    playtime = summarize_playtime(df)
    helpful = helpfulness_summary(df)
    recommendation = recommendation_rate(df)

    # LLM-derived actionable metrics use only validated LLM classifications.
    if "llm_label_origin" in df.columns and "llm_validated" in df.columns:
        classified_mask = df["llm_label_origin"].isin(["llm", "offline_fixture"]) & (df["llm_validated"] == True)  # noqa: E712
        classified_df = df[classified_mask].copy()
    else:
        classified_df = df.iloc[0:0].copy()
    classified_count = len(classified_df)
    population_count = len(df)
    feature_request_rate = 0.0
    issue_rate = 0.0
    if "llm_request_subcategories" in classified_df.columns:
        feature_request_rate = float(
            classified_df["llm_request_subcategories"].apply(lambda v: isinstance(v, list) and len(v) > 0).mean()
        )
    if "llm_issue_subcategories" in classified_df.columns:
        issue_rate = float(
            classified_df["llm_issue_subcategories"].apply(lambda v: isinstance(v, list) and len(v) > 0).mean()
        )

    coverage_rate = float(classified_count / population_count) if population_count else 0.0

    category_breakdown: dict[str, dict[str, int]] = {}
    category_recommendation_rates: dict[str, dict[str, Any]] = {}
    if "llm_subcategories" in classified_df.columns:
        exploded = classified_df["llm_subcategories"].apply(_listify).explode().dropna()
        if not exploded.empty:
            for item in exploded:
                text = str(item)
                if "/" in text:
                    main_cat, subcat = text.split("/", 1)
                else:
                    main_cat, subcat = "other", text
                if not main_cat or not subcat:
                    continue
                category_breakdown.setdefault(main_cat, {})
                category_breakdown[main_cat][subcat] = category_breakdown[main_cat].get(subcat, 0) + 1

        main_categories = list(category_breakdown.keys())
        for main_cat in main_categories:
            mask = classified_df["llm_subcategories"].apply(
                lambda values: isinstance(values, list) and any(
                    isinstance(entry, str) and entry.startswith(f"{main_cat}/") for entry in values
                )
            )
            main_df = classified_df[mask]
            if main_df.empty:
                continue
            recommendation_rate_cat = float(main_df["voted_up"].mean()) if "voted_up" in main_df.columns else 0.0
            category_recommendation_rates[main_cat] = {
                "rate": recommendation_rate_cat,
                "count": len(main_df),
                "recommended": int(main_df["voted_up"].sum()) if "voted_up" in main_df.columns else 0,
                "not_recommended": int((~main_df["voted_up"]).sum()) if "voted_up" in main_df.columns else 0,
            }

    metrics.update(
        {
            "feature_request_rate": feature_request_rate,
            "issue_rate": issue_rate,
            "coverage_rate": coverage_rate,
        }
    )

    # Derive sentiment counts from voted_up (thumbs up/down)
    sentiment_counts = pd.DataFrame([
        {"sentiment": "positive", "count": int(df["voted_up"].sum())},
        {"sentiment": "negative", "count": int((~df["voted_up"]).sum())},
    ])

    trend_df = recommended_share_over_time(df, freq="W-SUN", fill_missing=True)


    llm_summary = {
        "feature_request_rate": feature_request_rate,
        "issue_rate": issue_rate,
        "coverage_rate": coverage_rate,
    }
    subcategory_insights = aggregate_subcategory_insights(classified_df, run_id=run_id, app_id=app_id)

    insights = {
        "metrics": metrics,
        "llm": llm_summary,
        "category_breakdown": category_breakdown,
        "category_recommendation_rates": category_recommendation_rates,
        "category_trend": category_trend_over_time(df),
        "version_insights": version_based_insights(classified_df),
        "playtime": playtime,
        "helpful": helpful,
        "recommendation": recommendation,
        "sentiment_counts": _frame_records(sentiment_counts),
        "trend": _frame_records(trend_df),
        "segments": {
            "early_access_vs_release": _frame_records(early_access_vs_release_sentiment(df)),
            "free_vs_paid": _frame_records(free_vs_paid_sentiment(df)),
            "playtime_buckets": _frame_records(playtime_segment_sentiment(df)),
        },
        "audience": {
            "reviewer_influence": _frame_records(reviewer_influence_sentiment(df)),
            "veteran_benchmarking": _frame_records(veteran_benchmarking(df)),
            "market_quality": _frame_records(market_quality_signal(df)),
        },
        "risk": {
            "refund_risk": refund_risk_index(df),
            "core_fan_disappointment": core_fan_disappointment(df),
        },
        "subcategory_insights": subcategory_insights,
        "player_segments": {
            "experience_level": experience_level_issues(df),
            "purchase_type": purchase_type_insights(df),
            "engagement_topics": engagement_based_topics(df),
            "activity_status": activity_based_feedback(df),
            "platform": platform_segment_insights(df),
            "language": language_segment_insights(df),
        },
        "quality_weighted": quality_weighted_insights(df),
        "cross_segment": cross_segment_analysis(df),
        "theme": derive_theme(metrics),
        "metric_provenance": build_metric_provenance(df, run_id),
    }
    insights["five_questions"] = build_five_question_contract(insights, run_id=run_id)

    return insights


def derive_theme(metrics: Dict[str, float]) -> Dict[str, Any]:
    """Create a color palette derived from sentiment distribution."""
    positive_share = metrics.get("share_positive", 0.0)
    negative_share = metrics.get("share_negative", 0.0)

    if positive_share >= 0.6 and positive_share - negative_share >= 0.25:
        theme_name = "Aurora"
        gradient = ["#0ea5e9", "#6366f1", "#03111f"]
        palette = {
            "accent": "#38bdf8",
            "secondary": "#6366f1",
            "positive": "#6366f1",
            "neutral": "#cbd5f5",
            "negative": "#fa8072",
            "surface": "#082f49",
            "surface_alt": "#0f172a",
            "border": "rgba(148,163,184,0.25)",
        }
    elif negative_share >= 0.45:
        theme_name = "Inferno"
        gradient = ["#f97316", "#fa8072", "#111827"]
        palette = {
            "accent": "#f97316",
            "secondary": "#fa8072",
            "positive": "#6366f1",
            "neutral": "#fca5a5",
            "negative": "#fa8072",
            "surface": "#1f1b2e",
            "surface_alt": "#111827",
            "border": "rgba(248,113,113,0.25)",
        }
    else:
        theme_name = "Twilight"
        gradient = ["#6366f1", "#22d3ee", "#0b1120"]
        palette = {
            "accent": "#6366f1",
            "secondary": "#22d3ee",
            "positive": "#6366f1",
            "neutral": "#cbd5f5",
            "negative": "#fa8072",
            "surface": "#151635",
            "surface_alt": "#0f172a",
            "border": "rgba(129,140,248,0.25)",
        }

    return {
        "name": theme_name,
        "gradient": gradient,
        "palette": palette,
    }
