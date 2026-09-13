from __future__ import annotations

import importlib.util
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[2] / "tooling" / "vertical_slice" / "stage4b_real_steam_slice.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("stage4b_real_steam_slice", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_defaults_and_forbids_fake_or_secret_paths() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "FakeEmbeddingBackend" not in source
    assert "fake_classifier" not in source
    assert "mock_classifier" not in source
    assert "API_KEY=" not in source
    assert "BEGIN PRIVATE KEY" not in source

    runner = _load_runner()
    args = runner.build_parser().parse_args([])
    assert args.app_id == 553850
    assert args.review_count == 80
    assert args.language == "english"
    assert runner._request_payload(args)["filter"] == "recent"


def test_immutable_summary_is_aggregate_only() -> None:
    runner = _load_runner()
    report = {
        "schema_version": "research-report-v1",
        "recommendation": {"population": {"valid_n": 1}},
    }
    result = {
        "run_id": "run-1",
        "app_id": 553850,
        "metadata": {"analysis_population_count": 1},
        "research_report": report,
        "semantic_status": {"status": "unavailable"},
        "semantic_measurement_result": None,
        "unified_research_result": {
            "result_fingerprint": "fp",
            "quantitative": report,
        },
        "reviews": [{"review": "must not be copied"}],
    }
    summary = runner._immutable_summary(result)
    assert summary["quantitative_persisted"] is True
    assert "reviews" not in summary
    assert "must not be copied" not in str(summary)
