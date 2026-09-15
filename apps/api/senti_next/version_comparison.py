"""Four-cohort deterministic version comparison primitives.

Acquisition and semantic sampling are intentionally separate. Raw metrics use
all acquired reviews. Semantic classification uses a reproducible manifest
balanced only on language and relative lifecycle day; recommendation outcome is
never a balancing variable.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from math import floor, sqrt
from statistics import NormalDist
from typing import Any, Iterable, Mapping, Sequence

from .population_validity import compare_populations
from .sampling import SamplingContract
from .standardization import standardize_populations

COHORTS = ("A_PRE", "A_POST", "B_PRE", "B_POST")
SENSITIVITY_WINDOWS = (3, 7, 14)
DAY_SECONDS = 86_400
SEMANTIC_SAMPLING_METHOD = "pooled_common_support_language_relative_day_v1"


def _utc_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.replace(".", "", 1).isdigit():
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        try:
            parsed_date = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)


def _date_only_anchor(event: Mapping[str, Any]) -> bool:
    precision = str(event.get("anchor_precision") or "").lower()
    effective = event.get("effective_at")
    if precision in {"minute", "hour", "second", "timestamp", "exact"} and effective:
        return False
    if precision in {"day", "date", "range", "unresolved"}:
        return True
    raw = effective or event.get("event_date")
    return not (isinstance(raw, str) and "T" in raw)


def event_anchor(event: Mapping[str, Any]) -> dict[str, Any]:
    anchor = _utc_datetime(event.get("effective_at") or event.get("event_date"))
    if anchor is None:
        raise ValueError("version event requires a valid effective_at or event_date")
    date_only = _date_only_anchor(event)
    if date_only:
        anchor = datetime.combine(anchor.date(), time.min, tzinfo=timezone.utc)
    return {"timestamp": anchor, "date_only": date_only, "precision": "day" if date_only else "timestamp"}


def chronological_events(event_a: Mapping[str, Any], event_b: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    a, b = dict(event_a), dict(event_b)
    return (a, b) if event_anchor(a)["timestamp"] <= event_anchor(b)["timestamp"] else (b, a)


def _window_bounds(event: Mapping[str, Any], side: str, window_days: int) -> tuple[datetime, datetime, str]:
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    anchor = event_anchor(event)
    point = anchor["timestamp"]
    if anchor["date_only"]:
        if side == "pre":
            return point - timedelta(days=window_days), point, "event_day_excluded"
        if side == "post":
            start = point + timedelta(days=1)
            return start, start + timedelta(days=window_days), "event_day_excluded"
    else:
        if side == "pre":
            return point - timedelta(days=window_days), point, "exact_timestamp"
        if side == "post":
            return point, point + timedelta(days=window_days), "exact_timestamp"
    raise ValueError("side must be 'pre' or 'post'")


def cohort_windows(event_a: Mapping[str, Any], event_b: Mapping[str, Any], window_days: int) -> dict[str, dict[str, Any]]:
    older, newer = chronological_events(event_a, event_b)
    output: dict[str, dict[str, Any]] = {}
    for label, event, side in (("A_PRE", older, "pre"), ("A_POST", older, "post"), ("B_PRE", newer, "pre"), ("B_POST", newer, "post")):
        start, end, boundary_mode = _window_bounds(event, side, window_days)
        output[label] = {
            "cohort": label,
            "event_id": event.get("event_id"),
            "event_name": event.get("event_name") or event.get("title"),
            "side": side,
            "start_time": int(start.timestamp()),
            "end_time_exclusive": int(end.timestamp()),
            "window_days": window_days,
            "boundary_mode": boundary_mode,
        }
    return output


def build_sampling_contracts(app_id: int, event_a: Mapping[str, Any], event_b: Mapping[str, Any], *, window_days: int = 14, languages: Sequence[str] = ("all",), max_reviews_per_cohort: int = 10_000) -> dict[str, SamplingContract]:
    windows = cohort_windows(event_a, event_b, window_days)
    return {
        cohort: SamplingContract(
            app_id=app_id,
            start_time=window["start_time"],
            end_time=window["end_time_exclusive"] - 1,
            languages=list(languages) or ["all"],
            review_type="all",
            purchase_type="all",
            collection_order="recent",
            include_offtopic_activity=False,
            max_reviews=max_reviews_per_cohort,
        )
        for cohort, window in windows.items()
    }


def slice_cohort(reviews: Iterable[Mapping[str, Any]], event: Mapping[str, Any], side: str, window_days: int) -> list[dict[str, Any]]:
    start, end, _ = _window_bounds(event, side, window_days)
    start_ts, end_ts = start.timestamp(), end.timestamp()
    return [dict(row) for row in reviews if (created := _utc_datetime(row.get("timestamp_created"))) is not None and start_ts <= created.timestamp() < end_ts]


def primary_cohorts(acquired: Mapping[str, Sequence[Mapping[str, Any]]], event_a: Mapping[str, Any], event_b: Mapping[str, Any], window_days: int) -> dict[str, list[dict[str, Any]]]:
    older, newer = chronological_events(event_a, event_b)
    return {
        "A_PRE": slice_cohort(acquired.get("A_PRE", []), older, "pre", window_days),
        "A_POST": slice_cohort(acquired.get("A_POST", []), older, "post", window_days),
        "B_PRE": slice_cohort(acquired.get("B_PRE", []), newer, "pre", window_days),
        "B_POST": slice_cohort(acquired.get("B_POST", []), newer, "post", window_days),
    }


def _review_id(review: Mapping[str, Any]) -> str:
    return str(review.get("recommendationid") or review.get("review_id") or "")


def _language(review: Mapping[str, Any]) -> str:
    return str(review.get("language") or "unknown").strip().lower() or "unknown"


def _relative_day(review: Mapping[str, Any], event: Mapping[str, Any], side: str) -> int | None:
    created = _utc_datetime(review.get("timestamp_created"))
    if created is None:
        return None
    anchor = event_anchor(event)
    point = anchor["timestamp"]
    if anchor["date_only"]:
        distance = (point.date() - created.date()).days if side == "pre" else (created.date() - point.date()).days
        return distance if distance >= 1 else None
    seconds = (point - created).total_seconds() if side == "pre" else (created - point).total_seconds()
    return int(floor(seconds / DAY_SECONDS)) + 1 if seconds >= 0 else None


def _relative_day_bucket(day: int | None) -> str:
    if day is None or day <= 0: return "unknown"
    if day == 1: return "D1"
    if day == 2: return "D2"
    if day <= 4: return "D3-4"
    if day <= 7: return "D5-7"
    if day <= 14: return "D8-14"
    return "D15+"


def _cohort_event_side(cohort: str, event_a: Mapping[str, Any], event_b: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    older, newer = chronological_events(event_a, event_b)
    return {"A_PRE": (older, "pre"), "A_POST": (older, "post"), "B_PRE": (newer, "pre"), "B_POST": (newer, "post")}[cohort]


def _stratum(review: Mapping[str, Any], event: Mapping[str, Any], side: str) -> str:
    return f"language={_language(review)}|relative_day={_relative_day_bucket(_relative_day(review, event, side))}"


def _allocate_quotas(total: int, weights: Mapping[str, int], capacities: Mapping[str, int]) -> dict[str, int]:
    if total <= 0 or not weights:
        return {key: 0 for key in weights}
    keys = sorted(weights)
    weight_sum = sum(max(0, int(weights[key])) for key in keys)
    if weight_sum <= 0:
        return {key: 0 for key in keys}
    exact = {key: total * max(0, int(weights[key])) / weight_sum for key in keys}
    quotas = {key: min(int(capacities.get(key, 0)), int(floor(exact[key]))) for key in keys}
    remaining = total - sum(quotas.values())
    while remaining > 0:
        candidates = [key for key in keys if quotas[key] < int(capacities.get(key, 0))]
        if not candidates:
            break
        candidates.sort(key=lambda key: (exact[key] - floor(exact[key]), weights[key], key), reverse=True)
        progressed = False
        for key in candidates:
            if remaining <= 0: break
            if quotas[key] < int(capacities.get(key, 0)):
                quotas[key] += 1
                remaining -= 1
                progressed = True
        if not progressed: break
    return quotas


def build_semantic_sample_manifest(cohorts: Mapping[str, Sequence[Mapping[str, Any]]], event_a: Mapping[str, Any], event_b: Mapping[str, Any], *, total_budget: int = 4_000, seed: str = "version-comparison-v1") -> dict[str, Any]:
    """Build equal-size samples with identical language × relative-day quotas."""
    buckets_by_cohort: dict[str, dict[str, list[dict[str, Any]]]] = {}
    counts: dict[str, Counter[str]] = {}
    for cohort in COHORTS:
        event, side = _cohort_event_side(cohort, event_a, event_b)
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in cohorts.get(cohort, []):
            item = dict(row)
            buckets[_stratum(item, event, side)].append(item)
        buckets_by_cohort[cohort] = buckets
        counts[cohort] = Counter({key: len(rows) for key, rows in buckets.items()})
    common = set(counts[COHORTS[0]])
    for cohort in COHORTS[1:]:
        common &= set(counts[cohort])
    common = {key for key in common if "relative_day=unknown" not in key}
    capacities = {key: min(counts[cohort][key] for cohort in COHORTS) for key in sorted(common)}
    pooled = {key: sum(counts[cohort][key] for cohort in COHORTS) for key in sorted(common)}
    target_per_cohort = min(max(0, total_budget // 4), sum(capacities.values()))
    quotas = _allocate_quotas(target_per_cohort, pooled, capacities)
    selected_ids: dict[str, list[str]] = {cohort: [] for cohort in COHORTS}
    entries: list[dict[str, Any]] = []
    for cohort in COHORTS:
        for stratum, quota in sorted(quotas.items()):
            available = buckets_by_cohort[cohort][stratum]
            if quota <= 0: continue
            ranked = sorted(available, key=lambda row: sha256(f"{seed}|{stratum}|{_review_id(row)}".encode()).hexdigest())
            probability = quota / len(available) if available else 0.0
            for row in ranked[:quota]:
                rid = _review_id(row)
                if rid: selected_ids[cohort].append(rid)
                entries.append({
                    "cohort": cohort, "review_id": rid, "language": _language(row),
                    "relative_day_bucket": stratum.split("relative_day=", 1)[-1], "stratum": stratum,
                    "selection_probability": round(probability, 8),
                    "sampling_weight": round(len(available) / quota, 8) if quota else None,
                })
    ready = target_per_cohort > 0 and all(len(selected_ids[c]) == target_per_cohort for c in COHORTS)
    denominator = sum(pooled.values()) or 1
    return {
        "schema_version": "semantic-sample-manifest-v1", "status": "ready" if ready else "insufficient_common_support",
        "method": SEMANTIC_SAMPLING_METHOD, "seed": seed, "total_budget": total_budget,
        "target_per_cohort": target_per_cohort, "actual_total": sum(map(len, selected_ids.values())),
        "balancing_dimensions": ["language", "relative_day_bucket"], "outcome_balanced": False,
        "common_support_strata": sorted(common), "target_distribution": {k: round(pooled[k] / denominator, 8) for k in sorted(pooled)},
        "quotas": quotas, "selected_review_ids": selected_ids, "entries": entries,
    }


def semantic_reviews_from_manifest(cohorts: Mapping[str, Sequence[Mapping[str, Any]]], manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    wanted = {rid for values in (manifest.get("selected_review_ids") or {}).values() for rid in values}
    unique: dict[str, dict[str, Any]] = {}
    for cohort in COHORTS:
        for row in cohorts.get(cohort, []):
            rid = _review_id(row)
            if rid and rid in wanted: unique[rid] = dict(row)
    return list(unique.values())


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool): return value
    if isinstance(value, (int, float)) and value in (0, 1): return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "positive", "recommended"}: return True
        if text in {"false", "0", "no", "negative", "not recommended", "not_recommended"}: return False
    return None


def _wilson(recommended: int, total: int, confidence: float = 0.95) -> tuple[float | None, float | None]:
    if total <= 0: return None, None
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    p = recommended / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def cohort_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid = [value for row in rows if (value := _bool(row.get("voted_up"))) is not None]
    recommended = sum(value is True for value in valid)
    rate = recommended / len(valid) if valid else None
    low, high = _wilson(recommended, len(valid))
    return {"reviews": len(rows), "outcome_valid_n": len(valid), "recommended": recommended,
            "not_recommended": len(valid) - recommended, "recommendation_rate": rate,
            "recommendation_ci95": [low, high], "languages": dict(sorted(Counter(_language(row) for row in rows).items()))}


def _rate(summary: Mapping[str, Any]) -> float | None:
    value = summary.get("recommendation_rate")
    return float(value) if isinstance(value, (int, float)) else None


def _pp(value: float | None) -> float | None:
    return round(value * 100, 2) if value is not None else None


def raw_comparison(cohorts: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    summaries = {cohort: cohort_summary(cohorts.get(cohort, [])) for cohort in COHORTS}
    rates = {cohort: _rate(summary) for cohort, summary in summaries.items()}
    def diff(left: str, right: str) -> float | None:
        return rates[right] - rates[left] if rates[left] is not None and rates[right] is not None else None
    delta_a, delta_b = diff("A_PRE", "A_POST"), diff("B_PRE", "B_POST")
    did = delta_b - delta_a if delta_a is not None and delta_b is not None else None
    return {"cohorts": summaries, "deltas": {
        "a_pre_to_post_pp": _pp(delta_a), "b_pre_to_post_pp": _pp(delta_b),
        "b_post_minus_a_post_pp": _pp(diff("A_POST", "B_POST")), "difference_in_differences_pp": _pp(did),
    }, "interpretation": "Observational comparison. Difference-in-differences is descriptive and not a causal estimate."}


def _safe_compare(reference: Sequence[Mapping[str, Any]], comparison: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    try: return compare_populations(reference, comparison)
    except Exception as exc: return {"comparability": {"level": "unknown", "warnings": [f"comparability_error:{type(exc).__name__}"]}}


def comparability_matrix(cohorts: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    return {
        "A_PRE_vs_A_POST": _safe_compare(cohorts.get("A_PRE", []), cohorts.get("A_POST", [])),
        "B_PRE_vs_B_POST": _safe_compare(cohorts.get("B_PRE", []), cohorts.get("B_POST", [])),
        "A_POST_vs_B_POST": _safe_compare(cohorts.get("A_POST", []), cohorts.get("B_POST", [])),
    }


def _safe_standardize(reference: Sequence[Mapping[str, Any]], comparison: Sequence[Mapping[str, Any]], variables: Sequence[str]) -> dict[str, Any]:
    try: return standardize_populations(reference, comparison, variables=variables, target="pooled", include_single_dimension_sensitivity=False)
    except Exception as exc: return {"status": "unavailable", "error": type(exc).__name__, "variables": list(variables)}


def standardization_sensitivity(cohorts: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    pairs = {"A_PRE_vs_A_POST": (cohorts.get("A_PRE", []), cohorts.get("A_POST", [])),
             "B_PRE_vs_B_POST": (cohorts.get("B_PRE", []), cohorts.get("B_POST", [])),
             "A_POST_vs_B_POST": (cohorts.get("A_POST", []), cohorts.get("B_POST", []))}
    return {name: {"language": _safe_standardize(a, b, ["language"]),
                   "language_plus_playtime": _safe_standardize(a, b, ["language", "playtime_cohort"])} for name, (a, b) in pairs.items()}


def _label_payload(labels: Mapping[str, Mapping[str, Any]], review: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = labels.get(_review_id(review), {}) or {}
    payload = raw.get("payload", raw) if isinstance(raw, Mapping) else {}
    return payload if isinstance(payload, Mapping) else {}


def _values(payload: Mapping[str, Any], key: str) -> set[str]:
    values = payload.get(key) or payload.get(f"llm_{key}") or []
    if isinstance(values, str): values = [values]
    return {str(value).strip() for value in values if str(value).strip()}


def semantic_comparison(cohorts: Mapping[str, Sequence[Mapping[str, Any]]], labels: Mapping[str, Mapping[str, Any]], manifest: Mapping[str, Any]) -> dict[str, Any]:
    selected = manifest.get("selected_review_ids") or {}
    selected_sets = {cohort: set(selected.get(cohort) or []) for cohort in COHORTS}
    samples = {cohort: [row for row in cohorts.get(cohort, []) if _review_id(row) in selected_sets[cohort]] for cohort in COHORTS}
    topics: set[str] = set()
    topic_sets: dict[str, dict[str, set[str]]] = {cohort: {} for cohort in COHORTS}
    families: dict[str, str] = {}
    for cohort in COHORTS:
        for row in samples[cohort]:
            payload = _label_payload(labels, row)
            issues, requests = _values(payload, "issue_subcategories"), _values(payload, "request_subcategories")
            rid = _review_id(row)
            for topic in _values(payload, "subcategories") | issues | requests:
                if topic.startswith("other/"): continue
                topics.add(topic); topic_sets[cohort].setdefault(topic, set()).add(rid)
                families[topic] = "request" if topic in requests else "problem" if topic in issues else families.get(topic, "positive")
    rows: list[dict[str, Any]] = []
    for topic in sorted(topics):
        supports, rates = {}, {}
        for cohort in COHORTS:
            supports[cohort] = len(topic_sets[cohort].get(topic, set()))
            rates[cohort] = supports[cohort] / len(samples[cohort]) if samples[cohort] else None
        da = rates["A_POST"] - rates["A_PRE"] if rates["A_POST"] is not None and rates["A_PRE"] is not None else None
        db = rates["B_POST"] - rates["B_PRE"] if rates["B_POST"] is not None and rates["B_PRE"] is not None else None
        did = db - da if da is not None and db is not None else None
        rows.append({"topic_id": topic, "display_name": topic.split("/", 1)[-1], "family": families.get(topic, "positive"),
                     "support": supports, "rates": rates, "a_change_pp": _pp(da), "b_change_pp": _pp(db),
                     "difference_in_differences_pp": _pp(did)})
    rows.sort(key=lambda row: abs(row.get("difference_in_differences_pp") or 0), reverse=True)
    classified = {cohort: sum(bool(_label_payload(labels, row)) for row in samples[cohort]) for cohort in COHORTS}
    return {"status": "ready" if manifest.get("status") == "ready" else "insufficient_common_support",
            "sample_counts": {cohort: len(samples[cohort]) for cohort in COHORTS}, "classified_counts": classified,
            "topics": rows, "problems": [r for r in rows if r["family"] == "problem"],
            "requests": [r for r in rows if r["family"] == "request"], "positives": [r for r in rows if r["family"] == "positive"]}


def window_sensitivity(acquired: Mapping[str, Sequence[Mapping[str, Any]]], event_a: Mapping[str, Any], event_b: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for days in SENSITIVITY_WINDOWS:
        cohorts = primary_cohorts(acquired, event_a, event_b, days)
        comparison = raw_comparison(cohorts)
        rows.append({"window_days": days, **comparison["deltas"], "counts": {key: len(value) for key, value in cohorts.items()}})
    return rows


def confounder_events(catalog: Sequence[Mapping[str, Any]], event_a: Mapping[str, Any], event_b: Mapping[str, Any], *, window_days: int) -> list[dict[str, Any]]:
    selected_ids = {str(event_a.get("event_id")), str(event_b.get("event_id"))}
    windows = cohort_windows(event_a, event_b, window_days)
    earliest, latest = min(item["start_time"] for item in windows.values()), max(item["end_time_exclusive"] for item in windows.values())
    result = []
    for event in catalog:
        if str(event.get("event_id")) in selected_ids: continue
        try: stamp = int(event_anchor(event)["timestamp"].timestamp())
        except ValueError: continue
        if earliest <= stamp < latest:
            event_type = str(event.get("event_type") or "other")
            result.append({"event_id": event.get("event_id"), "event_name": event.get("event_name") or event.get("title"),
                           "event_type": event_type, "event_date": event.get("effective_at") or event.get("event_date"),
                           "severity": "major" if event_type in {"major_patch", "season", "expansion", "pricing", "outage", "controversy"} else "minor"})
    return sorted(result, key=lambda item: str(item.get("event_date") or ""))


__all__ = ["COHORTS", "SENSITIVITY_WINDOWS", "SEMANTIC_SAMPLING_METHOD", "event_anchor", "chronological_events",
           "cohort_windows", "build_sampling_contracts", "slice_cohort", "primary_cohorts", "build_semantic_sample_manifest",
           "semantic_reviews_from_manifest", "cohort_summary", "raw_comparison", "comparability_matrix",
           "standardization_sensitivity", "semantic_comparison", "window_sensitivity", "confounder_events"]
