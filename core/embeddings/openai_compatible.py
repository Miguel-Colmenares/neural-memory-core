"""Embeddings mediante cualquier API compatible con ``POST /v1/embeddings``.

Sirve para OpenAI y para servidores compatibles (Ollama, LM Studio, vLLM...).
ADVERTENCIA: un proveedor en la nube puede tener costo y recibe el texto de
los recuerdos. Solo se activa si el usuario lo configura explícitamente.
"""

from __future__ import annotations

import math

import httpx

from core.embeddings.base import EmbeddingError, EmbeddingProvider

DEFAULT_MODEL = "text-embedding-3-small"


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    name = "openai"
    duplicate_threshold = 0.93
    related_threshold = 0.55
    min_relevance = 0.25
    semantic = True
    external = True

    def __init__(
        self,
        api_base: str,
        api_key: str = "",
        model: str = "",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model or DEFAULT_MODEL
        self._url = api_base.rstrip("/") + "/embeddings"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout
        self._transport = transport

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            for start in range(0, len(texts), 64):
                batch = texts[start : start + 64]
                payload = {"model": self.model, "input": batch, "dimensions": self.dim}
                try:
                    response = client.post(self._url, json=payload, headers=self._headers)
                    response.raise_for_status()
                    data = sorted(response.json()["data"], key=lambda item: item["index"])
                except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                    raise EmbeddingError(f"Fallo del proveedor de embeddings: {exc}") from exc
                for item in data:
                    values = [float(v) for v in item["embedding"]]
                    norm = math.sqrt(sum(v * v for v in values)) or 1.0
                    vectors.append([v / norm for v in values])
        if len(vectors) != len(texts):
            raise EmbeddingError("El proveedor devolvió un número de vectores inesperado.")
        return self._check(vectors)
