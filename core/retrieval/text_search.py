"""Búsqueda textual con el índice de texto completo de PostgreSQL."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from core.database.models import FTS_CONFIG, Memory
from core.memory_engine.filters import MemoryFilters
from core.textutils import tokenize


@dataclass
class TextHit:
    memory_id: uuid.UUID
    rank: float
    headline: str


def build_tsquery(terms: list[str]) -> str:
    """Consulta OR: basta con que aparezca un término; más coincidencias, más rango."""
    safe = [t for t in terms if t.isalnum()]
    return " | ".join(dict.fromkeys(safe[:32]))


def text_search(
    session: Session,
    query: str,
    filters: MemoryFilters | None = None,
    *,
    limit: int = 30,
    terms: list[str] | None = None,
) -> list[TextHit]:
    filters = filters or MemoryFilters()
    expression = build_tsquery(terms if terms is not None else tokenize(query))
    if not expression:
        return []
    config = literal_column(f"'{FTS_CONFIG}'::regconfig")
    tsquery = func.to_tsquery(config, expression)
    rank = func.ts_rank_cd(Memory.search_vector, tsquery, 32).label("rank")
    headline = func.ts_headline(
        config,
        func.left(Memory.content, 20000),
        tsquery,
        "MaxFragments=2, MaxWords=30, MinWords=10, StartSel=**, StopSel=**, FragmentDelimiter= … ",
    ).label("headline")
    stmt = (
        select(Memory.id, rank, headline)
        .where(Memory.search_vector.op("@@")(tsquery))
        .order_by(rank.desc(), Memory.updated_at.desc())
        .limit(limit)
    )
    stmt = filters.apply(stmt)
    return [TextHit(row[0], float(row[1]), row[2]) for row in session.execute(stmt)]
