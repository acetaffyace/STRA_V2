"""Immutable persistence and explicit governance for Game/Archetype Topics."""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import db
from .research_contracts import canonical_json, sha256_json, utc_iso

_STATUSES = {"DRAFT", "PUBLISHED", "RETIRED"}


def _normalize_entries(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        raise ValueError("topic_catalog_entries_required")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        key = str(entry.get("topic_key") or entry.get("id") or "").strip()
        if not key or key in seen:
            raise ValueError("topic_catalog_topic_key_invalid_or_duplicate")
        required = ("display_name", "definition", "include", "exclude", "boundary")
        if any(not str(entry.get(field) or "").strip() for field in required):
            raise ValueError("topic_catalog_topic_definition_incomplete")
        aliases = entry.get("aliases") or []
        if not isinstance(aliases, list) or any(not str(alias).strip() for alias in aliases):
            raise ValueError("topic_catalog_aliases_invalid")
        status = str(entry.get("topic_status") or "active")
        if status not in {"active", "deprecated"}:
            raise ValueError("topic_catalog_topic_status_invalid")
        result.append({
            "topic_key": key,
            "display_name": str(entry["display_name"]).strip(),
            "definition": str(entry["definition"]).strip(),
            "include": str(entry["include"]).strip(),
            "exclude": str(entry["exclude"]).strip(),
            "boundary": str(entry["boundary"]).strip(),
            "aliases": sorted({str(alias).strip() for alias in aliases}),
            "topic_status": status,
        })
        seen.add(key)
    return sorted(result, key=lambda item: item["topic_key"])


def _catalog_row(row: Mapping[str, Any], topics: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    return {
        "catalog_version_id": str(row["catalog_version_id"]),
        "catalog_scope": str(row["catalog_scope"]),
        "app_id": row["app_id"],
        "catalog_version": str(row["catalog_version"]),
        "parent_catalog_version_id": row["parent_catalog_version_id"],
        "catalog_hash": str(row["catalog_hash"]),
        "status": str(row["status"]),
        "created_at": utc_iso(row["created_at"]),
        "published_at": utc_iso(row["published_at"]) if row["published_at"] else None,
        "topic_catalog_schema_version": str(row["topic_catalog_schema_version"]),
        "topics": [dict(topic) for topic in topics],
    }


def _load(conn, catalog_version_id: str) -> dict[str, Any] | None:
    row = conn.execute(text("SELECT * FROM topic_catalog_versions WHERE catalog_version_id=:id"), {"id": catalog_version_id}).mappings().first()
    if not row:
        return None
    topics = conn.execute(text("SELECT * FROM topic_catalog_topics WHERE catalog_version_id=:id ORDER BY topic_key"), {"id": catalog_version_id}).mappings().all()
    parsed = []
    for topic in topics:
        value = dict(topic)
        value["aliases"] = json.loads(value.pop("aliases_json") or "[]")
        parsed.append(value)
    return _catalog_row(row, parsed)


def create_topic_catalog_version(*, catalog_scope: str, catalog_version: str, entries: Sequence[Mapping[str, Any]], app_id: int | None = None, parent_catalog_version_id: str | None = None, status: str = "DRAFT") -> dict[str, Any]:
    scope = str(catalog_scope).strip().lower()
    if scope not in {"game", "archetype"}:
        raise ValueError("topic_catalog_scope_invalid")
    if scope == "game" and (app_id is None or int(app_id) <= 0):
        raise ValueError("game_topic_catalog_app_id_required")
    if scope == "archetype" and app_id is not None:
        raise ValueError("archetype_catalog_must_not_bind_app")
    version = str(catalog_version).strip()
    if not version:
        raise ValueError("topic_catalog_version_required")
    target_status = str(status).upper()
    if target_status not in _STATUSES:
        raise ValueError("topic_catalog_status_invalid")
    normalized = _normalize_entries(entries)
    identity = {"catalog_scope": scope, "app_id": int(app_id) if app_id is not None else None, "catalog_version": version, "parent_catalog_version_id": parent_catalog_version_id, "topics": normalized}
    catalog_hash = sha256_json(identity)
    catalog_id = "catalog_" + catalog_hash[:40]
    with db.get_connection() as conn:
        existing = _load(conn, catalog_id)
        if existing:
            if existing["catalog_hash"] != catalog_hash:
                raise ValueError("topic_catalog_conflict")
            return existing
        try:
            conn.execute(text("""INSERT INTO topic_catalog_versions
                (catalog_version_id, catalog_scope, app_id, catalog_version, parent_catalog_version_id, catalog_hash, status, created_at, published_at)
                VALUES (:id, :scope, :app_id, :version, :parent, :hash, :status, :created_at, :published_at)"""), {"id": catalog_id, "scope": scope, "app_id": int(app_id) if app_id is not None else None, "version": version, "parent": parent_catalog_version_id, "hash": catalog_hash, "status": target_status, "created_at": utc_iso(None), "published_at": utc_iso(None) if target_status == "PUBLISHED" else None})
            for topic in normalized:
                topic_id = "catalog_topic_" + sha256_json({"catalog_version_id": catalog_id, "topic_key": topic["topic_key"]})[:32]
                conn.execute(text("""INSERT INTO topic_catalog_topics
                    (catalog_topic_id, catalog_version_id, topic_key, display_name, definition, include_text, exclude_text, boundary_text, aliases_json, topic_status)
                    VALUES (:id, :catalog_id, :topic_key, :display_name, :definition, :include, :exclude, :boundary, :aliases, :status)"""), {"id": topic_id, "catalog_id": catalog_id, "topic_key": topic["topic_key"], "display_name": topic["display_name"], "definition": topic["definition"], "include": topic["include"], "exclude": topic["exclude"], "boundary": topic["boundary"], "aliases": canonical_json(topic["aliases"]), "status": topic["topic_status"]})
        except IntegrityError:
            existing = _load(conn, catalog_id)
            if existing:
                return existing
            raise
        return _load(conn, catalog_id) or {}


def get_topic_catalog_version(catalog_version_id: str) -> dict[str, Any] | None:
    with db.get_connection() as conn:
        return _load(conn, str(catalog_version_id))


def transition_topic_catalog_version(catalog_version_id: str, status: str) -> dict[str, Any]:
    target = str(status).upper()
    if target not in _STATUSES:
        raise ValueError("topic_catalog_status_invalid")
    with db.get_connection() as conn:
        row = conn.execute(text("SELECT status FROM topic_catalog_versions WHERE catalog_version_id=:id"), {"id": str(catalog_version_id)}).mappings().first()
        if not row:
            raise KeyError(f"topic_catalog_not_found:{catalog_version_id}")
        current = str(row["status"])
        allowed = {"DRAFT": {"DRAFT", "PUBLISHED"}, "PUBLISHED": {"PUBLISHED", "RETIRED"}, "RETIRED": {"RETIRED"}}
        if target not in allowed[current]:
            raise ValueError(f"invalid_topic_catalog_transition:{current}->{target}")
        conn.execute(text("UPDATE topic_catalog_versions SET status=:status, published_at=CASE WHEN :status='PUBLISHED' THEN COALESCE(published_at, :now) ELSE published_at END WHERE catalog_version_id=:id"), {"status": target, "now": utc_iso(None), "id": str(catalog_version_id)})
        return _load(conn, str(catalog_version_id)) or {}


__all__ = ["create_topic_catalog_version", "get_topic_catalog_version", "transition_topic_catalog_version"]
