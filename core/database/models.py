"""Modelo de datos del núcleo.

Las tablas propias de un módulo viven en el paquete del módulo
(por ejemplo ``modules/tasks/models.py``) y comparten ``Base``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.base import Base

EMBEDDING_DIM = 384
FTS_CONFIG = "spanish"

MEMORY_TYPES = ("episodic", "semantic", "project", "preference", "document")
MEMORY_STATUSES = ("active", "archived")
PROJECT_STATUSES = ("active", "paused", "completed", "archived")
SOURCE_TYPES = ("manual", "conversation", "document", "import", "api", "module")
RELATION_ORIGINS = ("auto", "manual")
USER_ROLES = ("admin", "editor", "reader")


def utcnow() -> datetime:
    return datetime.now(UTC)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", USER_ROLES), name="ck_users_role"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint(_in("status", PROJECT_STATUSES), name="ck_projects_status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    objectives: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class ProjectRelation(Base):
    __tablename__ = "project_relations"
    __table_args__ = (
        UniqueConstraint("source_project_id", "target_project_id", "relation_type"),
        CheckConstraint("source_project_id <> target_project_id", name="ck_project_rel_distinct"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False, default="related")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint(_in("memory_type", MEMORY_TYPES), name="ck_memories_type"),
        CheckConstraint(_in("status", MEMORY_STATUSES), name="ck_memories_status"),
        CheckConstraint(_in("source_type", SOURCE_TYPES), name="ck_memories_source_type"),
        CheckConstraint("importance BETWEEN 1 AND 5", name="ck_memories_importance"),
        Index("ix_memories_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_memories_tags", "tags", postgresql_using="gin"),
        Index("ix_memories_type_status", "memory_type", "status"),
        Index("ix_memories_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="note", index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Procedencia: de dónde salió el recuerdo.
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(500))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    module: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(80)), nullable=False, default=list)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            f"setweight(to_tsvector('{FTS_CONFIG}'::regconfig, coalesce(title, '')), 'A') || "
            f"setweight(to_tsvector('{FTS_CONFIG}'::regconfig, content), 'B')",
            persisted=True,
        ),
    )

    project: Mapped[Project | None] = relationship(lazy="joined")


class MemoryVersion(Base):
    """Fotografía inmutable del recuerdo en cada versión (incluida la primera)."""

    __tablename__ = "memory_versions"
    __table_args__ = (UniqueConstraint("memory_id", "version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text)
    changed_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    changed_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class MemoryEmbedding(Base):
    """Un vector por fragmento del recuerdo. Regenerable: no se exporta."""

    __tablename__ = "memory_embeddings"
    __table_args__ = (
        UniqueConstraint("memory_id", "chunk_index"),
        Index(
            "ix_memory_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class MemoryRelation(Base):
    __tablename__ = "memory_relations"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relation_type"),
        CheckConstraint("source_id <> target_id", name="ck_memory_rel_distinct"),
        CheckConstraint(_in("origin", RELATION_ORIGINS), name="ck_memory_rel_origin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False, default="related")
    origin: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    confidence: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ChangeLog(Base):
    """Historial de actualizaciones de todo el sistema (auditoría)."""

    __tablename__ = "change_log"
    __table_args__ = (
        Index("ix_change_log_entity", "entity_type", "entity_id"),
        Index("ix_change_log_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    actor: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
