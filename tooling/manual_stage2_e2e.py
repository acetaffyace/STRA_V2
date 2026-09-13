"""Manual live Steam smoke test for the deterministic Stage 1–2E pipeline.

This is orchestration only.  It intentionally does not call the normal
``/analyze`` route, does not import an LLM provider, and does not reimplement
the Stage 2 analytical modules.  Live output is written below ``artifacts/``
which is gitignored.

Example:
    python tooling/manual_stage2_e2e.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from senti_next.activity_diagnostics import analyze_review_activity, normalize_review_text  # noqa: E402
from senti_next.acquisition_provenance import derive_acquisition_coverage  # noqa: E402
from senti_next.population_validity import compare_populations  # noqa: E402
from senti_next.rate_inference import compare_recommendation_rates  # noqa: E402
from senti_next.sampling import SamplingContract  # noqa: E402
from senti_next.standardization import standardize_populations  # noqa: E402
from senti_next.steam_api import fetch_reviews_multi_language  # noqa: E402
from senti_next.window_robustness import matched_window_robustness  # noqa: E402


APP_ID = 2_909_400
START_TIME = int(datetime(2026, 8, 15, tzinfo=timezone.utc).timestamp())
END_TIME = int(datetime(2026, 9, 12, tzinfo=timezone.utc).timestamp())
REFERENCE_END = int(datetime(2026, 8, 29, tzinfo=timezone.utc).timestamp())


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def _semantic_modules_loaded() -> list[str]:
    """Return optional semantic/provider modules present in this process."""
    return sorted(
        name
        for name in sys.modules
        if name == "senti_next.llm"
        or name.startswith("senti_next.providers")
        or name.startswith("senti_next.routes")
    )


def _timestamp(row: Mapping[str, Any]) -> int | None:
    value = row.get("timestamp_created")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _review_id(row: Mapping[str, Any], index: int) -> str:
    value = row.get("recommendationid")
    return str(value) if value is not None and str(value).strip() else f"row:{index}"


def _raw_integrity(reviews: list[Mapping[str, Any]]) -> dict[str, Any]:
    ids = [_review_id(row, index) for index, row in enumerate(reviews)]
    id_counts = Counter(ids)
    text_groups: defaultdict[str, list[str]] = defaultdict(list)
    non_empty_text_n = 0
    for review_id, row in zip(ids, reviews):
        text = str(row.get("review") or "")
        normalized = normalize_review_text(text)
        if normalized:
            non_empty_text_n += 1
            text_groups[hashlib.sha256(normalized.encode("utf-8")).hexdigest()].append(review_id)
    duplicate_text_groups = {key: values for key, values in text_groups.items() if len(set(values)) > 1}
    voted_up = [row.get("voted_up") for row in reviews if isinstance(row.get("voted_up"), bool)]
    recommended_n = sum(value is True for value in voted_up)
    not_recommended_n = sum(value is False for value in voted_up)
    timestamps = [value for row in reviews if (value := _timestamp(row)) is not None]
    return {
        "raw_row_count": len(reviews),
        "unique_recommendationid_count": len(set(ids)),
        "duplicate_review_id_count": sum(count - 1 for count in id_counts.values() if count > 1),
        "non_empty_text_count": non_empty_text_n,
        "duplicate_normalized_text_group_count": len(duplicate_text_groups),
        "duplicate_normalized_text_review_count": sum(len(set(values)) for values in duplicate_text_groups.values()),
        "valid_voted_up_count": len(voted_up),
        "recommended_n": recommended_n,
        "not_recommended_n": not_recommended_n,
        "raw_recommendation_rate": recommended_n / len(voted_up) if voted_up else None,
        "observed_timestamp_min": min(timestamps) if timestamps else None,
        "observed_timestamp_max": max(timestamps) if timestamps else None,
    }


def _slice(reviews: Iterable[Mapping[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    return [dict(row) for row in reviews if (timestamp := _timestamp(row)) is not None and start <= timestamp < end]


def _cohort_metadata(contract: SamplingContract, parent_metadata: Mapping[str, Any], start: int, end: int) -> dict[str, Any]:
    result = dict(parent_metadata)
    result["window_start"] = start
    result["window_end"] = end
    result["coverage_start_time"] = start
    result["coverage_end_time"] = end
    result["coverage_status"] = parent_metadata.get("coverage_status")
    result["coverage_end_inclusive"] = False
    result["acquisition_coverage"] = {
        "start_time": start,
        "end_time": end,
        "status": result["coverage_status"],
        "end_inclusive": False,
    }
    result["sampling_contract"] = {
        **contract.to_dict(),
        "start_time": start,
        "end_time": end,
    }
    return result


def _compact_stage2e(report: Mapping[str, Any]) -> dict[str, Any]:
    repetition = report["text_repetition"]
    summary = report["summary"]
    clusters = report["clusters"]["all"]
    compact_clusters = [
        {
            key: cluster.get(key)
            for key in ("cluster_type", "review_count", "languages", "recommendation_rate", "duration_seconds", "share_within_24h")
        }
        for cluster in sorted(clusters, key=lambda item: (-int(item["review_count"]), item["cluster_id"]))[:5]
    ]
    return {
        "raw_review_count": report["population"]["raw_review_count"],
        "unique_normalized_text_count": repetition["unique_normalized_text_count"],
        "unique_text_share": repetition["unique_text_share"],
        "exact_duplicate_review_count": repetition["exact_duplicate_review_count"],
        "exact_duplicate_share": repetition["exact_duplicate_share"],
        "near_copy_additional_review_count": repetition["near_copy_additional_review_count"],
        "near_copy_additional_share": repetition["near_copy_additional_share"],
        "coordinated_expression_review_count": repetition["coordinated_expression_review_count"],
        "coordinated_expression_share": repetition["coordinated_expression_share"],
        "activity_spike_detected": summary["activity_spike_detected"],
        "spike_bin_count": report["spikes"]["spike_bin_count"],
        "largest_cluster_share": summary["largest_cluster_share"],
        "peak_bin_coordinated_share": summary["peak_bin_coordinated_share"],
        "largest_clusters": compact_clusters,
    }


def run(output_dir: Path) -> dict[str, Any]:
    contract = SamplingContract(
        app_id=APP_ID,
        start_time=START_TIME,
        end_time=END_TIME,
        languages=["english", "schinese", "japanese"],
        review_type="all",
        purchase_type="all",
        collection_order="recent",
        include_offtopic_activity=True,
        max_reviews=0,
    )
    semantic_modules_at_start = _semantic_modules_loaded()
    stats_events: list[dict[str, Any]] = []
    acquisition_error: str | None = None
    reviews: list[dict[str, Any]] = []
    try:
        reviews = fetch_reviews_multi_language(
            APP_ID,
            sampling_contract=contract,
            stats_callback=lambda stats: stats_events.append(dict(stats)),
        )
    except Exception as exc:  # preserve partial provenance for a failed live run
        acquisition_error = f"{type(exc).__name__}: {exc}"

    fetch_stats = dict(stats_events[-1]) if stats_events else {
        "collection_complete": False,
        "truncated_by_max_reviews": False,
        "stop_reason": "api_failure" if acquisition_error else "invalid_response",
        "error": acquisition_error,
        "retrieved_reviews": 0,
        "population_reviews_after_scope": len(reviews),
    }
    if acquisition_error:
        fetch_stats.setdefault("error", acquisition_error)
    coverage = derive_acquisition_coverage(contract, fetch_stats)
    acquisition_stats = {
        **fetch_stats,
        **coverage,
        "contract": contract.to_dict(),
        "observed_timestamp_min": _raw_integrity(reviews)["observed_timestamp_min"] if reviews else None,
        "observed_timestamp_max": _raw_integrity(reviews)["observed_timestamp_max"] if reviews else None,
    }
    _json_write(output_dir / "sampling_contract.json", contract.to_dict())
    _json_write(output_dir / "acquisition_stats.json", acquisition_stats)

    raw_integrity = _raw_integrity(reviews)
    _json_write(output_dir / "population_summary.json", raw_integrity)
    parent_metadata = {
        "app_id": APP_ID,
        "sampling_contract": contract.to_dict(),
        "collection_complete": fetch_stats.get("collection_complete"),
        "scope_complete": fetch_stats.get("scope_complete", fetch_stats.get("collection_complete")),
        "truncated_by_max_reviews": fetch_stats.get("truncated_by_max_reviews", False),
        "stop_reason": fetch_stats.get("stop_reason"),
        "language_stats": fetch_stats.get("language_stats", {}),
        **coverage,
    }

    complete = fetch_stats.get("collection_complete") is True and coverage.get("coverage_status") == "complete"
    acceptance: dict[str, Any] = {
        "A_live_steam_acquisition_succeeded": bool(not acquisition_error and complete),
        "B_no_llm_invoked": not semantic_modules_at_start,
        "C_stage1_provenance_captured": bool(stats_events and "language_stats" in fetch_stats),
        "D_stage2a_executed": False,
        "E_stage2b_executed": False,
        "F_stage2c_executed": False,
        "G_stage2d_executed": False,
        "H_stage2e_executed": False,
        "I_denominators_unchanged": False,
        "J_reports_json_serializable": False,
    }
    if not complete:
        summary = {
            "status": "FAIL",
            "failure": "complete bounded acquisition was not established",
            "acquisition_error": acquisition_error,
            "acceptance": acceptance,
            "deterministic_execution": {
                "llm_provider_calls": 0 if not semantic_modules_at_start else None,
                "semantic_modules_loaded": semantic_modules_at_start,
            },
            "raw_integrity": raw_integrity,
        }
        _json_write(output_dir / "e2e_summary.json", summary)
        return summary

    reference = _slice(reviews, START_TIME, REFERENCE_END)
    comparison = _slice(reviews, REFERENCE_END, END_TIME)
    reference_metadata = _cohort_metadata(contract, parent_metadata, START_TIME, REFERENCE_END)
    comparison_metadata = _cohort_metadata(contract, parent_metadata, REFERENCE_END, END_TIME)

    stage2a = compare_populations(reference, comparison, reference_metadata, comparison_metadata)
    acceptance["D_stage2a_executed"] = True
    _json_write(output_dir / "stage2a_comparability.json", stage2a)

    stage2b = compare_recommendation_rates(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        comparability_report=stage2a,
    )
    acceptance["E_stage2b_executed"] = True
    _json_write(output_dir / "stage2b_rate_inference.json", stage2b)

    stage2c = standardize_populations(
        reference,
        comparison,
        reference_metadata=reference_metadata,
        comparison_metadata=comparison_metadata,
        comparability_report=stage2a,
        variables=["language", "playtime_cohort"],
        target="reference",
    )
    acceptance["F_stage2c_executed"] = True
    _json_write(output_dir / "stage2c_standardization.json", stage2c)

    stage2d = matched_window_robustness(
        reference,
        comparison,
        START_TIME,
        REFERENCE_END,
        reference_metadata=parent_metadata,
        comparison_metadata=parent_metadata,
        comparability_report=stage2a,
        windows_days=[3, 7, 14],
        standardization_variables=["language", "playtime_cohort"],
    )
    acceptance["G_stage2d_executed"] = True
    _json_write(output_dir / "stage2d_window_robustness.json", stage2d)

    stage2e_full = analyze_review_activity(reviews, grain="day")
    stage2e_comparison = analyze_review_activity(comparison, grain="day")
    acceptance["H_stage2e_executed"] = True
    _json_write(output_dir / "stage2e_activity_full.json", stage2e_full)
    _json_write(output_dir / "stage2e_activity_comparison.json", stage2e_comparison)

    stage2b_reference = stage2b["reference"]
    stage2b_comparison = stage2b["comparison"]
    denominator_integrity = {
        "reference": {
            "stage2b": {key: stage2b_reference.get(key) for key in ("valid_n", "recommended_n", "not_recommended_n", "recommendation_rate")},
            "independent": {
                "valid_n": raw_integrity_for(reference)["valid_voted_up_count"],
                "recommended_n": raw_integrity_for(reference)["recommended_n"],
                "not_recommended_n": raw_integrity_for(reference)["not_recommended_n"],
                "recommendation_rate": raw_integrity_for(reference)["raw_recommendation_rate"],
            },
        },
        "comparison": {
            "stage2b": {key: stage2b_comparison.get(key) for key in ("valid_n", "recommended_n", "not_recommended_n", "recommendation_rate")},
            "independent": {
                "valid_n": raw_integrity_for(comparison)["valid_voted_up_count"],
                "recommended_n": raw_integrity_for(comparison)["recommended_n"],
                "not_recommended_n": raw_integrity_for(comparison)["not_recommended_n"],
                "recommendation_rate": raw_integrity_for(comparison)["raw_recommendation_rate"],
            },
        },
    }
    denominator_integrity["matches"] = all(
        denominator_integrity[label]["stage2b"] == denominator_integrity[label]["independent"]
        for label in ("reference", "comparison")
    )
    acceptance["I_denominators_unchanged"] = denominator_integrity["matches"]
    stage2a_dimensions = stage2a.get("dimensions", {})

    summary = {
        "status": "PASS" if all(acceptance.values()) else "FAIL",
        "game": {"name": "FINAL FANTASY VII REBIRTH", "app_id": APP_ID},
        "requested_scope": contract.to_dict(),
        "acquisition": {
            "retrieved_reviews": fetch_stats.get("retrieved_reviews"),
            "population_reviews_after_scope": fetch_stats.get("population_reviews_after_scope"),
            "collection_complete": fetch_stats.get("collection_complete"),
            "truncated_by_max_reviews": fetch_stats.get("truncated_by_max_reviews"),
            "stop_reason": fetch_stats.get("stop_reason"),
            "coverage_start_time": coverage.get("coverage_start_time"),
            "coverage_end_time": coverage.get("coverage_end_time"),
            "coverage_status": coverage.get("coverage_status"),
            "language_stats": fetch_stats.get("language_stats", {}),
            "observed_timestamp_min": raw_integrity.get("observed_timestamp_min"),
            "observed_timestamp_max": raw_integrity.get("observed_timestamp_max"),
        },
        "reference_n": len(reference),
        "comparison_n": len(comparison),
        "stage2a_key_metrics": {
            "acquisition_validity": stage2a.get("acquisition_validity"),
            "composition_comparability": stage2a.get("composition_comparability"),
            "language_tvd": stage2a_dimensions.get("language", {}).get("distance"),
            "playtime_tvd": stage2a_dimensions.get("playtime", {}).get("distance"),
            "steam_purchase_difference": stage2a_dimensions.get("purchase_source", {}).get("absolute_percentage_point_difference"),
            "received_for_free_difference": stage2a_dimensions.get("free_copy", {}).get("absolute_percentage_point_difference"),
            "early_access_difference": stage2a_dimensions.get("early_access", {}).get("absolute_percentage_point_difference"),
            "steam_deck_difference": stage2a_dimensions.get("steam_deck", {}).get("absolute_percentage_point_difference"),
            "review_activity": stage2a.get("review_activity"),
            "missingness": stage2a.get("data_quality", {}).get("missingness"),
        },
        "stage2b_key_metrics": {
            "reference": stage2b_reference,
            "comparison": stage2b_comparison,
            "difference": stage2b.get("difference"),
        },
        "stage2c_key_metrics": {
            "raw_difference": stage2c["raw"]["difference"],
            "standardized_difference": stage2c["standardization"]["standardized_difference"],
            "composition_standardization_shift": stage2c["standardization"]["composition_standardization_shift"],
            "support_status": stage2c["standardization"]["status"],
            "support": stage2c["support"],
            "weights": stage2c["weights"],
        },
        "stage2d_key_metrics": {
            "windows": {
                key: {
                    "reference_n": value["reference_population"]["review_count"],
                    "comparison_n": value["comparison_population"]["review_count"],
                    "raw_recommendation_delta": value["recommendation"]["raw_difference"],
                    "composition_comparability": value["comparability"]["composition_comparability"],
                    "standardized_delta": (value["standardization"] or {}).get("standardized_difference") if value["standardization"] else None,
                    "window_status": value["window_status"],
                }
                for key, value in stage2d["windows"].items()
            },
            "robustness": stage2d["robustness"],
        },
        "stage2e_key_metrics": {
            "full": _compact_stage2e(stage2e_full),
            "comparison": _compact_stage2e(stage2e_comparison),
        },
        "population_integrity": raw_integrity,
        "denominator_integrity": denominator_integrity,
        "acceptance": acceptance,
        "deterministic_execution": {
            "llm_provider_calls": 0 if not semantic_modules_at_start else None,
            "semantic_modules_loaded": semantic_modules_at_start,
        },
        "limitations": {
            "descriptive_only": True,
            "no_causal_interpretation": True,
            "no_review_bomb_attribution": True,
            "no_bot_inference": True,
        },
    }
    _json_write(output_dir / "e2e_summary.json", summary)
    acceptance["J_reports_json_serializable"] = True
    # Rewrite after setting the final serialization acceptance check.
    summary["acceptance"] = acceptance
    summary["status"] = "PASS" if all(acceptance.values()) else "FAIL"
    _json_write(output_dir / "e2e_summary.json", summary)
    return summary


def raw_integrity_for(reviews: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Small alias kept separate for explicit cohort denominator checks."""
    return _raw_integrity(list(reviews))


def main() -> int:
    output_dir = ROOT / "artifacts" / "manual_e2e" / "ff7_rebirth_2026_08_15_09_12"
    print(f"Running live Steam Stage 1–2E smoke test for app {APP_ID}...")
    print(f"Artifacts: {output_dir}")
    try:
        summary = run(output_dir)
    except Exception as exc:
        print(f"E2E FAILURE: {type(exc).__name__}: {exc}")
        return 1
    acquisition = summary.get("acquisition", {})
    print(json.dumps({
        "status": summary.get("status"),
        "retrieved_reviews": acquisition.get("retrieved_reviews"),
        "population_reviews_after_scope": acquisition.get("population_reviews_after_scope"),
        "collection_complete": acquisition.get("collection_complete"),
        "stop_reason": acquisition.get("stop_reason"),
        "reference_n": summary.get("reference_n"),
        "comparison_n": summary.get("comparison_n"),
        "acceptance": summary.get("acceptance"),
    }, indent=2, sort_keys=True))
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
