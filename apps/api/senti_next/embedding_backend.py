"""Embedding backends for the Stage 3A semantic index.

The semantic index depends on this small provider-neutral interface.  The
production local backend is optional and imports ONNX/tokenizer dependencies
only when it is instantiated; deterministic tests use ``FakeEmbeddingBackend``.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np


DEFAULT_MODEL_ID = "intfloat/multilingual-e5-small"
# This is an immutable model revision, never the mutable Hugging Face ``main``.
# Installers may override it explicitly when a newer audited revision is chosen.
DEFAULT_MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
DEFAULT_DIMENSIONS = 384
DEFAULT_MAX_TOKENS = 512
DEFAULT_POOLING = "attention_mask_mean"
DEFAULT_NORMALIZATION = "l2"
DEFAULT_PREFIX_POLICY = "query"


@dataclass(frozen=True)
class EmbeddingModelIdentity:
    provider: str
    model_id: str
    model_revision: str
    artifact_sha256: str
    dimensions: int
    max_tokens: int
    pooling: str = DEFAULT_POOLING
    normalization: str = DEFAULT_NORMALIZATION
    prefix_policy: str = DEFAULT_PREFIX_POLICY

    def __post_init__(self) -> None:
        if not self.model_revision or self.model_revision.lower() == "main":
            raise ValueError("model_revision must be an immutable revision, not main")
        if self.dimensions <= 0 or self.max_tokens <= 0:
            raise ValueError("dimensions and max_tokens must be positive")
        if self.pooling != DEFAULT_POOLING:
            raise ValueError(f"unsupported pooling: {self.pooling}")
        if self.normalization != DEFAULT_NORMALIZATION:
            raise ValueError(f"unsupported normalization: {self.normalization}")
        if self.prefix_policy != DEFAULT_PREFIX_POLICY:
            raise ValueError(f"unsupported prefix policy: {self.prefix_policy}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "artifact_sha256": self.artifact_sha256,
            "dimensions": self.dimensions,
            "max_tokens": self.max_tokens,
            "pooling": self.pooling,
            "normalization": self.normalization,
            "prefix_policy": self.prefix_policy,
        }


class EmbeddingBackend(Protocol):
    @property
    def identity(self) -> EmbeddingModelIdentity:
        ...

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Return one float32 vector per text."""
        ...


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (values / norms).astype(np.float32, copy=False)


class FakeEmbeddingBackend:
    """Deterministic test backend; not a semantic-quality substitute."""

    def __init__(self, *, dimensions: int = DEFAULT_DIMENSIONS, model_revision: str = "fake-test-revision") -> None:
        artifact = hashlib.sha256(f"fake:{dimensions}:{model_revision}".encode()).hexdigest()
        self._identity = EmbeddingModelIdentity(
            provider="fake",
            model_id="fake/multilingual-e5-small",
            model_revision=model_revision,
            artifact_sha256=artifact,
            dimensions=dimensions,
            max_tokens=DEFAULT_MAX_TOKENS,
        )

    @property
    def identity(self) -> EmbeddingModelIdentity:
        return self._identity

    def tokenize(self, text: str) -> list[str]:
        return text.split()

    def decode(self, tokens: Sequence[str]) -> str:
        return " ".join(tokens)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        rows: list[np.ndarray] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            values = np.empty(self.identity.dimensions, dtype=np.float32)
            for index in range(self.identity.dimensions):
                byte = digest[index % len(digest)]
                values[index] = (byte / 127.5) - 1.0
            rows.append(values)
        if not rows:
            return np.empty((0, self.identity.dimensions), dtype=np.float32)
        return _l2_normalize(np.stack(rows))


