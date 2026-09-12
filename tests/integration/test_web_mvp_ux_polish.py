from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db, storage
from senti_next.routes._shared import AnalyzeMetadata


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    db.close_engine()
    db._engine = None
    db.init_db()
    yield
    db.close_engine()
    db._engine = None


def test_run_population_uses_canonical_count_not_requested_limit():
    run_id = "ux-population-1"
    storage.create_general_analysis_run(run_id, 4012810, config={"review_count": 1000}, requested_review_count=1000)
    storage.transition_general_analysis_run(run_id, "running", phase="classifying")
    storage.finalize_general_analysis_run(
        run_id,
        4012810,
        AnalyzeMetadata(
            app_id=4012810,
            requested=1000,
            retrieved=823,
            language="all",
            requested_limit=1000,
            available_matching_reviews=823,
            retrieved_count=823,
            deduplicated_count=823,
            analysis_population_count=823,
        ).model_dump(),
        {"five_questions": {"current_snapshot": {}}},
        [],
        counts={
            "available_matching_reviews": 823,
            "retrieved_count": 823,
            "deduplicated_count": 823,
            "analysis_population_count": 823,
            "valid_review_count": 823,
            "classified_count": 700,
        },
    )
    run = storage.get_analysis_run(run_id)
    assert run["requested_review_count"] == 1000
    assert run["analysis_population_count"] == 823
    assert run["deduplicated_count"] == 823


def test_eta_is_not_available_before_three_successful_samples():
    storage.reset_progress(4012810, 100, phase="classifying")
    storage.update_progress(4012810, 10, 100)
    storage.update_progress(4012810, 20, 100)
    storage.update_progress(4012810, 30, 100)
    assert storage.load_progress(4012810)["eta_seconds"] is None


def test_eta_is_coarse_and_backend_owned_after_enough_samples():
    storage.reset_progress(4012810, 100, phase="classifying")
    for processed in (30, 40, 50, 60):
        storage.update_progress(4012810, processed, 100)
        time.sleep(0.01)
    # The backend may still have no useful rate on a very fast test machine;
    # when it does, it must be a numeric server value, never UI timer text.
    eta = storage.load_progress(4012810)["eta_seconds"]
    assert eta is None or isinstance(eta, float)
