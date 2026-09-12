from apps.api.senti_next.routes.analysis import _build_population_provenance


def test_population_provenance_preserves_exact_minimal_temporal_fields():
    output = _build_population_provenance([
        {"recommendationid": "steam-a", "timestamp_created": 1700000000, "voted_up": True, "review": "long text"},
        {"recommendationid": "steam-b", "timestamp_created": 1700000100, "voted_up": False, "llm_main_category": "issue"},
    ])

    assert output["population_count"] == 2
    assert output["complete"] is True
    assert output["rows"] == [
        {"review_id": "steam-a", "timestamp_created": 1700000000, "voted_up": True},
        {"review_id": "steam-b", "timestamp_created": 1700000100, "voted_up": False},
    ]


def test_population_provenance_marks_missing_temporal_source_incomplete():
    output = _build_population_provenance([
        {"recommendationid": "steam-a", "timestamp_created": 1700000000, "voted_up": True},
        {"recommendationid": "steam-b", "timestamp_created": None, "voted_up": False},
    ])

    assert output["population_count"] == 2
    assert output["complete"] is False
