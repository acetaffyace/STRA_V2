from __future__ import annotations

import os

import numpy as np
import pytest

from apps.api.senti_next.embedding_backend import LocalONNXEmbeddingBackend, default_model_cache_dir, inspect_local_model


@pytest.mark.skipif(
    os.getenv("STRA_RUN_REAL_EMBEDDING_SMOKE") != "1",
    reason="opt-in real multilingual E5 smoke; CI uses FakeEmbeddingBackend",
)
def test_real_multilingual_e5_embedding_smoke() -> None:
    availability = inspect_local_model()
    if availability.get("status") != "ready":
        pytest.skip(f"local embedding model unavailable: {availability}")
    backend = LocalONNXEmbeddingBackend(model_dir=default_model_cache_dir())
    texts = [
        "query: game crashes after update",
        "query: 更新后游戏崩溃",
        "query: アップデート後にゲームがクラッシュする",
        "query: the soundtrack is beautiful",
    ]
    vectors = backend.encode(texts)
    assert vectors.shape == (4, 384)
    assert np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3)
    crash = vectors[:3].mean(axis=0)
    crash /= np.linalg.norm(crash)
    assert float(np.dot(crash, vectors[3])) < float(np.dot(crash, vectors[0]))

