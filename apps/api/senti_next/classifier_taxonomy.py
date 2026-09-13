"""Explicit taxonomy contracts consumed by the classifier.

Stage 3D owns immutable taxonomy snapshots.  This module is the small
adapter between those snapshots and the classifier prompt/schema boundary.
It deliberately does not import :mod:`llm`, so taxonomy loading remains safe
for callers that only need to inspect a contract.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .taxonomy_registry import BASELINE_TAXONOMY_VERSION, TaxonomySnapshot, build_baseline_snapshot

CLASSIFIER_TAXONOMY_CONTRACT_VERSION = "classifier-taxonomy-contract-v1"

# This is intentionally byte-for-byte the taxonomy section used by the
# frozen v1 classifier prompt.  Keep it separate from dynamic renderers so
# the default classifier remains prompt-compatible with historical labels.
LEGACY_TAXONOMY_SECTION = """TAXONOMY (use only these main/subcategory paths):
gameplay={mechanics,controls,balance,difficulty,progression,ai}; technical={performance,bugs,stability_crashes,compatibility,networking,installation,save_data};
content_design={amount_variety,level_design,quests_modes,narrative_characters,replayability,pacing,customization}; ui_ux_accessibility={menus_hud,readability,quality_of_life,controller_support,accessibility_options};
onboarding={tutorial,learning_curve,clarity,tooltips}; presentation={visuals_art_style,animation,audio_music,voice_acting,atmosphere,localization};
online_community={multiplayer_experience,matchmaking,social_features,toxicity_moderation,mods_ugc,cheating_anti_cheat};
developer_updates={patch_quality,update_frequency,roadmap_events,communication,customer_support,response_time};
monetization_value={pricing,regional_pricing,dlc,microtransactions,battle_pass_fomo,pay_to_win_grind,value_for_money};
other={general,mixed,meta,unclear,off_topic,meme}.
Map DLC pricing→monetization_value/dlc, patch quality→developer_updates/patch_quality, saves→technical/save_data, multiplayer→online_community/multiplayer_experience, localization→presentation/localization."""


@dataclass(frozen=True)
class ClassifierTaxonomyContract:
    """Immutable taxonomy identity and active output vocabulary."""

    contract_version: str
    snapshot_id: str
    taxonomy_version: str
    taxonomy_fingerprint: str
    topic_keys: tuple[str, ...]
    active_topic_keys: tuple[str, ...]
    topic_count: int

    @classmethod
    def from_snapshot(cls, snapshot: TaxonomySnapshot) -> "ClassifierTaxonomyContract":
        snapshot.validate()
        topic_keys = tuple(sorted(topic.canonical_key for topic in snapshot.topics))
        active = tuple(sorted(topic.canonical_key for topic in snapshot.topics if topic.topic_status == "active"))
        contract = cls(
            contract_version=CLASSIFIER_TAXONOMY_CONTRACT_VERSION,
            snapshot_id=snapshot.snapshot_id,
            taxonomy_version=snapshot.taxonomy_version,
            taxonomy_fingerprint=snapshot.taxonomy_fingerprint,
            topic_keys=topic_keys,
            active_topic_keys=active,
            topic_count=len(active),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        if self.contract_version != CLASSIFIER_TAXONOMY_CONTRACT_VERSION:
            raise ValueError("unsupported_classifier_taxonomy_contract")
        if not self.snapshot_id or not self.taxonomy_version or not self.taxonomy_fingerprint:
            raise ValueError("classifier_taxonomy_identity_incomplete")
        if len(self.topic_keys) != len(set(self.topic_keys)):
            raise ValueError("classifier_taxonomy_topic_collision")
        if len(self.active_topic_keys) != len(set(self.active_topic_keys)):
            raise ValueError("classifier_taxonomy_active_topic_collision")
        if not set(self.active_topic_keys).issubset(self.topic_keys):
            raise ValueError("classifier_taxonomy_active_topic_invalid")
        if self.topic_count != len(self.active_topic_keys):
            raise ValueError("classifier_taxonomy_topic_count_mismatch")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        payload = {
            "contract_version": self.contract_version,
            "snapshot_id": self.snapshot_id,
            "taxonomy_version": self.taxonomy_version,
            "taxonomy_fingerprint": self.taxonomy_fingerprint,
            "active_topic_keys": self.active_topic_keys,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def baseline_classifier_taxonomy() -> ClassifierTaxonomyContract:
    """Build the frozen v1 contract without touching the database."""
    return ClassifierTaxonomyContract.from_snapshot(build_baseline_snapshot())


def load_classifier_taxonomy(
    taxonomy_version: str | None = None,
    snapshot_id: str | None = None,
) -> ClassifierTaxonomyContract:
    """Load an explicit snapshot; omitted arguments always mean baseline v1.

    In particular, this function never consults ``current_active_snapshot``
    unless the caller explicitly asks for ``taxonomy_version="active"``.
    """
    if taxonomy_version is not None and snapshot_id is not None:
        raise ValueError("taxonomy_version_and_snapshot_id_are_mutually_exclusive")
    if taxonomy_version is None and snapshot_id is None:
        return baseline_classifier_taxonomy()
    if taxonomy_version == BASELINE_TAXONOMY_VERSION and snapshot_id is None:
        return baseline_classifier_taxonomy()

    from .taxonomy_governance import current_active_snapshot, get_taxonomy_snapshot

    if taxonomy_version == "active":
        snapshot = current_active_snapshot()
    else:
        snapshot = get_taxonomy_snapshot(snapshot_id or taxonomy_version or "")
    return ClassifierTaxonomyContract.from_snapshot(snapshot)


def allowed_topic_keys(contract: ClassifierTaxonomyContract) -> tuple[str, ...]:
    contract.validate()
    return contract.active_topic_keys


def render_classifier_taxonomy(contract: ClassifierTaxonomyContract) -> str:
    """Render a deterministic prompt vocabulary for a contract."""
    contract.validate()
    if contract.taxonomy_version == BASELINE_TAXONOMY_VERSION:
        # The baseline snapshot has the exact historical vocabulary and
        # therefore retains the old prompt bytes.
        from .taxonomy_registry import BASELINE_TAXONOMY_V1
        if tuple(contract.active_topic_keys) == tuple(sorted(BASELINE_TAXONOMY_V1)):
            return LEGACY_TAXONOMY_SECTION
    lines = ["TAXONOMY (use only these exact canonical topic paths):"]
    lines.extend(f"- {key}" for key in contract.active_topic_keys)
    return "\n".join(lines)


def _classification_schema(contract: ClassifierTaxonomyContract) -> dict[str, Any]:
    enum = list(allowed_topic_keys(contract))
    return {
        "type": "object",
        "properties": {
            "subcategories": {"type": "array", "items": {"type": "string", "enum": enum}},
            "issue_subcategories": {"type": "array", "items": {"type": "string", "enum": enum}},
            "request_subcategories": {"type": "array", "items": {"type": "string", "enum": enum}},
            "evidence": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
            "aspects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "aspect": {"type": "string", "enum": enum},
                        "subtopic": {"type": "string"},
                        "sentiment": {"type": "integer", "minimum": -2, "maximum": 2},
                        "evidence_span": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["aspect", "sentiment", "evidence_span", "confidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["subcategories", "issue_subcategories", "request_subcategories", "evidence"],
    }


def build_review_classification_schema(contract: ClassifierTaxonomyContract) -> dict[str, Any]:
    contract.validate()
    return _classification_schema(contract)


def build_batch_classification_schema(review_ids: list[str], contract: ClassifierTaxonomyContract) -> dict[str, Any]:
    contract.validate()
    single = build_review_classification_schema(contract)
    return {"type": "object", "properties": {str(rid): copy.deepcopy(single) for rid in review_ids}, "required": [str(rid) for rid in review_ids]}


__all__ = [
    "CLASSIFIER_TAXONOMY_CONTRACT_VERSION",
    "ClassifierTaxonomyContract",
    "allowed_topic_keys",
    "baseline_classifier_taxonomy",
    "build_batch_classification_schema",
    "build_review_classification_schema",
    "load_classifier_taxonomy",
    "render_classifier_taxonomy",
]
