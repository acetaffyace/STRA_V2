from __future__ import annotations

import json
from pathlib import Path

from tooling.evals.semantic_v2.export_candidates import export_unlabeled_candidates


def _write_reviews(path: Path) -> None:
    rows = [
        {"app_id": 10, "recommendationid": "r-1", "language": "english", "review": "Great controls."},
        {"app_id": 10, "recommendationid": "r-2", "language": "schinese", "review": "操作很顺手。"},
        {"app_id": 10, "recommendationid": "r-3", "language": "japanese", "review": "操作が快適です。"},
        {"app_id": 10, "recommendationid": "r-4", "language": "english", "review": "Great controls."},
    ]
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_candidate_export_is_deterministic_and_has_no_gold_labels(tmp_path: Path) -> None:
    source = tmp_path / "reviews.jsonl"
    _write_reviews(source)
    first = tmp_path / "first.jsonl"
    first_manifest = tmp_path / "first.manifest.json"
    second = tmp_path / "second.jsonl"
    second_manifest = tmp_path / "second.manifest.json"
    export_unlabeled_candidates(source, first, first_manifest, asset_type="boundary_regression", seed="seed-1", count=3, languages=["en", "zh", "ja"])
    export_unlabeled_candidates(source, second, second_manifest, asset_type="boundary_regression", seed="seed-1", count=3, languages=["en", "zh", "ja"])
    assert first.read_bytes() == second.read_bytes()
    records = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 3
    assert all(record["gold"] is None for record in records)
    assert all(record["annotation_provenance"]["first_pass"] is None for record in records)
    assert all(record["candidate_sampling"]["status"] == "UNLABELED" for record in records)
    assert json.loads(first_manifest.read_text(encoding="utf-8"))["status"] == "UNLABELED_CANDIDATES"


def test_holdout_candidate_export_declares_evaluation_only(tmp_path: Path) -> None:
    source = tmp_path / "reviews.jsonl"
    _write_reviews(source)
    output = tmp_path / "holdout.jsonl"
    manifest = tmp_path / "holdout.manifest.json"
    export_unlabeled_candidates(source, output, manifest, asset_type="evaluation_holdout", seed="holdout-seed", count=2)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["calibration_training_policy"] == {"evaluation_only": True, "allowed_for_calibration_training": False}
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert all(record["holdout_metadata"]["calibration_training_use"] == "prohibited" for record in records)

