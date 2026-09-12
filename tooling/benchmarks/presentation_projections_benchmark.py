"""Small deterministic benchmark for Presentation Projections V1.

This benchmark uses synthetic in-memory rows and never opens or mutates a runtime DB.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from senti_next import presentation_projections as projections


class FakeStorage:
    def __init__(self, run: dict, result: dict):
        self.run = run
        self.result = result

    def get_analysis_run(self, run_id: str):
        return self.run if run_id == self.run["run_id"] else None

    def get_analysis_run_result(self, run_id: str):
        return self.result if run_id == self.run["run_id"] else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [
        {
            "timestamp_created": 1_756_665_600 + (index % 30) * 86400,
            "voted_up": index % 5 != 0,
            "review": f"synthetic review {index}",
        }
        for index in range(1000)
    ]
    run = {"run_id": "benchmark-run", "target_app_id": 553850, "run_type": "general_analysis", "status": "completed", "analysis_population_count": len(rows)}
    result = {"reviews": rows, "metadata": {}}
    original = projections.storage
    projections.storage = FakeStorage(run, result)
    try:
        timings = {}
        for name, function in {
            "daily_review_volume": projections.daily_review_volume,
            "daily_recommendation_rate": projections.daily_recommendation_rate,
        }.items():
            started = time.perf_counter()
            payload = function("benchmark-run")
            timings[name] = {
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "available": payload["available"],
                "input_population": len(rows),
                "output_points": len(payload["points"]),
            }
    finally:
        projections.storage = original
    output = {
        "projection_version": projections.PROJECTION_VERSION,
        "measurement": "single-process synthetic deterministic benchmark",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "database_access": False,
        "results": timings,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
