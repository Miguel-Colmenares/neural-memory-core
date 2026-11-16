"""Exportación e importación completas de la memoria en JSON portable.

Se exporta todo lo necesario para reconstruir la memoria en otra instalación:
proyectos, recuerdos, versiones, relaciones, historial y datos de módulos.
No se exportan usuarios ni contraseñas, ni embeddings (se regeneran).
La importación fusiona: nunca sobrescribe un registro existente.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import read_version
from core.database.changelog import log_change
from core.database.models import (
    ChangeLog,
    Memory,
    MemoryRelation,
    MemoryVersion,
    Project,
    ProjectRelation,
    utcnow,
)
from core.embeddings.base import EmbeddingProvider
from core.embeddings.indexer import reindex
from core.errors import InvalidInputError
from core.module_system.registry import registry
from core.textutils import content_hash

FORMAT_NAME = "neural-memory-core-export"
FORMAT_VERSION = 1


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None


def export_all(session: Session) -> dict[str, Any]:
    projects = [
        {
            "id": str(p.id),
            "slug": p.slug,
            "name": p.name,
            "description": p.description,
            "objectives": p.objectives,
            "status": p.status,
            "metadata": p.metadata_,
            "created_at": _iso(p.created_at),
            "updated_at": _iso(p.updated_at),
        }
        for p in session.scalars(select(Project).order_by(Project.created_at))
    ]
    project_relations = [
        {
            "id": str(r.id),
            "source_project_id": str(r.source_project_id),
            "target_project_id": str(r.target_project_id),
            "relation_type": r.relation_type,
            "description": r.description,
            "created_at": _iso(r.created_at),
        }
        for r in session.scalars(select(ProjectRelation).order_by(ProjectRelation.created_at))
    ]
    memories = [
        {
            "id": str(m.id),
            "memory_type": m.memory_type,
            "kind": m.kind,
            "title": m.title,
            "content": m.content,
            "source_type": m.source_type,
            "source_ref": m.source_ref,
            "provenance": m.provenance,
            "project_id": str(m.project_id) if m.project_id else None,
            "module": m.module,
            "tags": m.tags,
            "importance": m.importance,
            "metadata": m.metadata_,
            "status": m.status,
            "occurred_at": _iso(m.occurred_at),
            "version": m.version,
            "created_by": m.created_by,
            "created_at": _iso(m.created_at),
            "updated_at": _iso(m.updated_at),
        }
        for m in session.scalars(
            select(Memory).order_by(Memory.created_at, Memory.id).execution_options(yield_per=500)
        )
    ]
    versions = [
        {
            "memory_id": str(v.memory_id),
            "version": v.version,
            "snapshot": v.snapshot,
            "change_type": v.change_type,
            "change_reason": v.change_reason,
            "changed_fields": v.changed_fields,
            "changed_by": v.changed_by,
            "created_at": _iso(v.created_at),
        }
        for v in session.scalars(
            select(MemoryVersion)
            .order_by(MemoryVersion.memory_id, MemoryVersion.version)
            .execution_options(yield_per=500)
        )
    ]
    relations = [
        {
            "id": str(r.id),
            "source_id": str(r.source_id),
            "target_id": str(r.target_id),
            "relation_type": r.relation_type,
            "origin": r.origin,
            "confidence": r.confidence,
            "note": r.note,
            "created_by": r.created_by,
            "created_at": _iso(r.created_at),
        }
        for r in session.scalars(select(MemoryRelation).order_by(MemoryRelation.created_at))
    ]
    change_log = [
        {
            "entity_type": c.entity_type,
            "entity_id": c.entity_id,
            "project_id": str(c.project_id) if c.project_id else None,
            "action": c.action,
            "summary": c.summary,
            "details": c.details,
            "actor": c.actor,
            "created_at": _iso(c.created_at),
        }
        for c in session.scalars(
            select(ChangeLog).order_by(ChangeLog.id).execution_options(yield_per=1000)
        )
    ]
    modules = {m.manifest.name: m.export_data(session) for m in registry.all()}
    modules = {name: data for name, data in modules.items() if data}
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "app_version": read_version(),
        "exported_at": _iso(utcnow()),
        "counts": {
            "projects": len(projects),
            "project_relations": len(project_relations),
            "memories": len(memories),
            "memory_versions": len(versions),
            "memory_relations": len(relations),
            "change_log": len(change_log),
        },
        "projects": projects,
        "project_relations": project_relations,
        "memories": memories,
        "memory_versions": versions,
        "memory_relations": relations,
        "change_log": change_log,
        "modules": modules,
    }


def import_all(
    session: Session,
    data: dict[str, Any],
    embedder: EmbeddingProvider,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise InvalidInputError("El archivo no es una exportación de Neural Memory Core.")
    if int(data.get("format_version", 0)) > FORMAT_VERSION:
        raise InvalidInputError(
            "La exportación proviene de una versión más nueva; actualiza antes de importar."
        )
    report: dict[str, dict[str, int]] = {}

    def count(section: str, key: str) -> None:
        report.setdefault(section, {"imported": 0, "skipped": 0})[key] += 1

    try:
        existing_projects = {p.id for p in session.scalars(select(Project))}
        slugs = set(session.scalars(select(Project.slug)))
        for item in data.get("projects", []):
            pid = uuid.UUID(item["id"])
            if pid in existing_projects:
                count("projects", "skipped")
                continue
            slug = item["slug"]
            while slug in slugs:
                slug = f"{slug}-importado"[:120]
            slugs.add(slug)
            session.add(
                Project(
                    id=pid,
                    slug=slug,
                    name=item["name"],
                    description=item.get("description", ""),
                    objectives=item.get("objectives", []),
                    status=item.get("status", "active"),
                    metadata_=item.get("metadata", {}),
                    created_at=_dt(item["created_at"]),
                    updated_at=_dt(item["updated_at"]),
                )
            )
            existing_projects.add(pid)
            count("projects", "imported")
        session.flush()

        existing_rel = set(session.scalars(select(ProjectRelation.id)))
        for item in data.get("project_relations", []):
            rid = uuid.UUID(item["id"])
            src, dst = uuid.UUID(item["source_project_id"]), uuid.UUID(item["target_project_id"])
            if rid in existing_rel or src not in existing_projects or dst not in existing_projects:
                count("project_relations", "skipped")
                continue
            session.add(
                ProjectRelation(
                    id=rid,
                    source_project_id=src,
                    target_project_id=dst,
                    relation_type=item["relation_type"],
                    description=item.get("description", ""),
                    created_at=_dt(item["created_at"]),
                )
            )
            count("project_relations", "imported")

        existing_memories = set(session.scalars(select(Memory.id)))
        imported_memories: set[uuid.UUID] = set()
        for item in data.get("memories", []):
            mid = uuid.UUID(item["id"])
            if mid in existing_memories:
                count("memories", "skipped")
                continue
            project_id = _uuid(item.get("project_id"))
            session.add(
                Memory(
                    id=mid,
                    memory_type=item["memory_type"],
                    kind=item.get("kind", "note"),
                    title=item.get("title"),
                    content=item["content"],
                    content_hash=content_hash(item["content"]),
                    source_type=item.get("source_type", "import"),
                    source_ref=item.get("source_ref"),
                    provenance=item.get("provenance", {}),
                    project_id=project_id if project_id in existing_projects else None,
                    module=item.get("module"),
                    tags=item.get("tags", []),
                    importance=item.get("importance", 3),
                    metadata_=item.get("metadata", {}),
                    status=item.get("status", "active"),
                    occurred_at=_dt(item.get("occurred_at")),
                    version=item.get("version", 1),
                    created_by=item.get("created_by"),
                    created_at=_dt(item["created_at"]),
                    updated_at=_dt(item["updated_at"]),
                )
            )
            imported_memories.add(mid)
            count("memories", "imported")
        session.flush()
        all_memories = existing_memories | imported_memories

        for item in data.get("memory_versions", []):
            mid = uuid.UUID(item["memory_id"])
            if mid not in imported_memories:  # el historial solo viaja con su recuerdo
                count("memory_versions", "skipped")
                continue
            session.add(
                MemoryVersion(
                    memory_id=mid,
                    version=item["version"],
                    snapshot=item["snapshot"],
                    change_type=item["change_type"],
                    change_reason=item.get("change_reason"),
                    changed_fields=item.get("changed_fields", []),
                    changed_by=item.get("changed_by"),
                    created_at=_dt(item["created_at"]),
                )
            )
            count("memory_versions", "imported")

        existing_relations = set(session.scalars(select(MemoryRelation.id)))
        existing_keys = {
            (r.source_id, r.target_id, r.relation_type)
            for r in session.scalars(select(MemoryRelation))
        }
        for item in data.get("memory_relations", []):
            rid = uuid.UUID(item["id"])
            src, dst = uuid.UUID(item["source_id"]), uuid.UUID(item["target_id"])
            key = (src, dst, item["relation_type"])
            if (
                rid in existing_relations
                or key in existing_keys
                or src not in all_memories
                or dst not in all_memories
            ):
                count("memory_relations", "skipped")
                continue
            session.add(
                MemoryRelation(
                    id=rid,
                    source_id=src,
                    target_id=dst,
                    relation_type=item["relation_type"],
                    origin=item.get("origin", "manual"),
                    confidence=item.get("confidence"),
                    note=item.get("note"),
                    created_by=item.get("created_by"),
                    created_at=_dt(item["created_at"]),
                )
            )
            existing_keys.add(key)
            count("memory_relations", "imported")

        known_entries = {
            (c.entity_type, c.entity_id, c.action, c.created_at)
            for c in session.scalars(select(ChangeLog))
        }
        for item in data.get("change_log", []):
            created = _dt(item["created_at"])
            key = (item["entity_type"], item["entity_id"], item["action"], created)
            if key in known_entries:
                count("change_log", "skipped")
                continue
            session.add(
                ChangeLog(
                    entity_type=item["entity_type"],
                    entity_id=item["entity_id"],
                    project_id=_uuid(item.get("project_id")),
                    action=item["action"],
                    summary=item.get("summary", ""),
                    details=item.get("details", {}),
                    actor=item.get("actor"),
                    created_at=created,
                )
            )
            known_entries.add(key)
            count("change_log", "imported")
        session.flush()

        module_reports: dict[str, Any] = {}
        for name, payload in (data.get("modules") or {}).items():
            module = registry.get(name)
            if module is None:
                module_reports[name] = {"error": "módulo no activo; sus datos no se importaron"}
                continue
            module_reports[name] = module.import_data(session, payload)
        session.flush()
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidInputError(f"La exportación está dañada o incompleta: {exc!r}") from exc

    index_report = reindex(session, embedder, only_pending=True)
    log_change(
        session,
        entity_type="system",
        entity_id="import",
        action="import",
        summary="Importación de datos completada",
        details={"report": report, "modules": module_reports, "reindex": index_report},
        actor=actor,
    )
    return {"sections": report, "modules": module_reports, "reindex": index_report}
