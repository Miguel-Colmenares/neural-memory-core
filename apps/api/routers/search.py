from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from core.llm.client import LLMClient, get_llm
from core.memory_engine.filters import MemoryFilters
from core.retrieval.answer import AnswerEngine
from core.retrieval.engine import HybridRetriever
from core.web.deps import Editor, EmbedderDep, GraphDep, Reader, SessionDep
from core.web.schemas import (
    AskOut,
    AskRequest,
    MemoryOut,
    RelationCreate,
    RelationOut,
    SearchOut,
    SearchRequest,
    SearchResultOut,
)

router = APIRouter(tags=["Búsqueda y conocimiento"])


@router.post("/search", response_model=SearchOut, summary="Búsqueda híbrida")
def search(body: SearchRequest, session: SessionDep, embedder: EmbedderDep, _: Reader):
    """Combina texto completo y similitud de embeddings, aplica filtros, añade
    recuerdos relacionados y reordena. Cada resultado explica su puntuación."""
    response = HybridRetriever(session, embedder).search(
        body.query,
        body.filters.to_filters(),
        mode=body.mode,
        limit=body.limit,
        include_related=body.include_related,
    )
    return SearchOut(
        query=response.query,
        mode=response.mode,
        results=[
            SearchResultOut(
                memory=MemoryOut.from_model(r.memory, max_content=2000),
                score=r.score,
                matched_by=r.matched_by,
                text_rank=r.text_rank,
                semantic_similarity=r.semantic_similarity,
                excerpt=r.excerpt,
                via_relation=r.via_relation,
                score_breakdown=r.score_breakdown,
            )
            for r in response.results
        ],
        total_candidates=response.total_candidates,
        filters=response.filters,
        warnings=response.warnings,
        embedding=response.embedding,
    )


@router.post("/ask", response_model=AskOut, summary="Preguntar en lenguaje natural")
def ask(
    body: AskRequest,
    session: SessionDep,
    embedder: EmbedderDep,
    _: Reader,
    llm: Annotated[LLMClient | None, Depends(get_llm)],
):
    """Responde solo con lo almacenado, citando fuentes y separando lo
    confirmado, lo inferido y lo no encontrado."""
    answer = AnswerEngine(session, embedder, llm).ask(
        body.question, body.filters.to_filters(), limit=body.limit, use_llm=body.use_llm
    )
    return AskOut(**answer.__dict__)


@router.post("/relations", response_model=RelationOut, status_code=201, summary="Crear relación")
def create_relation(body: RelationCreate, graph: GraphDep, _: Editor):
    relation = graph.relate(
        body.source_id, body.target_id, body.relation_type, origin="manual", note=body.note
    )
    return RelationOut.model_validate(relation, from_attributes=True)


@router.delete("/relations/{relation_id}", status_code=204, summary="Eliminar relación")
def delete_relation(relation_id: uuid.UUID, graph: GraphDep, _: Editor):
    graph.remove(relation_id)


@router.get("/graph", summary="Grafo de relaciones entre recuerdos")
def graph_view(
    graph: GraphDep,
    _: Reader,
    focus_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    memory_type: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 150,
) -> dict:
    filters = MemoryFilters(
        project_ids=[project_id] if project_id else [],
        memory_types=memory_type or [],
        status=None,
    )
    return graph.graph(filters, limit=limit, focus_id=focus_id)
