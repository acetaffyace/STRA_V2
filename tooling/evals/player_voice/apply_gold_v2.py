"""Create the human-approved P0.5c Gold v2 without touching v1."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


CLEAR_ASPECT_IDS = {
    "pv-1172470-231768442",
    "pv-4162040-232740798",
    "pv-4162040-232989490",
    "pv-1172470-232155751",
    "pv-4162040-233002020",
    "pv-2868840-232792409",
    "pv-2584270-233573481",
    "pv-4162040-232942889",
    "pv-4162040-233306549",
    "pv-4162040-232967794",
    "pv-1172470-233023949",
    "pv-2868840-232996219",
    "pv-1172470-232959876",
}

# The audit contains 16 candidates. Keep the explicit mapping here so that
# the v1 -> v2 transformation is reviewable and cannot silently broaden scope.
EXPLICIT_ACTIONS = {
    **{sample_id: "clear_aspect_praise" for sample_id in CLEAR_ASPECT_IDS},
    "pv-2868840-233323994": "watcher_omission_complaint_and_request",
    "pv-2584270-233528988": "unspecified_minor_issue_not_taxonomy_specific",
    "pv-2868840-233307187": "retain_mild_progression_issue",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8")


def apply_action(record: dict, action: str) -> dict:
    updated = copy.deepcopy(record)
    gold = updated["gold"]
    if action == "clear_aspect_praise":
        gold["issue_present"] = False
        gold["issue_labels"] = []
    elif action == "watcher_omission_complaint_and_request":
        gold["issue_present"] = True
        gold["issue_labels"] = ["content_design/narrative_characters"]
        gold["request_present"] = True
        gold["request_labels"] = ["content_design/narrative_characters"]
    elif action == "unspecified_minor_issue_not_taxonomy_specific":
        gold["issue_present"] = False
        gold["issue_labels"] = []
    elif action == "retain_mild_progression_issue":
        return updated
    else:  # pragma: no cover
        raise ValueError(f"unknown action: {action}")

    updated["correction_reason"] = "issue_semantics_alignment"
    updated["correction_source"] = "human_adjudication_p0.5cv"
    updated["previous_gold_version"] = "p0.5c-gold-verified-v1"
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--v2", type=Path, required=True)
    parser.add_argument("--diff", type=Path, required=True)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    candidate_ids = {item["sample_id"] for item in audit["candidates"]}
    if candidate_ids != set(EXPLICIT_ACTIONS):
        raise ValueError("explicit adjudication mapping does not exactly match audit candidates")

    v1 = load_jsonl(args.v1)
    v2 = []
    changed = []
    for record in v1:
        action = EXPLICIT_ACTIONS.get(record["sample_id"])
        updated = apply_action(record, action) if action else copy.deepcopy(record)
        v2.append(updated)
        if updated != record:
            changed.append({
                "sample_id": record["sample_id"],
                "fields_before": {"gold": record["gold"]},
                "fields_after": {"gold": updated["gold"]},
                "human_approved_reason": action,
            })

    if len(v1) != 150 or len(v2) != len(v1):
        raise ValueError("Gold record count changed")
    dump_jsonl(args.v2, v2)
    args.diff.write_text(json.dumps({
        "diff_version": "p0.5c-gold-v1-to-v2",
        "source_gold": str(args.v1),
        "target_gold": str(args.v2),
        "human_reviewed_candidate_count": len(candidate_ids),
        "changed_record_count": len(changed),
        "unchanged_reviewed_record_ids": ["pv-2868840-233307187"],
        "changes": changed,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(v2), "reviewed": len(candidate_ids), "changed": len(changed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
