"""Registro de cambios (auditoría) usado por el núcleo y por los módulos."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from core.database.models import ChangeLog


def log_change(
    session: Session,
    *,
    entity_type: str,
    entity_id: Any,
    action: str,
    summary: str = "",
    details: dict[str, Any] | None = None,
    actor: str | None = None,
    project_id: uuid.UUID | None = None,
) -> ChangeLog:
    entry = ChangeLog(
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        summary=summary[:2000],
        details=details or {},
        actor=actor,
        project_id=project_id,
    )
    session.add(entry)
    return entry
