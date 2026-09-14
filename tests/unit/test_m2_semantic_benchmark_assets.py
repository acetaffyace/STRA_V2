from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tooling.evals.semantic_v2.validate_assets import validate_manifest


def _write_asset(path: Path, sample_id: str, language: str, *, boundary_pair: str | None = None) -> None:
    record = {
        "sample_id": sample_id,
        "app_id": 1,
        "language": language,
        "source_review_text": "The controls feel great.",
        "taxonomy_version": "stra-core-taxonomy-v2",
        "guideline_version": "stra-semantic-v2-guidelines-v1",
        "annotation_status": "labeled",
        "gold": {"core_topic_ids": ["mechanics_controls"], "evidence_spans": ["controls feel great"]},
    }
    if boundary_pair:
        record["boundary_pair"] = boundary_pair
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _write_manifest(root: Path, *, overlap: bool = False) -> Path:
    boundary = root / "boundary.jsonl"
    holdout = root / "holdout.jsonl"
    _write_asset(boundary, "boundary-1", "english", boundary_pair="mechanics_vs_controls")
    _write_asset(holdout, "boundary-1" if overlap else "holdout-en", "english")
    _write_asset(root / "holdout-zh.jsonl", "holdout-zh", "schinese")
    _write_asset(root / "holdout-ja.jsonl", "holdout-ja", "japanese")
    holdout.write_text(
        "".join(
            json.dumps(json.loads(path.read_text(encoding="utf-8"))) + "\n"
            for path in (holdout, root / "holdout-zh.jsonl", root / "holdout-ja.jsonl")
        ),
        encoding="utf-8",
    )
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "semantic-v2-benchmark-manifest-v1",
        "dataset_version": "test-v1",
        "taxonomy_version": "stra-core-taxonomy-v2",
        "guideline_version": "stra-semantic-v2-guidelines-v1",
        "evaluation_code_commit": "test-commit",
        "minimum_primary_language_support": 1,
        "boundary_regression": {"path": boundary.name, "sha256": digest(boundary), "min_examples": 1, "max_examples": 1},
        "holdout": {"path": holdout.name, "sha256": digest(holdout), "min_examples": 3, "max_examples": 3},
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_semantic_v2_manifest_accepts_complete_disjoint_assets(tmp_path: Path) -> None:
    report = validate_manifest(_write_manifest(tmp_path))
    assert report["valid"] is True
    assert report["assets"]["holdout"]["primary_language_counts"] == {"en": 1, "zh": 1, "ja": 1}


def test_semantic_v2_manifest_rejects_cross_split_overlap(tmp_path: Path) -> None:
    report = validate_manifest(_write_manifest(tmp_path, overlap=True))
    assert report["valid"] is False
    assert any("overlaps another evaluation asset" in error for error in report["errors"])


def test_semantic_v2_manifest_rejects_missing_assets(tmp_path: Path) -> None:
    manifest = {
        "schema_version": "semantic-v2-benchmark-manifest-v1",
        "dataset_version": "test-v1",
        "taxonomy_version": "stra-core-taxonomy-v2",
        "evaluation_code_commit": "test-commit",
        "boundary_regression": {"path": "missing.jsonl", "sha256": "", "min_examples": 200, "max_examples": 500},
        "holdout": {"path": "missing-holdout.jsonl", "sha256": "", "min_examples": 300, "max_examples": 600},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    report = validate_manifest(path)
    assert report["valid"] is False
    assert any("missing asset" in error for error in report["errors"])

