"""Content-addressed taxonomy definitions and immutable snapshot helpers."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

TAXONOMY_REGISTRY_SCHEMA_VERSION = "taxonomy-registry-v1"
BASELINE_TAXONOMY_VERSION = "sentinext-taxonomy-v1"
_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*(?:/[a-z0-9]+(?:_[a-z0-9]+)*)+$")

# Structured stdlib-only baseline.  It is intentionally a flat list because
# this is the exact canonical key set consumed by the frozen classifier.
BASELINE_TAXONOMY_V1: tuple[str, ...] = (
    "content_design/amount_variety", "content_design/customization", "content_design/level_design", "content_design/narrative_characters", "content_design/pacing", "content_design/quests_modes", "content_design/replayability",
    "developer_updates/communication", "developer_updates/customer_support", "developer_updates/patch_quality", "developer_updates/response_time", "developer_updates/roadmap_events", "developer_updates/update_frequency",
    "gameplay/ai", "gameplay/balance", "gameplay/controls", "gameplay/difficulty", "gameplay/mechanics", "gameplay/progression",
    "monetization_value/battle_pass_fomo", "monetization_value/dlc", "monetization_value/microtransactions", "monetization_value/pay_to_win_grind", "monetization_value/pricing", "monetization_value/regional_pricing", "monetization_value/value_for_money",
    "onboarding/clarity", "onboarding/learning_curve", "onboarding/tooltips", "onboarding/tutorial",
    "online_community/cheating_anti_cheat", "online_community/matchmaking", "online_community/mods_ugc", "online_community/multiplayer_experience", "online_community/social_features", "online_community/toxicity_moderation",
    "other/general", "other/meme", "other/meta", "other/mixed", "other/off_topic", "other/unclear",
    "presentation/animation", "presentation/atmosphere", "presentation/audio_music", "presentation/localization", "presentation/visuals_art_style", "presentation/voice_acting",
    "technical/bugs", "technical/compatibility", "technical/installation", "technical/networking", "technical/performance", "technical/save_data", "technical/stability_crashes",
    "ui_ux_accessibility/accessibility_options", "ui_ux_accessibility/controller_support", "ui_ux_accessibility/menus_hud", "ui_ux_accessibility/quality_of_life", "ui_ux_accessibility/readability",
)


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def topic_id_for_key(canonical_key: str) -> str:
    validate_canonical_key(canonical_key)
    return "topic_" + hashlib.sha256(("stra-taxonomy-topic-v1:" + canonical_key).encode()).hexdigest()[:16]


def validate_canonical_key(value: str) -> str:
    key = str(value or "").strip()
    if not _KEY_RE.fullmatch(key):
        raise ValueError("canonical_key_invalid")
    return key


@dataclass(frozen=True)
class TaxonomyTopic:
    topic_id: str
    canonical_key: str
    display_name: str
    description: str
    parent_topic_id: str | None = None
    topic_status: str = "active"
    source_kind: str = "baseline"
    source_candidate_id: str | None = None

    def validate(self) -> None:
        validate_canonical_key(self.canonical_key)
        if self.topic_id != topic_id_for_key(self.canonical_key):
            raise ValueError("topic_id_mismatch")
        if not str(self.display_name).strip() or not str(self.description).strip():
            raise ValueError("topic_definition_incomplete")
        if self.topic_status not in {"active", "deprecated"}:
            raise ValueError("invalid_topic_status")
        if self.source_kind not in {"baseline", "promoted_candidate"}:
            raise ValueError("invalid_topic_source")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class TaxonomySnapshot:
    snapshot_id: str
    taxonomy_version: str
    parent_snapshot_id: str | None
    taxonomy_fingerprint: str
    status: str
    topics: tuple[TaxonomyTopic, ...]
    source_change_set_id: str | None = None
    created_by: str | None = None

    def validate(self) -> None:
        if self.status not in {"draft", "published", "retired"}:
            raise ValueError("invalid_snapshot_status")
        if not self.topics:
            raise ValueError("taxonomy_empty")
        keys = [topic.canonical_key for topic in self.topics]
        ids = [topic.topic_id for topic in self.topics]
        if len(keys) != len(set(keys)) or len(ids) != len(set(ids)):
            raise ValueError("taxonomy_topic_collision")
        by_id = set(ids)
        for topic in self.topics:
            topic.validate()
            if topic.parent_topic_id and topic.parent_topic_id not in by_id:
                raise ValueError("invalid_parent")
            if topic.parent_topic_id == topic.topic_id:
                raise ValueError("taxonomy_cycle")
        # Parent links form a forest.  Validate the complete chain rather
        # than only self-parenting so a malformed draft cannot contain a
        # two-node (or longer) cycle.
        parents = {topic.topic_id: topic.parent_topic_id for topic in self.topics}
        for topic_id in parents:
            seen: set[str] = set()
            cursor = topic_id
            while cursor is not None:
                if cursor in seen:
                    raise ValueError("taxonomy_cycle")
                seen.add(cursor)
                cursor = parents.get(cursor)
        if taxonomy_fingerprint(self.topics) != self.taxonomy_fingerprint:
            raise ValueError("taxonomy_fingerprint_mismatch")
        if snapshot_id_for(self.taxonomy_version, self.parent_snapshot_id, self.topics) != self.snapshot_id:
            raise ValueError("snapshot_id_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "taxonomy_version": self.taxonomy_version, "parent_snapshot_id": self.parent_snapshot_id, "taxonomy_fingerprint": self.taxonomy_fingerprint, "status": self.status, "topic_n": len(self.topics), "source_change_set_id": self.source_change_set_id, "created_by": self.created_by, "topics": [topic.to_dict() for topic in self.topics]}


def taxonomy_fingerprint(topics: Iterable[TaxonomyTopic | Mapping[str, Any]]) -> str:
    payload = []
    for value in topics:
        topic = value if isinstance(value, TaxonomyTopic) else TaxonomyTopic(**{key: value[key] for key in TaxonomyTopic.__dataclass_fields__ if key in value})
        payload.append({"topic_id": topic.topic_id, "canonical_key": topic.canonical_key, "parent_topic_id": topic.parent_topic_id, "display_name": topic.display_name, "description": topic.description, "topic_status": topic.topic_status})
    return _sha(sorted(payload, key=lambda item: (item["canonical_key"], item["topic_id"])))


def snapshot_id_for(taxonomy_version: str, parent_snapshot_id: str | None, topics: Iterable[TaxonomyTopic]) -> str:
    payload = {"schema_version": TAXONOMY_REGISTRY_SCHEMA_VERSION, "taxonomy_version": taxonomy_version, "parent_snapshot_id": parent_snapshot_id, "topics": sorted([topic.to_dict() for topic in topics], key=lambda item: (item["canonical_key"], item["topic_id"]))}
    return "snapshot_" + _sha(payload)[:32]


def _display_name(canonical_key: str) -> str:
    return canonical_key.rsplit("/", 1)[-1].replace("_", " ").title()


def baseline_topics() -> tuple[TaxonomyTopic, ...]:
    return tuple(TaxonomyTopic(topic_id_for_key(key), key, _display_name(key), f"Feedback related to {_display_name(key).lower()}.") for key in BASELINE_TAXONOMY_V1)


def build_snapshot(topics: Sequence[TaxonomyTopic], *, taxonomy_version: str, parent_snapshot_id: str | None = None, status: str = "draft", created_by: str | None = None, source_change_set_id: str | None = None) -> TaxonomySnapshot:
    ordered = tuple(sorted(topics, key=lambda topic: (topic.canonical_key, topic.topic_id)))
    snapshot = TaxonomySnapshot(snapshot_id_for(taxonomy_version, parent_snapshot_id, ordered), taxonomy_version, parent_snapshot_id, taxonomy_fingerprint(ordered), status, ordered, source_change_set_id, created_by)
    snapshot.validate()
    return snapshot


def build_baseline_snapshot() -> TaxonomySnapshot:
    return build_snapshot(baseline_topics(), taxonomy_version=BASELINE_TAXONOMY_VERSION, status="published", created_by="system")


def ensure_baseline_snapshot(conn) -> TaxonomySnapshot:
    baseline = build_baseline_snapshot()
    if hasattr(conn, "exec_driver_sql"):
        row = conn.exec_driver_sql("SELECT snapshot_id, taxonomy_fingerprint, status FROM taxonomy_snapshots WHERE taxonomy_version = ?", (BASELINE_TAXONOMY_VERSION,)).fetchone()
        execute = lambda sql, params: conn.exec_driver_sql(sql, params)
    else:
        row = conn.execute("SELECT snapshot_id, taxonomy_fingerprint, status FROM taxonomy_snapshots WHERE taxonomy_version = ?", (BASELINE_TAXONOMY_VERSION,)).fetchone()
        execute = lambda sql, params: conn.execute(sql, params)
    if row:
        if str(row[0]) != baseline.snapshot_id or str(row[1]) != baseline.taxonomy_fingerprint or str(row[2]) != "published":
            raise RuntimeError("baseline_taxonomy_parity_mismatch")
        return baseline
    execute("INSERT INTO taxonomy_snapshots(snapshot_id,taxonomy_version,parent_snapshot_id,taxonomy_fingerprint,status,topic_n,source_change_set_id,created_by,published_at) VALUES (?,?,?,?,?,?,?,?,datetime('now'))", (baseline.snapshot_id, baseline.taxonomy_version, None, baseline.taxonomy_fingerprint, "published", len(baseline.topics), None, "system"))
    for topic in baseline.topics:
        execute("INSERT INTO taxonomy_topics(snapshot_id,topic_id,canonical_key,parent_topic_id,display_name,description,topic_status,source_kind,source_candidate_id) VALUES (?,?,?,?,?,?,?,?,?)", (baseline.snapshot_id, topic.topic_id, topic.canonical_key, topic.parent_topic_id, topic.display_name, topic.description, topic.topic_status, topic.source_kind, topic.source_candidate_id))
    activation_id = "activation_" + _sha({"snapshot_id": baseline.snapshot_id, "reason": "baseline"})[:32]
    execute("INSERT INTO taxonomy_activation_events(activation_id,snapshot_id,taxonomy_version,reason,operator) VALUES (?,?,?,?,?)", (activation_id, baseline.snapshot_id, baseline.taxonomy_version, "baseline", "system"))
    return baseline


def snapshot_from_rows(snapshot_row: Mapping[str, Any], topic_rows: Iterable[Mapping[str, Any]]) -> TaxonomySnapshot:
    topics = tuple(TaxonomyTopic(topic_id=str(row["topic_id"]), canonical_key=str(row["canonical_key"]), parent_topic_id=row.get("parent_topic_id"), display_name=str(row["display_name"]), description=str(row["description"]), topic_status=str(row.get("topic_status") or "active"), source_kind=str(row.get("source_kind") or "baseline"), source_candidate_id=row.get("source_candidate_id")) for row in topic_rows)
    snapshot = TaxonomySnapshot(snapshot_id=str(snapshot_row["snapshot_id"]), taxonomy_version=str(snapshot_row["taxonomy_version"]), parent_snapshot_id=snapshot_row.get("parent_snapshot_id"), taxonomy_fingerprint=str(snapshot_row["taxonomy_fingerprint"]), status=str(snapshot_row["status"]), topics=tuple(sorted(topics, key=lambda topic: (topic.canonical_key, topic.topic_id))), source_change_set_id=snapshot_row.get("source_change_set_id"), created_by=snapshot_row.get("created_by"))
    snapshot.validate()
    return snapshot
