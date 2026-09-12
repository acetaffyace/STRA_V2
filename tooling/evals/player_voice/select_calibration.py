"""Select a blind, deterministic calibration subset from pending candidates."""
from __future__ import annotations

import argparse
import hashlib
import json

from .common import read_jsonl, write_jsonl


def select_calibration(records: list[dict], limit: int = 30, salt: str = "p0.5b-calibration") -> list[dict]:
    if any(record.get("annotation_status") != "pending" for record in records):
        raise ValueError("calibration selection requires pending records")
    ranked = sorted(records, key=lambda record: hashlib.sha256(f"{salt}:{record['sample_id']}".encode()).hexdigest())
    # Keep the calibration subset balanced by the pre-existing neutral stratum
    # only; no model label or inferred answer is used.
    chosen: list[dict] = []
    for stratum in ("core", "challenge"):
        pool = [record for record in ranked if record.get("sampling_stratum") == stratum]
        quota = min(len(pool), limit // 2)
        chosen.extend(pool[:quota])
    remaining = [record for record in ranked if record not in chosen]
    chosen.extend(remaining[: max(0, limit - len(chosen))])
    return sorted(chosen[:limit], key=lambda record: record["sample_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    selected = select_calibration(read_jsonl(args.input), args.limit)
    write_jsonl(args.output, selected)
    print(json.dumps({"calibration": len(selected), "core": sum(r.get("sampling_stratum") == "core" for r in selected), "challenge": sum(r.get("sampling_stratum") == "challenge" for r in selected)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
