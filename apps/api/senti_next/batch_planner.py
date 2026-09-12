"""Length-lane batch planning and response validation.

The planner is deliberately independent from providers, prompts, taxonomy,
storage, and the cost ledger.  It only receives the exact text selected for a
model call and produces deterministic plans.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence


# Current engineering safety budget for the review text sent in one dynamic
# batch. This is not a prompt-size, token, or model-context hard limit.
DEFAULT_MAX_TOTAL_CHARS = 32000


class BatchLane(str, Enum):
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"
    VERY_LONG = "VERY_LONG"


@dataclass(frozen=True)
class BatchPlannerConfig:
    short_max_chars: int = 80
    medium_max_chars: int = 300
    long_max_chars: int = 1200
    short_max_reviews: int = 100
    medium_max_reviews: int = 80
    long_max_reviews: int = 40
    very_long_max_reviews: int = 15
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS
    max_retry_attempts: int = 2
    min_split_size: int = 2

    @classmethod
    def from_env(cls) -> "BatchPlannerConfig":
        def integer(name: str, default: int) -> int:
            try:
                return max(1, int(os.getenv(name, str(default))))
            except (TypeError, ValueError):
                return default

        return cls(
            short_max_chars=integer("SENTINEXT_BATCH_SHORT_MAX_CHARS", 80),
            medium_max_chars=integer("SENTINEXT_BATCH_MEDIUM_MAX_CHARS", 300),
            long_max_chars=integer("SENTINEXT_BATCH_LONG_MAX_CHARS", 1200),
            short_max_reviews=integer("SENTINEXT_BATCH_SHORT_MAX_REVIEWS", 100),
            medium_max_reviews=integer("SENTINEXT_BATCH_MEDIUM_MAX_REVIEWS", 80),
            long_max_reviews=integer("SENTINEXT_BATCH_LONG_MAX_REVIEWS", 40),
            very_long_max_reviews=integer("SENTINEXT_BATCH_VERY_LONG_MAX_REVIEWS", 15),
            max_total_chars=integer("SENTINEXT_BATCH_MAX_TOTAL_CHARS", DEFAULT_MAX_TOTAL_CHARS),
            max_retry_attempts=integer("SENTINEXT_BATCH_MAX_RETRY_ATTEMPTS", 2),
            min_split_size=integer("SENTINEXT_BATCH_MIN_SPLIT_SIZE", 2),
        )

    def max_reviews_for(self, lane: BatchLane) -> int:
        return {
            BatchLane.SHORT: self.short_max_reviews,
            BatchLane.MEDIUM: self.medium_max_reviews,
            BatchLane.LONG: self.long_max_reviews,
            BatchLane.VERY_LONG: self.very_long_max_reviews,
        }[lane]


def lane_for_length(length: int, config: BatchPlannerConfig | None = None) -> BatchLane:
    config = config or BatchPlannerConfig.from_env()
    if length <= config.short_max_chars:
        return BatchLane.SHORT
    if length <= config.medium_max_chars:
        return BatchLane.MEDIUM
    if length <= config.long_max_chars:
        return BatchLane.LONG
    return BatchLane.VERY_LONG


@dataclass(frozen=True)
class PlannedBatch:
    batch_id: str
    lane: BatchLane
    review_ids: tuple[str, ...]
    items: tuple[Mapping[str, Any], ...]
    review_count: int
    total_processed_chars: int
    avg_processed_chars: float
    max_processed_chars: int
    min_processed_chars: int
    attempt_number: int = 0
    is_retry: bool = False
    split_depth: int = 0


class DynamicBatchPlanner:
    def __init__(self, config: BatchPlannerConfig | None = None) -> None:
        self.config = config or BatchPlannerConfig.from_env()

    def plan(
        self,
        items: Sequence[Mapping[str, Any]],
        *,
        batch_id_prefix: str = "batch",
        attempt_number: int = 0,
        is_retry: bool = False,
        split_depth: int = 0,
    ) -> list[PlannedBatch]:
        lanes: dict[BatchLane, list[Mapping[str, Any]]] = {lane: [] for lane in BatchLane}
        for item in items:
            text = str(item.get("review_text_for_model", item.get("review_text", "")) or "")
            lanes[lane_for_length(len(text), self.config)].append(item)

        planned: list[PlannedBatch] = []
        index = 0
        for lane in BatchLane:
            current: list[Mapping[str, Any]] = []
            current_chars = 0
            max_reviews = self.config.max_reviews_for(lane)
            for item in lanes[lane]:
                text = str(item.get("review_text_for_model", item.get("review_text", "")) or "")
                size = len(text)
                would_overflow = current and current_chars + size > self.config.max_total_chars
                would_hit_count = current and len(current) >= max_reviews
                if would_overflow or would_hit_count:
                    planned.append(self._batch(current, lane, f"{batch_id_prefix}-{index}", attempt_number, is_retry, split_depth))
                    index += 1
                    current = []
                    current_chars = 0
                current.append(item)
                current_chars += size
                # An individual oversized review cannot be split without
                # changing text; keep it isolated and observable.
                if size > self.config.max_total_chars:
                    planned.append(self._batch(current, lane, f"{batch_id_prefix}-{index}", attempt_number, is_retry, split_depth))
                    index += 1
                    current = []
                    current_chars = 0
            if current:
                planned.append(self._batch(current, lane, f"{batch_id_prefix}-{index}", attempt_number, is_retry, split_depth))
                index += 1
        return planned

    @staticmethod
    def _batch(items, lane, batch_id, attempt_number, is_retry, split_depth):
        sizes = [len(str(item.get("review_text_for_model", item.get("review_text", "")) or "")) for item in items]
        return PlannedBatch(
            batch_id=batch_id,
            lane=lane,
            review_ids=tuple(str(item.get("review_id") or "") for item in items),
            items=tuple(items),
            review_count=len(items),
            total_processed_chars=sum(sizes),
            avg_processed_chars=round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
            max_processed_chars=max(sizes, default=0),
            min_processed_chars=min(sizes, default=0),
            attempt_number=attempt_number,
            is_retry=is_retry,
            split_depth=split_depth,
        )

    def metrics(self, batches: Sequence[PlannedBatch]) -> dict[str, int | float]:
        counts = {lane.value.lower() + "_batch_count": sum(batch.lane is lane for batch in batches) for lane in BatchLane}
        return {
            "planned_batch_count": len(batches),
            "planned_reviews": sum(batch.review_count for batch in batches),
            "avg_reviews_per_batch": round(sum(batch.review_count for batch in batches) / len(batches), 2) if batches else 0.0,
            "avg_chars_per_batch": round(sum(batch.total_processed_chars for batch in batches) / len(batches), 2) if batches else 0.0,
            **counts,
        }


@dataclass(frozen=True)
class BatchValidationResult:
    valid_results: dict[str, dict[str, Any]]
    invalid_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    duplicate_return_ids: tuple[str, ...]
    unexpected_ids: tuple[str, ...]
    retry_ids: tuple[str, ...]
    validation_error_counts: dict[str, int] = field(default_factory=dict)


def validate_batch_results(
    expected_ids: Sequence[str],
    returned: Mapping[str, Any] | Sequence[tuple[str, Any]],
    *,
    parse_result: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
) -> BatchValidationResult:
    expected = [str(value) for value in expected_ids]
    expected_set = set(expected)
    pairs = list(returned.items()) if isinstance(returned, Mapping) else list(returned)
    seen: set[str] = set()
    valid: dict[str, dict[str, Any]] = {}
    invalid: list[str] = []
    duplicate: list[str] = []
    unexpected: list[str] = []
    errors: dict[str, int] = {}
    for raw_id, raw_value in pairs:
        review_id = str(raw_id)
        if review_id in seen:
            duplicate.append(review_id)
            continue
        seen.add(review_id)
        if review_id not in expected_set:
            unexpected.append(review_id)
            continue
        if not isinstance(raw_value, Mapping):
            invalid.append(review_id)
            errors["not_mapping"] = errors.get("not_mapping", 0) + 1
            continue
        try:
            valid[review_id] = parse_result(raw_value) if parse_result else dict(raw_value)
        except Exception:
            invalid.append(review_id)
            errors["parse_error"] = errors.get("parse_error", 0) + 1
    missing = [review_id for review_id in expected if review_id not in seen]
    retry = list(dict.fromkeys(invalid + missing + duplicate))
    return BatchValidationResult(
        valid_results=valid,
        invalid_ids=tuple(invalid),
        missing_ids=tuple(missing),
        duplicate_return_ids=tuple(duplicate),
        unexpected_ids=tuple(unexpected),
        retry_ids=tuple(retry),
        validation_error_counts=errors,
    )


def classify_provider_error(error: BaseException) -> str:
    code = str(getattr(error, "code", "") or "").upper()
    if code in {"OUTPUT_TRUNCATED", "TRUNCATED"}:
        return "OUTPUT_TRUNCATED"
    if code in {"AUTHENTICATION", "AUTH", "CONFIGURATION"}:
        return "AUTH_ERROR"
    if code in {"RATE_LIMIT", "429"}:
        return "RATE_LIMIT"
    if code in {"PROVIDER_SERVER", "SERVER", "5XX"}:
        return "PROVIDER_SERVER_ERROR"
    if code in {"TIMEOUT", "TIMED_OUT"}:
        return "TIMEOUT"
    if code in {"NETWORK", "CONNECTION"}:
        return "NETWORK_ERROR"
    return "UNKNOWN"


def batch_telemetry(batch: PlannedBatch, *, valid_count=0, invalid_count=0, missing_count=0, success=False, error_type="NONE", latency_ms=0.0) -> dict[str, Any]:
    max_total_chars = BatchPlannerConfig.from_env().max_total_chars
    return {
        "batch_id": batch.batch_id,
        "lane": batch.lane.value,
        "review_count": batch.review_count,
        "total_processed_chars": batch.total_processed_chars,
        "avg_processed_chars": batch.avg_processed_chars,
        "max_processed_chars": batch.max_processed_chars,
        "attempt_number": batch.attempt_number,
        "is_retry": batch.is_retry,
        "split_depth": batch.split_depth,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "missing_count": missing_count,
        "success": success,
        "error_type": error_type,
        "latency_ms": round(float(latency_ms), 3),
        "max_total_chars": max_total_chars,
        "char_fill_ratio": round(batch.total_processed_chars / max_total_chars, 4) if max_total_chars else 0.0,
        "oversized_input": batch.max_processed_chars > max_total_chars,
    }
