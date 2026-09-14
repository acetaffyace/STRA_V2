"""Deterministic Discovery Pool selection for Semantic Engine V2.

The pool is a diagnostic input to clustering/adjudication. It never changes
formal topic prevalence and never promotes a candidate into a catalog.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping


_BANDS = {"HIGH", "MEDIUM", "LOW"}


def _stable_rank(seed: str, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()


def build_discovery_pool(
    units: Iterable[Mapping[str, Any]],
    *,
    seed: str,
    max_low: int = 500,
    max_medium: int = 300,
    max_high_per_topic: int = 25,
    high_volume_topic_min: int = 100,
    recent_review_ids: Iterable[str] = (),
    novelty_unit_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Select deterministic, reason-coded units for open-set discovery.

    LOW units are eligible by default, MEDIUM units are sampled, and HIGH
    units are included when they come from a high-volume topic or a recent
    burst. Novelty/outlier flags can add a unit from any band. Stable hash
    ranking keeps the selection independent of input/query order.
    """
    if not str(seed).strip():
        raise ValueError("discovery_pool_seed_required")
    if min(max_low, max_medium, max_high_per_topic, high_volume_topic_min) < 0:
        raise ValueError("discovery_pool_limits_invalid")
    recent = {str(value) for value in recent_review_ids}
    novelty = {str(value) for value in novelty_unit_ids}
    normalized: list[dict[str, Any]] = []
    topic_counts: Counter[str] = Counter()
    for unit in units:
        if not isinstance(unit, Mapping):
            raise ValueError("discovery_pool_unit_invalid")
        unit_id = str(unit.get("semantic_unit_id") or unit.get("unit_id") or "").strip()
        review_id = str(unit.get("review_id") or "").strip()
        band = str(unit.get("decision_band") or "").upper().strip()
        if not unit_id or not review_id or band not in _BANDS:
            raise ValueError("discovery_pool_unit_identity_invalid")
        topic = str(unit.get("core_topic_id") or "").strip()
        if topic:
            topic_counts[topic] += 1
        normalized.append({"unit": dict(unit), "unit_id": unit_id, "review_id": review_id, "band": band, "topic": topic})
    normalized.sort(key=lambda item: item["unit_id"])

    selected: dict[str, dict[str, Any]] = {}

    def add(item: dict[str, Any], reason: str) -> None:
        current = selected.get(item["unit_id"])
        if current is None:
            selected[item["unit_id"]] = {**item["unit"], "pool_reasons": [reason]}
        elif reason not in current["pool_reasons"]:
            current["pool_reasons"].append(reason)

    for item in sorted((item for item in normalized if item["band"] == "LOW"), key=lambda item: _stable_rank(seed, item["unit_id"]))[:max_low]:
        add(item, "low_confidence")
    for item in sorted((item for item in normalized if item["band"] == "MEDIUM"), key=lambda item: _stable_rank(seed, item["unit_id"]))[:max_medium]:
        add(item, "medium_confidence_sample")

    high_by_topic: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in normalized:
        if item["band"] == "HIGH" and item["topic"]:
            high_by_topic[item["topic"]].append(item)
    for topic, topic_items in sorted(high_by_topic.items()):
        if topic_counts[topic] < high_volume_topic_min:
            continue
        for item in sorted(topic_items, key=lambda value: _stable_rank(seed, value["unit_id"]))[:max_high_per_topic]:
            add(item, "high_volume_topic_sample")
    for item in normalized:
        if item["review_id"] in recent:
            add(item, "recent_temporal_burst")
        if item["unit_id"] in novelty:
            add(item, "novelty_or_outlier")
    result = []
    for unit_id in sorted(selected):
        selected[unit_id]["pool_reasons"] = sorted(selected[unit_id]["pool_reasons"])
        result.append(selected[unit_id])
    return result


def sample_cluster_evidence(
    members: Iterable[Mapping[str, Any]],
    *,
    representative_ids: Iterable[str] = (),
    limit_per_type: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Return central, diverse and boundary evidence without first-N slicing."""
    if limit_per_type < 1:
        raise ValueError("cluster_sample_limit_invalid")
    items = [dict(item) for item in members if isinstance(item, Mapping)]
    items.sort(key=lambda item: str(item.get("semantic_unit_id") or item.get("unit_id") or ""))
    by_id = {str(item.get("semantic_unit_id") or item.get("unit_id")): item for item in items}
    central = [by_id[item_id] for item_id in representative_ids if item_id in by_id][:limit_per_type]
    if not central:
        central = items[:limit_per_type]
    diverse: list[dict[str, Any]] = []
    seen_languages: set[str] = set()
    for item in items:
        language = str(item.get("language") or "unknown")
        if language not in seen_languages:
            diverse.append(item)
            seen_languages.add(language)
        if len(diverse) >= limit_per_type:
            break
    boundary = sorted(items, key=lambda item: (float(item.get("similarity_score") or 0.0), str(item.get("semantic_unit_id") or item.get("unit_id") or "")))[:limit_per_type]
    return {"central": central, "diverse": diverse, "boundary": boundary}


__all__ = ["build_discovery_pool", "sample_cluster_evidence"]

