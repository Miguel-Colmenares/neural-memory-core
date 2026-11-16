"""Módulo documental: archivos, notas y material de referencia."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from core.database.models import Memory
from core.module_system.base import ModuleManifest, NMCModule


class DocumentsModule(NMCModule):
    manifest = ModuleManifest(
        name="documents",
        version="1.0.0",
        description="Ingesta de archivos (texto y PDF) y notas como memoria documental.",
        memory_types=("document",),
        kinds=("document",),
    )

    def get_router(self):
        from modules.documents.router import router

        return router

    def stats(self, session) -> dict[str, Any]:
        total, characters = session.execute(
            select(func.count(), func.coalesce(func.sum(func.length(Memory.content)), 0)).where(
                Memory.memory_type == "document", Memory.status == "active"
            )
        ).one()
        return {"total": total, "characters": int(characters)}


module = DocumentsModule()
