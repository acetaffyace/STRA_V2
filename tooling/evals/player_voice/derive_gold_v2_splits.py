"""Derive Gold-v2 Dev/Holdout files using the frozen v1 split membership."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-v2", type=Path, required=True)
    parser.add_argument("--dev-v1", type=Path, required=True)
    parser.add_argument("--holdout-v1", type=Path, required=True)
    parser.add_argument("--dev-v2", type=Path, required=True)
    parser.add_argument("--holdout-v2", type=Path, required=True)
    args = parser.parse_args()
    gold = {row["sample_id"]: row for row in read_jsonl(args.gold_v2)}
    outputs = []
    for source, target in ((args.dev_v1, args.dev_v2), (args.holdout_v1, args.holdout_v2)):
        rows = [gold[row["sample_id"]] for row in read_jsonl(source)]
        write_jsonl(target, rows)
        outputs.append(len(rows))
    print(json.dumps({"dev": outputs[0], "holdout": outputs[1]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
