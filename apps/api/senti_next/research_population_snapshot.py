"""Provider-independent immutable Research Population snapshots."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from sqlalchemy import text

from . import db
from .research_run_store import (
    create_population_snapshot,
    create_research_run,
    get_population_snapshot,
    get_research_run,
    get_review_snapshot,
    save_review_snapshot,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _review_id(review: Mapping[str, Any]) -> str:
    value = review.get("recommendationid") or review.get("review_id")
    if value is None or str(value) == "":
        raise ValueError("research_population_snapshot_review_id_required")
    return str(value)


def review_hash(review: Mapping[str, Any]) -> str:
    return hashlib.sha256(str(review.get("review") or "").encode("utf-8")).hexdigest()


def compute_population_fingerprint(reviews: Sequence[Mapping[str, Any]]) -> str:
    """Return the stable Stage 4A-compatible id/text population fingerprint."""
    canonical = sorted(
        ({"review_id": _review_id(review), "review_hash": review_hash(review)} for review in reviews),
        key=lambda item: item["review_id"],
    )
    return hashlib.sha256(_json(canonical).encode("utf-8")).hexdigest()


def _row_to_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "app_id": int(row["app_id"]),
        "population_fingerprint": str(row["population_fingerprint"]),
        "population_n": int(row["population_n"]),
        "created_at": row["created_at"],
        "population_snapshot_status": "frozen",
    }


def get_analysis_run_population_metadata(run_id: str) -> dict[str, Any] | None:
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            text("SELECT run_id, app_id, population_fingerprint, population_n, created_at FROM analysis_run_populations WHERE run_id=:run_id"),
            {"run_id": str(run_id)},
        ).mappings().first()
    return _row_to_metadata(row) if row else None


def get_analysis_run_population(run_id: str) -> dict[str, Any] | None:
    """Load the exact frozen population; never fall back to mutable app rows."""
    db.init_db()
    with db.get_connection() as conn:
        row = conn.execute(
            text("SELECT run_id, app_id, population_fingerprint, population_n, created_at FROM analysis_run_populations WHERE run_id=:run_id"),
            {"run_id": str(run_id)},
        ).mappings().first()
        if not row:
            return None
        items = conn.execute(
            text("SELECT ordinal, review_id, review_hash, payload_json FROM analysis_run_population_items WHERE run_id=:run_id ORDER BY ordinal"),
            {"run_id": str(run_id)},
        ).mappings().all()
    metadata = _row_to_metadata(row)
    reviews = []
    for item in items:
        payload = json.loads(str(item["payload_json"]))
        if not isinstance(payload, dict):
            raise ValueError("research_population_snapshot_invalid_payload")
        reviews.append(payload)
    if len(reviews) != metadata["population_n"]:
        raise ValueError("research_population_snapshot_incomplete")
    if compute_population_fingerprint(reviews) != metadata["population_fingerprint"]:
        raise ValueError("research_population_snapshot_corrupt")
    metadata["reviews"] = reviews
    return metadata


def freeze_analysis_run_population(
    *, run_id: str, app_id: int, reviews: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Freeze one run's complete input population, idempotently and immutably."""
    db.init_db()
    canonical_reviews = [dict(review) for review in reviews]
    review_ids = [_review_id(review) for review in canonical_reviews]
    if len(set(review_ids)) != len(review_ids):
        raise ValueError("research_population_snapshot_duplicate_review_id")
    fingerprint = compute_population_fingerprint(canonical_reviews)
    with db.get_connection() as conn:
        existing = conn.execute(
            text("SELECT run_id, app_id, population_fingerprint, population_n, created_at FROM analysis_run_populations WHERE run_id=:run_id"),
            {"run_id": str(run_id)},
        ).mappings().first()
        if existing:
            if str(existing["population_fingerprint"]) != fingerprint or int(existing["population_n"]) != len(canonical_reviews):
                raise ValueError("research_population_snapshot_conflict")
            row = existing
        else:
            run = conn.execute(
                text("SELECT target_app_id FROM analysis_runs WHERE run_id=:run_id AND run_type='general_analysis'"),
                {"run_id": str(run_id)},
            ).mappings().first()
            if not run:
                raise ValueError("analysis_run_not_found")
            if int(run["target_app_id"]) != int(app_id):
                raise ValueError("research_population_snapshot_app_mismatch")
            conn.execute(
                text("INSERT INTO analysis_run_populations(run_id, app_id, population_fingerprint, population_n) VALUES (:run_id, :app_id, :fingerprint, :population_n)"),
                {"run_id": str(run_id), "app_id": int(app_id), "fingerprint": fingerprint, "population_n": len(canonical_reviews)},
            )
            for ordinal, (review_id, review) in enumerate(zip(review_ids, canonical_reviews)):
                conn.execute(
                    text("INSERT INTO analysis_run_population_items(run_id, ordinal, review_id, review_hash, payload_json) VALUES (:run_id, :ordinal, :review_id, :review_hash, :payload_json)"),
                    {
                        "run_id": str(run_id),
                        "ordinal": ordinal,
                        "review_id": review_id,
                        "review_hash": review_hash(review),
                        "payload_json": _json(review),
                    },
                )
            row = conn.execute(
                text("SELECT run_id, app_id, population_fingerprint, population_n, created_at FROM analysis_run_populations WHERE run_id=:run_id"),
                {"run_id": str(run_id)},
            ).mappings().one()
        run_row = conn.execute(
            text("SELECT config, created_at FROM analysis_runs WHERE run_id=:run_id AND run_type='general_analysis'"),
            {"run_id": str(run_id)},
        ).mappings().first()

    # New general-analysis writes receive the canonical M0 identity graph at
    # the same freeze point.  The legacy return shape remains unchanged for
    # existing callers, with exact canonical IDs added as provenance.
    canonical = None
    if run_row:
        try:
            config = json.loads(str(run_row["config"] or "{}"))
        except (TypeError, ValueError):
            config = {}
        contract = config.get("sampling_contract")
        if not isinstance(contract, dict):
            contract = {"app_id": int(app_id), "languages": config.get("languages") or ["all"]}
        canonical = create_research_run(
            run_id=str(run_id),
            app_id=int(app_id),
            sampling_contract=contract,
            reviews=canonical_reviews,
            anchor_time=run_row["created_at"],
            acquisition_provenance={"legacy_bridge": True, "source": config.get("source", "steam_reviews")},
            config=config,
            status="RUNNING",
        )
    metadata = _row_to_metadata(row)
    if canonical:
        metadata.update({
            "population_snapshot_id": canonical["population_snapshot_id"],
            "canonical_population_hash": canonical["population_hash"],
            "canonical_run_id": canonical["run_id"],
        })
    return metadata


__all__ = [
    "compute_population_fingerprint",
    "create_population_snapshot",
    "create_research_run",
    "freeze_analysis_run_population",
    "get_population_snapshot",
    "get_analysis_run_population",
    "get_analysis_run_population_metadata",
    "get_research_run",
    "get_review_snapshot",
    "review_hash",
    "save_review_snapshot",
]
