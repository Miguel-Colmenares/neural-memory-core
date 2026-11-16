"""Módulo de conversaciones: memoria episódica de diálogos."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from core.database.models import Memory
from core.module_system.base import ModuleManifest, NMCModule


class ConversationsModule(NMCModule):
    manifest = ModuleManifest(
        name="conversations",
        version="1.0.0",
        description="Guarda conversaciones (mensajes o transcripción) como memoria episódica.",
        memory_types=("episodic",),
        kinds=("conversation",),
    )

    def get_router(self):
        from modules.conversations.router import router

        return router

    def stats(self, session) -> dict[str, Any]:
        total = session.scalar(
            select(func.count())
            .select_from(Memory)
            .where(Memory.kind == "conversation", Memory.status == "active")
        )
        return {"total": total or 0}


module = ConversationsModule()
