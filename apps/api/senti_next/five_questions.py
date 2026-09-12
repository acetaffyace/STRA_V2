"""Deterministic five-question decision contract for V1/P1."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _observation(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {"value": None, "status": "unavailable", "unavailable_reason": "missing_observation"}


def _top_signals(insights: Mapping[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for item in insights.get("subcategory_insights") or []:
        if not isinstance(item, Mapping):
            continue
        count = int(item.get("count") or 0)
        issues = int(item.get("issue_count") or 0)
        requests = int(item.get("request_count") or 0)
        denominator = max(count, 0)
        negative = int(item.get("not_recommended") or 0)
        prevalence = _ratio(count, int((insights.get("metric_provenance") or {}).get("review_count", {}).get("value") or 0))
        negative_concentration = _ratio(negative, denominator)
        score = round((prevalence or 0) * 0.45 + (negative_concentration or 0) * 0.35 + min(issues + requests, denominator) / max(denominator, 1) * 0.20, 6)
        topic = item.get("subcategory") or item.get("sub_category") or "other/general"
        signals.append({
            "topic": topic,
            "display_title": _display_topic(str(topic)),
            "count": count,
            "denominator": denominator,
            "prevalence": prevalence,
            "negative_concentration": negative_concentration,
            "issue_count": issues,
            "request_count": requests,
            "evidence": item.get("issue_evidence") or item.get("request_evidence") or [],
            "priority_score": score,
            "score_is_heuristic": True,
        })
    return sorted(signals, key=lambda x: (x["priority_score"], x["count"]), reverse=True)[:limit]


def _display_topic(topic: str) -> str:
    labels = {
        "technical/bugs": "技术与稳定性 / 缺陷与错误",
        "gameplay/feature_requests": "游戏玩法 / 功能需求",
        "content_design/general": "内容与设计 / 一般反馈",
    }
    return labels.get(topic, topic.replace("_", " ").replace("/", " / "))


def build_five_question_contract(
    insights: Mapping[str, Any],
    *,
    previous_insights: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    mode: str = "production",
) -> dict[str, Any]:
    """Build a provenance-aware, non-causal decision structure.

    This function deliberately uses existing observations and evidence only;
    it does not invent a comparison window or causal explanation.
    """
    provenance = insights.get("metric_provenance") or {}
    current_rec = _observation(provenance.get("recommendation_rate"))
    current_issue = _observation(provenance.get("technical_issue_rate"))
    current_request = _observation(provenance.get("feature_request_rate"))
    population = int(current_rec.get("denominator") or 0)
    signals = _top_signals(insights)

    changes: dict[str, Any]
    if not previous_insights:
        changes = {
            "status": "unavailable",
            "reason": "comparison_window_missing",
            "observations": [],
            "confidence_note": "没有基线窗口，不能声称近期发生了变化。",
        }
    else:
        previous = previous_insights.get("metric_provenance") or {}
        observations = []
        for metric_id in ("recommendation_rate", "technical_issue_rate", "feature_request_rate"):
            now = _observation(provenance.get(metric_id))
            before = _observation(previous.get(metric_id))
            if now.get("value") is None or before.get("value") is None:
                continue
            observations.append({
                "metric_id": metric_id,
                "current": now,
                "previous": before,
                "delta": round(float(now["value"]) - float(before["value"]), 6),
            })
        changes = {
            "status": "available" if observations else "unavailable",
            "observations": observations,
            "confidence_note": "这是窗口间观察关联，不是因果证明。",
        }

    language_segments = ((insights.get("player_segments") or {}).get("language") or [])
    if isinstance(language_segments, dict):
        language_segments = list(language_segments.values())
    elif not isinstance(language_segments, list):
        language_segments = []
    who = {
        "supported_dimensions": ["language", "playtime", "recommendation_state"],
        "observations": language_segments,
        "denominator_note": "每个 cohort 结论必须使用其自身样本分母；未提供的 cohort 不推断。",
    }

    actions: list[dict[str, Any]] = []
    for signal in signals[:5]:
        if signal["request_count"] > signal["issue_count"] and signal["request_count"] > 0:
            action_class = "BUILD"
            action = "评估是否纳入需求池，并用后续请求支持率和推荐率验证。"
        elif signal["issue_count"] > 0:
            action_class = "FIX" if signal["negative_concentration"] and signal["negative_concentration"] >= 0.5 else "IMPROVE"
            action = "优先复核该问题的真实复现范围，再用后续窗口的负面率和问题率验证。"
        else:
            action_class = "AMPLIFY"
            action = "保留并强化这一正向体验，同时用后续窗口的推荐率验证。"
        actions.append({
            "action_class": action_class,
            "title": signal["display_title"],
            "taxonomy_key": signal["topic"],
            "observed_signal": signal,
            "rationale": "基于透明启发式排序，不代表因果或产品优先级事实。",
            "evidence": signal["evidence"],
            "affected_group": "当前 Run 人口；未观测 cohort 不外推。",
            "uncertainty": "Steam 评论是自选择观察样本，分类覆盖和 taxonomy 精度有限。",
            "validation_plan": action,
        })

    current_snapshot = {
        "status": "available" if population else "unavailable",
        "recommendation": current_rec,
        "strongest_positive_signal": next((s for s in signals if (s.get("negative_concentration") or 0) < 0.5), None),
        "leading_problem_signal": next((s for s in signals if s.get("issue_count", 0) > 0), None),
        "leading_request_signal": next((s for s in signals if s.get("request_count", 0) > 0), None),
        "observed_cohort_concentration": who.get("observations", [])[:3],
        "note": "这是当前 Run 的单窗口观察，不代表近期变化，也不是因果结论。",
    }

    return {
        "contract_version": "p1.1-v1",
        "analysis_design": (insights.get("adaptive_analysis") or {}).get("design"),
        "evidence_grade": (insights.get("adaptive_analysis") or {}).get("evidence_grade"),
        "run_id": run_id,
        "mode": mode,
        "what_changed": changes,
        "current_snapshot": current_snapshot,
        "why": {
            "positive_aspects": [s for s in signals if s["negative_concentration"] is not None and s["negative_concentration"] < 0.5][:5],
            "problem_aspects": [s for s in signals if s["issue_count"] > 0][:5],
            "explicit_requests": [s for s in signals if s["request_count"] > 0][:5],
            "observations": {"recommendation_rate": current_rec, "issue_rate": current_issue, "request_rate": current_request},
            "coverage": _observation(provenance.get("classification_coverage")),
        },
        "who_affected": who,
        "what_matters": {
            "signals": signals,
            "ranking_method": "prevalence 45% + negative concentration 35% + issue/request support 20%",
            "is_heuristic": True,
            "population_denominator": population,
        },
        "recommended_actions": actions,
    }
