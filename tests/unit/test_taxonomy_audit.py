from __future__ import annotations

from apps.api.senti_next.taxonomy_audit import audit_region_taxonomy


def test_well_covered_and_entropy_are_reported_without_mutation() -> None:
    labels = {str(i): {"main_category": "technical/performance"} for i in range(10)}
    result = audit_region_taxonomy(list(labels), labels)
    assert result["coverage_status"] == "well_covered"
    assert result["taxonomy_coverage_rate"] == 1.0
    assert result["primary_label_entropy"] == 0.0


def test_other_general_region_is_gap_candidate_not_new_taxonomy() -> None:
    labels = {str(i): {"main_category": "other/general"} for i in range(10)}
    result = audit_region_taxonomy(list(labels), labels)
    assert result["coverage_status"] == "potential_gap"
    assert result["gap_candidate"] is True


def test_mixed_labels_and_insufficient_coverage_are_distinct() -> None:
    mixed = {str(i): {"main_category": label} for i, label in enumerate(["technical/bugs", "technical/performance", "technical/compatibility", "other/general", "technical/bugs"])}
    assert audit_region_taxonomy(list(mixed), mixed)["coverage_status"] == "mixed_existing_labels"
    sparse = {str(i): {"main_category": "technical/bugs"} for i in range(2)}
    sparse.update({str(i): {} for i in range(2, 10)})
    assert audit_region_taxonomy(list(sparse), sparse)["coverage_status"] == "insufficient_taxonomy_coverage"


def test_unlabeled_is_not_other_general() -> None:
    labels = {str(i): {} for i in range(10)}
    result = audit_region_taxonomy(list(labels), labels)
    assert result["coverage_status"] == "unlabeled"
    assert result["other_general_share"] is None
