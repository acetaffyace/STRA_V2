from __future__ import annotations

import json

from tooling.offline_pilot.scenarios import SCENARIO_NAMES, scenario
from apps.api.senti_next.offline import run_offline_fixture
from apps.api.senti_next import db


def test_all_five_offline_scenarios_produce_explicit_five_question_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'scenarios.db'}")
    db.close_engine(); db._engine = None
    for name in SCENARIO_NAMES:
        app_id, rows, _expected = scenario(name)
        path = tmp_path / f"{name}.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        result = run_offline_fixture(app_id=app_id, reviews_path=path)
        five = result["insights"]["five_questions"]
        assert five["contract_version"] == "p1.1-v1"
        assert five["mode"] == "codex_offline_fixture"
        assert "recommended_actions" in five
    db.close_engine(); db._engine = None

