"""Embeddings semánticos locales y gratuitos con FastEmbed (ONNX, sin GPU).

Requiere ``pip install '.[local-embeddings]'``. La primera ejecución descarga
el modelo (~220 MB) desde Hugging Face; después funciona sin conexión.
"""

from __future__ import annotations

import math
import threading

from core.embeddings.base import EmbeddingError, EmbeddingProvider

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class FastEmbedProvider(EmbeddingProvider):
    name = "fastembed"
    duplicate_threshold = 0.93
    related_threshold = 0.6
    min_relevance = 0.3
    semantic = True
    external = False

    def __init__(self, model: str = "", cache_dir: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._cache_dir = cache_dir
        self._engine = None
        self._lock = threading.Lock()

    def _load(self):
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    try:
                        from fastembed import TextEmbedding
                    except ImportError as exc:  # pragma: no cover - depende del entorno
                        raise EmbeddingError(
                            "Falta el paquete 'fastembed'. Instala el extra con "
                            "pip install '.[local-embeddings]' o usa "
                            "NMC_EMBEDDING_PROVIDER=hashing."
                        ) from exc
                    try:
                        self._engine = TextEmbedding(self.model, cache_dir=self._cache_dir)
                    except Exception as exc:
                        raise EmbeddingError(
                            f"No se pudo cargar el modelo local '{self.model}': {exc}"
                        ) from exc
        return self._engine

    def embed(self, texts: list[str]) -> list[list[float]]:
        engine = self._load()
        vectors = []
        for raw in engine.embed(texts):
            values = [float(v) for v in raw]
            norm = math.sqrt(sum(v * v for v in values)) or 1.0
            vectors.append([v / norm for v in values])
        return self._check(vectors)
