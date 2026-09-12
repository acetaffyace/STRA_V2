"""Run an explicit codex_offline_fixture pilot without any provider call."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", type=int, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = f"sqlite:///{args.database.resolve()}"
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from apps.api.senti_next.offline import run_offline_fixture
    result = run_offline_fixture(app_id=args.app_id, reviews_path=args.reviews)
    print(json.dumps({
        "run_id": result["run_id"],
        "mode": result["mode"],
        "review_count": result["review_count"],
        "five_question_contract": result["insights"].get("five_questions", {}).get("contract_version"),
        "recommended_action_count": len(result["insights"].get("five_questions", {}).get("recommended_actions", [])),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
