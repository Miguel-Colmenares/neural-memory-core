"""Módulo de conocimiento: conceptos y definiciones (memoria semántica)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from core.database.models import Memory
from core.module_system.base import ModuleManifest, NMCModule


class KnowledgeModule(NMCModule):
    manifest = ModuleManifest(
        name="knowledge",
        version="1.0.0",
        description="Conceptos, definiciones y sus relaciones.",
        memory_types=("semantic",),
        kinds=("concept",),
    )

    def get_router(self):
        from modules.knowledge.router import router

        return router

    def stats(self, session) -> dict[str, Any]:
        total = session.scalar(
            select(func.count())
            .select_from(Memory)
            .where(Memory.kind == "concept", Memory.status == "active")
        )
        return {"concepts": total or 0}


module = KnowledgeModule()
