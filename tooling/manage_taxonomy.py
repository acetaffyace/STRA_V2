"""Manage the independent, human-governed taxonomy registry (Stage 3D).

The CLI intentionally exposes separate plan, validate, apply, and publish
actions.  It never calls an LLM and never changes the classifier taxonomy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from senti_next import db  # noqa: E402
from senti_next.taxonomy_governance import (  # noqa: E402
    activate_snapshot,
    apply_change_set,
    activation_history,
    current_active_snapshot,
    diff_taxonomies,
    get_taxonomy_snapshot,
    list_eligible_candidates,
    plan_add_topic,
    publish_snapshot,
    taxonomy_status,
    trace_taxonomy_topic,
    validate_change_set,
)


def _print(value) -> None:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))


def _snapshot(identifier: str):
    return get_taxonomy_snapshot(identifier)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="SQLite URL/path is read from DATABASE_URL by the application")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("status")
    show = commands.add_parser("show")
    show.add_argument("--version", required=True)
    commands.add_parser("list-candidates")

    plan = commands.add_parser("plan-add")
    plan.add_argument("--candidate-id", required=True)
    plan.add_argument("--base-version", default="sentinext-taxonomy-v1")
    plan.add_argument("--canonical-key", required=True)
    plan.add_argument("--display-name", required=True)
    plan.add_argument("--description", required=True)
    plan.add_argument("--operator", required=True)
    plan.add_argument("--parent-key")

    validate = commands.add_parser("validate")
    validate.add_argument("--change-set-id", required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--change-set-id", required=True)

    publish = commands.add_parser("publish")
    publish.add_argument("--version", required=True)
    publish.add_argument("--operator", required=True)
    publish.add_argument("--reason", default="publish")

    diff = commands.add_parser("diff")
    diff.add_argument("--from", dest="from_version", required=True)
    diff.add_argument("--to", dest="to_version", required=True)

    commands.add_parser("history")
    activate = commands.add_parser("activate")
    activate.add_argument("--version", required=True)
    activate.add_argument("--operator", required=True)
    activate.add_argument("--reason", default="activate")

    trace = commands.add_parser("trace")
    trace.add_argument("--version", required=True)
    trace.add_argument("--topic-id")
    trace.add_argument("--canonical-key")

    args = parser.parse_args(argv)
    if args.database:
        # Keep the application as the single database configuration owner.
        import os
        os.environ["DATABASE_URL"] = args.database
    db.init_db()

    if args.command == "status":
        _print(taxonomy_status())
    elif args.command == "show":
        _print(_snapshot(args.version))
    elif args.command == "list-candidates":
        _print(list_eligible_candidates())
    elif args.command == "plan-add":
        _print(plan_add_topic(candidate_id=args.candidate_id, base_version=args.base_version, canonical_key=args.canonical_key, display_name=args.display_name, description=args.description, operator=args.operator, parent_key=args.parent_key))
    elif args.command == "validate":
        _print(validate_change_set(args.change_set_id))
    elif args.command == "apply":
        _print(apply_change_set(args.change_set_id))
    elif args.command == "publish":
        _print(publish_snapshot(args.version, operator=args.operator, reason=args.reason))
    elif args.command == "diff":
        _print(diff_taxonomies(args.from_version, args.to_version))
    elif args.command == "history":
        _print(activation_history())
    elif args.command == "activate":
        _print(activate_snapshot(args.version, operator=args.operator, reason=args.reason))
    elif args.command == "trace":
        if bool(args.topic_id) == bool(args.canonical_key):
            parser.error("trace requires exactly one of --topic-id or --canonical-key")
        snapshot = _snapshot(args.version)
        topic_id = args.topic_id
        if args.canonical_key:
            matches = [topic.topic_id for topic in snapshot.topics if topic.canonical_key == args.canonical_key]
            if not matches:
                raise ValueError("topic_not_found")
            topic_id = matches[0]
        _print(trace_taxonomy_topic(topic_id, snapshot.snapshot_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
