"""Módulo de proyectos: espacio lógico por proyecto, decisiones y relaciones."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from core.database.models import Project
from core.module_system import events
from core.module_system.base import ModuleManifest, NMCModule


class ProjectsModule(NMCModule):
    manifest = ModuleManifest(
        name="projects",
        version="1.0.0",
        description="Proyectos con objetivos, decisiones, historial y relaciones entre ellos.",
        memory_types=("project",),
        kinds=("decision",),
    )

    def get_router(self):
        from modules.projects.router import router

        return router

    def register_events(self, bus) -> None:
        bus.subscribe(events.MEMORY_CREATED, self._touch_project)
        bus.subscribe(events.MEMORY_UPDATED, self._touch_project)

    @staticmethod
    def _touch_project(session, memory, **_: Any) -> None:
        """La actividad de un recuerdo cuenta como actividad de su proyecto."""
        if memory.project_id is not None:
            from modules.projects.service import ProjectService

            ProjectService(session).touch(memory.project_id)

    def stats(self, session) -> dict[str, Any]:
        rows = session.execute(select(Project.status, func.count()).group_by(Project.status))
        by_status = {row[0]: row[1] for row in rows}
        return {"total": sum(by_status.values()), "by_status": by_status}


module = ProjectsModule()
