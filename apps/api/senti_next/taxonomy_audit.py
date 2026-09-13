"""Read-only coverage audit of existing taxonomy labels."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping, Sequence


def _labels_for(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Mapping):
        payload = value.get("labels") or value.get("taxonomy_labels") or value.get("all_labels")
        if payload is not None:
            return _labels_for(payload)
        for key in ("main_category", "taxonomy_key", "topic", "primary_label"):
            if value.get(key):
                return [str(value[key])]
        return []
    if isinstance(value, (list, tuple, set)):
        return sorted({str(item) for item in value if item})
    return []


def _entropy(counts: Counter[str]) -> float | None:
    total = sum(counts.values())
    if not total or len(counts) <= 1:
        return 0.0 if total else None
    return float(-sum((count / total) * math.log(count / total, 2) for count in counts.values()))


def audit_region_taxonomy(review_ids: Sequence[str], labels_by_review: Mapping[str, Any], *, minimum_support: int = 5) -> dict[str, Any]:
    """Return coverage primitives without creating or changing taxonomy labels."""
    support = len(review_ids)
    label_lists = {review_id: _labels_for(labels_by_review.get(review_id)) for review_id in review_ids}
    labeled_ids = [review_id for review_id, labels in label_lists.items() if labels]
    primary = Counter(labels[0] for labels in label_lists.values() if labels)
    all_labels = Counter(label for labels in label_lists.values() for label in labels)
    coverage_rate = len(labeled_ids) / support if support else 0.0
    primary_distribution = {key: value for key, value in sorted(primary.items())}
    all_distribution = {key: value for key, value in sorted(all_labels.items())}
    other_count = sum(value for key, value in primary.items() if key == "other/general" or key.startswith("other/"))
    concentration = max(primary.values()) / len(labeled_ids) if primary and labeled_ids else 0.0
    if support == 0 or not labeled_ids:
        status = "unlabeled"
    elif len(labeled_ids) < minimum_support or coverage_rate < 0.5:
        status = "insufficient_taxonomy_coverage"
    elif other_count / len(labeled_ids) >= 0.8:
        status = "potential_gap"
    elif concentration >= 0.8:
        status = "well_covered"
    else:
        status = "mixed_existing_labels"
    return {
        "support_reviews": support,
        "labeled_review_n": len(labeled_ids),
        "unlabeled_review_n": support - len(labeled_ids),
        "taxonomy_coverage_rate": coverage_rate,
        "primary_label_distribution": primary_distribution,
        "all_label_distribution": all_distribution,
        "primary_label_entropy": _entropy(primary),
        "other_general_share": other_count / len(labeled_ids) if labeled_ids else None,
        "coverage_status": status,
        "gap_candidate": status == "potential_gap" and support >= minimum_support,
        "minimum_support": minimum_support,
    }
