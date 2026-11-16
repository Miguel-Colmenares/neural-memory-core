from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.database.models import Memory
from core.errors import InvalidInputError, NotFoundError
from core.ingestion.pipeline import IngestionInput
from core.web.deps import Editor, IngestionDep, MemoryServiceDep, Reader, SessionDep
from core.web.schemas import StrictModel

router = APIRouter(prefix="/preferences", tags=["Preferencias personales"])
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")


class PreferenceSet(StrictModel):
    value: str = Field(min_length=1, max_length=5000, description="La preferencia, en texto.")
    category: str | None = Field(default=None, max_length=80)
    reason: str | None = Field(default=None, max_length=1000, description="Motivo del cambio.")


class PreferenceOut(BaseModel):
    key: str
    value: str
    category: str | None
    memory_id: uuid.UUID
    version: int
    updated_at: datetime


def _find(session, key: str) -> Memory | None:
    return session.scalar(
        select(Memory).where(
            Memory.memory_type == "preference",
            Memory.kind == "preference",
            Memory.status == "active",
            Memory.metadata_["preference_key"].astext == key,
        )
    )


def _out(memory: Memory) -> PreferenceOut:
    return PreferenceOut(
        key=memory.metadata_.get("preference_key", ""),
        value=memory.content,
        category=memory.metadata_.get("category"),
        memory_id=memory.id,
        version=memory.version,
        updated_at=memory.updated_at,
    )


def _check_key(key: str) -> str:
    key = key.strip().lower()
    if not _KEY_RE.match(key):
        raise InvalidInputError(
            "Clave no válida: usa minúsculas, números, '.', '_' o '-' (máx. 100)."
        )
    return key


@router.get("", response_model=list[PreferenceOut], summary="Listar preferencias")
def list_preferences(session: SessionDep, _: Reader, category: str | None = None):
    stmt = (
        select(Memory)
        .where(
            Memory.memory_type == "preference",
            Memory.kind == "preference",
            Memory.status == "active",
            Memory.metadata_.has_key("preference_key"),
        )
        .order_by(Memory.metadata_["preference_key"].astext)
    )
    if category:
        stmt = stmt.where(Memory.metadata_["category"].astext == category)
    return [_out(m) for m in session.scalars(stmt)]


@router.get("/{key}", response_model=PreferenceOut, summary="Obtener una preferencia")
def get_preference(key: str, session: SessionDep, _: Reader):
    memory = _find(session, _check_key(key))
    if memory is None:
        raise NotFoundError(f"No hay una preferencia con la clave '{key}'.")
    return _out(memory)


@router.put("/{key}", response_model=PreferenceOut, summary="Definir o cambiar una preferencia")
def set_preference(
    key: str,
    body: PreferenceSet,
    session: SessionDep,
    service: MemoryServiceDep,
    pipeline: IngestionDep,
    _: Editor,
    response: Response,
):
    """Si la clave ya existe se crea una versión nueva del mismo recuerdo, de modo
    que el valor anterior queda en el historial."""
    key = _check_key(key)
    existing = _find(session, key)
    if existing is not None:
        metadata = {
            **existing.metadata_,
            "category": body.category or existing.metadata_.get("category"),
        }
        memory = service.update(
            existing.id, {"content": body.value, "metadata": metadata}, reason=body.reason
        )
        return _out(memory)
    result = pipeline.ingest(
        IngestionInput(
            content=body.value,
            memory_type="preference",
            kind="preference",
            title=f"Preferencia: {key}",
            source_type="manual",
            module="personal",
            metadata={"preference_key": key, "category": body.category},
            auto_tag=False,
            auto_relate=False,
            allow_duplicate=True,
        )
    )
    response.status_code = 201
    return _out(result.memory)
