"""Read-only dry-run: preprocess stored reviews and plan representative batches."""
import json
import os
import sqlite3
import statistics
from pathlib import Path

from senti_next.batch_planner import BatchLane, DynamicBatchPlanner
from senti_next.review_preprocessor import ReviewPreprocessor


def database_path() -> Path:
    value = os.getenv("DATABASE_URL", "")
    if value.startswith("sqlite:///"):
        return Path(value[len("sqlite:///"):])
    return Path.home() / ".sentinext" / "data" / "sentinext.db"


def main() -> None:
    path = database_path()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    by_app = {}
    for row in connection.execute("SELECT app_id, review_id, data FROM reviews ORDER BY app_id, id"):
        data = json.loads(row["data"] or "{}")
        by_app.setdefault(int(row["app_id"]), []).append({
            "review_id": str(row["review_id"]),
            "review": data.get("review") or "",
        })

    for app_id, reviews in by_app.items():
        prep = ReviewPreprocessor(mode="active").process_reviews(app_id, reviews)
        representatives = []
        for review_id in prep.representatives:
            result = prep.results[review_id]
            representatives.append({"review_id": review_id, "review_text_for_model": result.processed_text})
        planner = DynamicBatchPlanner()
        batches = planner.plan(representatives)
        metrics = planner.metrics(batches)
        metrics["app_id"] = app_id
        metrics["total_reviews"] = len(reviews)
        metrics["representative_reviews"] = len(representatives)
        metrics["empty_reviews"] = sum(not str(item.get("review") or "").strip() for item in reviews)
        metrics["pure_nonlexical_skips"] = sum(result.skip_llm for result in prep.results.values())
        metrics["short_lexical_reviews_preserved"] = sum(
            "short_text" in result.flags and not result.skip_llm and bool(result.processed_text.strip())
            for result in prep.results.values()
        )
        metrics["preprocessor_duplicate_members_saved"] = prep.metrics["potential_llm_inputs_saved"]
        metrics["lane_review_counts"] = {lane.value: sum(batch.review_count for batch in batches if batch.lane is lane) for lane in BatchLane}
        metrics["lane_batch_counts"] = {lane.value: sum(batch.lane is lane for batch in batches) for lane in BatchLane}
        metrics["max_planned_batch_chars"] = max((batch.total_processed_chars for batch in batches), default=0)
        max_total_chars = planner.config.max_total_chars
        metrics["average_fill_ratio"] = round(
            statistics.mean(batch.total_processed_chars / max_total_chars for batch in batches), 4
        ) if batches and max_total_chars else 0.0
        old_count = 0
        old_size = 0
        old_chars = 0
        for item in representatives:
            size = len(item["review_text_for_model"])
            if size >= 8000:
                if old_size:
                    old_count += 1
                    old_size = old_chars = 0
                old_count += 1
                continue
            target = 50 if size >= 1200 else 100
            if old_size and (old_size >= target or old_chars + size > 32000):
                old_count += 1
                old_size = old_chars = 0
            old_size += 1
            old_chars += size
        if old_size:
            old_count += 1
        metrics["old_fixed_batch_count_estimate"] = old_count
        print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    main()
