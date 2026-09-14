"""安全、结构化的 Semantic V2 adjudication boundary."""
from __future__ import annotations

import json
import math
from typing import Any, Mapping

ADJUDICATION_SCHEMA_VERSION = "semantic-adjudication-v1"
_ALLOWED_FIELDS = {
    "core_topic_id", "secondary_topic_id", "signal_type", "assignment_source",
    "similarity_score", "calibrated_confidence", "decision_band", "prototype_version", "adjudication_ref",
}
_SIGNALS = {"issue", "request", "praise"}
_BANDS = {"HIGH", "MEDIUM", "LOW"}


def wrap_untrusted_review(text: str) -> str:
    """Encode review text as data for an adjudicator; never as instructions."""
    value = str(text or "")
    return json.dumps({"review_text": value}, ensure_ascii=False, separators=(",", ":"))


def validate_adjudication_output(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a structured decision before it can create a SemanticMention."""
    if not isinstance(value, Mapping):
        raise ValueError("adjudication_output_not_object")
    unknown = set(value) - _ALLOWED_FIELDS
    if unknown:
        raise ValueError("adjudication_output_unknown_field")
    core = str(value.get("core_topic_id") or "").strip()
    secondary = value.get("secondary_topic_id")
    if secondary is not None and not str(secondary).strip():
        secondary = None
    signal = value.get("signal_type")
    if signal is not None and signal not in _SIGNALS:
        raise ValueError("adjudication_signal_invalid")
    band = str(value.get("decision_band") or "").upper()
    if band not in _BANDS:
        raise ValueError("adjudication_decision_band_invalid")
    source = str(value.get("assignment_source") or "llm_adjudication").strip()
    prototype = str(value.get("prototype_version") or "").strip()
    if not source or not prototype:
        raise ValueError("adjudication_provenance_incomplete")
    result: dict[str, Any] = {
        "core_topic_id": core or None,
        "secondary_topic_id": str(secondary).strip() if secondary is not None else None,
        "signal_type": signal,
        "assignment_source": source,
        "decision_band": band,
        "prototype_version": prototype,
        "adjudication_ref": value.get("adjudication_ref"),
    }
    for field in ("similarity_score", "calibrated_confidence"):
        raw = value.get(field)
        if raw is None:
            result[field] = None
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"adjudication_{field}_invalid") from exc
        if not math.isfinite(number) or (field == "calibrated_confidence" and not 0 <= number <= 1):
            raise ValueError(f"adjudication_{field}_invalid")
        result[field] = number
    result["semantic_adjudication_schema_version"] = ADJUDICATION_SCHEMA_VERSION
    return result


__all__ = ["ADJUDICATION_SCHEMA_VERSION", "validate_adjudication_output", "wrap_untrusted_review"]
