"""Embeddings locales por *feature hashing*.

No necesita descargas, claves ni GPU, y es determinista. Representa cada texto
con sus palabras (con raíz ligera), pares de palabras y n-gramas de caracteres.

Limitación honesta: mide parecido léxico y morfológico (plurales, conjugaciones,
erratas, palabras compartidas), **no** entiende sinónimos ni paráfrasis. Para
búsqueda por significado real usa el proveedor ``fastembed`` u ``openai``.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter

from core.embeddings.base import EmbeddingProvider
from core.textutils import stem, tokenize


def _bucket(feature: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % dim, 1.0 if (value >> 63) & 1 else -1.0


class HashingEmbeddingProvider(EmbeddingProvider):
    name = "hashing"
    model = "nmc-hashing-v1"
    duplicate_threshold = 0.90
    related_threshold = 0.4
    min_relevance = 0.2
    semantic = False
    external = False

    WORD_WEIGHT = 1.0
    BIGRAM_WEIGHT = 0.6
    CHAR_WEIGHT = 0.35

    def _features(self, text: str) -> Counter[str]:
        tokens = tokenize(text)
        features: Counter[str] = Counter()
        stems = [stem(t) for t in tokens]
        for s in stems:
            features[f"w:{s}"] += self.WORD_WEIGHT
        for a, b in zip(stems, stems[1:], strict=False):
            features[f"b:{a}_{b}"] += self.BIGRAM_WEIGHT
        for token in tokens:
            padded = f"<{token}>"
            for n in (3, 4):
                for i in range(len(padded) - n + 1):
                    features[f"c:{padded[i : i + n]}"] += self.CHAR_WEIGHT / 2
        return features

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        features = self._features(text)
        if not features:
            features = Counter({"__empty__": 1.0})
        for feature, weight in features.items():
            index, sign = _bucket(feature, self.dim)
            scaled = 1.0 + math.log(weight) if weight > 1 else weight
            vector[index] += sign * scaled
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0] = 1.0
            norm = 1.0
        return [v / norm for v in vector]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(t) for t in texts]
