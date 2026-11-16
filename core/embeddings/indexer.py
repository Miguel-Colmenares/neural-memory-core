"""Mantiene el índice vectorial (tabla ``memory_embeddings``)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.orm import Session

from core.config import Settings, get_settings
from core.database.models import Memory, MemoryEmbedding
from core.embeddings.base import EmbeddingError, EmbeddingProvider
from core.embeddings.chunking import chunk_text

logger = logging.getLogger("nmc.embeddings")


def chunks_for(memory: Memory, settings: Settings) -> list[str]:
    return chunk_text(memory.content, settings.chunk_chars, settings.chunk_overlap)


def embedding_input(title: str | None, chunk: str) -> str:
    """El título acompaña a cada fragmento para darle contexto."""
    return f"{title}\n{chunk}" if title else chunk


def embed_content(
    embedder: EmbeddingProvider, title: str | None, content: str, settings: Settings
) -> list[list[float]]:
    chunks = chunk_text(content, settings.chunk_chars, settings.chunk_overlap)
    return embedder.embed([embedding_input(title, c) for c in chunks]) if chunks else []


def index_memory(
    session: Session,
    memory: Memory,
    embedder: EmbeddingProvider,
    settings: Settings | None = None,
    vectors: list[list[float]] | None = None,
) -> int:
    """(Re)genera los vectores de un recuerdo. Devuelve el número de fragmentos."""
    settings = settings or get_settings()
    chunks = chunks_for(memory, settings)
    if vectors is None:
        vectors = embedder.embed([embedding_input(memory.title, c) for c in chunks])
    session.execute(delete(MemoryEmbedding).where(MemoryEmbedding.memory_id == memory.id))
    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        session.add(
            MemoryEmbedding(
                memory_id=memory.id,
                chunk_index=index,
                chunk_text=chunk,
                provider=embedder.name,
                model=embedder.model,
                embedding=vector,
            )
        )
    return len(chunks)


def try_index_memory(
    session: Session,
    memory: Memory,
    embedder: EmbeddingProvider,
    settings: Settings | None = None,
    vectors: list[list[float]] | None = None,
) -> str | None:
    """Indexa sin abortar la operación principal. Devuelve un aviso si falla."""
    try:
        index_memory(session, memory, embedder, settings, vectors)
        return None
    except EmbeddingError as exc:
        logger.warning("No se generaron embeddings para %s: %s", memory.id, exc)
        return (
            "El recuerdo se guardó, pero no se pudieron generar sus embeddings "
            f"({exc}). Ejecuta la reindexación cuando el proveedor esté disponible."
        )


def _indexed_ids_query(embedder: EmbeddingProvider):
    return select(MemoryEmbedding.memory_id).where(
        MemoryEmbedding.provider == embedder.name, MemoryEmbedding.model == embedder.model
    )


def index_status(session: Session, embedder: EmbeddingProvider) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(Memory)) or 0
    indexed = (
        session.scalar(
            select(func.count(distinct(MemoryEmbedding.memory_id))).where(
                MemoryEmbedding.provider == embedder.name, MemoryEmbedding.model == embedder.model
            )
        )
        or 0
    )
    vectors = session.scalar(select(func.count()).select_from(MemoryEmbedding)) or 0
    stale = (
        session.scalar(
            select(func.count())
            .select_from(MemoryEmbedding)
            .where(
                (MemoryEmbedding.provider != embedder.name)
                | (MemoryEmbedding.model != embedder.model)
            )
        )
        or 0
    )
    return {
        "memories_total": total,
        "memories_indexed": indexed,
        "memories_pending": max(total - indexed, 0),
        "vectors_total": vectors,
        "vectors_from_other_provider": stale,
    }


def reindex(
    session: Session,
    embedder: EmbeddingProvider,
    settings: Settings | None = None,
    *,
    only_pending: bool = True,
    batch_size: int = 100,
) -> dict[str, int]:
    """Regenera embeddings. Con ``only_pending`` solo procesa lo que falta."""
    settings = settings or get_settings()
    stmt = select(Memory.id).order_by(Memory.created_at)
    if only_pending:
        stmt = stmt.where(Memory.id.notin_(_indexed_ids_query(embedder)))
    ids: list[uuid.UUID] = list(session.scalars(stmt))
    processed = failed = 0
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        for memory in session.scalars(select(Memory).where(Memory.id.in_(batch))):
            try:
                index_memory(session, memory, embedder, settings)
                processed += 1
            except EmbeddingError:
                failed += 1
                logger.exception("Fallo al reindexar %s", memory.id)
        session.flush()
    return {"processed": processed, "failed": failed, "selected": len(ids)}
