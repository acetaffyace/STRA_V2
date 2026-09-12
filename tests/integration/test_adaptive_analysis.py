from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, storage
from senti_next.adaptive_analysis import (
    build_analysis_design,
    competing_mechanisms,
    evidence_grade,
    event_impact,
    infer_game_profile,
    population_comparability,
    public_opinion_events,
    resolve_event_anchor,
    robustness_matrix,
    select_adaptive_window,
)


def setup_function():
    db.close_engine()
    db._engine = None
    db.init_db()


def teardown_function():
    db.close_engine()
    db._engine = None


def reviews(n: int, *, start: int = 0, negative: bool = False, language: str = "english"):
    return [{"recommendationid": f"r-{start+i}", "timestamp_created": 1785600000 + i * 86400, "voted_up": not negative, "language": language} for i in range(n)]


def test_profile_and_window_are_explainable_and_adaptive():
    profile = infer_game_profile({"categories": ["Multi-player", "Online PvP"], "is_free": True}, reviews(30))
    assert profile["archetype"] == "live_service_competitive"
    event = resolve_event_anchor({"app_id": 7, "event_type": "major_patch", "event_date": "2026-08-03"})
    window = select_adaptive_window(profile, event, reviews(30))
    assert window["label"] in {"plus_minus_7d", "plus_minus_28d"}
    assert window["reason_codes"]


def test_unresolved_or_range_anchor_never_becomes_fake_single_date():
    result = resolve_event_anchor({"app_id": 7, "effective_at_start": "2026-08-03", "effective_at_end": "2026-08-05"})
    assert result["effective_at"] is None
    assert result["anchor_precision"] == "range"
    assert result["event_status"] == "confounded"


def test_population_effect_robustness_grade_and_competing_mechanisms():
    pre, post = reviews(30), reviews(30, start=100, negative=True, language="schinese")
    comparison = population_comparability(pre, post)
    effect = event_impact(pre, post)
    robustness = robustness_matrix({"plus_minus_3d": (pre[:10], post[:10]), "plus_minus_7d": (pre, post)}, lambda r: not r["voted_up"])
    grade = evidence_grade(sample_support=30, robustness=robustness, comparability=comparison, verified_evidence_count=2)
    assert effect["delta"] > 0
    assert comparison["overall"] in {"warn", "fail"}
    assert grade["grade"] in {"B", "C"}
    assert len(competing_mechanisms("technical/bugs", {"event_status": "resolved"}, comparison)) >= 5


def test_public_opinion_detector_requires_two_signals_and_unknown_cause():
    daily = [{"date": f"2026-08-{i:02d}", "reviews": 10, "negative_rate": 0.2} for i in range(1, 8)]
    daily[-1] = {"date": "2026-08-08", "reviews": 100, "negative_rate": 0.8}
    events = public_opinion_events(daily, min_support=20)
    assert events and events[0]["cause"] == "unknown"
    assert events[0]["signal_bundle"] == ["volume_burst", "negative_rate_shift"]


def test_analysis_design_snapshot_is_immutable_per_run():
    run_id = "adaptive-test-run"
    storage.create_analysis_run({"run_id": run_id, "target_app_id": 7, "event_id": None, "config": {}, "status": "created"})
    design = build_analysis_design(
        app_id=7, analysis_type="event_impact", profile={"archetype": "hybrid_unknown"},
        event={"event_date": "2026-08-03", "event_type": "patch"},
        window={"label": "descriptive_only", "reason_codes": ["unresolved_event_anchor"]},
        sensitivity_windows=[], comparison_basis="event_centered", population_rules={}, metrics=["recommendation_rate"],
    )
    saved = storage.save_analysis_design(design, run_id)
    assert saved["snapshot"]["design_id"] == design["design_id"]
    assert storage.get_analysis_design(run_id)["schema_version"] == "adaptive-analysis-v1"
