"""Lógica del módulo de proyectos."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.database.changelog import log_change
from core.database.models import PROJECT_STATUSES, Memory, Project, ProjectRelation, utcnow
from core.errors import ConflictError, InvalidInputError, NotFoundError
from core.textutils import slugify

EDITABLE = ("name", "description", "objectives", "status", "metadata")


class ProjectService:
    def __init__(self, session: Session, actor: str | None = None):
        self.session = session
        self.actor = actor

    def get(self, project_id: uuid.UUID) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError(f"No existe el proyecto {project_id}.")
        return project

    def list(self, status: str | None = None) -> list[Project]:
        stmt = select(Project).order_by(Project.updated_at.desc())
        if status:
            stmt = stmt.where(Project.status == status)
        return list(self.session.scalars(stmt))

    def _unique_slug(self, base: str) -> str:
        slug, n = base, 2
        while self.session.scalar(select(Project.id).where(Project.slug == slug)) is not None:
            slug = f"{base[:110]}-{n}"
            n += 1
        return slug

    def create(
        self,
        name: str,
        description: str = "",
        objectives: list[str] | None = None,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
    ) -> Project:
        name = name.strip()
        if not name:
            raise InvalidInputError("El proyecto necesita un nombre.")
        if status not in PROJECT_STATUSES:
            raise InvalidInputError(f"Estado no válido. Opciones: {PROJECT_STATUSES}.")
        if self.session.scalar(select(Project.id).where(func.lower(Project.name) == name.lower())):
            raise ConflictError(f"Ya existe un proyecto llamado '{name}'.")
        project = Project(
            slug=self._unique_slug(slugify(name)),
            name=name,
            description=description.strip(),
            objectives=[o.strip() for o in objectives or [] if o.strip()],
            status=status,
            metadata_=metadata or {},
        )
        self.session.add(project)
        self.session.flush()
        log_change(
            self.session,
            entity_type="project",
            entity_id=project.id,
            action="create",
            summary=f"Proyecto creado: {project.name}",
            actor=self.actor,
            project_id=project.id,
        )
        return project

    def update(self, project_id: uuid.UUID, changes: dict[str, Any]) -> Project:
        project = self.get(project_id)
        unknown = set(changes) - set(EDITABLE)
        if unknown:
            raise InvalidInputError(f"Campos no editables: {', '.join(sorted(unknown))}.")
        diff: dict[str, Any] = {}
        for key, value in changes.items():
            attribute = "metadata_" if key == "metadata" else key
            if key == "name":
                value = (value or "").strip()
                if not value:
                    raise InvalidInputError("El proyecto necesita un nombre.")
                clash = self.session.scalar(
                    select(Project.id).where(
                        func.lower(Project.name) == value.lower(), Project.id != project.id
                    )
                )
                if clash:
                    raise ConflictError(f"Ya existe un proyecto llamado '{value}'.")
            if key == "status" and value not in PROJECT_STATUSES:
                raise InvalidInputError(f"Estado no válido. Opciones: {PROJECT_STATUSES}.")
            if key == "objectives":
                value = [o.strip() for o in value or [] if o.strip()]
            if key == "description":
                value = (value or "").strip()
            before = getattr(project, attribute)
            if before != value:
                diff[key] = {"before": before, "after": value}
                setattr(project, attribute, value)
        if diff:
            project.updated_at = utcnow()
            log_change(
                self.session,
                entity_type="project",
                entity_id=project.id,
                action="update",
                summary=f"Proyecto actualizado ({', '.join(diff)}): {project.name}",
                details={"changes": diff},
                actor=self.actor,
                project_id=project.id,
            )
            self.session.flush()
        return project

    def delete(self, project_id: uuid.UUID) -> None:
        project = self.get(project_id)
        detached = (
            self.session.scalar(
                select(func.count()).select_from(Memory).where(Memory.project_id == project.id)
            )
            or 0
        )
        log_change(
            self.session,
            entity_type="project",
            entity_id=project.id,
            action="delete",
            summary=f"Proyecto eliminado: {project.name}",
            details={"memories_detached": detached, "slug": project.slug},
            actor=self.actor,
        )
        self.session.delete(project)
        self.session.flush()

    def touch(self, project_id: uuid.UUID) -> None:
        project = self.session.get(Project, project_id)
        if project is not None:
            project.updated_at = utcnow()

    # ------------------------------------------------------------ relaciones
    def relate(
        self, source_id: uuid.UUID, target_id: uuid.UUID, relation_type: str, description: str = ""
    ) -> ProjectRelation:
        if source_id == target_id:
            raise InvalidInputError("Un proyecto no puede relacionarse consigo mismo.")
        source, target = self.get(source_id), self.get(target_id)
        exists = self.session.scalar(
            select(ProjectRelation.id).where(
                ProjectRelation.source_project_id == source_id,
                ProjectRelation.target_project_id == target_id,
                ProjectRelation.relation_type == relation_type,
            )
        )
        if exists:
            raise ConflictError("Esa relación entre proyectos ya existe.")
        relation = ProjectRelation(
            source_project_id=source_id,
            target_project_id=target_id,
            relation_type=relation_type,
            description=description.strip(),
        )
        self.session.add(relation)
        self.session.flush()
        for project in (source, target):
            log_change(
                self.session,
                entity_type="project_relation",
                entity_id=relation.id,
                action="create",
                summary=f"Relación '{relation_type}': {source.name} → {target.name}",
                actor=self.actor,
                project_id=project.id,
            )
        return relation

    def relations(self, project_id: uuid.UUID) -> list[tuple[ProjectRelation, Project, str]]:
        self.get(project_id)
        rows = self.session.scalars(
            select(ProjectRelation).where(
                or_(
                    ProjectRelation.source_project_id == project_id,
                    ProjectRelation.target_project_id == project_id,
                )
            )
        )
        result = []
        for relation in rows:
            outgoing = relation.source_project_id == project_id
            other_id = relation.target_project_id if outgoing else relation.source_project_id
            other = self.session.get(Project, other_id)
            if other is not None:
                result.append((relation, other, "out" if outgoing else "in"))
        return result

    def unrelate(self, relation_id: uuid.UUID) -> None:
        relation = self.session.get(ProjectRelation, relation_id)
        if relation is None:
            raise NotFoundError(f"No existe la relación {relation_id}.")
        for pid in (relation.source_project_id, relation.target_project_id):
            log_change(
                self.session,
                entity_type="project_relation",
                entity_id=relation.id,
                action="delete",
                summary=f"Relación entre proyectos eliminada ({relation.relation_type})",
                actor=self.actor,
                project_id=pid,
            )
        self.session.delete(relation)
        self.session.flush()

    # --------------------------------------------------------------- resumen
    def memory_counts(self, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not project_ids:
            return {}
        rows = self.session.execute(
            select(Memory.project_id, func.count())
            .where(Memory.project_id.in_(project_ids), Memory.status == "active")
            .group_by(Memory.project_id)
        )
        return {row[0]: row[1] for row in rows}

    def overview(self, project_id: uuid.UUID, per_section: int = 10) -> dict[str, Any]:
        project = self.get(project_id)
        base = select(Memory).where(Memory.project_id == project.id, Memory.status == "active")

        def recent(*conditions) -> list[Memory]:
            return list(
                self.session.scalars(
                    base.where(*conditions).order_by(Memory.updated_at.desc()).limit(per_section)
                )
            )

        by_type = {
            row[0]: row[1]
            for row in self.session.execute(
                select(Memory.memory_type, func.count())
                .where(Memory.project_id == project.id, Memory.status == "active")
                .group_by(Memory.memory_type)
            )
        }
        archived = (
            self.session.scalar(
                select(func.count())
                .select_from(Memory)
                .where(Memory.project_id == project.id, Memory.status == "archived")
            )
            or 0
        )
        return {
            "project": project,
            "counts": {
                "active_memories": sum(by_type.values()),
                "archived_memories": archived,
                "by_type": by_type,
            },
            "decisions": recent(Memory.kind == "decision"),
            "documents": recent(Memory.memory_type == "document"),
            "conversations": recent(Memory.kind == "conversation"),
            "recent_memories": recent(),
            "relations": self.relations(project.id),
        }
