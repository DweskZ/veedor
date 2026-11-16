"""Embedding adapters: a fastembed (ONNX, local) adapter and a deterministic fake for tests."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from veedor.core.settings import get_settings

# Verified against fastembed 0.9.1 `TextEmbedding.list_supported_models()`: multilingual, dim 256, licence
# MIT, 0.512 GB. A static (Model2Vec-style) embedding: no transformer forward pass, so it runs at tens of
# thousands of texts/s on CPU. Chosen over paraphrase-multilingual-MiniLM-L12-v2 (see docs/VECTOR_SEARCH.md).
MODEL_NAME = "minishlab/potion-multilingual-128M"
DIMENSION = 256
DEFAULT_BATCH_SIZE = 64


class EmbeddingPort(Protocol):
    model_name: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Unit-length float32 vectors, shape ``(len(texts), dimension)``, same order as `texts`."""
        ...


def normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return (matrix / np.where(norms == 0, 1.0, norms)).astype(np.float32)


def model_cache_dir() -> Path:
    return get_settings().data_dir / "models" / "fastembed"


class FastEmbedEmbedder:
    """`fastembed.TextEmbedding` with a project-local model cache. No network once the model is cached."""

    model_name = MODEL_NAME
    dimension = DIMENSION

    def __init__(
        self,
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        threads: int | None = None,
        parallel: int | None = None,
        cache_dir: Path | None = None,
        local_files_only: bool = False,
    ) -> None:
        """`local_files_only`: never contact the network (the API container has a read-only cache)."""
        from fastembed import TextEmbedding  # heavy import: only when embeddings are really needed

        self._batch_size = batch_size
        self._parallel = parallel
        self._model = TextEmbedding(
            model_name=MODEL_NAME,
            cache_dir=str(cache_dir or model_cache_dir()),
            threads=threads,
            local_files_only=local_files_only,
        )

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, DIMENSION), dtype=np.float32)
        vectors = self._model.embed(list(texts), batch_size=self._batch_size, parallel=self._parallel)
        return normalise(np.vstack(list(vectors)))


_TOKEN = re.compile(r"[a-z0-9áéíóúñü]+")


class FakeEmbedder:
    """Deterministic hashed bag-of-words embedder: same tokens give similar vectors. Tests only."""

    model_name = "fake-hash-embedder"

    def __init__(self, dimension: int = DIMENSION) -> None:
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in _TOKEN.findall(text.lower()):
                digest = hashlib.sha256(token.encode()).digest()
                out[row, int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
        return normalise(out)
