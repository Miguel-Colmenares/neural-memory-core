"""Recuperación híbrida.

1. Búsqueda textual (PostgreSQL FTS).
2. Búsqueda semántica (pgvector).
3. Filtros (fechas, proyectos, tipos, etiquetas...) aplicados a ambas.
4. Expansión por relaciones del grafo de conocimiento.
5. Reordenamiento: fusión RRF + importancia + actualidad.

La fórmula está en ``docs/architecture/recuperacion.md`` y cada resultado
lleva el desglose de su puntuación.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import Memory
from core.embeddings.base import EmbeddingError, EmbeddingProvider
from core.knowledge_graph.service import KnowledgeGraph
from core.memory_engine.filters import MemoryFilters
from core.retrieval.semantic_search import SemanticHit, semantic_search
from core.retrieval.text_search import TextHit, text_search
from core.textutils import excerpt

RRF_K = 60
TEXT_WEIGHT = 1.0
SEMANTIC_WEIGHT = 1.0
RELATION_DISCOUNT = 0.5
RECENCY_HALF_LIFE_DAYS = 120.0
MODES = ("hybrid", "text", "semantic")


@dataclass
class SearchResult:
    memory: Memory
    score: float
    matched_by: list[str] = field(default_factory=list)  # text | semantic | relation | filter
    text_rank: float | None = None
    semantic_similarity: float | None = None
    excerpt: str = ""
    via_relation: dict[str, Any] | None = None
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class SearchResponse:
    query: str
    mode: str
    results: list[SearchResult]
    total_candidates: int
    filters: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    embedding: dict[str, Any] = field(default_factory=dict)


def recency_score(moment: datetime, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    age_days = max((now - moment).total_seconds() / 86400.0, 0.0)
    return math.exp(-math.log(2) * age_days / RECENCY_HALF_LIFE_DAYS)


def fuse(
    text_hits: list[TextHit],
    semantic_hits: list[SemanticHit],
    *,
    text_weight: float = TEXT_WEIGHT,
    semantic_weight: float = SEMANTIC_WEIGHT,
) -> dict[uuid.UUID, float]:
    """Reciprocal Rank Fusion normalizada a 0..1."""
    scores: dict[uuid.UUID, float] = {}
    for rank, hit in enumerate(text_hits, start=1):
        scores[hit.memory_id] = scores.get(hit.memory_id, 0.0) + text_weight / (RRF_K + rank)
    for rank, hit in enumerate(semantic_hits, start=1):
        scores[hit.memory_id] = scores.get(hit.memory_id, 0.0) + semantic_weight / (RRF_K + rank)
    best_possible = (text_weight + semantic_weight) / (RRF_K + 1)
    return {mid: value / best_possible for mid, value in scores.items()}


class HybridRetriever:
    def __init__(self, session: Session, embedder: EmbeddingProvider):
        self.session = session
        self.embedder = embedder
        self.graph = KnowledgeGraph(session)

    def search(
        self,
        query: str,
        filters: MemoryFilters | None = None,
        *,
        mode: str = "hybrid",
        limit: int = 10,
        include_related: bool = True,
        recency_weight: float = 0.08,
        importance_weight: float = 0.12,
        fts_terms: list[str] | None = None,
    ) -> SearchResponse:
        if mode not in MODES:
            raise ValueError(f"Modo no válido: {mode}")
        filters = filters or MemoryFilters()
        query = (query or "").strip()
        warnings: list[str] = []
        pool = max(limit * 4, 30)

        text_hits: list[TextHit] = []
        semantic_hits: list[SemanticHit] = []
        if query and mode in ("hybrid", "text"):
            text_hits = text_search(self.session, query, filters, limit=pool, terms=fts_terms)
        if query and mode in ("hybrid", "semantic"):
            try:
                vector = self.embedder.embed_one(query)
                raw = semantic_search(self.session, self.embedder, vector, filters, limit=pool)
                text_ids = {h.memory_id for h in text_hits}
                # Un resultado solo semántico debe superar el mínimo del proveedor.
                semantic_hits = [
                    h
                    for h in raw
                    if h.similarity >= self.embedder.min_relevance or h.memory_id in text_ids
                ]
            except EmbeddingError as exc:
                warnings.append(f"Búsqueda semántica no disponible: {exc}")

        fused = fuse(text_hits, semantic_hits)
        text_by_id = {h.memory_id: h for h in text_hits}
        semantic_by_id = {h.memory_id: h for h in semantic_hits}
        memories = self._load(list(fused))

        relevance_weight = max(1.0 - recency_weight - importance_weight, 0.0)
        results: dict[uuid.UUID, SearchResult] = {}
        for memory_id, relevance in fused.items():
            memory = memories.get(memory_id)
            if memory is None:
                continue
            results[memory_id] = self._build(
                memory,
                relevance,
                relevance_weight,
                importance_weight,
                recency_weight,
                text_by_id.get(memory_id),
                semantic_by_id.get(memory_id),
            )

        if include_related and results:
            self._expand(results, filters, limit)

        ordered = sorted(
            results.values(), key=lambda r: (r.score, r.memory.updated_at), reverse=True
        )
        return SearchResponse(
            query=query,
            mode=mode,
            results=ordered[:limit],
            total_candidates=len(ordered),
            filters=filters.describe(),
            warnings=warnings,
            embedding=self.embedder.describe(),
        )

    # ------------------------------------------------------------------ internos
    def _load(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, Memory]:
        if not ids:
            return {}
        return {m.id: m for m in self.session.scalars(select(Memory).where(Memory.id.in_(ids)))}

    def _build(
        self,
        memory: Memory,
        relevance: float,
        relevance_weight: float,
        importance_weight: float,
        recency_weight: float,
        text_hit: TextHit | None,
        semantic_hit: SemanticHit | None,
    ) -> SearchResult:
        importance = (memory.importance - 1) / 4.0
        recency = recency_score(memory.updated_at)
        breakdown = {
            "relevance": round(relevance_weight * relevance, 4),
            "importance": round(importance_weight * importance, 4),
            "recency": round(recency_weight * recency, 4),
        }
        matched = []
        if text_hit:
            matched.append("text")
        if semantic_hit:
            matched.append("semantic")
        if text_hit and text_hit.headline:
            snippet = text_hit.headline
        elif semantic_hit:
            snippet = excerpt(semantic_hit.chunk_text)
        else:
            snippet = excerpt(memory.content)
        return SearchResult(
            memory=memory,
            score=round(sum(breakdown.values()), 4),
            matched_by=matched,
            text_rank=round(text_hit.rank, 4) if text_hit else None,
            semantic_similarity=round(semantic_hit.similarity, 4) if semantic_hit else None,
            excerpt=snippet,
            score_breakdown=breakdown,
        )

    def _expand(
        self, results: dict[uuid.UUID, SearchResult], filters: MemoryFilters, limit: int
    ) -> None:
        """Añade vecinos del grafo de los mejores resultados, con puntuación reducida."""
        top = sorted(results.values(), key=lambda r: r.score, reverse=True)[: min(limit, 5)]
        neighbors = self.graph.neighbors([r.memory.id for r in top])
        allowed = self._passing_filters(
            {n.memory.id for group in neighbors.values() for n in group}, filters
        )
        for parent in top:
            for neighbor in neighbors.get(parent.memory.id, []):
                memory = neighbor.memory
                if memory.id in results or memory.id not in allowed:
                    continue
                confidence = neighbor.relation.confidence
                factor = RELATION_DISCOUNT * (confidence if confidence is not None else 1.0)
                score = round(parent.score * factor, 4)
                results[memory.id] = SearchResult(
                    memory=memory,
                    score=score,
                    matched_by=["relation"],
                    excerpt=excerpt(memory.content),
                    via_relation={
                        "from_memory_id": str(parent.memory.id),
                        "relation_type": neighbor.relation.relation_type,
                        "origin": neighbor.relation.origin,
                        "confidence": confidence,
                        "direction": neighbor.direction,
                    },
                    score_breakdown={"relation": score},
                )

    def _passing_filters(self, ids: set[uuid.UUID], filters: MemoryFilters) -> set[uuid.UUID]:
        if not ids:
            return set()
        stmt = filters.apply(select(Memory.id).where(Memory.id.in_(ids)))
        return set(self.session.scalars(stmt))
