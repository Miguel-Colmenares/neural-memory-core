import json
import math

import httpx
import pytest

from core.config import Settings
from core.embeddings.base import EmbeddingError
from core.embeddings.factory import build_embedder
from core.embeddings.hashing import HashingEmbeddingProvider
from core.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hashing_is_deterministic_and_normalized():
    provider = HashingEmbeddingProvider()
    a = provider.embed_one("Decidimos usar PostgreSQL")
    b = provider.embed_one("Decidimos usar PostgreSQL")
    assert a == b
    assert len(a) == 384
    assert math.isclose(math.sqrt(sum(v * v for v in a)), 1.0, rel_tol=1e-9)


def test_hashing_ranks_related_text_higher():
    provider = HashingEmbeddingProvider()
    query = provider.embed_one("decisiones sobre la base de datos PostgreSQL")
    related = provider.embed_one("Tomamos la decisión de usar PostgreSQL como base de datos")
    unrelated = provider.embed_one("Receta de pan con masa madre y harina integral")
    assert cosine(query, related) > provider.related_threshold
    assert cosine(query, related) > cosine(query, unrelated) + 0.2
    assert cosine(query, unrelated) < provider.min_relevance


def test_hashing_handles_morphology_and_typos():
    provider = HashingEmbeddingProvider()
    a = provider.embed_one("proyectos de investigación")
    b = provider.embed_one("proyecto de investigacion")
    assert cosine(a, b) > 0.7


def test_hashing_near_duplicate_threshold():
    provider = HashingEmbeddingProvider()
    a = provider.embed_one("La reunión con el equipo será el lunes a las diez de la mañana")
    b = provider.embed_one("La reunión con el equipo será el lunes a las diez de la mañana.")
    c = provider.embed_one("La reunión con el equipo será el martes por la tarde en la oficina")
    assert cosine(a, b) >= provider.duplicate_threshold
    assert cosine(a, c) < provider.duplicate_threshold


def test_hashing_empty_text_does_not_break():
    vector = HashingEmbeddingProvider().embed_one("   ")
    assert len(vector) == 384 and all(math.isfinite(v) for v in vector)


def test_hashing_declares_it_is_not_semantic():
    described = HashingEmbeddingProvider().describe()
    assert described["semantic"] is False and described["external"] is False


def _transport(dim: int, capture: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if capture is not None:
            capture.append((request, body))
        data = [
            {"index": i, "embedding": [float(i + 1)] + [0.0] * (dim - 1)}
            for i in range(len(body["input"]))
        ]
        return httpx.Response(200, json={"data": list(reversed(data))})

    return httpx.MockTransport(handler)


def test_openai_provider_sends_expected_request_and_normalizes():
    seen: list = []
    provider = OpenAICompatibleEmbeddingProvider(
        "https://example.test/v1", api_key="k", model="m", transport=_transport(384, seen)
    )
    vectors = provider.embed(["a", "b"])
    request, body = seen[0]
    assert str(request.url) == "https://example.test/v1/embeddings"
    assert request.headers["authorization"] == "Bearer k"
    assert body == {"model": "m", "input": ["a", "b"], "dimensions": 384}
    assert [v[0] for v in vectors] == [1.0, 1.0]  # normalizados y en el orden original


def test_openai_provider_rejects_wrong_dimensions():
    provider = OpenAICompatibleEmbeddingProvider(
        "https://example.test/v1", transport=_transport(768)
    )
    with pytest.raises(EmbeddingError, match="768"):
        provider.embed(["a"])


def test_openai_provider_wraps_http_errors():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "x"}))
    provider = OpenAICompatibleEmbeddingProvider("https://example.test/v1", transport=transport)
    with pytest.raises(EmbeddingError):
        provider.embed(["a"])


def test_factory_selects_provider():
    assert build_embedder(Settings(embedding_provider="hashing")).name == "hashing"
    provider = build_embedder(Settings(embedding_provider="openai", embedding_model="x"))
    assert provider.name == "openai" and provider.external is True
    assert build_embedder(Settings(embedding_provider="fastembed")).name == "fastembed"
