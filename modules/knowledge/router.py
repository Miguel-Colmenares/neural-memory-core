from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import Field

from core.ingestion.pipeline import IngestionInput
from core.memory_engine.filters import MemoryFilters
from core.web.deps import Editor, IngestionDep, MemoryServiceDep, Reader
from core.web.schemas import IngestionOut, MemoryList, MemoryOut, StrictModel

router = APIRouter(prefix="/knowledge", tags=["Conocimiento"])


class ConceptCreate(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    definition: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list, max_length=50)
    importance: int = Field(default=3, ge=1, le=5)
    project_id: uuid.UUID | None = None
    source_ref: str | None = Field(
        default=None, max_length=500, description="De dónde procede: libro, URL, curso..."
    )
    related_to: list[uuid.UUID] = Field(
        default_factory=list, max_length=20, description="Conceptos o recuerdos relacionados."
    )
    part_of: list[uuid.UUID] = Field(default_factory=list, max_length=20)


@router.post(
    "/concepts", response_model=IngestionOut, status_code=201, summary="Registrar un concepto"
)
def create_concept(body: ConceptCreate, pipeline: IngestionDep, _: Editor):
    for target in [*body.related_to, *body.part_of]:
        pipeline.memories.get(target)
    result = pipeline.ingest(
        IngestionInput(
            content=body.definition,
            memory_type="semantic",
            kind="concept",
            title=body.name,
            source_type="manual",
            source_ref=body.source_ref,
            project_id=body.project_id,
            module="knowledge",
            tags=body.tags,
            importance=body.importance,
        )
    )
    if result.outcome == "created":
        linked = {r.memory_id for r in result.relations if r.relation_type == "related"}
        for relation_type, targets in (("related", body.related_to), ("part_of", body.part_of)):
            for target in dict.fromkeys(targets):
                if relation_type == "related" and target in linked:
                    continue
                pipeline.graph.relate(result.memory.id, target, relation_type, origin="manual")
    return IngestionOut.from_result(result)


@router.get("/concepts", response_model=MemoryList, summary="Listar conceptos")
def list_concepts(
    service: MemoryServiceDep,
    _: Reader,
    tag: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters = MemoryFilters(
        memory_types=["semantic"], kinds=["concept"], tags=[t.lower() for t in tag or []]
    )
    items, total = service.list(filters, limit=limit, offset=offset)
    return MemoryList(
        items=[MemoryOut.from_model(m, max_content=800) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )
