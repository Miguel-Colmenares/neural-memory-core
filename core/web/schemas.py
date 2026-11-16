"""Esquemas de entrada y salida de la API (validación con Pydantic)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.database.models import Memory
from core.ingestion.pipeline import IngestionInput, IngestionResult
from core.memory_engine.filters import MemoryFilters

MemoryType = Literal["episodic", "semantic", "project", "preference", "document"]
SourceType = Literal["manual", "conversation", "document", "import", "api", "module"]
MemoryStatus = Literal["active", "archived"]
Tag = str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ------------------------------------------------------------------ recuerdos
class MemoryCreate(StrictModel):
    content: str = Field(min_length=1)
    memory_type: MemoryType | None = Field(
        default=None, description="Si se omite, el sistema lo clasifica por reglas."
    )
    kind: str | None = Field(default=None, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str | None = Field(default=None, max_length=300)
    source_type: SourceType = "manual"
    source_ref: str | None = Field(default=None, max_length=500)
    provenance: dict[str, Any] = Field(default_factory=dict)
    project_id: uuid.UUID | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=50)
    importance: int = Field(default=3, ge=1, le=5)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None
    contradicts: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    supersedes: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    auto_tag: bool = True
    auto_relate: bool = True
    allow_duplicate: bool = False

    def to_input(self, module: str | None = None) -> IngestionInput:
        return IngestionInput(
            content=self.content,
            memory_type=self.memory_type,
            kind=self.kind,
            title=self.title,
            source_type=self.source_type,
            source_ref=self.source_ref,
            provenance=self.provenance,
            project_id=self.project_id,
            module=module,
            tags=self.tags,
            importance=self.importance,
            metadata=self.metadata,
            occurred_at=self.occurred_at,
            contradicts=self.contradicts,
            supersedes=self.supersedes,
            auto_tag=self.auto_tag,
            auto_relate=self.auto_relate,
            allow_duplicate=self.allow_duplicate,
        )


class MemoryUpdate(StrictModel):
    content: str | None = Field(default=None, min_length=1)
    memory_type: MemoryType | None = None
    kind: str | None = Field(default=None, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str | None = Field(default=None, max_length=300)
    source_type: SourceType | None = None
    source_ref: str | None = Field(default=None, max_length=500)
    provenance: dict[str, Any] | None = None
    project_id: uuid.UUID | None = None
    tags: list[Tag] | None = Field(default=None, max_length=50)
    importance: int | None = Field(default=None, ge=1, le=5)
    metadata: dict[str, Any] | None = None
    occurred_at: datetime | None = None
    change_reason: str | None = Field(default=None, max_length=1000)
    is_correction: bool = Field(
        default=False, description="Marca el cambio como corrección manual en el historial."
    )


class ReasonBody(StrictModel):
    reason: str | None = Field(default=None, max_length=1000)


class MemoryOut(BaseModel):
    id: uuid.UUID
    memory_type: str
    kind: str
    title: str | None
    content: str
    source_type: str
    source_ref: str | None
    provenance: dict[str, Any]
    project_id: uuid.UUID | None
    project_name: str | None
    module: str | None
    tags: list[str]
    importance: int
    metadata: dict[str, Any]
    status: str
    occurred_at: datetime | None
    version: int
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, memory: Memory, *, max_content: int | None = None) -> MemoryOut:
        content = memory.content
        if max_content is not None and len(content) > max_content:
            content = content[:max_content].rstrip() + "…"
        return cls(
            id=memory.id,
            memory_type=memory.memory_type,
            kind=memory.kind,
            title=memory.title,
            content=content,
            source_type=memory.source_type,
            source_ref=memory.source_ref,
            provenance=memory.provenance or {},
            project_id=memory.project_id,
            project_name=memory.project.name if memory.project else None,
            module=memory.module,
            tags=list(memory.tags or []),
            importance=memory.importance,
            metadata=memory.metadata_ or {},
            status=memory.status,
            occurred_at=memory.occurred_at,
            version=memory.version,
            created_by=memory.created_by,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )


class MemoryList(BaseModel):
    items: list[MemoryOut]
    total: int
    limit: int
    offset: int


class DetectedRelationOut(BaseModel):
    memory_id: uuid.UUID
    relation_type: str
    confidence: float | None
    origin: str


class IngestionOut(BaseModel):
    outcome: Literal["created", "duplicate"]
    memory: MemoryOut
    duplicate_of: uuid.UUID | None
    relations: list[DetectedRelationOut]
    auto_tags: list[str]
    classification: dict[str, Any]
    warnings: list[str]
    steps: list[dict[str, str]]

    @classmethod
    def from_result(cls, result: IngestionResult) -> IngestionOut:
        return cls(
            outcome=result.outcome,  # type: ignore[arg-type]
            memory=MemoryOut.from_model(result.memory),
            duplicate_of=result.duplicate_of,
            relations=[
                DetectedRelationOut(
                    memory_id=r.memory_id,
                    relation_type=r.relation_type,
                    confidence=r.confidence,
                    origin=r.origin,
                )
                for r in result.relations
            ],
            auto_tags=result.auto_tags,
            classification=result.classification,
            warnings=result.warnings,
            steps=result.steps,
        )


class MemoryVersionOut(BaseModel):
    version: int
    change_type: str
    change_reason: str | None
    changed_fields: list[str]
    changed_by: str | None
    created_at: datetime
    snapshot: dict[str, Any]


# ------------------------------------------------------------------ relaciones
class RelationCreate(StrictModel):
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation_type: str = Field(default="related", max_length=40, pattern=r"^[a-z0-9_]+$")
    note: str | None = Field(default=None, max_length=1000)


class RelationOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    relation_type: str
    origin: str
    confidence: float | None
    note: str | None
    created_by: str | None
    created_at: datetime


class NeighborOut(BaseModel):
    relation: RelationOut
    direction: str
    memory: MemoryOut


# -------------------------------------------------------------------- búsqueda
class FilterParams(StrictModel):
    memory_types: list[MemoryType] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    project_ids: list[uuid.UUID] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: MemoryStatus | Literal["any"] = "active"
    source_types: list[SourceType] = Field(default_factory=list)
    min_importance: int | None = Field(default=None, ge=1, le=5)
    date_from: datetime | None = None
    date_to: datetime | None = None

    def to_filters(self) -> MemoryFilters:
        return MemoryFilters(
            memory_types=list(self.memory_types),
            kinds=[k.lower() for k in self.kinds],
            project_ids=list(self.project_ids),
            tags=[t.strip().lower() for t in self.tags if t.strip()],
            status=None if self.status == "any" else self.status,
            source_types=list(self.source_types),
            min_importance=self.min_importance,
            date_from=self.date_from,
            date_to=self.date_to,
        )


class SearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["hybrid", "text", "semantic"] = "hybrid"
    limit: int = Field(default=10, ge=1, le=50)
    include_related: bool = True
    filters: FilterParams = Field(default_factory=FilterParams)


class SearchResultOut(BaseModel):
    memory: MemoryOut
    score: float
    matched_by: list[str]
    text_rank: float | None
    semantic_similarity: float | None
    excerpt: str
    via_relation: dict[str, Any] | None
    score_breakdown: dict[str, float]


class SearchOut(BaseModel):
    query: str
    mode: str
    results: list[SearchResultOut]
    total_candidates: int
    filters: dict[str, Any]
    warnings: list[str]
    embedding: dict[str, Any]


class AskRequest(StrictModel):
    question: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=8, ge=1, le=20)
    use_llm: bool = True
    filters: FilterParams = Field(default_factory=FilterParams)


class AskOut(BaseModel):
    question: str
    answer: str
    answer_mode: Literal["extractive", "llm"]
    confirmed: list[dict[str, Any]]
    inferences: list[dict[str, Any]]
    not_found: list[str]
    sources: list[dict[str, Any]]
    interpretation: dict[str, Any]
    warnings: list[str]


# ------------------------------------------------------------------------ auth
class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    username: str
    role: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    role: str
    is_active: bool
    created_at: datetime


class UserCreate(StrictModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=200)
    role: Literal["admin", "editor", "reader"] = "reader"


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


# -------------------------------------------------------------------- historial
class ChangeLogOut(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    project_id: uuid.UUID | None
    action: str
    summary: str
    details: dict[str, Any]
    actor: str | None
    created_at: datetime


class ChangeLogList(BaseModel):
    items: list[ChangeLogOut]
    total: int
    limit: int
    offset: int
