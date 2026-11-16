"""Módulo personal: preferencias de trabajo con clave estable e historial."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from core.database.models import Memory
from core.module_system.base import ModuleManifest, NMCModule


class PersonalModule(NMCModule):
    manifest = ModuleManifest(
        name="personal",
        version="1.0.0",
        description="Preferencias personales (formatos, herramientas, configuraciones).",
        memory_types=("preference",),
        kinds=("preference",),
    )

    def get_router(self):
        from modules.personal.router import router

        return router

    def stats(self, session) -> dict[str, Any]:
        total = session.scalar(
            select(func.count())
            .select_from(Memory)
            .where(Memory.memory_type == "preference", Memory.status == "active")
        )
        return {"preferences": total or 0}


module = PersonalModule()
