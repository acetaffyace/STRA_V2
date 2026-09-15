from collections import Counter
from datetime import datetime, timezone

from apps.api.senti_next.version_comparison import (
    COHORTS,
    build_sampling_contracts,
    build_semantic_sample_manifest,
    chronological_events,
    cohort_windows,
    confounder_events,
    raw_comparison,
    window_sensitivity,
)


def ts(day: str, hour: int = 12) -> int:
    return int(datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00").timestamp())


def event(event_id: str, day: str, *, precision: str = "day", effective_at=None):
    return {"event_id": event_id, "event_name": event_id, "event_date": day, "effective_at": effective_at, "anchor_precision": precision}


def test_date_only_windows_exclude_event_day():
    a = event("a" * 8, "2026-01-10")
    b = event("b" * 8, "2026-02-10")
    windows = cohort_windows(a, b, 3)
    assert windows["A_PRE"]["start_time"] == ts("2026-01-07", 0)
    assert windows["A_PRE"]["end_time_exclusive"] == ts("2026-01-10", 0)
    assert windows["A_POST"]["start_time"] == ts("2026-01-11", 0)
    assert windows["A_POST"]["end_time_exclusive"] == ts("2026-01-14", 0)
    assert windows["A_PRE"]["boundary_mode"] == "event_day_excluded"


def test_exact_timestamp_anchor_uses_half_open_timestamp_windows():
    a = event("a" * 8, "2026-01-10", precision="timestamp", effective_at="2026-01-10T15:30:00+00:00")
    b = event("b" * 8, "2026-02-10")
    windows = cohort_windows(a, b, 3)
    assert windows["A_POST"]["start_time"] == int(datetime.fromisoformat("2026-01-10T15:30:00+00:00").timestamp())
    assert windows["A_POST"]["boundary_mode"] == "exact_timestamp"


def test_events_are_always_oriented_older_a_newer_b():
    newer = event("newer000", "2026-03-01")
    older = event("older000", "2026-01-01")
    a, b = chronological_events(newer, older)
    assert a["event_id"] == "older000"
    assert b["event_id"] == "newer000"


def test_four_sampling_contracts_share_acquisition_contract():
    a = event("a" * 8, "2026-01-10")
    b = event("b" * 8, "2026-02-10")
    contracts = build_sampling_contracts(123, a, b, window_days=7, languages=["english", "japanese"], max_reviews_per_cohort=2000)
    assert set(contracts) == set(COHORTS)
    assert all(c.app_id == 123 for c in contracts.values())
    assert all(c.collection_order == "recent" for c in contracts.values())
    assert all(c.max_reviews == 2000 for c in contracts.values())
    assert all(c.languages == ["english", "japanese"] for c in contracts.values())


def _cohort_rows(prefix: str, anchor_day: str, side: str, *, positive_share: float):
    anchor = datetime.fromisoformat(anchor_day + "T00:00:00+00:00")
    rows = []
    idx = 0
    for language in ("english", "japanese"):
        for distance in (1, 2, 3, 5):
            for _ in range(4):
                idx += 1
                ordinal = anchor.date().toordinal() + (-distance if side == "pre" else distance)
                actual = datetime.fromordinal(ordinal).replace(tzinfo=timezone.utc)
                rows.append({
                    "recommendationid": f"{prefix}-{idx}",
                    "timestamp_created": int(actual.timestamp()) + 12 * 3600,
                    "language": language,
                    "voted_up": idx / 32 <= positive_share,
                    "author": {"playtime_at_review": 600},
                })
    return rows


def test_semantic_manifest_is_equal_common_support_deterministic_and_not_outcome_balanced():
    a = event("a" * 8, "2026-01-10")
    b = event("b" * 8, "2026-02-10")
    cohorts = {
        "A_PRE": _cohort_rows("apre", "2026-01-10", "pre", positive_share=0.90),
        "A_POST": _cohort_rows("apost", "2026-01-10", "post", positive_share=0.75),
        "B_PRE": _cohort_rows("bpre", "2026-02-10", "pre", positive_share=0.55),
        "B_POST": _cohort_rows("bpost", "2026-02-10", "post", positive_share=0.25),
    }
    m1 = build_semantic_sample_manifest(cohorts, a, b, total_budget=40, seed="same-seed")
    m2 = build_semantic_sample_manifest(cohorts, a, b, total_budget=40, seed="same-seed")
    assert m1["status"] == "ready"
    assert m1["outcome_balanced"] is False
    assert m1["balancing_dimensions"] == ["language", "relative_day_bucket"]
    assert m1["selected_review_ids"] == m2["selected_review_ids"]
    sizes = [len(m1["selected_review_ids"][cohort]) for cohort in COHORTS]
    assert len(set(sizes)) == 1
    assert sum(sizes) <= 40
    baseline_strata = Counter(entry["stratum"] for entry in m1["entries"] if entry["cohort"] == COHORTS[0])
    for cohort in COHORTS:
        strata = Counter(entry["stratum"] for entry in m1["entries"] if entry["cohort"] == cohort)
        assert strata == baseline_strata
    selected_outcomes = {}
    for cohort in COHORTS:
        wanted = set(m1["selected_review_ids"][cohort])
        rows = [row for row in cohorts[cohort] if row["recommendationid"] in wanted]
        selected_outcomes[cohort] = sum(row["voted_up"] for row in rows) / len(rows)
    assert len(set(selected_outcomes.values())) > 1


def test_raw_comparison_reports_pre_post_post_gap_and_descriptive_did():
    def rows(prefix, positives, total=10):
        return [{"recommendationid": f"{prefix}-{i}", "voted_up": i < positives, "language": "english"} for i in range(total)]
    result = raw_comparison({
        "A_PRE": rows("apre", 8),
        "A_POST": rows("apost", 6),
        "B_PRE": rows("bpre", 5),
        "B_POST": rows("bpost", 7),
    })
    assert result["deltas"]["a_pre_to_post_pp"] == -20.0
    assert result["deltas"]["b_pre_to_post_pp"] == 20.0
    assert result["deltas"]["b_post_minus_a_post_pp"] == 10.0
    assert result["deltas"]["difference_in_differences_pp"] == 40.0


def test_window_sensitivity_always_emits_3_7_14_days():
    a = event("a" * 8, "2026-01-10")
    b = event("b" * 8, "2026-02-10")
    result = window_sensitivity({cohort: [] for cohort in COHORTS}, a, b)
    assert [row["window_days"] for row in result] == [3, 7, 14]


def test_confounder_catalog_flags_other_events_inside_comparison_span():
    a = event("a" * 8, "2026-01-10")
    b = event("b" * 8, "2026-02-10")
    catalog = [
        a,
        b,
        {**event("c" * 8, "2026-01-14"), "event_type": "hotfix"},
        {**event("d" * 8, "2026-02-12"), "event_type": "outage"},
        {**event("e" * 8, "2026-06-01"), "event_type": "major_patch"},
    ]
    result = confounder_events(catalog, a, b, window_days=14)
    assert [item["event_id"] for item in result] == ["c" * 8, "d" * 8]
    assert result[0]["severity"] == "minor"
    assert result[1]["severity"] == "major"
