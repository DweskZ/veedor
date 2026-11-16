"""An embedder that remembers vectors by text: fact keys are the same for every process and question."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Protocol

import numpy as np


class EmbedderLike(Protocol):
    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


class CachedEmbedder:
    """Wraps an embedder built on first use (loading the model is the expensive part); bounded LRU."""

    def __init__(self, factory: Callable[[], EmbedderLike], max_entries: int = 20_000) -> None:
        self._factory = factory
        self._inner: EmbedderLike | None = None
        self._max = max_entries
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()

    def _embedder(self) -> EmbedderLike:
        with self._lock:
            if self._inner is None:
                self._inner = self._factory()
            return self._inner

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        with self._lock:
            found = {t: self._cache[t] for t in set(texts) if t in self._cache}
            for t in found:
                self._cache.move_to_end(t)
        missing = [t for t in dict.fromkeys(texts) if t not in found]
        if missing:
            vectors = self._embedder().embed(missing)
            with self._lock:
                for text, vector in zip(missing, vectors, strict=True):
                    found[text] = vector
                    self._cache[text] = vector
                while len(self._cache) > self._max:
                    self._cache.popitem(last=False)
        return np.vstack([found[t] for t in texts])
