"""Add non-semantic batch metadata to already-paid prediction artifacts."""
from __future__ import annotations

import argparse

from .common import read_jsonl, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()
    records = read_jsonl(args.input)
    for index, record in enumerate(records):
        record["batch_index"] = index // max(1, args.batch_size)
        usage = dict(record.get("usage") or {})
        usage.setdefault("retries", 0)
        record["usage"] = usage
    write_jsonl(args.output, records)
    print({"records": len(records), "output": args.output})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
