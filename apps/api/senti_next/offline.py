"""Explicit offline fixture execution path for development/test mode."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import llm, storage
from .analysis import build_reviews_dataframe
from .five_questions import build_five_question_contract
from .adaptive_analysis import (
    build_analysis_design,
    evidence_grade,
    infer_game_profile,
    population_comparability,
    robustness_matrix,
    select_adaptive_window,
)
from .offline_chat import answer_offline_question
from .insights import prepare_insights

OFFLINE_ORIGIN = "codex_offline_fixture"
OFFLINE_LABEL_ORIGIN = "offline_fixture"


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _normalize_review(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.setdefault("recommendationid", item.get("review_id") or uuid4().hex)
    item.setdefault("author", {})
    item.setdefault("language", "english")
    item.setdefault("voted_up", True)
    item.setdefault("review", "")
    return item


def generate_codex_fixture_label(review: dict[str, Any]) -> dict[str, Any]:
    """Create a clearly development-only deterministic label.

    This is intentionally a conservative keyword fixture, not a quality claim
    and not a replacement for the accepted human Gold set.
    """
    text = str(review.get("review") or "")
    lowered = text.lower()
    issue = []
    request = []
    if any(word in lowered for word in ("bug", "crash", "stutter", "fps", "controller", "save", "reset", "sync")):
        issue.append("technical/bugs")
    if any(word in lowered for word in ("please", "add", "option", "slider", "more", "remap", "needs")):
        request.append("gameplay/feature_requests")
    if not issue and not request:
        subcategories = ["content_design/general"]
    elif issue and request:
        subcategories = ["technical/bugs", "gameplay/feature_requests"]
    elif issue:
        subcategories = list(issue)
    else:
        subcategories = list(request)
    evidence: dict[str, list[str]] = {}
    for subcategory in subcategories:
        evidence[subcategory] = [text[:180]] if text else []
    return {
        "main_category": subcategories[0].split("/", 1)[0],
        "subcategory": subcategories[0].split("/", 1)[-1],
        "subcategories": subcategories,
        "issue_subcategories": issue,
        "request_subcategories": request,
        "evidence": evidence,
        "aspects": [],
        "_label_source": OFFLINE_ORIGIN,
        "_label_model": OFFLINE_ORIGIN,
    }


def run_offline_fixture(
    *,
    app_id: int,
    reviews_path: str | Path,
    game_context: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run ingest -> labels -> insights -> immutable result without a provider."""
    raw_reviews = [_normalize_review(row) for row in load_jsonl(reviews_path)]
    reviews_by_id: dict[str, dict[str, Any]] = {}
    for review in raw_reviews:
        reviews_by_id.setdefault(str(review["recommendationid"]), review)
    reviews = list(reviews_by_id.values())
    if not reviews:
        raise ValueError("Offline fixture contains no reviews")
    run_id = run_id or f"offline-{uuid4().hex}"
    storage.init_db()
    storage.create_general_analysis_run(
        run_id, app_id,
        config={"mode": OFFLINE_ORIGIN, "reviews_path": str(reviews_path)},
        requested_languages=sorted({str(r.get("language") or "english") for r in reviews}),
        requested_review_count=len(reviews), provider=None, model_id=None,
        prompt_version=llm.ACTIVE_PROMPT_VERSION, taxonomy_version=llm.TAXONOMY_VERSION,
        analysis_version="offline-fixture-v1",
    )
    storage.transition_general_analysis_run(run_id, "running", phase="offline_fixture")
    storage.upsert_reviews(app_id, reviews)

    profile = infer_game_profile(game_context or {}, reviews)
    event: dict[str, Any] = {}
    selected_window = select_adaptive_window(profile, event, reviews)
    analysis_design = build_analysis_design(
        app_id=app_id,
        analysis_type="current_snapshot",
        profile=profile,
        event=event,
        window=selected_window,
        sensitivity_windows=[{"label": f"plus_minus_{days}d", "days": days} for days in selected_window.get("sensitivity_days", [])],
        comparison_basis="current_snapshot_no_valid_event",
        population_rules={"source": "offline_fixture", "review_count": len(reviews), "deduplication": "recommendationid"},
        metrics=["recommendation_rate", "technical_issue_rate", "feature_request_rate"],
    )
    analysis_design["descriptive_only"] = True
    analysis_design["selection_reasons"] = list(selected_window.get("reason_codes", []))
    storage.save_analysis_design(analysis_design, run_id)

    labels: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    existing_labels = storage.load_review_labels(app_id)
    cache_reused = 0
    cache_miss = 0
    for review in reviews:
        review_id = str(review["recommendationid"])
        review_hash = hashlib.sha256(str(review.get("review") or "").encode()).hexdigest()
        cached = existing_labels.get(review_id) or {}
        if cached.get("label_origin") == OFFLINE_LABEL_ORIGIN and cached.get("review_hash") == review_hash:
            cache_reused += 1
        else:
            cache_miss += 1
        payload = generate_codex_fixture_label(review)
        labels[review_id] = {**payload, "label_origin": OFFLINE_LABEL_ORIGIN, "validated": True}
        items.append({
            "app_id": app_id, "review_id": review_id,
            "review_hash": review_hash,
            "classification_input_hash": review_hash,
            "was_truncated": False, "original_char_count": len(str(review.get("review") or "")),
            "processed_char_count": len(str(review.get("review") or "")),
            "payload": payload, "model": OFFLINE_ORIGIN,
            "prompt_version": llm.ACTIVE_PROMPT_VERSION,
            "label_origin": OFFLINE_LABEL_ORIGIN, "validated": True,
            "taxonomy_version": llm.TAXONOMY_VERSION, "provider": None,
            "model_id": None,
        })
    storage.bulk_upsert_review_labels(items)
    df = llm.apply_review_labels(build_reviews_dataframe(reviews), labels)
    insights = prepare_insights(df, run_id=run_id, app_id=app_id)
    verified_evidence_count = sum(
        1 for item in insights.get("subcategory_insights", [])
        for evidence in (item.get("issue_evidence") or []) + (item.get("request_evidence") or [])
        if evidence.get("verification_status") == "verified"
    )
    robustness = robustness_matrix({}, lambda review: not bool(review.get("voted_up")))
    comparability = population_comparability([], [])
    insights["adaptive_analysis"] = {
        "profile": profile,
        "mode": "current_snapshot",
        "event": None,
        "design": analysis_design,
        "comparability": comparability,
        "robustness": robustness,
        "evidence_grade": evidence_grade(
            sample_support=len(reviews),
            robustness=robustness,
            comparability=comparability,
            verified_evidence_count=verified_evidence_count,
            label_reliability="warn",
            confounder_risk="high",
        ),
    }
    insights["five_questions"] = build_five_question_contract(insights, run_id=run_id, mode=OFFLINE_ORIGIN)
    metadata = {
        "app_id": app_id, "requested": len(reviews), "retrieved": len(reviews),
        "language": "all", "languages": sorted({str(r.get("language") or "english") for r in reviews}),
        "mode": OFFLINE_ORIGIN, "provider": None, "model": None,
        "provenance": {"origin": OFFLINE_ORIGIN, "human_gold": False, "provider_output": False},
        "crawl_quality": {
            "requested_window": None,
            "oldest_review_timestamp": min((r.get("timestamp_created") for r in reviews if r.get("timestamp_created")), default=None),
            "newest_review_timestamp": max((r.get("timestamp_created") for r in reviews if r.get("timestamp_created")), default=None),
            "raw_rows_received": len(raw_reviews),
            "unique_reviews": len(reviews),
            "duplicates_removed": len(raw_reviews) - len(reviews),
            "stop_reason": "offline_fixture_complete",
            "complete": True,
            "review_count_used": len(reviews),
        },
        "counters": {
            "requested_review_count": len(reviews), "retrieved_count": len(reviews),
            "cache_reused_count": cache_reused, "cache_miss_count": cache_miss,
            "classified_count": len(reviews), "fallback_count": 0, "unavailable_count": 0,
        },
    }
    snapshot_hash = hashlib.sha256(",".join(sorted(str(r["recommendationid"]) for r in reviews)).encode()).hexdigest()[:16]
    storage.finalize_general_analysis_run(
        run_id, app_id, metadata, insights, reviews,
        snapshot_hash=snapshot_hash, context_hash=None,
        counts={"retrieved_count": len(reviews), "valid_review_count": len(df), "classified_count": len(df)},
    )
    result = {"run_id": run_id, "metadata": metadata, "insights": insights, "reviews": reviews, "review_count": len(reviews), "mode": OFFLINE_ORIGIN}
    result["offline_chat"] = answer_offline_question(result, "当前评论中玩家最常提到哪些问题？请给我原始证据。")
    return result
