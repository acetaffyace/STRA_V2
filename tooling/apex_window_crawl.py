"""Fetch and window Apex Legends Steam reviews without invoking an LLM provider."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api.senti_next.steam_api import fetch_reviews


def ts(text: str, end: bool = False) -> int:
    value = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end:
        value = value.replace(hour=23, minute=59, second=59)
    return int(value.timestamp())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--start", default="2026-07-01")
    parser.add_argument("--end", default="2026-08-03")
    parser.add_argument("--app-id", type=int, default=1172470)
    parser.add_argument("--filter", default="recent", choices=["recent", "updated"])
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    start_ts, end_ts = ts(args.start), ts(args.end, end=True)
    raw = fetch_reviews(
        args.app_id,
        count=0,
        language="all",
        filter_type=args.filter,
        # day_range is only defined by Steam for filter=all; exact windows are
        # selected locally from timestamp_created instead.
        day_range=None,
        stop_before_timestamp=start_ts,
        progress_callback=lambda count: print(f"fetched={count}", flush=True),
    )
    window = [
        review for review in raw
        if start_ts <= int(review.get("timestamp_created") or 0) <= end_ts
    ]
    window.sort(key=lambda review: int(review.get("timestamp_created") or 0))
    with (args.out_dir / "reviews.jsonl").open("w", encoding="utf-8") as handle:
        for review in window:
            handle.write(json.dumps(review, ensure_ascii=False) + "\n")
    metadata = {
        "app_id": args.app_id,
        "game_name": "Apex Legends",
        "source": "Steam Reviews API",
        "filter": args.filter,
        "language": "all",
        "requested_window": {"start": args.start, "end": args.end, "timezone": "UTC"},
        "raw_fetched_count": len(raw),
        "window_review_count": len(window),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "crawl_note": "Crawl stops only after a full page is at or before the window start; Steam API pagination and window filtering still do not prove complete historical coverage.",
    }
    (args.out_dir / "crawl_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
