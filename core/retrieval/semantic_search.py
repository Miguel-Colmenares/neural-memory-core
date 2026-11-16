"""Búsqueda por similitud de embeddings (pgvector, distancia coseno)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import Memory, MemoryEmbedding
from core.embeddings.base import EmbeddingProvider
from core.memory_engine.filters import MemoryFilters


@dataclass
class SemanticHit:
    memory_id: uuid.UUID
    similarity: float
    chunk_index: int
    chunk_text: str


def semantic_search(
    session: Session,
    embedder: EmbeddingProvider,
    query_vector: list[float],
    filters: MemoryFilters | None = None,
    *,
    limit: int = 30,
    exclude_ids: list[uuid.UUID] | None = None,
) -> list[SemanticHit]:
    """Mejor fragmento por recuerdo, ordenado por similitud descendente.

    Solo compara contra vectores del proveedor y modelo activos: mezclar
    espacios vectoriales distintos daría similitudes sin sentido.
    """
    filters = filters or MemoryFilters()
    distance = MemoryEmbedding.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(
            MemoryEmbedding.memory_id,
            MemoryEmbedding.chunk_index,
            MemoryEmbedding.chunk_text,
            distance,
        )
        .join(Memory, Memory.id == MemoryEmbedding.memory_id)
        .where(MemoryEmbedding.provider == embedder.name, MemoryEmbedding.model == embedder.model)
        .order_by(distance)
        .limit(limit * 4)
    )
    if exclude_ids:
        stmt = stmt.where(MemoryEmbedding.memory_id.notin_(exclude_ids))
    stmt = filters.apply(stmt)

    best: dict[uuid.UUID, SemanticHit] = {}
    for memory_id, chunk_index, chunk_text, dist in session.execute(stmt):
        if memory_id in best or dist is None or dist != dist:  # NaN
            continue
        best[memory_id] = SemanticHit(memory_id, 1.0 - float(dist), chunk_index, chunk_text)
        if len(best) >= limit:
            break
    return list(best.values())
