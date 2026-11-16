"""Bus de eventos síncrono entre el núcleo y los módulos.

El núcleo publica; los módulos se suscriben. Un módulo que falla no rompe la
operación principal: el error se registra y se continúa.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("nmc.events")

MEMORY_CREATED = "memory.created"
MEMORY_UPDATED = "memory.updated"
MEMORY_ARCHIVED = "memory.archived"
MEMORY_RESTORED = "memory.restored"
MEMORY_DELETED = "memory.deleted"

Handler = Callable[..., Any]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        if handler not in self._handlers[event]:
            self._handlers[event].append(handler)

    def publish(self, event: str, **payload: Any) -> None:
        for handler in list(self._handlers.get(event, [])):
            try:
                handler(**payload)
            except Exception:  # noqa: BLE001 - un módulo no debe tumbar al núcleo
                logger.exception("El manejador %r falló para el evento %s", handler, event)

    def clear(self) -> None:
        self._handlers.clear()


bus = EventBus()
