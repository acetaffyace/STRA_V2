from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

EXPECTED_SCHEMA_VERSION = "semantic-v2-benchmark-manifest-v2"
EXPECTED_RECORD_SCHEMAS = {
    "boundary_regression": "semantic-v2-boundary-record-v1",
    "evaluation_holdout": "semantic-v2-holdout-record-v1",
}
EXPECTED_TAXONOMY_VERSION = "stra-core-taxonomy-v2"
PRIMARY_LANGUAGE_ALIASES = {
    "en": "en", "english": "en", "zh": "zh", "schinese": "zh",
    "tchinese": "zh", "japanese": "ja", "ja": "ja",
}
SIGNAL_TYPES = {"issue", "request", "praise"}
BOUNDARY_PAIRS = {
    "balance_vs_difficulty", "mechanics_vs_controls", "progression_vs_content_pacing",
    "networking_vs_matchmaking", "bugs_vs_stability", "technical_defect_vs_update_quality",
    "microtransactions_vs_monetization_fairness", "monetization_fairness_vs_monetization_pressure",
    "pricing_vs_value_for_money", "narrative_writing_vs_voice_acting", "ui_structure_vs_readability",
    "readability_vs_onboarding",
}
_VALID_SEMANTIC_STATUSES = {"resolved", "unresolved", "semantically_invalid"}
_VALID_DISAGREEMENT_STATES = {"not_applicable", "no_disagreement", "annotator_disagreement", "adjudicated"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_content_hash(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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


def _core_topic_ids() -> set[str]:
    taxonomy_path = Path(__file__).resolve().parents[3] / "docs" / "taxonomy" / "core_taxonomy_v2.yaml"
    try:
        source = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        return {str(topic["id"]) for topic in source.get("topics", [])}
    except (OSError, TypeError, ValueError, KeyError):
        return set()


def _validate_label_block(block: Any, *, prefix: str, text: str, known_topics: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(block, Mapping):
        return [f"{prefix}: label block is required"]
    status = block.get("semantic_status")
    if status not in _VALID_SEMANTIC_STATUSES:
        errors.append(f"{prefix}: semantic_status is invalid")
    core_topics = block.get("core_topic_ids")
    if not isinstance(core_topics, list) or any(not isinstance(item, str) or not item for item in core_topics) or len(set(core_topics)) != len(core_topics):
        errors.append(f"{prefix}: core_topic_ids must be a unique string list")
        core_topics = []
    unknown_topics = set(core_topics) - known_topics
    if unknown_topics:
        errors.append(f"{prefix}: unknown Core Topic IDs: {sorted(unknown_topics)}")
    game_topics = block.get("secondary_game_topic_ids")
    archetype_topics = block.get("secondary_archetype_topic_ids")
    for name, values in (("secondary_game_topic_ids", game_topics), ("secondary_archetype_topic_ids", archetype_topics)):
        if not isinstance(values, list) or any(not isinstance(item, str) or not item for item in values) or len(set(values)) != len(values):
            errors.append(f"{prefix}: {name} must be a unique string list")
    mentions = block.get("semantic_mentions")
    if not isinstance(mentions, list):
        errors.append(f"{prefix}: semantic_mentions must be a list")
        mentions = []
    mention_topics: list[str] = []
    mention_signals: set[tuple[str, str]] = set()
    for index, mention in enumerate(mentions):
        mention_prefix = f"{prefix}.semantic_mentions[{index}]"
        if not isinstance(mention, Mapping):
            errors.append(f"{mention_prefix}: must be an object")
            continue
        core = mention.get("core_topic_id")
        if not isinstance(core, str) or not core or core not in known_topics:
            errors.append(f"{mention_prefix}: core_topic_id must be a known Core Topic")
        else:
            mention_topics.append(core)
        for field in ("secondary_game_topic_id", "secondary_archetype_topic_id"):
            value = mention.get(field)
            if value is not None and (not isinstance(value, str) or not value):
                errors.append(f"{mention_prefix}: {field} must be a non-empty string or null")
        signal = mention.get("signal_type")
        if signal is not None and signal not in SIGNAL_TYPES:
            errors.append(f"{mention_prefix}: signal_type is invalid")
        if signal is not None and isinstance(core, str):
            mention_signals.add((core, signal))
        spans = mention.get("evidence_spans")
        if not isinstance(spans, list) or any(not isinstance(span, str) or not span for span in spans):
            errors.append(f"{mention_prefix}: evidence_spans must be a string list")
        elif any(span not in text for span in spans):
            errors.append(f"{mention_prefix}: evidence span is not an exact source substring")
    if status == "resolved":
        if not core_topics:
            errors.append(f"{prefix}: resolved labels require at least one Core Topic")
        if not mentions:
            errors.append(f"{prefix}: resolved labels require semantic_mentions")
        if sorted(set(core_topics)) != sorted(set(mention_topics)):
            errors.append(f"{prefix}: core_topic_ids must equal semantic mention Core Topics")
    else:
        if core_topics or mentions or game_topics or archetype_topics:
            errors.append(f"{prefix}: {status} labels must not assign topics")
        reason = block.get("unresolved_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{prefix}: {status} labels require unresolved_reason")
    signals = block.get("signals")
    if not isinstance(signals, list):
        errors.append(f"{prefix}: signals must be a list")
    else:
        declared_signals: set[tuple[str, str]] = set()
        for index, signal in enumerate(signals):
            signal_prefix = f"{prefix}.signals[{index}]"
            if not isinstance(signal, Mapping) or signal.get("core_topic_id") not in core_topics or signal.get("signal_type") not in SIGNAL_TYPES:
                errors.append(f"{signal_prefix}: signal must reference a labeled Core Topic and valid signal_type")
                continue
            key = (str(signal["core_topic_id"]), str(signal["signal_type"]))
            if key in declared_signals:
                errors.append(f"{signal_prefix}: duplicate signal")
            declared_signals.add(key)
            spans = signal.get("evidence_spans", [])
            if not isinstance(spans, list) or any(not isinstance(span, str) or span not in text for span in spans):
                errors.append(f"{signal_prefix}: evidence_spans must contain exact source substrings")
        if declared_signals != mention_signals:
            errors.append(f"{prefix}: signals must match semantic_mentions signal_type values")
    return errors


def _validate_provenance(record: Mapping[str, Any], *, text: str, known_topics: set[str], prefix: str) -> list[str]:
    errors: list[str] = []
    provenance = record.get("annotation_provenance")
    if not isinstance(provenance, Mapping):
        return [f"{prefix}: annotation_provenance is required"]
    if not isinstance(provenance.get("annotator_id"), str) or not provenance["annotator_id"].strip():
        errors.append(f"{prefix}: annotator_id is required")
    method = str(provenance.get("annotation_method") or "").lower()
    if not method or "model" in method or "machine" in method:
        errors.append(f"{prefix}: annotation_method must identify a human method")
    disagreement = provenance.get("disagreement_state")
    if disagreement not in _VALID_DISAGREEMENT_STATES:
        errors.append(f"{prefix}: disagreement_state is invalid")
    if disagreement in {"annotator_disagreement", "adjudicated"} and not str(provenance.get("reviewer_id") or "").strip():
        errors.append(f"{prefix}: reviewer_id is required for disagreement/adjudication")
    for name in ("first_pass", "final"):
        errors.extend(_validate_label_block(provenance.get(name), prefix=f"{prefix}.{name}", text=text, known_topics=known_topics))
    if isinstance(record.get("gold"), Mapping) and isinstance(provenance.get("final"), Mapping):
        if _canonical(record["gold"]) != _canonical(provenance["final"]):
            errors.append(f"{prefix}: annotation_provenance.final must equal gold")
    return errors


def _validate_record(record: dict[str, Any], asset_type: str, index: int, known_topics: set[str]) -> list[str]:
    errors: list[str] = []
    prefix = f"{asset_type}[{index}]"
    if record.get("record_schema_version") != EXPECTED_RECORD_SCHEMAS[asset_type]:
        errors.append(f"{prefix}: record_schema_version mismatch")
    if record.get("dataset_role") != asset_type:
        errors.append(f"{prefix}: dataset_role mismatch")
    if not isinstance(record.get("sample_id"), str) or not str(record["sample_id"]).strip():
        errors.append(f"{prefix}: sample_id is required")
    if not isinstance(record.get("language"), str) or not record["language"].strip():
        errors.append(f"{prefix}: language is required")
    if record.get("taxonomy_version") != EXPECTED_TAXONOMY_VERSION:
        errors.append(f"{prefix}: taxonomy_version must be {EXPECTED_TAXONOMY_VERSION}")
    source = record.get("source")
    if not isinstance(source, Mapping):
        errors.append(f"{prefix}: source object is required")
        source = {}
    text = source.get("source_review_text")
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{prefix}: source.source_review_text is required")
        text = ""
    if not isinstance(source.get("app_id"), int) or source["app_id"] <= 0:
        errors.append(f"{prefix}: source.app_id must be a positive integer")
    if not str(source.get("source_review_id") or "").strip():
        errors.append(f"{prefix}: source.source_review_id is required")
    if source.get("source_content_hash") != source_content_hash(text):
        errors.append(f"{prefix}: source_content_hash does not match source_review_text")
    errors.extend(_validate_provenance(record, text=text, known_topics=known_topics, prefix=prefix))
    errors.extend(_validate_label_block(record.get("gold"), prefix=f"{prefix}.gold", text=text, known_topics=known_topics))
    if asset_type == "boundary_regression":
        metadata = record.get("boundary_metadata")
        if not isinstance(metadata, Mapping) or metadata.get("boundary_category") not in BOUNDARY_PAIRS:
            errors.append(f"{prefix}: boundary_metadata.boundary_category is required and invalid")
        elif not isinstance(metadata.get("confusion_topic_ids"), list) or len(metadata["confusion_topic_ids"]) < 2:
            errors.append(f"{prefix}: boundary_metadata.confusion_topic_ids must list at least two topics")
    if asset_type == "evaluation_holdout":
        metadata = record.get("holdout_metadata")
        if not isinstance(metadata, Mapping) or not str(metadata.get("sampling_stratum") or "").strip():
            errors.append(f"{prefix}: holdout_metadata.sampling_stratum is required")
        if record.get("used_for_calibration") is True or record.get("used_for_training") is True:
            errors.append(f"{prefix}: holdout record is marked as calibration/training input")
    return errors


def _asset_entries(manifest: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    asset_type = manifest.get("asset_type")
    if asset_type in EXPECTED_RECORD_SCHEMAS:
        return [(str(asset_type), manifest.get("asset") if isinstance(manifest.get("asset"), Mapping) else {})]
    if asset_type == "bundle" and isinstance(manifest.get("assets"), Mapping):
        return [(name, value) for name, value in manifest["assets"].items() if name in EXPECTED_RECORD_SCHEMAS and isinstance(value, Mapping)]
    return []


def _validate_identity(manifest: Mapping[str, Any], *, asset_type: str, errors: list[str]) -> None:
    if manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA_VERSION}")
    identity = manifest.get("dataset_identity")
    if not isinstance(identity, Mapping):
        errors.append("dataset_identity object is required")
        identity = {}
    required = ("dataset_id", "dataset_version", "taxonomy_version", "guideline_version", "source_collection", "source_collection_hash", "annotation_protocol_version", "evaluation_code_commit")
    for field in required:
        if not isinstance(identity.get(field), str) or not identity[field].strip():
            errors.append(f"dataset_identity.{field} is required")
    if identity.get("taxonomy_version") != EXPECTED_TAXONOMY_VERSION:
        errors.append(f"dataset_identity.taxonomy_version must be {EXPECTED_TAXONOMY_VERSION}")
    policy = manifest.get("calibration_training_policy")
    if manifest.get("asset_type") == "bundle":
        policies = manifest.get("asset_policies")
        policy = policies.get(asset_type) if isinstance(policies, Mapping) else None
    if not isinstance(policy, Mapping):
        errors.append("calibration_training_policy object is required")
    elif asset_type == "evaluation_holdout" and (policy.get("evaluation_only") is not True or policy.get("allowed_for_calibration_training") is not False):
        errors.append("evaluation_holdout must be evaluation_only and prohibited from calibration/training")


def validate_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    errors: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": [f"manifest: {exc}"]}
    if not isinstance(manifest, Mapping):
        return {"valid": False, "errors": ["manifest must be a JSON object"]}
    entries = _asset_entries(manifest)
    if not entries:
        errors.append("manifest must declare asset_type boundary_regression/evaluation_holdout or bundle assets")
    known_topics = _core_topic_ids()
    if not known_topics:
        errors.append("Core Taxonomy V2 source is unavailable or invalid")
    seen_ids: set[str] = set()
    reports: dict[str, Any] = {}
    for asset_type, asset in entries:
        _validate_identity(manifest, asset_type=asset_type, errors=errors)
        relative_path = asset.get("path")
        if not isinstance(relative_path, str) or not relative_path:
            errors.append(f"{asset_type}: asset.path is required")
            continue
        asset_path = (path.parent / relative_path).resolve()
        if not asset_path.is_relative_to(path.parent):
            errors.append(f"{asset_type}: asset path escapes manifest directory")
            continue
        records, read_errors = _read_jsonl(asset_path)
        errors.extend(read_errors)
        if asset_path.exists() and asset.get("sha256") != _sha256(asset_path):
            errors.append(f"{asset_type}: sha256 does not match asset")
        minimum, maximum = asset.get("min_examples"), asset.get("max_examples")
        if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum < 1 or maximum < minimum:
            errors.append(f"{asset_type}: min_examples/max_examples are invalid")
        elif not minimum <= len(records) <= maximum:
            errors.append(f"{asset_type}: sample count {len(records)} is outside [{minimum}, {maximum}]")
        local_ids: set[str] = set()
        local_hashes: set[str] = set()
        language_counts: dict[str, int] = {}
        hashes: list[str] = []
        for index, record in enumerate(records):
            errors.extend(_validate_record(record, asset_type, index, known_topics))
            sample_id = record.get("sample_id")
            if isinstance(sample_id, str):
                if sample_id in local_ids:
                    errors.append(f"{asset_type}: duplicate sample_id {sample_id}")
                if sample_id in seen_ids:
                    errors.append(f"{asset_type}: sample_id overlaps another evaluation asset: {sample_id}")
                local_ids.add(sample_id)
                seen_ids.add(sample_id)
            language = PRIMARY_LANGUAGE_ALIASES.get(str(record.get("language", "")).lower())
            if language:
                language_counts[language] = language_counts.get(language, 0) + 1
            source = record.get("source")
            if isinstance(source, Mapping) and isinstance(source.get("source_content_hash"), str):
                content_hash = source["source_content_hash"]
                if content_hash in local_hashes:
                    errors.append(f"{asset_type}: duplicate source_content_hash {content_hash}")
                local_hashes.add(content_hash)
                hashes.append(content_hash)
        reports[asset_type] = {"count": len(records), "primary_language_counts": language_counts, "sample_ids": sorted(local_ids), "source_content_hashes": sorted(hashes)}
    if "evaluation_holdout" in reports:
        minimum_support = manifest.get("minimum_primary_language_support", 50)
        if not isinstance(minimum_support, int) or minimum_support < 1:
            errors.append("minimum_primary_language_support must be a positive integer")
        else:
            counts = reports["evaluation_holdout"]["primary_language_counts"]
            for language in ("en", "zh", "ja"):
                if counts.get(language, 0) < minimum_support:
                    errors.append(f"evaluation_holdout: {language} support {counts.get(language, 0)} is below {minimum_support}")
    return {"valid": not errors, "errors": errors, "assets": reports}


def validate_manifests(manifest_paths: Iterable[str | Path]) -> dict[str, Any]:
    paths = [Path(value) for value in manifest_paths]
    reports = [validate_manifest(path) for path in paths]
    errors = [f"{path}: {error}" for path, report in zip(paths, reports) for error in report.get("errors", [])]
    seen: dict[str, Path] = {}
    seen_ids: dict[str, Path] = {}
    for path, report in zip(paths, reports):
        for asset in report.get("assets", {}).values():
            for sample_id in asset.get("sample_ids", []):
                if sample_id in seen_ids:
                    errors.append(f"sample_id overlaps evaluation assets: {sample_id} ({seen_ids[sample_id]} and {path})")
                else:
                    seen_ids[sample_id] = path
            for content_hash in asset.get("source_content_hashes", []):
                if content_hash in seen:
                    errors.append(f"source_content_hash overlaps evaluation assets: {content_hash} ({seen[content_hash]} and {path})")
                else:
                    seen[content_hash] = path
    return {"valid": not errors, "errors": errors, "manifests": reports}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Semantic Engine V2 benchmark asset validator")
    parser.add_argument("manifest", type=Path, nargs="+")
    args = parser.parse_args(argv)
    report = validate_manifests(args.manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
