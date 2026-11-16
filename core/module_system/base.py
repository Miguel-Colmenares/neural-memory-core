"""Contrato que debe cumplir todo módulo de Neural Memory Core.

Un módulo es un paquete Python que expone una variable ``module`` (instancia
de :class:`NMCModule`). Puede aportar endpoints, tablas propias, reacciones a
eventos del núcleo, indicadores para el panel y datos para la exportación.
Guía completa: ``docs/modules/crear_modulo.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter
from sqlalchemy.orm import Session

from core.module_system.events import EventBus

MODULE_API_VERSION = 1


@dataclass(frozen=True)
class ModuleManifest:
    name: str
    version: str
    description: str
    #: Tipos de memoria con los que trabaja (informativo).
    memory_types: tuple[str, ...] = ()
    #: Valores de ``kind`` que introduce en los recuerdos.
    kinds: tuple[str, ...] = ()
    #: Otros módulos que deben estar activos.
    depends_on: tuple[str, ...] = ()
    #: Versión del contrato de módulos contra la que se escribió.
    api_version: int = MODULE_API_VERSION
    extra: dict[str, Any] = field(default_factory=dict)


class NMCModule:
    """Clase base. Sobrescribe solo lo que tu módulo necesite."""

    manifest: ModuleManifest

    def get_router(self) -> APIRouter | None:
        """Endpoints del módulo; se montan bajo ``/api/v1``."""
        return None

    def register_events(self, bus: EventBus) -> None:
        """Suscríbete aquí a los eventos del núcleo."""

    def stats(self, session: Session) -> dict[str, Any]:
        """Indicadores reales para el panel (consultas a la base de datos)."""
        return {}

    def contribute_to_answer(
        self, session: Session, analysis: Any, filters: Any
    ) -> list[dict[str, Any]]:
        """Hechos confirmados que el módulo aporta a una pregunta.

        Cada elemento: ``{"text", "source_kind", "id", "label", "excerpt"?}``.
        ``analysis`` es un ``QueryAnalysis`` (intenciones, proyectos, términos).
        """
        return []

    def export_data(self, session: Session) -> dict[str, Any]:
        """Datos de tablas propias del módulo para la exportación completa."""
        return {}

    def import_data(self, session: Session, data: dict[str, Any]) -> dict[str, int]:
        """Restaura lo devuelto por :meth:`export_data`. Devuelve contadores."""
        return {}