class LocalONNXEmbeddingBackend:
    """Local ONNX Runtime backend for multilingual-e5-small.

    Dependencies and model files are deliberately loaded lazily.  Importing
    STRA does not require a model or an embedding runtime.
    """

    def __init__(
        self,
        *,
        model_dir: str | Path,
        model_revision: str = DEFAULT_MODEL_REVISION,
        artifact_sha256: str | None = None,
        model_filename: str = "model.onnx",
    ) -> None:
        self.model_dir = Path(model_dir).expanduser()
        self.model_filename = model_filename
        artifact_path = self.model_dir / model_filename
        if not artifact_path.exists() and model_filename == "model.onnx":
            artifact_path = self.model_dir / "onnx" / model_filename
        if not artifact_path.exists():
            raise FileNotFoundError(f"embedding model artifact not found: {artifact_path}")
        actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if artifact_sha256 and actual_sha != artifact_sha256:
            raise ValueError("embedding model artifact checksum mismatch")
        self._identity = EmbeddingModelIdentity(
            provider="local_onnx",
            model_id=DEFAULT_MODEL_ID,
            model_revision=model_revision,
            artifact_sha256=actual_sha,
            dimensions=DEFAULT_DIMENSIONS,
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover - exercised by availability checks
            raise RuntimeError("onnxruntime and tokenizers are required for the local backend") from exc
        tokenizer_path = self.model_dir / "tokenizer.json"
        if not tokenizer_path.exists():
            tokenizer_path = self.model_dir / "onnx" / "tokenizer.json"
        if not tokenizer_path.exists():
            raise FileNotFoundError(f"tokenizer artifact not found: {tokenizer_path}")
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._session = ort.InferenceSession(str(artifact_path), providers=["CPUExecutionProvider"])

    @property
    def identity(self) -> EmbeddingModelIdentity:
        return self._identity

    def tokenize(self, text: str) -> list[int]:
        return self._tokenizer.encode(text, add_special_tokens=False).ids

    def decode(self, tokens: Sequence[int]) -> str:
        return self._tokenizer.decode(list(tokens), skip_special_tokens=True)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.identity.dimensions), dtype=np.float32)
        encodings = [self._tokenizer.encode(text, add_special_tokens=True) for text in texts]
        max_len = min(self.identity.max_tokens, max(len(item.ids) for item in encodings))
        pad_id = self._tokenizer.token_to_id("<pad>") or 0
        input_ids = np.full((len(encodings), max_len), pad_id, dtype=np.int64)
        attention = np.zeros((len(encodings), max_len), dtype=np.int64)
        for row, encoded in enumerate(encodings):
            ids = encoded.ids[:max_len]
            input_ids[row, : len(ids)] = ids
            attention[row, : len(ids)] = 1
        inputs = {"input_ids": input_ids, "attention_mask": attention}
        names = {item.name for item in self._session.get_inputs()}
        if "token_type_ids" in names:
            inputs["token_type_ids"] = np.zeros_like(input_ids)
        outputs = self._session.run(None, inputs)
        hidden = np.asarray(outputs[0], dtype=np.float32)
        mask = attention.astype(np.float32)[..., None]
        pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1.0)
        return _l2_normalize(pooled)


def default_model_cache_dir() -> Path:
    try:
        from platformdirs import user_cache_dir
        return Path(user_cache_dir("STRA", "acetaffyace")) / "models" / "multilingual-e5-small"
    except ImportError:  # pragma: no cover
        return Path.home() / ".cache" / "stra" / "models" / "multilingual-e5-small"


def inspect_local_model(model_dir: str | Path | None = None) -> dict[str, Any]:
    """Return an explicit model availability state without downloading anything."""
    directory = Path(model_dir) if model_dir else default_model_cache_dir()
    artifact = directory / "model.onnx"
    if not artifact.exists():
        artifact = directory / "onnx" / "model.onnx"
    tokenizer = directory / "tokenizer.json"
    if not tokenizer.exists():
        tokenizer = directory / "onnx" / "tokenizer.json"
    if not artifact.exists() or not tokenizer.exists():
        return {"status": "not_installed", "model_id": DEFAULT_MODEL_ID, "model_revision": DEFAULT_MODEL_REVISION}
    try:
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest_path = directory / "model_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return {"status": "load_failed", "model_id": DEFAULT_MODEL_ID, "reason": f"invalid model manifest: {exc}"}
            if manifest.get("model_revision") != DEFAULT_MODEL_REVISION or manifest.get("artifact_sha256") != digest:
                return {
                    "status": "load_failed",
                    "model_id": DEFAULT_MODEL_ID,
                    "reason": "model artifact checksum or revision does not match manifest",
                }
        return {
            "status": "ready",
            "model_id": DEFAULT_MODEL_ID,
            "model_revision": DEFAULT_MODEL_REVISION,
            "artifact_filename": str(artifact.relative_to(directory)),
            "artifact_sha256": digest,
            "cache_dir": str(directory),
        }
    except OSError as exc:
        return {"status": "load_failed", "model_id": DEFAULT_MODEL_ID, "reason": str(exc)}


def install_default_model(*, model_dir: str | Path | None = None, revision: str = DEFAULT_MODEL_REVISION) -> Path:
    """Explicitly download the optional model; never called by normal analysis."""
    if not revision or revision == "main":
        raise ValueError("an immutable model revision is required")
    directory = Path(model_dir) if model_dir else default_model_cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("huggingface_hub is required to install the local model") from exc
    snapshot_download(
        repo_id=DEFAULT_MODEL_ID,
        revision=revision,
        local_dir=str(directory),
        allow_patterns=["onnx/model.onnx", "onnx/tokenizer.json", "onnx/tokenizer_config.json", "onnx/special_tokens_map.json"],
    )
    artifact = directory / "onnx" / "model.onnx"
    if not artifact.exists():
        artifact = directory / "model.onnx"
    if not artifact.exists():
        raise FileNotFoundError("downloaded model did not contain an ONNX model.onnx artifact")
    manifest = {
        "model_id": DEFAULT_MODEL_ID,
        "model_revision": revision,
        "artifact_filename": str(artifact.relative_to(directory)),
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }
    (directory / "model_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
    return directory
