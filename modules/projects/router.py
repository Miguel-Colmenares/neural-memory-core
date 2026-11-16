from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from core.database.models import Project
from core.web.deps import CurrentUser, Editor, IngestionDep, Reader, SessionDep
from core.web.schemas import IngestionOut, MemoryOut, StrictModel
from modules.projects.service import ProjectService

router = APIRouter(prefix="/projects", tags=["Proyectos"])
ProjectStatus = Literal["active", "paused", "completed", "archived"]


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)
    objectives: list[str] = Field(default_factory=list, max_length=50)
    status: ProjectStatus = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    objectives: list[str] | None = Field(default=None, max_length=50)
    status: ProjectStatus | None = None
    metadata: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    objectives: list[str]
    status: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    memory_count: int | None = None

    @classmethod
    def from_model(cls, project: Project, memory_count: int | None = None) -> ProjectOut:
        return cls(
            id=project.id,
            slug=project.slug,
            name=project.name,
            description=project.description,
            objectives=list(project.objectives or []),
            status=project.status,
            metadata=project.metadata_ or {},
            created_at=project.created_at,
            updated_at=project.updated_at,
            memory_count=memory_count,
        )


class ProjectRelationCreate(StrictModel):
    target_project_id: uuid.UUID
    relation_type: str = Field(default="related", max_length=50, pattern=r"^[a-z0-9_]+$")
    description: str = Field(default="", max_length=2000)


class ProjectRelationOut(BaseModel):
    id: uuid.UUID
    relation_type: str
    description: str
    direction: str
    project: ProjectOut
    created_at: datetime


class DecisionCreate(StrictModel):
    content: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=300)
    tags: list[str] = Field(default_factory=list, max_length=50)
    importance: int = Field(default=4, ge=1, le=5)
    source_ref: str | None = Field(default=None, max_length=500)
    occurred_at: datetime | None = None
    contradicts: list[uuid.UUID] = Field(default_factory=list)
    supersedes: list[uuid.UUID] = Field(default_factory=list)


class ProjectOverview(BaseModel):
    project: ProjectOut
    counts: dict[str, Any]
    decisions: list[MemoryOut]
    documents: list[MemoryOut]
    conversations: list[MemoryOut]
    recent_memories: list[MemoryOut]
    relations: list[ProjectRelationOut]


def service(session: SessionDep, user: CurrentUser) -> ProjectService:
    return ProjectService(session, actor=user.username)


Service = Annotated[ProjectService, Depends(service)]


def _relation_out(item) -> ProjectRelationOut:
    relation, other, direction = item
    return ProjectRelationOut(
        id=relation.id,
        relation_type=relation.relation_type,
        description=relation.description,
        direction=direction,
        project=ProjectOut.from_model(other),
        created_at=relation.created_at,
    )


@router.post("", response_model=ProjectOut, status_code=201, summary="Crear proyecto")
def create_project(body: ProjectCreate, svc: Service, _: Editor):
    project = svc.create(body.name, body.description, body.objectives, body.status, body.metadata)
    return ProjectOut.from_model(project, 0)


@router.get("", response_model=list[ProjectOut], summary="Listar proyectos")
def list_projects(svc: Service, _: Reader, status: ProjectStatus | None = None):
    projects = svc.list(status)
    counts = svc.memory_counts([p.id for p in projects])
    return [ProjectOut.from_model(p, counts.get(p.id, 0)) for p in projects]


@router.get("/{project_id}", response_model=ProjectOverview, summary="Espacio del proyecto")
def get_project(project_id: uuid.UUID, svc: Service, _: Reader):
    data = svc.overview(project_id)

    def memories(key: str) -> list[MemoryOut]:
        return [MemoryOut.from_model(m, max_content=1200) for m in data[key]]

    return ProjectOverview(
        project=ProjectOut.from_model(data["project"], data["counts"]["active_memories"]),
        counts=data["counts"],
        decisions=memories("decisions"),
        documents=memories("documents"),
        conversations=memories("conversations"),
        recent_memories=memories("recent_memories"),
        relations=[_relation_out(r) for r in data["relations"]],
    )


@router.patch("/{project_id}", response_model=ProjectOut, summary="Actualizar proyecto")
def update_project(project_id: uuid.UUID, body: ProjectUpdate, svc: Service, _: Editor):
    project = svc.update(project_id, body.model_dump(exclude_unset=True))
    return ProjectOut.from_model(project)


@router.delete("/{project_id}", status_code=204, summary="Eliminar proyecto")
def delete_project(
    project_id: uuid.UUID,
    svc: Service,
    _: Editor,
    confirm: Annotated[bool, Query(description="Debe ser true.")],
):
    """Los recuerdos del proyecto no se borran: quedan sin proyecto asignado."""
    from core.errors import InvalidInputError

    if not confirm:
        raise InvalidInputError("Confirma el borrado con confirm=true.")
    svc.delete(project_id)


@router.post(
    "/{project_id}/decisions",
    response_model=IngestionOut,
    status_code=201,
    summary="Registrar una decisión del proyecto",
)
def add_decision(
    project_id: uuid.UUID, body: DecisionCreate, svc: Service, pipeline: IngestionDep, _: Editor
):
    from core.ingestion.pipeline import IngestionInput

    svc.get(project_id)
    result = pipeline.ingest(
        IngestionInput(
            content=body.content,
            memory_type="project",
            kind="decision",
            title=body.title,
            source_type="manual",
            source_ref=body.source_ref,
            project_id=project_id,
            module="projects",
            tags=body.tags,
            importance=body.importance,
            occurred_at=body.occurred_at,
            contradicts=body.contradicts,
            supersedes=body.supersedes,
        )
    )
    return IngestionOut.from_result(result)


@router.get(
    "/{project_id}/relations",
    response_model=list[ProjectRelationOut],
    summary="Relaciones con otros proyectos",
)
def project_relations(project_id: uuid.UUID, svc: Service, _: Reader):
    return [_relation_out(r) for r in svc.relations(project_id)]


@router.post(
    "/{project_id}/relations",
    response_model=ProjectRelationOut,
    status_code=201,
    summary="Relacionar con otro proyecto",
)
def relate_project(project_id: uuid.UUID, body: ProjectRelationCreate, svc: Service, _: Editor):
    relation = svc.relate(project_id, body.target_project_id, body.relation_type, body.description)
    return _relation_out((relation, svc.get(body.target_project_id), "out"))


@router.delete(
    "/relations/{relation_id}", status_code=204, summary="Eliminar relación entre proyectos"
)
def unrelate_project(relation_id: uuid.UUID, svc: Service, _: Editor):
    svc.unrelate(relation_id)
