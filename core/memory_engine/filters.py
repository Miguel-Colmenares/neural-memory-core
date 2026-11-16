"""Filtros comunes a los listados y a la recuperación."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Select

from core.database.models import Memory


@dataclass
class MemoryFilters:
    memory_types: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    project_ids: list[uuid.UUID] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # deben estar todas
    status: str | None = "active"  # None = cualquiera
    source_types: list[str] = field(default_factory=list)
    module: str | None = None
    min_importance: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    def apply(self, stmt: Select) -> Select:
        if self.memory_types:
            stmt = stmt.where(Memory.memory_type.in_(self.memory_types))
        if self.kinds:
            stmt = stmt.where(Memory.kind.in_(self.kinds))
        if self.project_ids:
            stmt = stmt.where(Memory.project_id.in_(self.project_ids))
        if self.tags:
            stmt = stmt.where(Memory.tags.contains(self.tags))
        if self.status:
            stmt = stmt.where(Memory.status == self.status)
        if self.source_types:
            stmt = stmt.where(Memory.source_type.in_(self.source_types))
        if self.module:
            stmt = stmt.where(Memory.module == self.module)
        if self.min_importance:
            stmt = stmt.where(Memory.importance >= self.min_importance)
        if self.date_from:
            stmt = stmt.where(Memory.created_at >= self.date_from)
        if self.date_to:
            stmt = stmt.where(Memory.created_at <= self.date_to)
        return stmt

    def describe(self) -> dict:
        data = {
            "memory_types": self.memory_types,
            "kinds": self.kinds,
            "project_ids": [str(p) for p in self.project_ids],
            "tags": self.tags,
            "status": self.status,
            "source_types": self.source_types,
            "module": self.module,
            "min_importance": self.min_importance,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
        }
        return {k: v for k, v in data.items() if v not in (None, [], "")}
