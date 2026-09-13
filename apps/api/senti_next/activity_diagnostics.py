"""Deterministic review-activity and coordinated-expression diagnostics.

This module is deliberately downstream of acquisition.  It annotates an
already acquired population; it never removes rows, changes recommendation
denominators, calls Steam, or invokes an LLM.  The signals are descriptive
and use the neutral term ``coordinated_expression``.  They are not evidence
of spam, bots, review bombing, or intent.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Any, Iterable, Mapping, Optional, Sequence
import unicodedata


# Keep every detection parameter in one JSON-serializable object.  These are
# heuristics, not confidence levels or statistical significance thresholds.
COORDINATION_SIMILARITY_CONFIG: dict[str, Any] = {
    "normalization_version": "unicode_nfkc_casefold_whitespace_v1",
    "similarity_method": "character_3gram_jaccard_with_64bit_simhash_lsh",
    "character_ngram_size": 3,
    "simhash_bits": 64,
    "simhash_bands": 4,
    "max_hamming_distance": 12,
    "min_character_ngram_jaccard": 0.78,
    "minimum_normalized_characters": 20,
    "max_lsh_bucket_size": 250,
    "baseline_window_bins": 7,
    "minimum_history_bins": 3,
    "spike_threshold": 3.5,
    "mad_scale": 1.4826,
    "mad_zero_absolute_increase": 3,
    "mad_zero_ratio": 2.0,
    "significant_expression_share_threshold": 0.10,
}

SPIKE_CONFIG = {
    key: COORDINATION_SIMILARITY_CONFIG[key]
    for key in (
        "baseline_window_bins",
        "minimum_history_bins",
        "spike_threshold",
        "mad_scale",
        "mad_zero_absolute_increase",
        "mad_zero_ratio",
    )
}

_WHITESPACE_RE = re.compile(r"\s+")
def normalize_review_text(text: Any) -> str:
    """Return the conservative text form used only for copy detection.

    NFKC handles compatible Unicode forms, ``casefold`` is multilingual-aware,
    and whitespace is collapsed.  Punctuation and CJK characters are retained
    so that the diagnostic does not erase meaning.
    """

    if text is None:
        return ""
    value = unicodedata.normalize("NFKC", str(text)).casefold()
    return _WHITESPACE_RE.sub(" ", value).strip()


def normalized_text_hash(text: Any) -> Optional[str]:
    """Return the stable hash of normalized text, or ``None`` when empty."""

    normalized = normalize_review_text(text)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _review_id(review: Mapping[str, Any], index: int) -> str:
    value = _first(review, "recommendationid", "review_id", "feedback_id")
    if value is None or str(value).strip() == "":
        # This is only a diagnostic identity for malformed/offline rows.  It
        # does not change raw population counts or claim a Steam ID exists.
        return f"row:{index}"
    return str(value)


def _text(review: Mapping[str, Any]) -> str:
    return str(_first(review, "review", "text", default="") or "")


def _author_id(review: Mapping[str, Any]) -> Optional[str]:
    author = review.get("author")
    if isinstance(author, Mapping):
        value = author.get("steamid")
    else:
        value = _first(review, "author_steamid", "author_id")
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def _language(review: Mapping[str, Any]) -> Optional[str]:
    value = review.get("language")
    return None if value is None or str(value).strip() == "" else str(value)


def _timestamp(review: Mapping[str, Any]) -> Optional[int]:
    value = _first(review, "timestamp_created", "created_at")
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp())
    if isinstance(value, str):
        try:
            value = value.strip()
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.astimezone(timezone.utc).timestamp())
        except ValueError:
            pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _voted_up(review: Mapping[str, Any]) -> Optional[bool]:
    value = _first(review, "voted_up", "recommendation", "reviewer_voted_up")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "recommended", "positive", "up"}:
            return True
        if normalized in {"false", "0", "no", "not recommended", "negative", "down"}:
            return False
    return None


def _char_ngrams(text: str, size: int) -> set[str]:
    if not text:
        return set()
    if len(text) <= size:
        return {text}
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def _simhash(shingles: Iterable[str], bits: int = 64) -> int:
    weights = [0] * bits
    for shingle in sorted(set(shingles)):
        digest = hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big", signed=False)
        for bit in range(bits):
            weights[bit] += 1 if value & (1 << bit) else -1
    result = 0
    for bit, weight in enumerate(weights):
        if weight >= 0:
            result |= 1 << bit
    return result


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return float(len(left & right) / len(union)) if union else 0.0


class _UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            parent = self.parent[value]
            self.parent[value] = root
            value = parent
        return root

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        # Lexical root choice makes components independent of input order.
        if root_right < root_left:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left


def _iso(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_and_concentration(timestamps: Sequence[int]) -> tuple[Optional[int], dict[str, float]]:
    if not timestamps:
        return None, {"share_within_1h": 0.0, "share_within_6h": 0.0, "share_within_24h": 0.0}
    values = sorted(int(item) for item in timestamps)
    duration = values[-1] - values[0]
    concentration: dict[str, float] = {}
    for label, seconds in (("1h", 3600), ("6h", 21600), ("24h", 86400)):
        right = 0
        best = 0
        for left, start in enumerate(values):
            while right < len(values) and values[right] - start <= seconds:
                right += 1
            best = max(best, right - left)
        concentration[f"share_within_{label}"] = float(best / len(values))
    return int(duration), concentration


def _cluster_id(cluster_type: str, review_ids: Sequence[str]) -> str:
    payload = "|".join(sorted(review_ids)).encode("utf-8")
    return f"{cluster_type}-{hashlib.sha256(payload).hexdigest()[:12]}"


def _cluster_report(
    cluster_type: str,
    review_ids: Sequence[str],
    rows_by_id: Mapping[str, Mapping[str, Any]],
    *,
    normalized_hashes: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    ids = sorted(set(review_ids))
    rows = [rows_by_id[item] for item in ids if item in rows_by_id]
    timestamps = [int(row["timestamp"]) for row in rows if row.get("timestamp") is not None]
    duration, concentration = _duration_and_concentration(timestamps)
    authors = {row["author"] for row in rows if row.get("author")}
    languages = sorted({row["language"] for row in rows if row.get("language")})
    language_counts = Counter(row["language"] for row in rows if row.get("language"))
    recommended = sum(row.get("voted_up") is True for row in rows)
    not_recommended = sum(row.get("voted_up") is False for row in rows)
    valid = recommended + not_recommended
    result: dict[str, Any] = {
        "cluster_id": _cluster_id(cluster_type, ids),
        "cluster_type": cluster_type,
        "review_count": len(ids),
        "unique_review_ids": ids,
        "representative_review_ids": ids[:5],
        "unique_author_count": len(authors),
        "missing_author_n": sum(row.get("author") is None for row in rows),
        "reviews_per_unique_author": float(len(ids) / len(authors)) if authors else None,
        "languages": languages,
        "language_counts": dict(sorted(language_counts.items())),
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "first_time": _iso(min(timestamps)) if timestamps else None,
        "last_time": _iso(max(timestamps)) if timestamps else None,
        "duration_seconds": duration,
        **concentration,
        "recommended_n": int(recommended),
        "not_recommended_n": int(not_recommended),
        "valid_outcome_n": int(valid),
        "recommendation_rate": float(recommended / valid) if valid else None,
    }
    if normalized_hashes is not None:
        result["normalized_text_hashes"] = sorted(set(normalized_hashes))
    return result


def _prepare_rows(reviews: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    prepared: list[dict[str, Any]] = []
    rows_by_id: dict[str, dict[str, Any]] = {}
    for index, review in enumerate(reviews):
        if not isinstance(review, Mapping):
            review = {}
        review_id = _review_id(review, index)
        text = _text(review)
        normalized = normalize_review_text(text)
        row = {
            "review_id": review_id,
            "raw_text": text,
            "normalized_text": normalized,
            "normalized_text_hash": normalized_text_hash(text),
            "timestamp": _timestamp(review),
            "author": _author_id(review),
            "language": _language(review),
            "voted_up": _voted_up(review),
        }
        prepared.append(row)
        # A Steam review ID is an event identity.  If malformed input repeats
        # one ID, use the first row for cluster annotations but retain all raw
        # rows in population metrics and bins.
        rows_by_id.setdefault(review_id, row)
    return prepared, rows_by_id


def _near_copy_clusters(
    rows_by_id: Mapping[str, Mapping[str, Any]],
    exact_ids: set[str],
    *,
    config: Mapping[str, Any],
) -> tuple[list[list[str]], dict[str, Any]]:
    minimum = int(config["minimum_normalized_characters"])
    ngram_size = int(config["character_ngram_size"])
    bits = int(config["simhash_bits"])
    bands = int(config["simhash_bands"])
    band_width = bits // bands
    eligible = {
        review_id: row
        for review_id, row in rows_by_id.items()
        if review_id not in exact_ids and len(row.get("normalized_text", "")) >= minimum
    }
    possible_pairs = len(eligible) * max(0, len(eligible) - 1) // 2
    shingles: dict[str, set[str]] = {}
    signatures: dict[str, int] = {}
    buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
    for review_id in sorted(eligible):
        current = _char_ngrams(eligible[review_id]["normalized_text"], ngram_size)
        shingles[review_id] = current
        signatures[review_id] = _simhash(current, bits)
        for band in range(bands):
            mask = (1 << band_width) - 1
            value = (signatures[review_id] >> (band * band_width)) & mask
            buckets[(band, value)].append(review_id)

    candidate_pairs: set[tuple[str, str]] = set()
    max_bucket = int(config["max_lsh_bucket_size"])
    oversized_bucket_count = 0
    oversized_bucket_members: set[str] = set()
    max_observed_bucket_size = 0
    for members in buckets.values():
        members = sorted(set(members))
        max_observed_bucket_size = max(max_observed_bucket_size, len(members))
        if len(members) > max_bucket:
            # Huge common-shingle buckets are not useful candidates and would
            # recreate an all-pairs comparison.  This is an auditable guard.
            oversized_bucket_count += 1
            oversized_bucket_members.update(members)
            continue
        for left_index, left in enumerate(members):
            for right in members[left_index + 1 :]:
                candidate_pairs.add((left, right))

    union_find = _UnionFind(eligible)
    accepted_pairs = 0
    for left, right in sorted(candidate_pairs):
        if _hamming_distance(signatures[left], signatures[right]) > int(config["max_hamming_distance"]):
            continue
        if _jaccard(shingles[left], shingles[right]) < float(config["min_character_ngram_jaccard"]):
            continue
        union_find.union(left, right)
        accepted_pairs += 1

    components: dict[str, list[str]] = defaultdict(list)
    for review_id in sorted(eligible):
        components[union_find.find(review_id)].append(review_id)
    result = [members for members in sorted(components.values()) if len(members) > 1]
    diagnostics = {
        "eligible_review_count": len(eligible),
        "candidate_pairs_examined": len(candidate_pairs),
        "accepted_near_copy_pairs": accepted_pairs,
        "possible_all_pairs": possible_pairs,
        "candidate_reduction_ratio": (
            float(1.0 - len(candidate_pairs) / possible_pairs) if possible_pairs else 1.0
        ),
        "oversized_bucket_count": oversized_bucket_count,
        "oversized_bucket_member_count": len(oversized_bucket_members),
        "max_observed_bucket_size": max_observed_bucket_size,
        "candidate_generation_complete": oversized_bucket_count == 0,
    }
    return result, diagnostics


def _bin_start(timestamp: int, grain: str) -> int:
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    if grain == "hour":
        dt = dt.replace(minute=0, second=0, microsecond=0)
    else:
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(dt.timestamp())


def _time_series(
    prepared: Sequence[Mapping[str, Any]],
    cluster_by_id: Mapping[str, str],
    *,
    grain: str,
    coordinated_ids: set[str],
    exact_ids: set[str],
) -> list[dict[str, Any]]:
    step = 3600 if grain == "hour" else 86400
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in prepared:
        timestamp = row.get("timestamp")
        if timestamp is not None:
            grouped[_bin_start(int(timestamp), grain)].append(row)
    if not grouped:
        return []
    first, last = min(grouped), max(grouped)
    bins: list[dict[str, Any]] = []
    for start in range(first, last + step, step):
        rows = grouped.get(start, [])
        recommended = sum(row.get("voted_up") is True for row in rows)
        not_recommended = sum(row.get("voted_up") is False for row in rows)
        valid = recommended + not_recommended
        coord_count = sum(row["review_id"] in coordinated_ids for row in rows)
        exact_count = sum(row["review_id"] in exact_ids for row in rows)
        cluster_counts = Counter(cluster_by_id.get(row["review_id"]) for row in rows if row["review_id"] in cluster_by_id)
        top_clusters = [cluster for cluster, _ in sorted(cluster_counts.items(), key=lambda item: (-item[1], item[0]))[:5]]
        bins.append(
            {
                "start_time": _iso(start),
                "end_time": _iso(start + step),
                "start_timestamp": start,
                "end_timestamp": start + step,
                "review_count": len(rows),
                "recommended_n": int(recommended),
                "not_recommended_n": int(not_recommended),
                "valid_outcome_n": int(valid),
                "recommended_share": float(recommended / valid) if valid else None,
                "exact_duplicate_reviews": int(exact_count),
                "coordinated_expression_reviews": int(coord_count),
                "coordinated_expression_share": float(coord_count / len(rows)) if rows else 0.0,
                "top_cluster_ids": top_clusters,
            }
        )
    return bins


def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _spike_bins(bins: Sequence[Mapping[str, Any]], *, config: Mapping[str, Any]) -> list[dict[str, Any]]:
    minimum_history = int(config["minimum_history_bins"])
    baseline_window = int(config["baseline_window_bins"])
    threshold = float(config["spike_threshold"])
    mad_scale = float(config["mad_scale"])
    result: list[dict[str, Any]] = []
    for index, current in enumerate(bins):
        history = bins[max(0, index - baseline_window) : index]
        if len(history) < minimum_history:
            continue
        values = [float(item["review_count"]) for item in history]
        median = _median(values)
        mad = _median([abs(value - median) for value in values])
        count = float(current["review_count"])
        if mad > 0:
            robust_score = (count - median) / (mad_scale * mad)
            is_spike = count > median and robust_score >= threshold
        else:
            increase = count - median
            ratio = count / median if median else (math.inf if count > 0 else 1.0)
            robust_score = increase / max(1.0, median)
            is_spike = increase >= float(config["mad_zero_absolute_increase"]) and ratio >= float(config["mad_zero_ratio"])
        if not is_spike:
            continue
        baseline_ratio = float(count / median) if median > 0 else None
        result.append(
            {
                "bin_start": current["start_time"],
                "bin_end": current["end_time"],
                "review_count": int(count),
                "baseline_median": float(median),
                "baseline_mad": float(mad),
                "robust_spike_score": float(robust_score),
                "review_count_ratio_to_baseline": baseline_ratio,
                "recommended_share": current["recommended_share"],
                "coordinated_expression_count": current["coordinated_expression_reviews"],
                "coordinated_expression_share": current["coordinated_expression_share"],
                "top_cluster_ids": list(current["top_cluster_ids"]),
            }
        )
    return result


def analyze_review_activity(
    reviews: Iterable[Mapping[str, Any]],
    *,
    grain: str = "day",
    config: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build a deterministic descriptive activity report for an acquired population.

    ``grain`` is ``day`` by default and may be ``hour``.  All timestamps are
    interpreted and emitted in UTC.  The input is materialized but never
    deduplicated or mutated.
    """

    if grain not in {"day", "hour"}:
        raise ValueError("grain must be 'day' or 'hour'")
    supplied = dict(config or {})
    effective_config = dict(COORDINATION_SIMILARITY_CONFIG)
    effective_config.update(supplied)
    materialized = [item for item in reviews]
    prepared, rows_by_id = _prepare_rows(materialized)

    by_hash: dict[str, list[str]] = defaultdict(list)
    for row in prepared:
        if row["normalized_text_hash"]:
            by_hash[row["normalized_text_hash"]].append(row["review_id"])
    exact_groups: list[list[str]] = []
    exact_ids: set[str] = set()
    for text_hash, ids in sorted(by_hash.items()):
        members = sorted(set(ids))
        if len(members) > 1:
            exact_groups.append(members)
            exact_ids.update(members)

    exact_clusters: list[dict[str, Any]] = []
    short_exact_ids: set[str] = set()
    informative_minimum = int(effective_config["minimum_normalized_characters"])
    for members in exact_groups:
        hashes = [rows_by_id[item].get("normalized_text_hash") for item in members]
        is_short = len(rows_by_id[members[0]].get("normalized_text", "")) < informative_minimum
        cluster_type = "exact_duplicate_short_text" if is_short else "exact"
        if is_short:
            short_exact_ids.update(members)
        exact_clusters.append(_cluster_report(cluster_type, members, rows_by_id, normalized_hashes=hashes))

    near_groups, candidate_diagnostics = _near_copy_clusters(rows_by_id, exact_ids, config=effective_config)
    near_clusters = [_cluster_report("near_copy", members, rows_by_id) for members in near_groups]
    significant_exact_ids = exact_ids - short_exact_ids
    near_ids = {member for group in near_groups for member in group}
    coordinated_ids = significant_exact_ids | near_ids
    cluster_by_id: dict[str, str] = {}
    all_clusters = exact_clusters + near_clusters
    for cluster in all_clusters:
        for review_id in cluster["unique_review_ids"]:
            cluster_by_id[review_id] = cluster["cluster_id"]

    exact_duplicate_count = len(exact_ids)
    near_additional_count = len(near_ids)
    raw_count = len(prepared)
    unique_ids = {row["review_id"] for row in prepared}
    normalized_values = {row["normalized_text_hash"] for row in prepared if row["normalized_text_hash"]}
    missing_text_n = sum(not row["raw_text"].strip() for row in prepared)
    missing_timestamp_n = sum(row["timestamp"] is None for row in prepared)
    valid_n = sum(row["voted_up"] is not None for row in prepared)
    recommended_n = sum(row["voted_up"] is True for row in prepared)
    not_recommended_n = sum(row["voted_up"] is False for row in prepared)

    bins = _time_series(
        prepared,
        cluster_by_id,
        grain=grain,
        coordinated_ids=coordinated_ids,
        exact_ids=exact_ids,
    )
    spikes = _spike_bins(bins, config=effective_config)
    largest_cluster = max((cluster["review_count"] for cluster in all_clusters if cluster["cluster_type"] != "exact_duplicate_short_text"), default=0)
    peak_bin = max(bins, key=lambda item: (item["coordinated_expression_share"], item["review_count"], item["start_time"]), default=None)
    coordinated_share = float(len(coordinated_ids) / raw_count) if raw_count else 0.0
    if not coordinated_ids:
        expression_level = "none"
    elif coordinated_share < 0.10:
        expression_level = "low"
    elif coordinated_share < 0.25:
        expression_level = "moderate"
    else:
        expression_level = "high"

    fingerprints = [
        {
            "review_id": row["review_id"],
            "raw_text": row["raw_text"],
            "normalized_text_hash": row["normalized_text_hash"],
            "raw_text_preserved": True,
        }
        for row in sorted(prepared, key=lambda item: item["review_id"])
    ]
    return {
        "schema_version": "2e.activity_diagnostics.v1",
        "population": {
            "raw_review_count": int(raw_count),
            "unique_review_id_count": int(len(unique_ids)),
            "missing_timestamp_n": int(missing_timestamp_n),
            "missing_text_n": int(missing_text_n),
            "missing_author_id_n": int(sum(row["author"] is None for row in prepared)),
            "valid_n": int(valid_n),
            "recommended_n": int(recommended_n),
            "not_recommended_n": int(not_recommended_n),
            "recommendation_rate": float(recommended_n / valid_n) if valid_n else None,
        },
        "text_repetition": {
            "unique_normalized_text_count": int(len(normalized_values)),
            "unique_text_share": float(len(normalized_values) / raw_count) if raw_count else 0.0,
            "exact_duplicate_review_count": int(exact_duplicate_count),
            "exact_duplicate_share": float(exact_duplicate_count / raw_count) if raw_count else 0.0,
            "near_copy_additional_review_count": int(near_additional_count),
            "near_copy_additional_share": float(near_additional_count / raw_count) if raw_count else 0.0,
            "coordinated_expression_review_count": int(len(coordinated_ids)),
            "coordinated_expression_share": coordinated_share,
            "short_text_exact_duplicate_review_count": int(len(short_exact_ids)),
            "review_text_fingerprints": fingerprints,
        },
        "time_series": {"grain": grain, "timezone": "UTC", "bins": bins},
        "spikes": {"spike_bin_count": len(spikes), "bins": spikes},
        "clusters": {
            "exact": exact_clusters,
            "near_copy": near_clusters,
            "all": sorted(all_clusters, key=lambda item: item["cluster_id"]),
        },
        "summary": {
            "activity_spike_detected": bool(spikes),
            "coordinated_expression_detected": bool(coordinated_ids),
            "coordinated_expression_level": expression_level,
            "largest_cluster_share": float(largest_cluster / raw_count) if raw_count else 0.0,
            "peak_bin_coordinated_share": peak_bin["coordinated_expression_share"] if peak_bin else 0.0,
            "spike_and_coordinated_expression": bool(spikes and coordinated_ids),
        },
        "methodology": {
            "normalization_version": effective_config["normalization_version"],
            "similarity_method": effective_config["similarity_method"],
            "thresholds": dict(effective_config),
            "candidate_diagnostics": candidate_diagnostics,
            "spike_formula": "(count - trailing_median) / (1.4826 * MAD) when MAD > 0; otherwise absolute-increase and ratio fallback",
            "raw_population_denominator": raw_count,
        },
        "limitations": {
            "coordinated_expression_is_not_proof_of_coordination": True,
            "duplicate_text_is_not_automatically_spam": True,
            "spike_is_not_automatically_review_bombing": True,
            "no_llm_or_live_steam_requests": True,
            "near_copy_detection_may_be_underestimated_due_to_oversized_lsh_buckets": (
                not candidate_diagnostics["candidate_generation_complete"]
            ),
        },
    }


# Descriptive aliases make the module easy to discover without introducing a
# second implementation.
build_activity_diagnostics = analyze_review_activity
review_activity_diagnostics = analyze_review_activity


__all__ = [
    "COORDINATION_SIMILARITY_CONFIG",
    "SPIKE_CONFIG",
    "analyze_review_activity",
    "build_activity_diagnostics",
    "normalize_review_text",
    "normalized_text_hash",
    "review_activity_diagnostics",
]
