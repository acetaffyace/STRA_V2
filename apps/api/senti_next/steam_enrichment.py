"""Steam review enrichment contract.

This module is intentionally informational.  Its values must not be used by
analysis, scoring, evidence selection, or model evaluation in v1.
"""
from __future__ import annotations

from typing import Any, Mapping

ENRICHMENT_SCHEMA_VERSION = "steam-review-enrichment-v1"
ENRICHMENT_SOURCE = "steam_review_api"
RAW_BACKFILL_SOURCE = "stored_raw_payload_backfill"

SOURCE_FIELDS = (
    "developer_response",
    "timestamp_dev_responded",
    "steam_purchase",
    "received_for_free",
    "primarily_steam_deck",
)


def optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    return None


def optional_timestamp(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def canonical_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "developer_response": payload.get("developer_response"),
        "timestamp_dev_responded": optional_timestamp(payload.get("timestamp_dev_responded")),
        "steam_purchase": optional_bool(payload.get("steam_purchase")),
        "received_for_free": optional_bool(payload.get("received_for_free")),
        "primarily_steam_deck": optional_bool(payload.get("primarily_steam_deck")),
    }


def purchase_source(value: Any) -> str:
    parsed = optional_bool(value)
    return "steam_purchase" if parsed is True else "non_steam_purchase" if parsed is False else "unknown"


def acquisition(value: Any) -> str:
    parsed = optional_bool(value)
    return "received_for_free" if parsed is True else "paid_or_not_marked_free" if parsed is False else "unknown"


def device_context(value: Any) -> str:
    parsed = optional_bool(value)
    return "primarily_deck" if parsed is True else "other_or_not_primarily_deck" if parsed is False else "unknown"


def public_context(fields: Mapping[str, Any]) -> dict[str, Any]:
    steam_purchase = fields.get("steam_purchase")
    received_for_free = fields.get("received_for_free")
    primarily_steam_deck = fields.get("primarily_steam_deck")
    response = fields.get("developer_response")
    timestamp = fields.get("timestamp_dev_responded")
    return {
        "steam_context": {
            "steam_purchase": steam_purchase,
            "received_for_free": received_for_free,
            "primarily_steam_deck": primarily_steam_deck,
            "purchase_source": purchase_source(steam_purchase),
            "acquisition": acquisition(received_for_free),
            "device_context": device_context(primarily_steam_deck),
        },
        "developer_response": {
            "text": response,
            "responded_at": timestamp,
            "present": response is not None and response != "",
        },
        "provenance": {
            "enrichment_source": ENRICHMENT_SOURCE,
            "enrichment_schema_version": ENRICHMENT_SCHEMA_VERSION,
        },
    }
