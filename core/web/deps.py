"""Dependencias de FastAPI compartidas por la API y por los módulos."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.config import Settings, get_settings
from core.database.base import get_session
from core.database.models import User
from core.embeddings.base import EmbeddingProvider
from core.embeddings.factory import get_embedder
from core.ingestion.pipeline import IngestionPipeline
from core.knowledge_graph.service import KnowledgeGraph
from core.memory_engine.service import MemoryService
from core.security.auth import decode_access_token

_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
EmbedderDep = Annotated[EmbeddingProvider, Depends(get_embedder)]


def current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticación requerida.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    payload = decode_access_token(credentials.credentials, settings)
    if payload is None:
        raise unauthorized
    try:
        user = session.get(User, uuid.UUID(payload["sub"]))
    except (KeyError, ValueError):
        raise unauthorized from None
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: str):
    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu rol no permite esta operación.",
            )
        return user

    return checker


#: Puede leer (cualquier usuario autenticado).
Reader = CurrentUser
#: Puede crear y modificar contenido.
Editor = Annotated[User, Depends(require_roles("admin", "editor"))]
#: Puede administrar el sistema (respaldos, exportación, reindexación).
Admin = Annotated[User, Depends(require_roles("admin"))]


def memory_service(
    session: SessionDep, embedder: EmbedderDep, settings: SettingsDep, user: CurrentUser
) -> MemoryService:
    return MemoryService(session, embedder, settings, actor=user.username)


def ingestion_pipeline(
    session: SessionDep, embedder: EmbedderDep, settings: SettingsDep, user: CurrentUser
) -> IngestionPipeline:
    return IngestionPipeline(session, embedder, settings, actor=user.username)


def knowledge_graph(session: SessionDep, user: CurrentUser) -> KnowledgeGraph:
    return KnowledgeGraph(session, actor=user.username)


MemoryServiceDep = Annotated[MemoryService, Depends(memory_service)]
IngestionDep = Annotated[IngestionPipeline, Depends(ingestion_pipeline)]
GraphDep = Annotated[KnowledgeGraph, Depends(knowledge_graph)]
