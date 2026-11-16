"""Historial de versiones de los recuerdos.

Regla del sistema: ningún recuerdo se sobrescribe sin dejar antes una
fotografía completa de su estado. La versión 1 se registra al crearlo.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import Memory, MemoryVersion

VERSIONED_FIELDS = (
    "memory_type",
    "kind",
    "title",
    "content",
    "source_type",
    "source_ref",
    "provenance",
    "project_id",
    "module",
    "tags",
    "importance",
    "metadata",
    "status",
    "occurred_at",
)


def snapshot(memory: Memory) -> dict[str, Any]:
    return {
        "memory_type": memory.memory_type,
        "kind": memory.kind,
        "title": memory.title,
        "content": memory.content,
        "source_type": memory.source_type,
        "source_ref": memory.source_ref,
        "provenance": dict(memory.provenance or {}),
        "project_id": str(memory.project_id) if memory.project_id else None,
        "module": memory.module,
        "tags": list(memory.tags or []),
        "importance": memory.importance,
        "metadata": dict(memory.metadata_ or {}),
        "status": memory.status,
        "occurred_at": memory.occurred_at.isoformat() if memory.occurred_at else None,
    }


def diff_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return [f for f in VERSIONED_FIELDS if before.get(f) != after.get(f)]


def record_version(
    session: Session,
    memory: Memory,
    *,
    change_type: str,
    reason: str | None = None,
    actor: str | None = None,
    changed_fields: list[str] | None = None,
) -> MemoryVersion:
    version = MemoryVersion(
        memory_id=memory.id,
        version=memory.version,
        snapshot=snapshot(memory),
        change_type=change_type,
        change_reason=reason,
        changed_fields=changed_fields or [],
        changed_by=actor,
    )
    session.add(version)
    return version


def list_versions(session: Session, memory_id: uuid.UUID) -> list[MemoryVersion]:
    return list(
        session.scalars(
            select(MemoryVersion)
            .where(MemoryVersion.memory_id == memory_id)
            .order_by(MemoryVersion.version.desc())
        )
    )


def get_version(session: Session, memory_id: uuid.UUID, version: int) -> MemoryVersion | None:
    return session.scalar(
        select(MemoryVersion).where(
            MemoryVersion.memory_id == memory_id, MemoryVersion.version == version
        )
    )
