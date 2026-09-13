"""Build an optional Stage 3A semantic index for an immutable Research run.

Normal commands never download a model.  Use ``--install-model`` explicitly
once, then run with ``--run-id``.  ``--fake`` is useful for offline fixture
checks and never claims semantic model quality.
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
from senti_next.embedding_backend import (  # noqa: E402
    FakeEmbeddingBackend,
    LocalONNXEmbeddingBackend,
    default_model_cache_dir,
    inspect_local_model,
    install_default_model,
)
from senti_next.semantic_index import build_semantic_index_for_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="immutable general-analysis run id")
    parser.add_argument("--install-model", action="store_true", help="explicitly download the pinned optional E5 ONNX model")
    parser.add_argument("--fake", action="store_true", help="use deterministic test backend instead of local E5")
    parser.add_argument("--model-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.install_model:
        directory = install_default_model(model_dir=args.model_dir)
        print(json.dumps({"status": "installed", "model_dir": str(directory)}, sort_keys=True))
    if not args.run_id:
        return 0

    db.init_db()
    if args.fake:
        backend = FakeEmbeddingBackend()
    else:
        availability = inspect_local_model(args.model_dir)
        if availability.get("status") != "ready":
            print(json.dumps({"status": "unavailable", "reason": "embedding_model_unavailable", **availability}, sort_keys=True))
            return 2
        backend = LocalONNXEmbeddingBackend(model_dir=args.model_dir or default_model_cache_dir())
    result = build_semantic_index_for_run(args.run_id, backend=backend)
    print(json.dumps(result.summary, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
