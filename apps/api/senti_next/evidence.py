"""Deterministic direct-quote verification and evidence metadata.

Evidence verification is deliberately local and conservative.  A normalized
match may locate a source span, but the returned/displayed quote is always the
exact slice from the source text.
"""
from __future__ import annotations

from hashlib import sha256
import re
import unicodedata
from typing import Any, Iterable, Mapping


def source_review_hash(source_text: str) -> str:
    return sha256(str(source_text).encode("utf-8")).hexdigest()


def _normalized_with_map(value: str) -> tuple[str, list[tuple[int, int]]]:
    normalized: list[str] = []
    mapping: list[tuple[int, int]] = []
    for index, char in enumerate(str(value)):
        piece = unicodedata.normalize("NFKC", char)
        if piece.isspace():
            piece = " "
        for output_char in piece:
            normalized.append(output_char)
            mapping.append((index, index + 1))

    collapsed: list[str] = []
    collapsed_map: list[tuple[int, int]] = []
    for char, span in zip(normalized, mapping):
        if char == " " and collapsed and collapsed[-1] == " ":
            collapsed_map[-1] = (collapsed_map[-1][0], span[1])
            continue
        collapsed.append(char)
        collapsed_map.append(span)
    return "".join(collapsed), collapsed_map


def _find_source_slice(source_text: str, quote: str) -> tuple[str, int, int, str] | None:
    source = str(source_text or "")
    candidate = str(quote or "")
    if not source or not candidate:
        return None
    exact_start = source.find(candidate)
    if exact_start >= 0:
        return candidate, exact_start, exact_start + len(candidate), "exact_substring"

    normalized_source, source_map = _normalized_with_map(source)
    normalized_quote, _ = _normalized_with_map(candidate)
    if not normalized_quote:
        return None
    normalized_start = normalized_source.find(normalized_quote)
    if normalized_start < 0 or normalized_start >= len(source_map):
        return None
    normalized_end = normalized_start + len(normalized_quote) - 1
    if normalized_end >= len(source_map):
        return None
    start = source_map[normalized_start][0]
    end = source_map[normalized_end][1]
    return source[start:end], start, end, "normalized_source_slice"


def verify_evidence(
    source_text: str | None,
    quote: str | None,
    *,
    review_id: str | None = None,
    source_review_id: str | None = None,
    app_id: int | None = None,
    source_app_id: int | None = None,
    run_id: str | None = None,
    source_run_id: str | None = None,
    allowed_review_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return structured, blocking verification metadata for one quote."""
    result: dict[str, Any] = {
        "verification_status": "rejected",
        "verification_method": "none",
        "quote": None,
        "quote_start": None,
        "quote_end": None,
        "source_review_hash": source_review_hash(source_text or "") if source_text is not None else None,
        "review_id": str(review_id) if review_id is not None else None,
        "run_id": run_id,
    }
    if not source_text or not quote:
        result["unavailable_reason"] = "missing_source_or_quote"
        return result
    if source_review_id is not None and review_id is not None and str(source_review_id) != str(review_id):
        result["unavailable_reason"] = "review_id_mismatch"
        return result
    if source_app_id is not None and app_id is not None and int(source_app_id) != int(app_id):
        result["unavailable_reason"] = "app_id_mismatch"
        return result
    if source_run_id is not None and run_id is not None and str(source_run_id) != str(run_id):
        result["unavailable_reason"] = "run_id_mismatch"
        return result
    if allowed_review_ids is not None and review_id is not None and str(review_id) not in {str(item) for item in allowed_review_ids}:
        result["unavailable_reason"] = "review_outside_run_scope"
        return result

    located = _find_source_slice(str(source_text), str(quote))
    if located is None:
        result["unavailable_reason"] = "quote_not_in_source"
        return result
    source_slice, start, end, method = located
    result.update({
        "verification_status": "verified",
        "verification_method": method,
        "quote": source_slice,
        "quote_start": start,
        "quote_end": end,
    })
    return result


def verify_quote(quote: str, source_text: str) -> bool:
    """Compatibility boolean used by the P0 contract and callers."""
    return verify_evidence(source_text, quote)["verification_status"] == "verified"


def build_evidence(
    source_text: str | None,
    quote: str | None,
    *,
    review_id: str | None = None,
    app_id: int | None = None,
    run_id: str | None = None,
    source_run_id: str | None = None,
    allowed_review_ids: Iterable[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result = verify_evidence(
        source_text,
        quote,
        review_id=review_id,
        source_review_id=review_id,
        app_id=app_id,
        source_app_id=app_id,
        run_id=run_id,
        source_run_id=source_run_id,
        allowed_review_ids=allowed_review_ids,
    )
    if result["verification_status"] == "verified":
        result["source_review_text"] = str(source_text)
    result.update(extra)
    return result


_QUOTE_PATTERN = re.compile(r'"([^"\n]{1,500})"')


def gate_response_quotes(response: str, sources: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Block invalid direct quotes and return trusted evidence records."""
    source_items = list(sources)
    evidence: list[dict[str, Any]] = []
    invalid: list[str] = []

    def replace(match: re.Match[str]) -> str:
        candidate = match.group(1)
        for source in source_items:
            verified = verify_evidence(
                source.get("text") or source.get("review") or "",
                candidate,
                review_id=source.get("review_id"),
                source_review_id=source.get("review_id"),
                app_id=source.get("app_id"),
                source_app_id=source.get("app_id"),
                run_id=source.get("run_id"),
                source_run_id=source.get("run_id"),
                allowed_review_ids=source.get("allowed_review_ids"),
            )
            if verified["verification_status"] == "verified":
                verified.update({"app_id": source.get("app_id"), "source_review_text": source.get("text") or source.get("review")})
                evidence.append(verified)
                return f'"{verified["quote"]}"'
        invalid.append(candidate)
        return "[unverified direct quote removed]"

    raw_response = str(response or "")
    fenced_blocks: list[str] = []

    def protect(match: re.Match[str]) -> str:
        fenced_blocks.append(match.group(0))
        return f"\u0000CODE_BLOCK_{len(fenced_blocks) - 1}\u0000"

    gated = _QUOTE_PATTERN.sub(replace, re.sub(r"```[\s\S]*?```", protect, raw_response))
    for index, block in enumerate(fenced_blocks):
        gated = gated.replace(f"\u0000CODE_BLOCK_{index}\u0000", block)
    return {"response": gated, "evidence": evidence, "rejected_quotes": invalid}
