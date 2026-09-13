from __future__ import annotations

import os
import json

import numpy as np
import pytest

from apps.api.senti_next.embedding_backend import LocalONNXEmbeddingBackend, default_model_cache_dir, inspect_local_model
from apps.api.senti_next.semantic_discovery import HDBSCANDiscoveryBackend, SemanticDiscoveryContract, SemanticUnitRecord, build_semantic_discovery


@pytest.mark.skipif(os.getenv("STRA_RUN_REAL_DISCOVERY_SMOKE") != "1", reason="opt-in real Stage 3B smoke")
def test_real_multilingual_discovery_smoke() -> None:
    if inspect_local_model().get("status") != "ready":
        pytest.skip("Stage 3A E5 model is not installed")
    backend = LocalONNXEmbeddingBackend(model_dir=default_model_cache_dir())
    texts = [
        "game crashes after the latest update",
        "the game keeps crashing after the patch",
        "更新后游戏一直崩溃",
        "アップデート後にゲームがクラッシュする",
        "save file was corrupted after restarting",
        "my saved progress disappeared",
        "更新后存档损坏",
        "サーバーに接続できない",
        "the server connection keeps timing out",
        "multiplayer matchmaking is unavailable",
        "controller support feels excellent",
        "the soundtrack is beautiful",
        "pricing for the DLC is too high",
        "the story ending was moving",
        "localization has awkward wording",
        "a very unusual unrelated sentence about gardening",
    ]
    vectors = backend.encode([f"query: {text}" for text in texts])
    units = [SemanticUnitRecord(f"r{i}:0", f"r{i}", 0, vectors[i], f"hash-{i}", texts[i]) for i in range(len(texts))]
    metadata = {
        f"r{i}": {
            "review": text,
            "language": "schinese" if any(char >= "\u4e00" and char <= "\u9fff" for char in text) else "english",
            "voted_up": i % 2 == 0,
            "timestamp_created": 1_700_000_000 + i,
            "semantic_text_hash": f"hash-{i}",
        }
        for i, text in enumerate(texts)
    }
    report = build_semantic_discovery(
        units,
        semantic_index_id="real-smoke-index",
        research_run_id="real-smoke-run",
        population_fingerprint="real-smoke-population",
        semantic_index_fingerprint="real-smoke-fingerprint",
        contract=SemanticDiscoveryContract(min_cluster_size=3, rare_region_max_size=2),
        review_metadata=metadata,
        backend=HDBSCANDiscoveryBackend(),
    )
    crash_similarity = float(np.dot(vectors[0], vectors[2]))
    unrelated_similarity = float(np.dot(vectors[0], vectors[-1]))
    assert vectors.shape == (len(texts), 384)
    assert np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3)
    assert crash_similarity > unrelated_similarity
    assert report["indexed_review_n"] == len(texts)
    json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False)
