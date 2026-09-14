from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from .validate_assets import EXPECTED_TAXONOMY_VERSION, EXPECTED_RECORD_SCHEMAS, source_content_hash
except ImportError:  # pragma: no cover - direct script execution
    from validate_assets import EXPECTED_TAXONOMY_VERSION, EXPECTED_RECORD_SCHEMAS, source_content_hash


LANGUAGE_ALIASES = {
    "english": "en", "en": "en", "schinese": "zh", "tchinese": "zh",
    "chinese": "zh", "japanese": "ja", "ja": "ja",
}


def _read_reviews(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: review must be an object")
            rows.append(value)
    return rows


def _candidate(row: Mapping[str, Any], *, asset_type: str, seed: str) -> dict[str, Any]:
    text = row.get("source_review_text") or row.get("review")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("source review text is required")
    app_id = row.get("app_id")
    if not isinstance(app_id, int) or app_id <= 0:
        raise ValueError("app_id must be a positive integer")
    review_id = str(row.get("source_review_id") or row.get("review_id") or row.get("recommendationid") or "").strip()
    if not review_id:
        raise ValueError("source review id is required")
    content_hash = source_content_hash(text)
    supplied_hash = row.get("source_content_hash")
    if supplied_hash is not None and supplied_hash != content_hash:
        raise ValueError(f"source_content_hash mismatch for {review_id}")
    language_raw = str(row.get("language") or "unknown").strip().lower()
    language = LANGUAGE_ALIASES.get(language_raw, language_raw)
    identity = f"{app_id}:{review_id}:{content_hash}"
    sample_id = "sv2-candidate-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    record: dict[str, Any] = {
        "record_schema_version": "semantic-v2-candidate-record-v1",
        "dataset_role": asset_type,
        "sample_id": sample_id,
        "taxonomy_version": EXPECTED_TAXONOMY_VERSION,
        "language": language,
        "source": {
            "source_system": str(row.get("source_system") or "steam"),
            "app_id": app_id,
            "source_review_id": review_id,
            "source_snapshot_id": row.get("source_snapshot_id"),
            "source_content_hash": content_hash,
            "source_review_text": text,
        },
        "annotation_provenance": {
            "annotator_id": None,
            "annotation_method": "pending_human_annotation",
            "first_pass": None,
            "final": None,
            "disagreement_state": "not_started",
            "reviewer_id": None,
        },
        "gold": None,
        "candidate_sampling": {"seed": seed, "status": "UNLABELED", "source_language": language_raw},
    }
    if asset_type == "boundary_regression":
        record["boundary_metadata"] = {
            "annotation_status": "to_be_annotated",
            "boundary_category": None,
            "confusion_topic_ids": [],
            "policy_edge_cases": [],
        }
    else:
        record["holdout_metadata"] = {
            "sampling_stratum": "candidate_pool",
            "evaluation_only": True,
            "calibration_training_use": "prohibited",
        }
    return record


def export_unlabeled_candidates(
    input_path: str | Path,
    output_path: str | Path,
    manifest_path: str | Path,
    *,
    asset_type: str,
    seed: str,
    count: int,
    languages: Iterable[str] = (),
) -> dict[str, Any]:
    """Deterministically export candidates; never create gold labels."""
    if asset_type not in EXPECTED_RECORD_SCHEMAS:
        raise ValueError("asset_type must be boundary_regression or evaluation_holdout")
    if count < 1:
        raise ValueError("count must be positive")
    source_path = Path(input_path)
    rows = _read_reviews(source_path)
    requested_languages = {LANGUAGE_ALIASES.get(str(value).lower(), str(value).lower()) for value in languages}
    candidates: dict[str, dict[str, Any]] = {}
    for row in rows:
        language = LANGUAGE_ALIASES.get(str(row.get("language") or "unknown").lower(), str(row.get("language") or "unknown").lower())
        if requested_languages and language not in requested_languages:
            continue
        record = _candidate(row, asset_type=asset_type, seed=seed)
        content_hash = record["source"]["source_content_hash"]
        candidates.setdefault(content_hash, record)
    selected = sorted(candidates.values(), key=lambda record: hashlib.sha256(f"{seed}:{record['sample_id']}".encode("utf-8")).hexdigest())[:count]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in selected), encoding="utf-8")
    selected_hashes = sorted(record["source"]["source_content_hash"] for record in selected)
    collection_hash = hashlib.sha256(json.dumps(selected_hashes, separators=(",", ":")).encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": "semantic-v2-candidate-manifest-v1",
        "asset_type": asset_type,
        "status": "UNLABELED_CANDIDATES",
        "dataset_identity": {
            "dataset_id": f"stra-semantic-v2-{asset_type}-candidates",
            "dataset_version": "candidate-export-v1",
            "taxonomy_version": EXPECTED_TAXONOMY_VERSION,
            "guideline_version": "pending-human-annotation",
            "source_collection": str(source_path),
            "source_collection_hash": collection_hash,
            "annotation_protocol_version": "pending-human-annotation",
            "evaluation_code_commit": "candidate-export-v1",
        },
        "calibration_training_policy": {
            "evaluation_only": asset_type == "evaluation_holdout",
            "allowed_for_calibration_training": asset_type != "evaluation_holdout",
        },
        "asset": {
            "path": output.name,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "min_examples": len(selected),
            "max_examples": len(selected),
        },
        "candidate_sampling": {"seed": seed, "requested_count": count, "exported_count": len(selected), "status": "UNLABELED"},
    }
    manifest_file = Path(manifest_path)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "UNLABELED_CANDIDATES", "count": len(selected), "output": str(output), "manifest": str(manifest_file)}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export deterministic unlabeled Semantic V2 annotation candidates")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--asset-type", choices=("boundary_regression", "evaluation_holdout"), required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--languages", nargs="*", default=())
    args = parser.parse_args(argv)
    print(json.dumps(export_unlabeled_candidates(args.input, args.output, args.manifest, asset_type=args.asset_type, seed=args.seed, count=args.count, languages=args.languages), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

