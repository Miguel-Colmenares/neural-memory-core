from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from core.database.models import Memory
from core.memory_engine.filters import MemoryFilters
from core.versioning import service as versioning
from core.web.deps import Editor, GraphDep, IngestionDep, MemoryServiceDep, Reader, SessionDep
from core.web.schemas import (
    IngestionOut,
    MemoryCreate,
    MemoryList,
    MemoryOut,
    MemoryUpdate,
    MemoryVersionOut,
    NeighborOut,
    ReasonBody,
    RelationOut,
)

router = APIRouter(prefix="/memories", tags=["Recuerdos"])


@router.post("", response_model=IngestionOut, status_code=201, summary="Incorporar un recuerdo")
def create_memory(body: MemoryCreate, pipeline: IngestionDep, _: Editor, response: Response):
    """Ejecuta el proceso completo de ingesta: validación, duplicados, relaciones,
    embeddings, clasificación, guardado y registro. Si ya existe un recuerdo con
    el mismo contenido devuelve ese (``outcome = "duplicate"``, HTTP 200)."""
    result = pipeline.ingest(body.to_input())
    if result.outcome == "duplicate":
        response.status_code = 200
    return IngestionOut.from_result(result)


@router.get("", response_model=MemoryList, summary="Explorar recuerdos")
def list_memories(
    service: MemoryServiceDep,
    _: Reader,
    memory_type: Annotated[list[str] | None, Query()] = None,
    kind: Annotated[list[str] | None, Query()] = None,
    project_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    status: Literal["active", "archived", "any"] = "active",
    source_type: Annotated[list[str] | None, Query()] = None,
    module: str | None = None,
    min_importance: Annotated[int | None, Query(ge=1, le=5)] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    order: Literal["created_desc", "created_asc", "updated_desc", "importance_desc"] = (
        "created_desc"
    ),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters = MemoryFilters(
        memory_types=memory_type or [],
        kinds=kind or [],
        project_ids=project_id or [],
        tags=[t.strip().lower() for t in tag or []],
        status=None if status == "any" else status,
        source_types=source_type or [],
        module=module,
        min_importance=min_importance,
        date_from=date_from,
        date_to=date_to,
    )
    items, total = service.list(filters, limit=limit, offset=offset, order=order)
    return MemoryList(
        items=[MemoryOut.from_model(m, max_content=2000) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tags", summary="Etiquetas en uso con su número de recuerdos")
def list_tags(session: SessionDep, _: Reader) -> list[dict]:
    tag = func.unnest(Memory.tags).label("tag")
    subquery = select(tag).where(Memory.status == "active").subquery()
    rows = session.execute(
        select(subquery.c.tag, func.count().label("count"))
        .group_by(subquery.c.tag)
        .order_by(func.count().desc(), subquery.c.tag)
        .limit(500)
    )
    return [{"tag": row[0], "count": row[1]} for row in rows]


@router.get("/{memory_id}", response_model=MemoryOut, summary="Obtener un recuerdo")
def get_memory(memory_id: uuid.UUID, service: MemoryServiceDep, _: Reader):
    return MemoryOut.from_model(service.get(memory_id))


@router.patch("/{memory_id}", response_model=MemoryOut, summary="Actualizar conservando historial")
def update_memory(memory_id: uuid.UUID, body: MemoryUpdate, service: MemoryServiceDep, _: Editor):
    """Cada cambio crea una versión nueva; la anterior queda en el historial."""
    changes = body.model_dump(exclude_unset=True, exclude={"change_reason", "is_correction"})
    memory = service.update(
        memory_id,
        changes,
        reason=body.change_reason,
        change_type="correction" if body.is_correction else "update",
    )
    return MemoryOut.from_model(memory)


@router.post("/{memory_id}/archive", response_model=MemoryOut, summary="Archivar")
def archive_memory(
    memory_id: uuid.UUID, service: MemoryServiceDep, _: Editor, body: ReasonBody | None = None
):
    return MemoryOut.from_model(service.archive(memory_id, body.reason if body else None))


@router.post("/{memory_id}/restore", response_model=MemoryOut, summary="Reactivar un archivado")
def restore_memory(
    memory_id: uuid.UUID, service: MemoryServiceDep, _: Editor, body: ReasonBody | None = None
):
    return MemoryOut.from_model(service.restore(memory_id, body.reason if body else None))


@router.get(
    "/{memory_id}/versions", response_model=list[MemoryVersionOut], summary="Historial de versiones"
)
def memory_versions(memory_id: uuid.UUID, service: MemoryServiceDep, _: Reader):
    service.get(memory_id)
    return [
        MemoryVersionOut(
            version=v.version,
            change_type=v.change_type,
            change_reason=v.change_reason,
            changed_fields=v.changed_fields,
            changed_by=v.changed_by,
            created_at=v.created_at,
            snapshot=v.snapshot,
        )
        for v in versioning.list_versions(service.session, memory_id)
    ]


@router.post(
    "/{memory_id}/revert/{version}",
    response_model=MemoryOut,
    summary="Volver a una versión anterior (crea una versión nueva)",
)
def revert_memory(
    memory_id: uuid.UUID,
    version: int,
    service: MemoryServiceDep,
    _: Editor,
    body: ReasonBody | None = None,
):
    return MemoryOut.from_model(service.revert(memory_id, version, body.reason if body else None))


@router.get(
    "/{memory_id}/relations", response_model=list[NeighborOut], summary="Recuerdos relacionados"
)
def memory_relations(memory_id: uuid.UUID, service: MemoryServiceDep, graph: GraphDep, _: Reader):
    service.get(memory_id)
    neighbors = graph.neighbors([memory_id], only_active=False)[memory_id]
    return [
        NeighborOut(
            relation=RelationOut.model_validate(n.relation, from_attributes=True),
            direction=n.direction,
            memory=MemoryOut.from_model(n.memory, max_content=600),
        )
        for n in neighbors
    ]


@router.delete("/{memory_id}", status_code=204, summary="Eliminar definitivamente")
def delete_memory(
    memory_id: uuid.UUID,
    service: MemoryServiceDep,
    _: Editor,
    confirm: Annotated[bool, Query(description="Debe ser true: el borrado no se puede deshacer.")],
    reason: Annotated[str | None, Query(max_length=1000)] = None,
):
    """Borra el recuerdo y su historial. Lo habitual es archivar; usa esto solo
    para retirar información que no debe conservarse."""
    from core.errors import InvalidInputError

    if not confirm:
        raise InvalidInputError("Confirma el borrado con confirm=true.")
    service.delete(memory_id, reason)
