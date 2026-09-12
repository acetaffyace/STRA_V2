"""Real-data V2 closure check for HELLDIVERS 2 lifecycle windows."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from senti_next.comparative_intelligence import evaluate_window_coverage, lifecycle_window, reviews_in_window
from senti_next.steam_api import fetch_reviews


def ts(day: date) -> int:
    return int(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).timestamp())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", type=int, default=553850)
    parser.add_argument("--event-a", default="2026-05-28")
    parser.add_argument("--event-b", default="2026-08-12")
    parser.add_argument("--out", default="data/version_review_v2_helldivers_validation.json")
    args = parser.parse_args()
    events = [{"event_id": "helldivers-2026-05-28", "event_name": "Patch Delay Update", "effective_at": args.event_a, "source": "steam_news"}, {"event_id": "helldivers-2026-08-12", "event_name": "HELLDIVERS 2 Devoid of Liberty Update Out Now", "effective_at": args.event_b, "source": "steam_news"}]
    oldest = min(date.fromisoformat(args.event_a), date.fromisoformat(args.event_b))
    # filter=recent is intentional: it is the chronological backfill contract.
    reviews = fetch_reviews(args.app_id, count=0, language="all", filter_type="recent", stop_before_timestamp=ts(oldest))
    rows = []
    for event in events:
        for days in (3, 7, 14):
            window = lifecycle_window(event, days)
            scoped = reviews_in_window(reviews, window)
            gate = evaluate_window_coverage(reviews, event, days, crawl_complete_for_window=True, coverage_source="steam_recent_real_backfill")
            rows.append({**gate, "event_name": event["event_name"], "reviews_per_day": round(len(scoped) / days, 2)})
    result = {"app_id": args.app_id, "acquisition": {"filter": "recent", "crawl_complete_for_window": True, "fetched_total": len(reviews), "oldest_fetched": min((r.get("timestamp_created", 0) for r in reviews), default=None), "newest_fetched": max((r.get("timestamp_created", 0) for r in reviews), default=None)}, "events": events, "windows": rows}
    path = Path(args.out); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
