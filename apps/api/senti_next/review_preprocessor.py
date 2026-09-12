"""Deterministic, reversible preprocessing for Steam review classification.

This module has no LLM, taxonomy, database, or UI dependencies.  It computes
shadowable transformations and current-run duplicate groups while retaining
the original review text and review identity.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

PREPROCESSOR_VERSION = "review_preprocess_v1"
VALID_MODES = frozenset({"off", "shadow", "active"})


def get_mode() -> str:
    """Return the configured mode, defaulting safely to off."""
    return _mode()

_DRAWING_CHARS = frozenset(
    "─━│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛"
    "├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻"
    "┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋█░▒▓▀▄▌▐▖▗▘▙▚▛▜▝▞▟"
    "⠁⠃⣿"
)
_ASCII_ART_CHARS = frozenset(r"/\|_-=*#@.:;+~")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _mode() -> str:
    value = os.getenv("SENTINEXT_REVIEW_PREPROCESS_MODE", "off").strip().lower()
    return value if value in VALID_MODES else "off"


def normalize_for_comparison(text: str) -> str:
    """Normalize text for hashes/comparison only; never for model display."""
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    value = re.sub(r"[ \t\f\v]+", " ", value)
    return value.casefold()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_emoji(char: str) -> bool:
    value = ord(char)
    return 0x1F000 <= value <= 0x1FAFF or 0x2600 <= value <= 0x27BF or value in {0xFE0F}


def _is_lexical(char: str) -> bool:
    return unicodedata.category(char).startswith(("L", "N"))


def _line_metrics(line: str) -> dict[str, float | int]:
    chars = list(line)
    length = max(len(chars), 1)
    lexical_count = sum(_is_lexical(char) for char in chars)
    symbol_count = sum(unicodedata.category(char).startswith("S") for char in chars)
    symbol_count += sum(char in _ASCII_ART_CHARS for char in chars)
    drawing_count = sum(char in _DRAWING_CHARS for char in chars)
    return {
        "line_length": len(chars),
        "lexical_count": lexical_count,
        "symbol_count": symbol_count,
        "drawing_char_count": drawing_count,
        "lexical_ratio": lexical_count / length,
        "symbol_ratio": symbol_count / length,
        "drawing_ratio": drawing_count / length,
    }


def detect_art_lines(text: str) -> list[int]:
    """Return 0-based high-confidence art-line indexes."""
    indexes: list[int] = []
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        metrics = _line_metrics(line)
        if (
            metrics["line_length"] >= 8
            and metrics["symbol_ratio"] >= 0.75
            and metrics["lexical_count"] <= 3
        ):
            indexes.append(index)
    return indexes


def detect_nonlexical(text: str) -> dict[str, Any]:
    """Classify non-lexical shape conservatively without semantic judgment."""
    value = str(text or "")
    chars = [char for char in value if not char.isspace()]
    lexical_count = sum(_is_lexical(char) for char in chars)
    if not chars:
        kind = "empty"
    elif lexical_count:
        kind = "low_lexical" if lexical_count <= 2 and lexical_count / len(chars) < 0.10 else "lexical"
    elif all(_is_emoji(char) for char in chars):
        kind = "emoji_only"
    elif all(char in _DRAWING_CHARS for char in chars):
        kind = "drawing_only"
    else:
        kind = "punctuation_or_symbol"
    return {
        "kind": kind,
        "lexical_count": lexical_count,
        "lexical_ratio": lexical_count / max(len(chars), 1),
        "char_count": len(value),
    }


def _deduplicate_lines(text: str) -> tuple[str, int, int]:
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    seen: set[str] = set()
    kept: list[str] = []
    removed = 0
    for raw_line in lines:
        comparison = normalize_for_comparison(raw_line)
        if not comparison:
            kept.append(raw_line)
        elif comparison in seen:
            removed += 1
        else:
            seen.add(comparison)
            kept.append(raw_line)
    processed = "\n".join(kept).strip()
    return processed, removed, max(0, len(str(text or "")) - len(processed))


def _deduplicate_paragraphs(text: str) -> tuple[str, int, int]:
    paragraphs = re.split(r"\n\s*\n+", str(text or "").replace("\r\n", "\n").replace("\r", "\n"))
    seen: set[str] = set()
    kept: list[str] = []
    removed = 0
    for paragraph in paragraphs:
        comparison = normalize_for_comparison(paragraph)
        if not comparison:
            continue
        if comparison in seen:
            removed += 1
            continue
        seen.add(comparison)
        kept.append(paragraph.strip())
    processed = "\n\n".join(kept).strip()
    return processed, removed, max(0, len(str(text or "")) - len(processed))


@dataclass(frozen=True)
class PreprocessResult:
    review_id: str
    app_id: int
    original_text: str
    processed_text: str
    original_char_count: int
    processed_char_count: int
    raw_normalized_hash: str
    processed_text_hash: str
    flags: frozenset[str] = field(default_factory=frozenset)
    skip_llm: bool = False
    skip_reason: str | None = None
    duplicate_group_key: tuple[int, str] | None = None
    removed_line_count: int = 0
    removed_paragraph_count: int = 0
    saved_char_count: int = 0
    art_line_count: int = 0
    lexical_count: int = 0


@dataclass
class PreprocessRun:
    results: dict[str, PreprocessResult]
    representatives: list[str]
    members_by_representative: dict[str, list[str]]
    metrics: dict[str, int | float]


class ReviewPreprocessor:
    """Deterministic review preprocessor with conservative defaults."""

    def __init__(
        self,
        *,
        mode: str | None = None,
        line_dedup: bool | None = None,
        paragraph_dedup: bool | None = None,
        art_removal: bool | None = None,
        nonlexical_skip: bool | None = None,
        exact_duplicate_reuse: bool | None = None,
    ) -> None:
        selected = (mode or _mode()).strip().lower()
        self.mode = selected if selected in VALID_MODES else "off"
        self.line_dedup = _env_bool("SENTINEXT_PREPROCESS_LINE_DEDUP", True) if line_dedup is None else line_dedup
        self.paragraph_dedup = _env_bool("SENTINEXT_PREPROCESS_PARAGRAPH_DEDUP", True) if paragraph_dedup is None else paragraph_dedup
        self.art_removal = _env_bool("SENTINEXT_PREPROCESS_ART_REMOVAL", False) if art_removal is None else art_removal
        self.nonlexical_skip = _env_bool("SENTINEXT_PREPROCESS_NONLEXICAL_SKIP", True) if nonlexical_skip is None else nonlexical_skip
        self.exact_duplicate_reuse = _env_bool("SENTINEXT_PREPROCESS_EXACT_DUP_REUSE", True) if exact_duplicate_reuse is None else exact_duplicate_reuse

    def process(self, app_id: int, review: Mapping[str, Any]) -> PreprocessResult:
        review_id = str(review.get("recommendationid") or review.get("review_id") or "")
        original = str(review.get("review") or review.get("review_text") or "")
        flags: set[str] = set()
        if not original.strip():
            flags.add("empty")
        if len(original) <= 30:
            flags.add("short_text")

        shape = detect_nonlexical(original)
        if shape["kind"] in {"punctuation_or_symbol", "emoji_only", "drawing_only"}:
            flags.add("pure_nonlexical")
        if shape["kind"] == "low_lexical":
            flags.add("low_lexical")

        art_indexes = detect_art_lines(original)
        if art_indexes:
            flags.add("ascii_art_candidate")

        processed = original
        removed_lines = 0
        removed_paragraphs = 0
        saved_chars = 0
        if self.mode != "off":
            if self.line_dedup:
                processed, removed_lines, saved = _deduplicate_lines(processed)
                saved_chars += saved
                if removed_lines:
                    flags.add("repeated_line_removed")
            if self.paragraph_dedup:
                processed, removed_paragraphs, saved = _deduplicate_paragraphs(processed)
                saved_chars += saved
                if removed_paragraphs:
                    flags.add("repeated_paragraph_removed")
            if self.art_removal and art_indexes:
                lines = processed.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                current_art_indexes = set(detect_art_lines(processed))
                remaining = [line for index, line in enumerate(lines) if index not in current_art_indexes]
                candidate = "\n".join(remaining).strip()
                if candidate != processed:
                    processed = candidate
                    flags.add("ascii_art_removed")
                    saved_chars += max(0, len(original) - len(processed)) - saved_chars
            if self.nonlexical_skip and shape["kind"] in {"punctuation_or_symbol", "emoji_only", "drawing_only"}:
                flags.add("nonlexical_skip_enabled")

        raw_hash = _hash(normalize_for_comparison(original))
        processed_hash = _hash(normalize_for_comparison(processed))
        key = (int(app_id), processed_hash)
        return PreprocessResult(
            review_id=review_id,
            app_id=int(app_id),
            original_text=original,
            processed_text=processed,
            original_char_count=len(original),
            processed_char_count=len(processed),
            raw_normalized_hash=raw_hash,
            processed_text_hash=processed_hash,
            flags=frozenset(flags),
            skip_llm=bool(self.nonlexical_skip and shape["kind"] in {"punctuation_or_symbol", "emoji_only", "drawing_only"}),
            skip_reason="pure_nonlexical" if self.nonlexical_skip and shape["kind"] in {"punctuation_or_symbol", "emoji_only", "drawing_only"} else None,
            duplicate_group_key=key,
            removed_line_count=removed_lines,
            removed_paragraph_count=removed_paragraphs,
            saved_char_count=saved_chars,
            art_line_count=len(art_indexes),
            lexical_count=int(shape["lexical_count"]),
        )

    def process_reviews(self, app_id: int, reviews: Sequence[Mapping[str, Any]]) -> PreprocessRun:
        results: dict[str, PreprocessResult] = {}
        groups: dict[tuple[int, str], list[str]] = defaultdict(list)
        original_chars = processed_chars = 0
        line_reviews = paragraph_reviews = art_reviews = mixed_art = nonlexical = short = 0
        for review in reviews:
            result = self.process(app_id, review)
            results[result.review_id] = result
            original_chars += result.original_char_count
            processed_chars += result.processed_char_count
            line_reviews += int("repeated_line_removed" in result.flags)
            paragraph_reviews += int("repeated_paragraph_removed" in result.flags)
            art_reviews += int("ascii_art_candidate" in result.flags)
            nonlexical += int("pure_nonlexical" in result.flags)
            short += int("short_text" in result.flags)
            if "ascii_art_candidate" in result.flags and result.lexical_count:
                mixed_art += 1
            if self.exact_duplicate_reuse and result.review_id and not result.skip_llm:
                groups[result.duplicate_group_key].append(result.review_id)
        members_by_rep = {members[0]: members for members in groups.values() if members}
        representatives = [member_ids[0] for member_ids in members_by_rep.values()]
        duplicate_groups = sum(len(members) >= 2 for members in members_by_rep.values())
        duplicate_members = sum(max(0, len(members) - 1) for members in members_by_rep.values())
        metrics: dict[str, int | float] = {
            "reviews_seen": len(reviews),
            "original_chars": original_chars,
            "processed_chars": processed_chars,
            "saved_chars": max(0, original_chars - processed_chars),
            "saved_char_pct": round(100 * max(0, original_chars - processed_chars) / max(original_chars, 1), 4),
            "line_dedup_reviews": line_reviews,
            "paragraph_dedup_reviews": paragraph_reviews,
            "art_candidate_reviews": art_reviews,
            "mixed_art_reviews": mixed_art,
            "pure_nonlexical_candidates": nonlexical,
            "exact_duplicate_groups": duplicate_groups,
            "exact_duplicate_members": duplicate_members,
            "potential_llm_inputs_saved": duplicate_members,
            "short_text_count": short,
        }
        return PreprocessRun(results, representatives, members_by_rep, metrics)


def preprocess_reviews_for_classification(
    app_id: int,
    reviews: Sequence[Mapping[str, Any]],
    *,
    mode: str | None = None,
) -> PreprocessRun:
    return ReviewPreprocessor(mode=mode).process_reviews(app_id, reviews)


def future_cache_key(
    app_id: int,
    processed_text_hash: str,
    *,
    prompt_version: str,
    taxonomy_version: str,
    model_id: str,
) -> tuple[str, int, str, str, str, str, str]:
    """Stable shape for a future persistent duplicate-classification store."""
    return (
        PREPROCESSOR_VERSION,
        int(app_id),
        processed_text_hash,
        prompt_version,
        taxonomy_version,
        model_id,
        "classification",
    )
