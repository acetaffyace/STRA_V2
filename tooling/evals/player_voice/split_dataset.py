from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict

try:
    from .common import read_jsonl, write_jsonl
except ImportError:  # pragma: no cover
    from common import read_jsonl, write_jsonl


def bucket(record: dict) -> str:
    labels = (record.get("gold") or {}).get("subcategories") or (record.get("gold") or {}).get("issue_labels") or []
    family = str(labels[0]).split("/", 1)[0] if labels else "none"
    return f"{record.get('sampling_stratum')}|{record.get('language') or 'unknown'}|{family}"


def split_records(records: list[dict], holdout_fraction: float = 0.25, salt: str = "p0.5a") -> tuple[list[dict], list[dict]]:
    if not 0.2 <= holdout_fraction <= 0.3:
        raise ValueError("holdout_fraction must be between 0.20 and 0.30")
    development: list[dict] = []
    holdout: list[dict] = []
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if record.get("annotation_status") != "labeled":
            raise ValueError("final split requires labeled records only; P0.5a does not label records")
        groups[bucket(record)].append(record)
    total_target = round(len(records) * holdout_fraction)
    allocations: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    for key, group_records in groups.items():
        desired = len(group_records) * holdout_fraction
        base = min(max(0, int(desired)), max(0, len(group_records) - 1))
        allocations[key] = base
        remainders.append((desired - int(desired), key))
    remaining = total_target - sum(allocations.values())
    for _, key in sorted(remainders, reverse=True):
        if remaining <= 0:
            break
        if allocations[key] < len(groups[key]) - 1:
            allocations[key] += 1
            remaining -= 1
    for key, group_records in groups.items():
        ranked = sorted(group_records, key=lambda item: hashlib.sha256(f"{salt}:{item['sample_id']}".encode()).hexdigest())
        holdout.extend(ranked[:allocations[key]])
        development.extend(ranked[allocations[key]:])
    development.sort(key=lambda item: item["sample_id"])
    holdout.sort(key=lambda item: item["sample_id"])
    return development, holdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Dev/Holdout split after human annotation")
    parser.add_argument("--input", required=True)
    parser.add_argument("--dev-output", required=True)
    parser.add_argument("--holdout-output", required=True)
    parser.add_argument("--holdout-fraction", type=float, default=0.25)
    parser.add_argument("--salt", default="p0.5a")
    args = parser.parse_args()
    development, holdout = split_records(read_jsonl(args.input), args.holdout_fraction, args.salt)
    write_jsonl(args.dev_output, development)
    write_jsonl(args.holdout_output, holdout)
    print(json.dumps({"development": len(development), "holdout": len(holdout), "holdout_fraction": args.holdout_fraction}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
