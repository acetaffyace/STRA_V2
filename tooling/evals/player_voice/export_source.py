"""Export the minimum non-identifying review context for P0.5b sampling."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .common import write_jsonl


FIELDS = (
    "language",
    "voted_up",
    "votes_up",
    "timestamp_created",
    "steam_purchase",
    "received_for_free",
)


def export_reviews(database: str) -> list[dict]:
    with sqlite3.connect(database) as conn:
        rows = conn.execute("SELECT app_id, review_id, data FROM reviews ORDER BY app_id, review_id").fetchall()
    exported = []
    for app_id, review_id, raw in rows:
        data = json.loads(raw)
        record = {
            "app_id": int(app_id),
            "review_id": str(review_id),
            "review": str(data.get("review") or ""),
        }
        record.update({field: data.get(field) for field in FIELDS if field in data})
        exported.append(record)
    return exported


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records = export_reviews(args.database)
    write_jsonl(args.output, records)
    print(json.dumps({"records": len(records), "output": str(Path(args.output))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
