"""Strict loader and validator for the Master Spec Core Taxonomy V2 source."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

CORE_TAXONOMY_VERSION = "stra-core-taxonomy-v2"
CORE_TAXONOMY_SCHEMA_VERSION = "core-taxonomy-source-v1"
_SOURCE_PATH = Path(__file__).resolve().parents[3] / "docs" / "taxonomy" / "core_taxonomy_v2.yaml"
_REQUIRED_FIELDS = ("id", "definition", "include", "exclude", "boundary", "typical_examples", "counterexamples")

CORE_TOPIC_IDS: tuple[str, ...] = (
    "overall_experience/general",
    "gameplay/mechanics", "gameplay/controls", "gameplay/balance", "gameplay/difficulty", "gameplay/progression", "gameplay/ai_behavior",
    "technical/performance", "technical/bugs", "technical/stability_crashes", "technical/compatibility", "technical/networking", "technical/installation_launch", "technical/save_data",
    "content/scope_variety", "content/world_level_design", "content/activities_modes", "content/narrative_characters", "content/replayability", "content/content_pacing", "content/customization",
    "ux_accessibility/interface_hud", "ux_accessibility/readability_clarity", "ux_accessibility/quality_of_life", "ux_accessibility/input_device_support", "ux_accessibility/accessibility", "ux_accessibility/onboarding_learnability",
    "presentation/visuals_art", "presentation/animation", "presentation/audio_music", "presentation/voice_acting", "presentation/localization",
    "online_community/multiplayer_experience", "online_community/matchmaking", "online_community/social_features", "online_community/competitive_integrity", "online_community/moderation_safety", "online_community/mods_ugc_ecosystem",
    "service_operations/update_quality", "service_operations/update_cadence", "service_operations/roadmap_delivery", "service_operations/developer_communication", "service_operations/customer_support",
    "commercial_model/pricing", "commercial_model/regional_pricing", "commercial_model/paid_content", "commercial_model/microtransactions", "commercial_model/monetization_fairness", "commercial_model/monetization_pressure", "commercial_model/value_for_money",
)


def _read_source(path: Path) -> Mapping[str, Any]:
    try:
        # The checked-in .yaml is JSON-compatible YAML, so validation remains
        # dependency-free while standard YAML tooling can still consume it.
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("core_taxonomy_source_invalid_json_yaml") from exc
    if not isinstance(value, Mapping):
        raise ValueError("core_taxonomy_source_not_object")
    return value


def validate_core_taxonomy_v2(source: Mapping[str, Any]) -> dict[str, Any]:
    if source.get("taxonomy_version") != CORE_TAXONOMY_VERSION or source.get("schema_version") != CORE_TAXONOMY_SCHEMA_VERSION:
        raise ValueError("core_taxonomy_source_version_mismatch")
    topics = source.get("topics")
    if not isinstance(topics, list) or len(topics) != 50:
        raise ValueError("core_taxonomy_topic_count_mismatch")
    ids: list[str] = []
    for topic in topics:
        if not isinstance(topic, Mapping) or any(field not in topic for field in _REQUIRED_FIELDS):
            raise ValueError("core_taxonomy_topic_required_field_missing")
        topic_id = str(topic.get("id") or "")
        if not topic_id or "/" not in topic_id or topic_id in ids:
            raise ValueError("core_taxonomy_topic_id_invalid_or_duplicate")
        if any(not isinstance(topic[field], str) or not topic[field].strip() for field in ("definition", "include", "exclude", "boundary")):
            raise ValueError("core_taxonomy_topic_definition_incomplete")
        if any(not isinstance(topic[field], list) or not topic[field] or any(not str(item).strip() for item in topic[field]) for field in ("typical_examples", "counterexamples")):
            raise ValueError("core_taxonomy_topic_examples_incomplete")
        ids.append(topic_id)
    if tuple(ids) != CORE_TOPIC_IDS:
        raise ValueError("core_taxonomy_topic_ids_mismatch")
    return {"taxonomy_version": CORE_TAXONOMY_VERSION, "schema_version": CORE_TAXONOMY_SCHEMA_VERSION, "topics": [dict(topic) for topic in topics]}


def load_core_taxonomy_v2(path: str | Path | None = None) -> dict[str, Any]:
    return validate_core_taxonomy_v2(_read_source(Path(path) if path else _SOURCE_PATH))


def core_taxonomy_fingerprint(source: Mapping[str, Any] | None = None) -> str:
    value = validate_core_taxonomy_v2(source or load_core_taxonomy_v2())
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = ["CORE_TOPIC_IDS", "CORE_TAXONOMY_SCHEMA_VERSION", "CORE_TAXONOMY_VERSION", "core_taxonomy_fingerprint", "load_core_taxonomy_v2", "validate_core_taxonomy_v2"]
