"""Módulo de tareas pendientes, con tabla propia."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select

from core.database.models import Project
from core.module_system.base import ModuleManifest, NMCModule
from modules.tasks.models import OPEN_STATUSES, Task


class TasksModule(NMCModule):
    manifest = ModuleManifest(
        name="tasks",
        version="1.0.0",
        description="Tareas pendientes, asociables a proyectos.",
        depends_on=("projects",),
    )

    def get_router(self):
        from modules.tasks.router import router

        return router

    def stats(self, session) -> dict[str, Any]:
        rows = session.execute(select(Task.status, func.count()).group_by(Task.status))
        by_status = {row[0]: row[1] for row in rows}
        return {
            "total": sum(by_status.values()),
            "open": sum(by_status.get(s, 0) for s in OPEN_STATUSES),
            "by_status": by_status,
        }

    def contribute_to_answer(self, session, analysis, filters) -> list[dict[str, Any]]:
        if not analysis.has("tasks"):
            return []
        stmt = (
            select(Task)
            .where(Task.status.in_(OPEN_STATUSES))
            .order_by(Task.priority.desc(), Task.created_at.desc())
            .limit(15)
        )
        project_ids = filters.project_ids or analysis.project_ids
        if project_ids:
            stmt = stmt.where(Task.project_id.in_(project_ids))
        facts = []
        for task in session.scalars(stmt):
            due = f", vence {task.due_date.isoformat()}" if task.due_date else ""
            facts.append(
                {
                    "text": f"Tarea {task.status} (prioridad {task.priority}{due}): {task.title}",
                    "source_kind": "task",
                    "id": str(task.id),
                    "label": task.title,
                    "excerpt": task.description[:300],
                }
            )
        return facts

    def export_data(self, session) -> dict[str, Any]:
        return {
            "tasks": [
                {
                    "id": str(t.id),
                    "project_id": str(t.project_id) if t.project_id else None,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status,
                    "priority": t.priority,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "created_at": t.created_at.isoformat(),
                    "updated_at": t.updated_at.isoformat(),
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                }
                for t in session.scalars(select(Task).order_by(Task.created_at))
            ]
        }

    def import_data(self, session, data) -> dict[str, int]:
        existing = set(session.scalars(select(Task.id)))
        projects = set(session.scalars(select(Project.id)))
        imported = skipped = 0
        for item in data.get("tasks", []):
            task_id = uuid.UUID(item["id"])
            if task_id in existing:
                skipped += 1
                continue
            project_id = uuid.UUID(item["project_id"]) if item.get("project_id") else None
            session.add(
                Task(
                    id=task_id,
                    project_id=project_id if project_id in projects else None,
                    title=item["title"],
                    description=item.get("description", ""),
                    status=item.get("status", "pending"),
                    priority=item.get("priority", 3),
                    due_date=date.fromisoformat(item["due_date"]) if item.get("due_date") else None,
                    created_at=datetime.fromisoformat(item["created_at"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                    completed_at=(
                        datetime.fromisoformat(item["completed_at"])
                        if item.get("completed_at")
                        else None
                    ),
                )
            )
            imported += 1
        return {"imported": imported, "skipped": skipped}


module = TasksModule()
