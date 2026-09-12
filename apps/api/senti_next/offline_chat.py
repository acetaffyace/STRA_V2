"""Deterministic evidence-first chat helper for offline development mode."""
from __future__ import annotations

from typing import Any, Mapping


def answer_offline_question(result: Mapping[str, Any], question: str) -> dict[str, Any]:
    """Answer a bounded question from a stored result without generating prose via an LLM."""
    insights = result.get("insights") or {}
    five = insights.get("five_questions") or {}
    q = question.lower()
    if any(word in q for word in ("变化", "changed", "最近", "recent")):
        section = five.get("what_changed") or {}
        title = "最近变化"
    elif any(word in q for word in ("为什么", "why", "满意", "不满意")):
        section = five.get("why") or {}
        title = "满意 / 不满意原因"
    elif any(word in q for word in ("谁", "who", "影响", "affected")):
        section = five.get("who_affected") or {}
        title = "受影响群体"
    elif any(word in q for word in ("行动", "做什么", "action", "priorit")):
        section = {"actions": five.get("recommended_actions") or []}
        title = "建议行动"
    else:
        section = five.get("what_matters") or {}
        title = "重要信号"

    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for signal in (section.get("problem_aspects") or []) + (section.get("explicit_requests") or []) + (section.get("positive_aspects") or []):
        for evidence in signal.get("evidence") or []:
            review_id = str(evidence.get("review_id") or "")
            if not review_id or review_id in seen:
                continue
            seen.add(review_id)
            citations.append({
                "review_id": review_id,
                "quote": str(evidence.get("quote") or "")[:240],
                "verification_status": evidence.get("verification_status", "verified"),
                "verification_method": evidence.get("verification_method", "exact_substring"),
                "source_review_hash": evidence.get("source_review_hash"),
            })
            if len(citations) >= 5:
                break
        if len(citations) >= 5:
            break
    if not citations:
        for review in result.get("reviews") or []:
            text = str(review.get("review") or "").strip()
            if not text:
                continue
            citations.append({
                "review_id": str(review.get("recommendationid") or review.get("review_id") or ""),
                "quote": text[:180],
                "verification_status": "verified",
                "verification_method": "exact_substring_of_source_review",
            })
            if len(citations) >= 3:
                break

    if title == "重要信号":
        items = section.get("signals") or []
        answer = {
            "观察": [
                {"主题": item.get("topic"), "评论数": item.get("count"), "问题数": item.get("issue_count"), "需求数": item.get("request_count")}
                for item in items[:5]
            ],
            "说明": "排序为透明启发式辅助，不代表因果关系或正式优先级。",
        }
    elif title == "建议行动":
        answer = {
            "行动": [
                {"类型": item.get("action_class"), "信号": item.get("title"), "验证计划": item.get("validation_plan")}
                for item in section.get("actions", [])[:5]
            ],
            "说明": "离线 Fixture 仅用于验证产品行为，不代表真实模型质量。",
        }
    return {
        "mode": result.get("mode", "codex_offline_fixture"),
        "title": title,
        "answer": answer if "answer" in locals() else section,
        "citations": citations,
        "traceability": "deterministic result/evidence lookup; no provider call",
        "causal_claim": False,
    }
