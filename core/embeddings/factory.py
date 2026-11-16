"""Selección del proveedor de embeddings según la configuración."""

from __future__ import annotations

from functools import lru_cache

from core.config import Settings, get_settings
from core.embeddings.base import EmbeddingProvider
from core.embeddings.hashing import HashingEmbeddingProvider


def build_embedder(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "hashing":
        return HashingEmbeddingProvider()
    if settings.embedding_provider == "fastembed":
        from core.embeddings.fastembed_provider import FastEmbedProvider

        return FastEmbedProvider(model=settings.embedding_model)
    if settings.embedding_provider == "openai":
        from core.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider

        return OpenAICompatibleEmbeddingProvider(
            api_base=settings.embedding_api_base,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )
    raise ValueError(f"Proveedor de embeddings desconocido: {settings.embedding_provider}")


@lru_cache
def get_embedder() -> EmbeddingProvider:
    return build_embedder(get_settings())
