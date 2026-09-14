from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

EXPECTED_SCHEMA_VERSION = "semantic-v2-benchmark-manifest-v1"
EXPECTED_TAXONOMY_VERSION = "stra-core-taxonomy-v2"
PRIMARY_LANGUAGE_ALIASES = {
    "en": "en",
    "english": "en",
    "zh": "zh",
    "schinese": "zh",
    "tchinese": "zh",
    "japanese": "ja",
    "ja": "ja",
}
BOUNDARY_PAIRS = {
    "balance_vs_difficulty",
    "mechanics_vs_controls",
    "progression_vs_content_pacing",
    "networking_vs_matchmaking",
    "bugs_vs_stability",
    "technical_defect_vs_update_quality",
    "microtransactions_vs_monetization_fairness",
    "monetization_fairness_vs_monetization_pressure",
    "pricing_vs_value_for_money",
    "narrative_writing_vs_voice_acting",
    "ui_structure_vs_readability",
    "readability_vs_onboarding",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return records, [f"missing asset: {path}"]
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                errors.append(f"{path}:{line_number}: blank line is not allowed")
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number}: invalid JSON ({exc.msg})")
                continue
            if not isinstance(value, dict):
                errors.append(f"{path}:{line_number}: record must be a JSON object")
                continue
            records.append(value)
    return records, errors


def _validate_record(record: dict[str, Any], asset_type: str, index: int) -> list[str]:
    errors: list[str] = []
    prefix = f"{asset_type}[{index}]"
    sample_id = record.get("sample_id")
    if not isinstance(sample_id, str) or not sample_id:
        errors.append(f"{prefix}: sample_id is required")
    language = record.get("language")
    if not isinstance(language, str) or not language:
        errors.append(f"{prefix}: language is required")
    text = record.get("source_review_text")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{prefix}: source_review_text is required")
    if record.get("taxonomy_version") != EXPECTED_TAXONOMY_VERSION:
        errors.append(f"{prefix}: taxonomy_version must be {EXPECTED_TAXONOMY_VERSION}")
    if not isinstance(record.get("guideline_version"), str) or not record["guideline_version"]:
        errors.append(f"{prefix}: guideline_version is required")
    if record.get("annotation_status") != "labeled":
        errors.append(f"{prefix}: annotation_status must be labeled")

    gold = record.get("gold")
    if not isinstance(gold, dict):
        errors.append(f"{prefix}: gold object is required")
        return errors
    topic_ids = gold.get("core_topic_ids")
    if not isinstance(topic_ids, list) or not topic_ids or any(not isinstance(value, str) or not value for value in topic_ids):
        errors.append(f"{prefix}: gold.core_topic_ids must be a non-empty string list")
    spans = gold.get("evidence_spans")
    if not isinstance(spans, list) or any(not isinstance(value, str) or not value for value in spans):
        errors.append(f"{prefix}: gold.evidence_spans must be a non-empty string list")
    elif isinstance(text, str) and any(span not in text for span in spans):
        errors.append(f"{prefix}: every evidence span must be an exact source substring")

    if asset_type == "boundary":
        boundary_pair = record.get("boundary_pair")
        if boundary_pair not in BOUNDARY_PAIRS:
            errors.append(f"{prefix}: invalid or missing boundary_pair")
    return errors


def _validate_asset(
    manifest: dict[str, Any],
    manifest_path: Path,
    asset_name: str,
    asset_type: str,
    seen_ids: set[str],
) -> tuple[list[str], int, dict[str, int]]:
    errors: list[str] = []
    asset = manifest.get(asset_name)
    if not isinstance(asset, dict):
        return [f"{asset_name}: manifest entry is required"], 0, {}
    relative_path = asset.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        return [f"{asset_name}: path is required"], 0, {}
    path = (manifest_path.parent / relative_path).resolve()
    if not path.is_relative_to(manifest_path.parent.resolve()):
        errors.append(f"{asset_name}: path escapes the manifest directory")
        return errors, 0, {}
    records, read_errors = _read_jsonl(path)
    errors.extend(read_errors)
    if path.exists() and asset.get("sha256") != _sha256(path):
        errors.append(f"{asset_name}: sha256 does not match the asset")
    minimum = asset.get("min_examples")
    maximum = asset.get("max_examples")
    if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum < 1 or maximum < minimum:
        errors.append(f"{asset_name}: min_examples/max_examples are invalid")
    elif not minimum <= len(records) <= maximum:
        errors.append(f"{asset_name}: sample count {len(records)} is outside [{minimum}, {maximum}]")

    languages: dict[str, int] = {}
    local_ids: set[str] = set()
    for index, record in enumerate(records):
        errors.extend(_validate_record(record, asset_type, index))
        sample_id = record.get("sample_id")
        if isinstance(sample_id, str):
            if sample_id in local_ids:
                errors.append(f"{asset_name}: duplicate sample_id {sample_id}")
            if sample_id in seen_ids:
                errors.append(f"{asset_name}: sample_id overlaps another evaluation asset: {sample_id}")
            local_ids.add(sample_id)
            seen_ids.add(sample_id)
        language = PRIMARY_LANGUAGE_ALIASES.get(str(record.get("language", "")).lower())
        if language:
            languages[language] = languages.get(language, 0) + 1
    return errors, len(records), languages


def validate_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    errors: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": [f"manifest: {exc}"]}
    if not isinstance(manifest, dict):
        return {"valid": False, "errors": ["manifest must be a JSON object"]}
    if manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA_VERSION}")
    if manifest.get("taxonomy_version") != EXPECTED_TAXONOMY_VERSION:
        errors.append(f"taxonomy_version must be {EXPECTED_TAXONOMY_VERSION}")
    if not isinstance(manifest.get("dataset_version"), str) or not manifest["dataset_version"]:
        errors.append("dataset_version is required")
    if not isinstance(manifest.get("evaluation_code_commit"), str) or not manifest["evaluation_code_commit"]:
        errors.append("evaluation_code_commit is required")

    seen_ids: set[str] = set()
    asset_reports: dict[str, Any] = {}
    for name, asset_type in (("boundary_regression", "boundary"), ("holdout", "holdout")):
        asset_errors, count, languages = _validate_asset(manifest, path, name, asset_type, seen_ids)
        errors.extend(asset_errors)
        asset_reports[name] = {"count": count, "primary_language_counts": languages}

    holdout_languages = asset_reports["holdout"]["primary_language_counts"]
    minimum_primary_support = manifest.get("minimum_primary_language_support", 50)
    if not isinstance(minimum_primary_support, int) or minimum_primary_support < 1:
        errors.append("minimum_primary_language_support must be a positive integer")
    else:
        for language in ("en", "zh", "ja"):
            if holdout_languages.get(language, 0) < minimum_primary_support:
                errors.append(
                    f"holdout: {language} support {holdout_languages.get(language, 0)} "
                    f"is below {minimum_primary_support}"
                )
    return {"valid": not errors, "errors": errors, "assets": asset_reports}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Semantic Engine V2 benchmark assets")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    report = validate_manifest(args.manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

