"""Grafo de conocimiento: relaciones tipadas entre recuerdos."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.database.changelog import log_change
from core.database.models import Memory, MemoryRelation
from core.errors import ConflictError, InvalidInputError, NotFoundError
from core.memory_engine.filters import MemoryFilters
from core.textutils import excerpt

# Tipos conocidos. Los módulos pueden usar otros: el campo es texto libre validado.
RELATION_TYPES = (
    "related",  # relación temática general
    "possible_duplicate",  # contenido casi idéntico detectado automáticamente
    "contradicts",  # información incompatible; se conservan ambas
    "supersedes",  # el origen reemplaza al destino (que no se borra)
    "derived_from",  # el origen se obtuvo a partir del destino
    "part_of",  # el origen forma parte del destino
    "references",  # el origen menciona al destino
)
SYMMETRIC_TYPES = {"related", "possible_duplicate", "contradicts"}


@dataclass
class Neighbor:
    memory: Memory
    relation: MemoryRelation
    direction: str  # "out" (origen -> vecino) | "in"


class KnowledgeGraph:
    def __init__(self, session: Session, actor: str | None = None):
        self.session = session
        self.actor = actor

    def relate(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation_type: str = "related",
        *,
        origin: str = "manual",
        confidence: float | None = None,
        note: str | None = None,
        log: bool = True,
    ) -> MemoryRelation:
        relation_type = (relation_type or "").strip().lower()
        if (
            not relation_type
            or len(relation_type) > 40
            or not relation_type.replace("_", "").isalnum()
        ):
            raise InvalidInputError("Tipo de relación no válido.")
        if source_id == target_id:
            raise InvalidInputError("Un recuerdo no puede relacionarse consigo mismo.")
        for memory_id in (source_id, target_id):
            if self.session.get(Memory, memory_id) is None:
                raise NotFoundError(f"No existe el recuerdo {memory_id}.")
        existing = self._find(source_id, target_id, relation_type)
        if existing is not None:
            if origin == "auto":
                return existing
            raise ConflictError("Esa relación ya existe.")
        relation = MemoryRelation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            origin=origin,
            confidence=confidence,
            note=note,
            created_by=self.actor,
        )
        self.session.add(relation)
        self.session.flush()
        if log:
            log_change(
                self.session,
                entity_type="relation",
                entity_id=relation.id,
                action="create",
                summary=f"Relación '{relation_type}' creada ({origin})",
                details={
                    "source_id": str(source_id),
                    "target_id": str(target_id),
                    "confidence": confidence,
                },
                actor=self.actor,
            )
        return relation

    def _find(self, source_id, target_id, relation_type) -> MemoryRelation | None:
        stmt = select(MemoryRelation).where(MemoryRelation.relation_type == relation_type)
        direct = (MemoryRelation.source_id == source_id) & (MemoryRelation.target_id == target_id)
        if relation_type in SYMMETRIC_TYPES:
            inverse = (MemoryRelation.source_id == target_id) & (
                MemoryRelation.target_id == source_id
            )
            stmt = stmt.where(or_(direct, inverse))
        else:
            stmt = stmt.where(direct)
        return self.session.scalar(stmt.limit(1))

    def remove(self, relation_id: uuid.UUID) -> None:
        relation = self.session.get(MemoryRelation, relation_id)
        if relation is None:
            raise NotFoundError(f"No existe la relación {relation_id}.")
        log_change(
            self.session,
            entity_type="relation",
            entity_id=relation.id,
            action="delete",
            summary=f"Relación '{relation.relation_type}' eliminada",
            details={"source_id": str(relation.source_id), "target_id": str(relation.target_id)},
            actor=self.actor,
        )
        self.session.delete(relation)
        self.session.flush()

    def neighbors(
        self, memory_ids: list[uuid.UUID], *, only_active: bool = True
    ) -> dict[uuid.UUID, list[Neighbor]]:
        """Vecinos a un salto de cada recuerdo indicado."""
        result: dict[uuid.UUID, list[Neighbor]] = {mid: [] for mid in memory_ids}
        if not memory_ids:
            return result
        relations = list(
            self.session.scalars(
                select(MemoryRelation).where(
                    or_(
                        MemoryRelation.source_id.in_(memory_ids),
                        MemoryRelation.target_id.in_(memory_ids),
                    )
                )
            )
        )
        other_ids = {r.source_id for r in relations} | {r.target_id for r in relations}
        memories = {
            m.id: m for m in self.session.scalars(select(Memory).where(Memory.id.in_(other_ids)))
        }
        for relation in relations:
            for own, other, direction in (
                (relation.source_id, relation.target_id, "out"),
                (relation.target_id, relation.source_id, "in"),
            ):
                if own in result and other in memories:
                    neighbor = memories[other]
                    if only_active and neighbor.status != "active":
                        continue
                    result[own].append(Neighbor(neighbor, relation, direction))
        return result

    def graph(
        self,
        filters: MemoryFilters | None = None,
        *,
        limit: int = 200,
        focus_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Nodos y aristas para la visualización.

        Con ``focus_id`` devuelve el vecindario de ese recuerdo; sin él, los
        recuerdos con más relaciones que cumplan los filtros.
        """
        filters = filters or MemoryFilters()
        if focus_id is not None:
            center = self.session.get(Memory, focus_id)
            if center is None:
                raise NotFoundError(f"No existe el recuerdo {focus_id}.")
            first = self.neighbors([focus_id], only_active=False)[focus_id]
            ids = [focus_id] + [n.memory.id for n in first][: limit - 1]
        else:
            degree = (
                select(Memory.id, func.count(MemoryRelation.id).label("degree"))
                .join(
                    MemoryRelation,
                    or_(
                        MemoryRelation.source_id == Memory.id, MemoryRelation.target_id == Memory.id
                    ),
                )
                .group_by(Memory.id)
                .order_by(func.count(MemoryRelation.id).desc(), Memory.created_at.desc())
                .limit(limit)
            )
            ids = [row[0] for row in self.session.execute(filters.apply(degree))]
        if not ids:
            return {"nodes": [], "edges": [], "total_relations": self.count()}
        memories = list(self.session.scalars(select(Memory).where(Memory.id.in_(ids))))
        relations = list(
            self.session.scalars(
                select(MemoryRelation).where(
                    MemoryRelation.source_id.in_(ids), MemoryRelation.target_id.in_(ids)
                )
            )
        )
        degrees: dict[uuid.UUID, int] = {}
        for r in relations:
            degrees[r.source_id] = degrees.get(r.source_id, 0) + 1
            degrees[r.target_id] = degrees.get(r.target_id, 0) + 1
        return {
            "nodes": [
                {
                    "id": str(m.id),
                    "label": m.title or excerpt(m.content, 60),
                    "memory_type": m.memory_type,
                    "kind": m.kind,
                    "status": m.status,
                    "project_id": str(m.project_id) if m.project_id else None,
                    "importance": m.importance,
                    "degree": degrees.get(m.id, 0),
                }
                for m in memories
            ],
            "edges": [
                {
                    "id": str(r.id),
                    "source": str(r.source_id),
                    "target": str(r.target_id),
                    "relation_type": r.relation_type,
                    "origin": r.origin,
                    "confidence": r.confidence,
                }
                for r in relations
            ],
            "total_relations": self.count(),
        }

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(MemoryRelation)) or 0
