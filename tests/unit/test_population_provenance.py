from apps.api.senti_next.routes.analysis import AnalyzeMetadata, _build_population_provenance, _derive_acquisition_coverage
from apps.api.senti_next.sampling import SamplingContract


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


def test_complete_sampling_contract_defines_acquisition_coverage_not_observed_bounds():
    contract = SamplingContract(app_id=10, start_time=1700000000, end_time=1701209600)
    coverage = _derive_acquisition_coverage(contract, {"collection_complete": True, "truncated_by_max_reviews": False})
    metadata = AnalyzeMetadata(
        app_id=10,
        requested=0,
        retrieved=1,
        language="all",
        sampling_contract=contract.to_dict(),
        coverage_start_time=coverage["coverage_start_time"],
        coverage_end_time=coverage["coverage_end_time"],
        coverage_status=coverage["coverage_status"],
        coverage_end_inclusive=coverage["coverage_end_inclusive"],
        window_start="2023-11-14",
        window_end="2023-11-15",
    )
    output = _build_population_provenance(
        [{"recommendationid": "r", "timestamp_created": 1700600000, "voted_up": True}],
        metadata,
    )
    assert output["coverage_start_time"] == 1700000000.0
    assert output["coverage_end_time"] == 1701209600.0
    assert output["coverage_status"] == "complete"
    assert output["observed_review_start_time"] == 1700600000
    assert output["observed_review_end_time"] == 1700600000


def test_incomplete_or_truncated_contract_has_incomplete_coverage():
    contract = SamplingContract(app_id=10, start_time=1700000000, end_time=1701209600)
    for stats in (
        {"collection_complete": False, "truncated_by_max_reviews": False},
        {"collection_complete": True, "truncated_by_max_reviews": True},
    ):
        coverage = _derive_acquisition_coverage(contract, stats)
        assert coverage["coverage_start_time"] is None
        assert coverage["coverage_end_time"] is None
        assert coverage["coverage_status"] == "incomplete"


def test_unbounded_complete_contract_has_unknown_temporal_coverage():
    contract = SamplingContract(app_id=10)
    coverage = _derive_acquisition_coverage(contract, {"collection_complete": True, "truncated_by_max_reviews": False})
    assert coverage["coverage_start_time"] is None
    assert coverage["coverage_end_time"] is None
    assert coverage["coverage_status"] == "unknown"
