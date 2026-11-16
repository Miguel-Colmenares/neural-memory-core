"""Motor de memoria: ciclo de vida de los recuerdos.

Toda escritura pasa por aquí para garantizar tres cosas: historial de
versiones, registro de cambios y actualización del índice vectorial.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from core.config import Settings, get_settings
from core.database.changelog import log_change
from core.database.models import (
    MEMORY_TYPES,
    SOURCE_TYPES,
    ChangeLog,
    Memory,
    Project,
    utcnow,
)
from core.embeddings.base import EmbeddingProvider
from core.embeddings.indexer import try_index_memory
from core.errors import InvalidInputError, NotFoundError
from core.memory_engine.filters import MemoryFilters
from core.module_system import events
from core.textutils import clean_content, content_hash, excerpt
from core.versioning import service as versioning

EDITABLE_FIELDS = (
    "memory_type",
    "kind",
    "title",
    "content",
    "source_type",
    "source_ref",
    "provenance",
    "project_id",
    "tags",
    "importance",
    "metadata",
    "occurred_at",
)

ORDERINGS = {
    "created_desc": (Memory.created_at.desc(), Memory.id),
    "created_asc": (Memory.created_at.asc(), Memory.id),
    "updated_desc": (Memory.updated_at.desc(), Memory.id),
    "importance_desc": (Memory.importance.desc(), Memory.created_at.desc()),
}


@dataclass
class MemoryData:
    content: str
    memory_type: str
    kind: str = "note"
    title: str | None = None
    source_type: str = "manual"
    source_ref: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    project_id: uuid.UUID | None = None
    module: str | None = None
    tags: list[str] = field(default_factory=list)
    importance: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime | None = None


def normalize_tags(tags: list[str] | None) -> list[str]:
    seen: list[str] = []
    for tag in tags or []:
        tag = " ".join(str(tag).strip().lower().split())[:80]
        if tag and tag not in seen:
            seen.append(tag)
    return seen[:50]


class MemoryService:
    def __init__(
        self,
        session: Session,
        embedder: EmbeddingProvider,
        settings: Settings | None = None,
        actor: str | None = None,
    ):
        self.session = session
        self.embedder = embedder
        self.settings = settings or get_settings()
        self.actor = actor
        self.warnings: list[str] = []

    # ------------------------------------------------------------------ lectura
    def get(self, memory_id: uuid.UUID) -> Memory:
        memory = self.session.get(Memory, memory_id)
        if memory is None:
            raise NotFoundError(f"No existe el recuerdo {memory_id}.")
        return memory

    def find_by_hash(self, digest: str) -> Memory | None:
        return self.session.scalar(
            select(Memory).where(Memory.content_hash == digest).order_by(Memory.created_at).limit(1)
        )

    def list(
        self,
        filters: MemoryFilters | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
        order: str = "created_desc",
    ) -> tuple[list[Memory], int]:
        filters = filters or MemoryFilters()
        if order not in ORDERINGS:
            raise InvalidInputError(f"Orden no válido: {order}.")
        total = self.session.scalar(filters.apply(select(func.count()).select_from(Memory))) or 0
        stmt = filters.apply(select(Memory)).order_by(*ORDERINGS[order]).limit(limit).offset(offset)
        return list(self.session.scalars(stmt)), total

    # --------------------------------------------------------------- validación
    def validate(self, data: MemoryData) -> MemoryData:
        content = clean_content(data.content or "")
        if not content:
            raise InvalidInputError("El contenido del recuerdo no puede estar vacío.")
        if len(content) > self.settings.max_content_chars:
            raise InvalidInputError(
                f"El contenido supera el máximo de {self.settings.max_content_chars} caracteres."
            )
        if data.memory_type not in MEMORY_TYPES:
            raise InvalidInputError(
                f"Tipo de memoria no válido: '{data.memory_type}'. Opciones: {MEMORY_TYPES}."
            )
        if data.source_type not in SOURCE_TYPES:
            raise InvalidInputError(f"Tipo de fuente no válido: '{data.source_type}'.")
        if not 1 <= int(data.importance) <= 5:
            raise InvalidInputError("La importancia debe estar entre 1 y 5.")
        if data.project_id is not None and self.session.get(Project, data.project_id) is None:
            raise InvalidInputError(f"No existe el proyecto {data.project_id}.")
        data.content = content
        data.title = (data.title or "").strip()[:300] or None
        data.kind = (data.kind or "note").strip().lower()[:50] or "note"
        data.tags = normalize_tags(data.tags)
        data.source_ref = (data.source_ref or "").strip()[:500] or None
        return data

    # ---------------------------------------------------------------- escritura
    def create(
        self,
        data: MemoryData,
        *,
        validated: bool = False,
        vectors: list[list[float]] | None = None,
    ) -> Memory:
        if not validated:
            data = self.validate(data)
        now = utcnow()
        memory = Memory(
            id=uuid.uuid4(),
            memory_type=data.memory_type,
            kind=data.kind,
            title=data.title,
            content=data.content,
            content_hash=content_hash(data.content),
            source_type=data.source_type,
            source_ref=data.source_ref,
            provenance=data.provenance or {},
            project_id=data.project_id,
            module=data.module,
            tags=data.tags,
            importance=int(data.importance),
            metadata_=data.metadata or {},
            status="active",
            occurred_at=data.occurred_at,
            version=1,
            created_by=self.actor,
            created_at=now,
            updated_at=now,
        )
        self.session.add(memory)
        self.session.flush()
        versioning.record_version(self.session, memory, change_type="create", actor=self.actor)
        self._index(memory, vectors)
        log_change(
            self.session,
            entity_type="memory",
            entity_id=memory.id,
            action="create",
            summary=f"Recuerdo creado: {memory.title or excerpt(memory.content, 80)}",
            details={"memory_type": memory.memory_type, "kind": memory.kind},
            actor=self.actor,
            project_id=memory.project_id,
        )
        self.session.flush()
        events.bus.publish(events.MEMORY_CREATED, session=self.session, memory=memory)
        return memory

    def update(
        self,
        memory_id: uuid.UUID,
        changes: dict[str, Any],
        *,
        reason: str | None = None,
        change_type: str = "update",
    ) -> Memory:
        memory = self.get(memory_id)
        unknown = set(changes) - set(EDITABLE_FIELDS)
        if unknown:
            raise InvalidInputError(f"Campos no editables: {', '.join(sorted(unknown))}.")
        before = versioning.snapshot(memory)

        candidate = MemoryData(
            content=changes.get("content", memory.content),
            memory_type=changes.get("memory_type", memory.memory_type),
            kind=changes.get("kind", memory.kind),
            title=changes.get("title", memory.title),
            source_type=changes.get("source_type", memory.source_type),
            source_ref=changes.get("source_ref", memory.source_ref),
            provenance=changes.get("provenance", memory.provenance),
            project_id=changes.get("project_id", memory.project_id),
            module=memory.module,
            tags=changes.get("tags", memory.tags),
            importance=changes.get("importance", memory.importance),
            metadata=changes.get("metadata", memory.metadata_),
            occurred_at=changes.get("occurred_at", memory.occurred_at),
        )
        candidate = self.validate(candidate)

        memory.content = candidate.content
        memory.memory_type = candidate.memory_type
        memory.kind = candidate.kind
        memory.title = candidate.title
        memory.source_type = candidate.source_type
        memory.source_ref = candidate.source_ref
        memory.provenance = candidate.provenance or {}
        memory.project_id = candidate.project_id
        memory.tags = candidate.tags
        memory.importance = int(candidate.importance)
        memory.metadata_ = candidate.metadata or {}
        memory.occurred_at = candidate.occurred_at

        changed = versioning.diff_fields(before, versioning.snapshot(memory))
        if not changed:
            self.session.expire(memory)
            return self.get(memory_id)

        text_changed = "content" in changed or "title" in changed
        self._bump(memory, change_type, reason, changed)
        if text_changed:
            memory.content_hash = content_hash(memory.content)
            self._index(memory)
        log_change(
            self.session,
            entity_type="memory",
            entity_id=memory.id,
            action=change_type,
            summary=f"Recuerdo actualizado (v{memory.version}): "
            f"{memory.title or excerpt(memory.content, 80)}",
            details={"changed_fields": changed, "reason": reason, "version": memory.version},
            actor=self.actor,
            project_id=memory.project_id,
        )
        self.session.flush()
        self.session.refresh(memory)
        events.bus.publish(events.MEMORY_UPDATED, session=self.session, memory=memory)
        return memory

    def set_status(self, memory_id: uuid.UUID, status: str, reason: str | None = None) -> Memory:
        memory = self.get(memory_id)
        if memory.status == status:
            return memory
        memory.status = status
        action = "archive" if status == "archived" else "restore"
        self._bump(memory, action, reason, ["status"])
        log_change(
            self.session,
            entity_type="memory",
            entity_id=memory.id,
            action=action,
            summary=("Recuerdo archivado: " if status == "archived" else "Recuerdo restaurado: ")
            + (memory.title or excerpt(memory.content, 80)),
            details={"reason": reason, "version": memory.version},
            actor=self.actor,
            project_id=memory.project_id,
        )
        self.session.flush()
        event = events.MEMORY_ARCHIVED if status == "archived" else events.MEMORY_RESTORED
        events.bus.publish(event, session=self.session, memory=memory)
        return memory

    def archive(self, memory_id: uuid.UUID, reason: str | None = None) -> Memory:
        return self.set_status(memory_id, "archived", reason)

    def restore(self, memory_id: uuid.UUID, reason: str | None = None) -> Memory:
        return self.set_status(memory_id, "active", reason)

    def revert(self, memory_id: uuid.UUID, version: int, reason: str | None = None) -> Memory:
        """Vuelve al estado de una versión anterior creando una versión nueva."""
        target = versioning.get_version(self.session, memory_id, version)
        if target is None:
            raise NotFoundError(f"El recuerdo {memory_id} no tiene versión {version}.")
        snap = target.snapshot
        project_id = uuid.UUID(snap["project_id"]) if snap.get("project_id") else None
        if project_id is not None and self.session.get(Project, project_id) is None:
            project_id = None  # el proyecto ya no existe
        changes = {
            "memory_type": snap["memory_type"],
            "kind": snap["kind"],
            "title": snap["title"],
            "content": snap["content"],
            "source_type": snap["source_type"],
            "source_ref": snap["source_ref"],
            "provenance": snap["provenance"],
            "project_id": project_id,
            "tags": snap["tags"],
            "importance": snap["importance"],
            "metadata": snap["metadata"],
            "occurred_at": (
                datetime.fromisoformat(snap["occurred_at"]) if snap.get("occurred_at") else None
            ),
        }
        note = f"Revertido a la versión {version}" + (f": {reason}" if reason else "")
        return self.update(memory_id, changes, reason=note, change_type="revert")

    def delete(self, memory_id: uuid.UUID, reason: str | None = None) -> None:
        """Borrado definitivo y explícito. Queda constancia sin el contenido."""
        memory = self.get(memory_id)
        log_change(
            self.session,
            entity_type="memory",
            entity_id=memory.id,
            action="delete",
            summary="Recuerdo eliminado definitivamente",
            details={
                "reason": reason,
                "memory_type": memory.memory_type,
                "kind": memory.kind,
                "versions": memory.version,
                "content_hash": memory.content_hash,
            },
            actor=self.actor,
            project_id=memory.project_id,
        )
        # El historial previo citaba el contenido en sus resúmenes: se depura.
        self.session.execute(
            update(ChangeLog)
            .where(
                ChangeLog.entity_type == "memory",
                ChangeLog.entity_id == str(memory.id),
                ChangeLog.action != "delete",
            )
            .values(summary="[recuerdo eliminado]")
        )
        events.bus.publish(events.MEMORY_DELETED, session=self.session, memory=memory)
        self.session.delete(memory)
        self.session.flush()

    # ----------------------------------------------------------------- internos
    def _bump(self, memory: Memory, change_type: str, reason: str | None, changed: list[str]):
        memory.version += 1
        memory.updated_at = utcnow()
        self.session.flush()
        versioning.record_version(
            self.session,
            memory,
            change_type=change_type,
            reason=reason,
            actor=self.actor,
            changed_fields=changed,
        )

    def _index(self, memory: Memory, vectors: list[list[float]] | None = None) -> None:
        warning = try_index_memory(self.session, memory, self.embedder, self.settings, vectors)
        if warning:
            self.warnings.append(warning)
