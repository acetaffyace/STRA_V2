"""Human-governed, immutable taxonomy promotion (Stage 3D).

This module never calls an LLM and never changes classifier prompts or review
labels.  Every mutation is an explicit plan/validate/apply/publish action.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any, Mapping, Sequence

from sqlalchemy import text

from . import db
from .taxonomy_registry import (
    BASELINE_TAXONOMY_VERSION,
    TaxonomySnapshot,
    TaxonomyTopic,
    build_snapshot,
    ensure_baseline_snapshot,
    snapshot_from_rows,
    topic_id_for_key,
    validate_canonical_key,
)

SUPPORTED_PROMOTIONS = {"candidate_new_topic", "candidate_child_topic"}
STRUCTURAL_RECOMMENDATIONS = {"taxonomy_boundary_review"}
_VERSION_RE = re.compile(r"^sentinext-taxonomy-v(\d+)$")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _normalise_decision(value: str | None) -> str | None:
    aliases = {"approve": "approve_candidate", "approve_candidate": "approve_candidate", "reject": "reject_candidate", "reject_candidate": "reject_candidate", "defer": "defer_candidate", "defer_candidate": "defer_candidate", "request_revision": "request_revision"}
    return aliases.get(str(value or "").strip())


def _load_snapshot_with_conn(conn, identifier: str) -> TaxonomySnapshot:
    row = conn.execute(text("SELECT * FROM taxonomy_snapshots WHERE snapshot_id=:id OR taxonomy_version=:id"), {"id": identifier}).mappings().first()
    if not row:
        raise ValueError("snapshot_not_found")
    topics = conn.execute(text("SELECT * FROM taxonomy_topics WHERE snapshot_id=:id ORDER BY canonical_key, topic_id"), {"id": row["snapshot_id"]}).mappings().all()
    return snapshot_from_rows(dict(row), topics)


def get_taxonomy_snapshot(identifier: str) -> TaxonomySnapshot:
    with db.get_connection() as conn:
        return _load_snapshot_with_conn(conn, identifier)


def current_active_snapshot() -> TaxonomySnapshot:
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT snapshot_id FROM taxonomy_activation_events ORDER BY created_at DESC, rowid DESC LIMIT 1")).first()
        if not row:
            raw = conn.connection.driver_connection
            ensure_baseline_snapshot(raw)
            row = conn.execute(text("SELECT snapshot_id FROM taxonomy_activation_events ORDER BY created_at DESC, rowid DESC LIMIT 1")).first()
        return _load_snapshot_with_conn(conn, str(row[0]))


def taxonomy_status() -> dict[str, Any]:
    active = current_active_snapshot()
    with db.get_connection() as conn:
        published_n = int(conn.execute(text("SELECT COUNT(*) FROM taxonomy_snapshots WHERE status='published'")).scalar() or 0)
        activation_n = int(conn.execute(text("SELECT COUNT(*) FROM taxonomy_activation_events")).scalar() or 0)
    return {"active_snapshot_id": active.snapshot_id, "active_taxonomy_version": active.taxonomy_version, "active_taxonomy_fingerprint": active.taxonomy_fingerprint, "topic_n": len(active.topics), "published_snapshot_n": published_n, "activation_event_n": activation_n}


def _candidate_with_latest_decision(conn, candidate_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    row = conn.execute(text("SELECT * FROM semantic_taxonomy_candidates WHERE candidate_id=:id"), {"id": candidate_id}).mappings().first()
    if not row:
        raise ValueError("candidate_not_found")
    candidate = dict(row)
    try:
        candidate["candidate_payload"] = json.loads(candidate.get("candidate_json") or "{}")
    except Exception:
        candidate["candidate_payload"] = {}
    # created_at is second-resolution in the legacy Stage 3C table.  rowid
    # preserves append order when several human decisions occur in one
    # second, while still sorting by timestamp first for older data.
    decision = conn.execute(text("SELECT * FROM semantic_taxonomy_candidate_decisions WHERE candidate_id=:id ORDER BY created_at DESC, rowid DESC LIMIT 1"), {"id": candidate_id}).mappings().first()
    return candidate, (dict(decision) if decision else None)


def list_eligible_candidates() -> list[dict[str, Any]]:
    with db.get_connection() as conn:
        rows = conn.execute(text("SELECT candidate_id FROM semantic_taxonomy_candidates ORDER BY candidate_id")).scalars().all()
        result = []
        for candidate_id in rows:
            candidate, decision = _candidate_with_latest_decision(conn, str(candidate_id))
            payload = candidate.get("candidate_payload") or {}
            recommendation = str(candidate.get("recommendation") or payload.get("recommendation") or "")
            if _normalise_decision((decision or {}).get("decision")) != "approve_candidate" or recommendation not in SUPPORTED_PROMOTIONS or str(candidate.get("evidence_sufficiency") or payload.get("evidence_sufficiency")) == "insufficient":
                continue
            promoted = conn.execute(text("SELECT 1 FROM taxonomy_topics WHERE source_candidate_id=:id LIMIT 1"), {"id": candidate_id}).scalar()
            if promoted:
                continue
            result.append({"candidate_id": str(candidate_id), "candidate_name": payload.get("candidate_name") or candidate.get("candidate_name"), "recommendation": recommendation, "evidence_sufficiency": candidate.get("evidence_sufficiency") or payload.get("evidence_sufficiency"), "region_id": payload.get("region_id") or candidate.get("region_id"), "interpretation_run_id": payload.get("interpretation_run_id")})
        return result


def _next_taxonomy_version(conn) -> str:
    numbers = []
    # Revision numbering follows published taxonomy history.  Drafts are
    # provisional and must not make the public version jump unexpectedly.
    for value in conn.execute(text("SELECT taxonomy_version FROM taxonomy_snapshots WHERE status='published'")).scalars().all():
        match = _VERSION_RE.fullmatch(str(value))
        if match:
            numbers.append(int(match.group(1)))
    return f"sentinext-taxonomy-v{(max(numbers) if numbers else 0) + 1}"


def plan_add_topic(*, candidate_id: str, base_version: str = BASELINE_TAXONOMY_VERSION, canonical_key: str, display_name: str, description: str, operator: str, parent_key: str | None = None) -> dict[str, Any]:
    validate_canonical_key(canonical_key)
    if not str(display_name).strip() or not str(description).strip():
        raise ValueError("topic_definition_incomplete")
    with db.get_connection() as conn:
        base = _load_snapshot_with_conn(conn, base_version)
        if base.status != "published":
            raise ValueError("base_snapshot_not_published")
        candidate, decision = _candidate_with_latest_decision(conn, candidate_id)
        if conn.execute(text("SELECT 1 FROM taxonomy_topics WHERE source_candidate_id=:id LIMIT 1"), {"id": candidate_id}).scalar():
            raise ValueError("candidate_already_promoted")
        decision_value = _normalise_decision((decision or {}).get("decision"))
        payload = candidate.get("candidate_payload") or {}
        recommendation = str(candidate.get("recommendation") or payload.get("recommendation") or "")
        evidence_sufficiency = str(candidate.get("evidence_sufficiency") or payload.get("evidence_sufficiency") or "")
        if decision_value != "approve_candidate":
            raise ValueError("candidate_not_approved")
        if recommendation in STRUCTURAL_RECOMMENDATIONS:
            raise ValueError("requires_structural_governance")
        if recommendation not in SUPPORTED_PROMOTIONS:
            raise ValueError("unsupported_candidate_recommendation")
        if evidence_sufficiency == "insufficient":
            raise ValueError("insufficient_evidence")
        if recommendation == "candidate_child_topic" and not parent_key:
            raise ValueError("invalid_parent")
        parent_topic_id = None
        if parent_key:
            parent_key = validate_canonical_key(parent_key)
            parent = next((topic for topic in base.topics if topic.canonical_key == parent_key), None)
            if parent is None or parent.topic_status != "active":
                raise ValueError("invalid_parent")
            parent_topic_id = parent.topic_id
        if any(topic.canonical_key == canonical_key for topic in base.topics):
            raise ValueError("canonical_key_conflict")
        topic_id = topic_id_for_key(canonical_key)
        if any(topic.topic_id == topic_id for topic in base.topics):
            raise ValueError("topic_id_conflict")
        requested_version = _next_taxonomy_version(conn)
        plan_payload = {"action": "add_topic", "candidate_id": candidate_id, "canonical_key": canonical_key, "topic_id": topic_id, "parent_topic_id": parent_topic_id, "display_name": str(display_name).strip(), "description": str(description).strip(), "base_snapshot_id": base.snapshot_id, "base_taxonomy_fingerprint": base.taxonomy_fingerprint, "requested_version": requested_version}
        change_set_id = "changeset_" + _sha(plan_payload)[:32]
        existing = conn.execute(text("SELECT * FROM taxonomy_change_sets WHERE change_set_id=:id"), {"id": change_set_id}).mappings().first()
        if existing:
            return {**dict(existing), "plan": json.loads(existing["plan_json"]), "change_set_id": change_set_id}
        conn.execute(text("INSERT INTO taxonomy_change_sets(change_set_id,base_snapshot_id,base_taxonomy_fingerprint,status,requested_version,operator,plan_json) VALUES (:id,:base,:fingerprint,'planned',:version,:operator,:plan)"), {"id": change_set_id, "base": base.snapshot_id, "fingerprint": base.taxonomy_fingerprint, "version": requested_version, "operator": operator, "plan": json.dumps(plan_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))})
        conn.execute(text("INSERT INTO taxonomy_change_items(change_item_id,change_set_id,action,source_candidate_id,topic_id,canonical_key,parent_topic_id,display_name,description) VALUES (:item,:set,'add_topic',:candidate,:topic,:key,:parent,:name,:description)"), {"item": "item_" + _sha(plan_payload)[:32], "set": change_set_id, "candidate": candidate_id, "topic": topic_id, "key": canonical_key, "parent": parent_topic_id, "name": str(display_name).strip(), "description": str(description).strip()})
        return {"change_set_id": change_set_id, "status": "planned", "plan": plan_payload, "candidate": {"candidate_id": candidate_id, "decision": decision_value, "recommendation": recommendation, "evidence_sufficiency": evidence_sufficiency}, "base_snapshot": {"snapshot_id": base.snapshot_id, "taxonomy_version": base.taxonomy_version, "taxonomy_fingerprint": base.taxonomy_fingerprint}, "requested_version": requested_version}


def validate_change_set(change_set_id: str) -> dict[str, Any]:
    errors: list[str] = []
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM taxonomy_change_sets WHERE change_set_id=:id"), {"id": change_set_id}).mappings().first()
        if not row:
            raise ValueError("change_set_not_found")
        change = dict(row)
        try:
            plan = json.loads(change["plan_json"])
        except Exception:
            plan = {}
        try:
            base = _load_snapshot_with_conn(conn, str(change["base_snapshot_id"]))
            if base.status != "published":
                errors.append("base_snapshot_not_found")
        except ValueError:
            base = None
            errors.append("base_snapshot_not_found")
        active_row = conn.execute(text("SELECT snapshot_id FROM taxonomy_activation_events ORDER BY created_at DESC, rowid DESC LIMIT 1")).first()
        if base and active_row and str(active_row[0]) != base.snapshot_id:
            errors.append("stale_taxonomy_base")
        item = conn.execute(text("SELECT * FROM taxonomy_change_items WHERE change_set_id=:id ORDER BY change_item_id"), {"id": change_set_id}).mappings().first()
        if not item:
            errors.append("change_set_empty")
        else:
            item = dict(item)
            if base and any(topic.canonical_key == item["canonical_key"] for topic in base.topics):
                errors.append("canonical_key_conflict")
            candidate, decision = _candidate_with_latest_decision(conn, str(item["source_candidate_id"]))
            payload = candidate.get("candidate_payload") or {}
            recommendation = str(candidate.get("recommendation") or payload.get("recommendation") or "")
            if _normalise_decision((decision or {}).get("decision")) != "approve_candidate":
                errors.append("candidate_not_approved")
            if recommendation in STRUCTURAL_RECOMMENDATIONS:
                errors.append("requires_structural_governance")
            if recommendation not in SUPPORTED_PROMOTIONS:
                errors.append("unsupported_candidate_recommendation")
            if str(candidate.get("evidence_sufficiency") or payload.get("evidence_sufficiency") or "") == "insufficient":
                errors.append("insufficient_evidence")
            if recommendation == "candidate_child_topic" and not item.get("parent_topic_id"):
                errors.append("invalid_parent")
            if conn.execute(text("SELECT 1 FROM taxonomy_topics WHERE source_candidate_id=:id LIMIT 1"), {"id": item["source_candidate_id"]}).scalar():
                errors.append("candidate_already_promoted")
            if base and item.get("parent_topic_id") and not any(topic.topic_id == item["parent_topic_id"] and topic.topic_status == "active" for topic in base.topics):
                errors.append("invalid_parent")
        errors = sorted(set(errors))
        result = {"change_set_id": change_set_id, "valid": not errors, "status": "validated" if not errors else str(change["status"]), "errors": errors, "base_snapshot_id": change["base_snapshot_id"], "base_taxonomy_fingerprint": change["base_taxonomy_fingerprint"], "requested_version": change["requested_version"]}
        conn.execute(text("UPDATE taxonomy_change_sets SET status=:status, validation_json=:validation, validated_at=CASE WHEN :valid=1 THEN datetime('now') ELSE validated_at END WHERE change_set_id=:id"), {"status": "validated" if not errors else ("rejected" if change["status"] == "rejected" else change["status"]), "validation": json.dumps(result, sort_keys=True, separators=(",", ":")), "valid": 1 if not errors else 0, "id": change_set_id})
        return result


def apply_change_set(change_set_id: str) -> TaxonomySnapshot:
    validation = validate_change_set(change_set_id)
    if not validation["valid"]:
        raise ValueError(validation["errors"][0])
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT * FROM taxonomy_change_sets WHERE change_set_id=:id"), {"id": change_set_id}).mappings().one()
        if row["status"] != "validated":
            raise ValueError("change_set_not_validated")
        base = _load_snapshot_with_conn(conn, str(row["base_snapshot_id"]))
        active_row = conn.execute(text("SELECT snapshot_id FROM taxonomy_activation_events ORDER BY created_at DESC, rowid DESC LIMIT 1")).first()
        active = _load_snapshot_with_conn(conn, str(active_row[0])) if active_row else None
        if active is None or active.snapshot_id != base.snapshot_id or active.taxonomy_fingerprint != row["base_taxonomy_fingerprint"]:
            raise ValueError("stale_taxonomy_base")
        items = conn.execute(text("SELECT * FROM taxonomy_change_items WHERE change_set_id=:id ORDER BY change_item_id"), {"id": change_set_id}).mappings().all()
        topics = list(base.topics)
        for item in items:
            topics.append(TaxonomyTopic(topic_id=str(item["topic_id"]), canonical_key=str(item["canonical_key"]), parent_topic_id=item["parent_topic_id"], display_name=str(item["display_name"]), description=str(item["description"]), topic_status="active", source_kind="promoted_candidate", source_candidate_id=str(item["source_candidate_id"])))
        draft = build_snapshot(topics, taxonomy_version=str(row["requested_version"]), parent_snapshot_id=base.snapshot_id, status="draft", created_by=str(row["operator"]), source_change_set_id=change_set_id)
        conn.execute(text("INSERT INTO taxonomy_snapshots(snapshot_id,taxonomy_version,parent_snapshot_id,taxonomy_fingerprint,status,topic_n,source_change_set_id,created_by) VALUES (:id,:version,:parent,:fingerprint,'draft',:n,:change,:operator)"), {"id": draft.snapshot_id, "version": draft.taxonomy_version, "parent": draft.parent_snapshot_id, "fingerprint": draft.taxonomy_fingerprint, "n": len(draft.topics), "change": change_set_id, "operator": row["operator"]})
        for topic in draft.topics:
            conn.execute(text("INSERT INTO taxonomy_topics(snapshot_id,topic_id,canonical_key,parent_topic_id,display_name,description,topic_status,source_kind,source_candidate_id) VALUES (:snapshot,:id,:key,:parent,:name,:description,:status,:source,:candidate)"), {"snapshot": draft.snapshot_id, "id": topic.topic_id, "key": topic.canonical_key, "parent": topic.parent_topic_id, "name": topic.display_name, "description": topic.description, "status": topic.topic_status, "source": topic.source_kind, "candidate": topic.source_candidate_id})
        conn.execute(text("UPDATE taxonomy_change_sets SET status='applied',result_snapshot_id=:snapshot,applied_at=datetime('now') WHERE change_set_id=:id"), {"snapshot": draft.snapshot_id, "id": change_set_id})
        return draft


def publish_snapshot(identifier: str, *, operator: str, reason: str = "publish") -> TaxonomySnapshot:
    with db.get_connection() as conn:
        draft = _load_snapshot_with_conn(conn, identifier)
        if draft.status != "draft":
            raise ValueError("snapshot_not_draft")
        if not draft.source_change_set_id:
            raise ValueError("snapshot_not_validated")
        change = conn.execute(text("SELECT status,validation_json FROM taxonomy_change_sets WHERE change_set_id=:id"), {"id": draft.source_change_set_id}).mappings().first()
        if not change or change["status"] != "applied":
            raise ValueError("snapshot_not_validated")
        validation = json.loads(change["validation_json"] or "{}")
        if not validation.get("valid"):
            raise ValueError("snapshot_not_validated")
        draft.validate()
        conn.execute(text("UPDATE taxonomy_snapshots SET status='published',published_at=datetime('now') WHERE snapshot_id=:id AND status='draft'"), {"id": draft.snapshot_id})
        activation_id = "activation_" + _sha({"snapshot_id": draft.snapshot_id, "operator": operator, "reason": reason, "nonce": uuid.uuid4().hex})[:32]
        conn.execute(text("INSERT INTO taxonomy_activation_events(activation_id,snapshot_id,taxonomy_version,reason,operator) VALUES (:id,:snapshot,:version,:reason,:operator)"), {"id": activation_id, "snapshot": draft.snapshot_id, "version": draft.taxonomy_version, "reason": reason, "operator": operator})
        return _load_snapshot_with_conn(conn, draft.snapshot_id)


def activate_snapshot(identifier: str, *, operator: str, reason: str = "activate") -> TaxonomySnapshot:
    with db.get_connection() as conn:
        snapshot = _load_snapshot_with_conn(conn, identifier)
        if snapshot.status != "published":
            raise ValueError("snapshot_not_published")
        activation_id = "activation_" + _sha({"snapshot_id": snapshot.snapshot_id, "operator": operator, "reason": reason, "nonce": uuid.uuid4().hex})[:32]
        conn.execute(text("INSERT INTO taxonomy_activation_events(activation_id,snapshot_id,taxonomy_version,reason,operator) VALUES (:id,:snapshot,:version,:reason,:operator)"), {"id": activation_id, "snapshot": snapshot.snapshot_id, "version": snapshot.taxonomy_version, "reason": reason, "operator": operator})
        return snapshot


def _snapshot_topics(identifier: str) -> tuple[TaxonomySnapshot, dict[str, TaxonomyTopic]]:
    snapshot = get_taxonomy_snapshot(identifier)
    return snapshot, {topic.canonical_key: topic for topic in snapshot.topics}


def diff_taxonomies(from_identifier: str, to_identifier: str) -> dict[str, Any]:
    left, left_topics = _snapshot_topics(from_identifier)
    right, right_topics = _snapshot_topics(to_identifier)
    added = sorted(set(right_topics) - set(left_topics))
    removed = sorted(set(left_topics) - set(right_topics))
    changed_names, changed_descriptions, changed_parents = [], [], []
    for key in sorted(set(left_topics) & set(right_topics)):
        a, b = left_topics[key], right_topics[key]
        if a.display_name != b.display_name:
            changed_names.append({"canonical_key": key, "from": a.display_name, "to": b.display_name})
        if a.description != b.description:
            changed_descriptions.append({"canonical_key": key, "from": a.description, "to": b.description})
        if a.parent_topic_id != b.parent_topic_id:
            changed_parents.append({"canonical_key": key, "from": a.parent_topic_id, "to": b.parent_topic_id})
    return {"from_snapshot_id": left.snapshot_id, "to_snapshot_id": right.snapshot_id, "from_version": left.taxonomy_version, "to_version": right.taxonomy_version, "added_topics": added, "removed_topics": removed, "changed_display_names": changed_names, "changed_descriptions": changed_descriptions, "changed_parent_relationships": changed_parents}


def activation_history() -> list[dict[str, Any]]:
    with db.get_connection() as conn:
        return [dict(row) for row in conn.execute(text("SELECT * FROM taxonomy_activation_events ORDER BY created_at ASC, rowid ASC")).mappings().all()]


def trace_taxonomy_topic(topic_id: str, snapshot_id: str | None = None) -> dict[str, Any]:
    snapshot = get_taxonomy_snapshot(snapshot_id) if snapshot_id else current_active_snapshot()
    topic = next((topic for topic in snapshot.topics if topic.topic_id == topic_id), None)
    if topic is None:
        raise ValueError("topic_not_found")
    result: dict[str, Any] = {"snapshot": snapshot.to_dict(), "topic": topic.to_dict(), "source_candidate": None, "latest_decision": None, "evidence_package": None, "materialization": None}
    if not topic.source_candidate_id:
        return result
    with db.get_connection() as conn:
        candidate = conn.execute(text("SELECT * FROM semantic_taxonomy_candidates WHERE candidate_id=:id"), {"id": topic.source_candidate_id}).mappings().first()
        if not candidate:
            return result
        result["source_candidate"] = dict(candidate)
        result["source_candidate"]["candidate_json"] = json.loads(result["source_candidate"].get("candidate_json") or "{}")
        decision = conn.execute(text("SELECT * FROM semantic_taxonomy_candidate_decisions WHERE candidate_id=:id ORDER BY created_at DESC, rowid DESC LIMIT 1"), {"id": topic.source_candidate_id}).mappings().first()
        result["latest_decision"] = dict(decision) if decision else None
        evidence_id = str(result["source_candidate"].get("evidence_package_id") or "")
        if evidence_id:
            evidence = conn.execute(text("SELECT evidence_json FROM semantic_region_evidence_packages WHERE evidence_package_id=:id"), {"id": evidence_id}).scalar()
            if evidence:
                result["evidence_package"] = json.loads(evidence)
                materialization_id = result["evidence_package"].get("materialization_id")
                if materialization_id:
                    materialization = conn.execute(text("SELECT report_json FROM semantic_discovery_materializations WHERE materialization_id=:id"), {"id": materialization_id}).scalar()
                    result["materialization"] = json.loads(materialization) if materialization else None
    return result


# Explicit aliases keep the service vocabulary readable for callers that use
# "promotion" terminology while retaining the small, testable primitives
# above.  They do not introduce an implicit candidate->taxonomy mutation.
create_promotion_plan = plan_add_topic
validate_promotion_plan = validate_change_set
apply_promotion_plan = apply_change_set
publish_taxonomy_snapshot = publish_snapshot
activate_taxonomy_snapshot = activate_snapshot
get_active_taxonomy_snapshot = current_active_snapshot
list_eligible_taxonomy_candidates = list_eligible_candidates
plan_taxonomy_change = plan_add_topic
validate_taxonomy_change = validate_change_set
apply_taxonomy_change = apply_change_set
