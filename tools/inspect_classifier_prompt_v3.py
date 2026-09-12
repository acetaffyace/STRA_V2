"""Render legacy and V3 classifier prompts without calling an API."""
from __future__ import annotations

import json
import os
from pathlib import Path

from senti_next import llm
from senti_next.batch_planner import BatchLane


FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "classifier_v3_reviews.json"


def render(items, variant: str) -> dict[str, int | str]:
    previous = os.environ.get("SENTINEXT_CLASSIFIER_PROMPT_VARIANT")
    os.environ["SENTINEXT_CLASSIFIER_PROMPT_VARIANT"] = variant
    try:
        prompt = llm._build_batch_prompt(items, game_context={
            "name": "Prompt Inspection Game",
            "type": "game",
            "genres": ["Action"],
            "categories": ["Single-player"],
            "short_description": "This metadata must not appear in V3.",
        })
    finally:
        if previous is None:
            os.environ.pop("SENTINEXT_CLASSIFIER_PROMPT_VARIANT", None)
        else:
            os.environ["SENTINEXT_CLASSIFIER_PROMPT_VARIANT"] = previous
    review_chars = sum(len(str(item.get("review_text") or item.get("review") or "")) for item in items)
    return {
        "variant": variant,
        "review_count": len(items),
        "review_chars": review_chars,
        "rendered_prompt_chars": len(prompt),
        "fixed_overhead_chars": len(prompt) - review_chars,
    }


def main() -> None:
    reviews = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = [{"review_id": row["review_id"], "review_text": row["review"]} for row in reviews]
    print(json.dumps({"overall": [render(items, "legacy"), render(items, "v3")]}, ensure_ascii=False))

    for lane in BatchLane:
        # Use representative fixture text at the lane boundary; this reports
        # prompt overhead independently of the planner's batch parameters.
        target = {BatchLane.SHORT: 20, BatchLane.MEDIUM: 100, BatchLane.LONG: 400, BatchLane.VERY_LONG: 1400}[lane]
        lane_items = [{"review_id": lane.value, "review_text": "x" * target}]
        legacy = render(lane_items, "legacy")
        v3 = render(lane_items, "v3")
        reduction = legacy["rendered_prompt_chars"] - v3["rendered_prompt_chars"]
        print(json.dumps({
            "lane": lane.value,
            "legacy_rendered_chars": legacy["rendered_prompt_chars"],
            "v3_rendered_chars": v3["rendered_prompt_chars"],
            "reduction": reduction,
            "reduction_pct": round(reduction / legacy["rendered_prompt_chars"] * 100, 2),
        }))


if __name__ == "__main__":
    main()
