"""Read-only smoke check for ReviewPreprocessor against the configured SQLite DB."""
import json
import os
import sqlite3
from pathlib import Path

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
        result = ReviewPreprocessor(mode="shadow").process_reviews(app_id, reviews)
        print(json.dumps({"app_id": app_id, **result.metrics}, ensure_ascii=False))


if __name__ == "__main__":
    main()
