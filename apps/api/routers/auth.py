from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from core.database.changelog import log_change
from core.database.models import User
from core.security.auth import (
    LoginThrottle,
    authenticate,
    create_access_token,
    create_user,
    hash_password,
    verify_password,
)
from core.web.deps import Admin, CurrentUser, SessionDep, SettingsDep
from core.web.schemas import LoginRequest, PasswordChange, TokenOut, UserCreate, UserOut

logger = logging.getLogger("nmc.auth")
router = APIRouter(prefix="/auth", tags=["Autenticación"])
_throttle: LoginThrottle | None = None


def _get_throttle(settings) -> LoginThrottle:
    global _throttle
    if _throttle is None:
        _throttle = LoginThrottle(settings.max_login_attempts, settings.login_window_seconds)
    return _throttle


def reset_throttle() -> None:
    global _throttle
    _throttle = None


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenOut, summary="Iniciar sesión")
def login(body: LoginRequest, request: Request, session: SessionDep, settings: SettingsDep):
    throttle = _get_throttle(settings)
    client = request.client.host if request.client else "desconocido"
    key = f"{body.username.strip().lower()}|{client}"
    if throttle.blocked(key):
        logger.warning("Inicio de sesión bloqueado por exceso de intentos: %s", key)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.",
        )
    user = authenticate(session, body.username, body.password)
    if user is None:
        throttle.failure(key)
        logger.warning("Inicio de sesión fallido para %s", key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos.")
    throttle.success(key)
    token, expires = create_access_token(user, settings)
    return TokenOut(access_token=token, expires_at=expires, username=user.username, role=user.role)


@router.get("/me", response_model=UserOut, summary="Usuario actual")
def me(user: CurrentUser):
    return _user_out(user)


@router.post("/password", status_code=204, summary="Cambiar la contraseña propia")
def change_password(body: PasswordChange, user: CurrentUser, session: SessionDep):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta.")
    user.password_hash = hash_password(body.new_password)
    log_change(
        session,
        entity_type="user",
        entity_id=user.id,
        action="password_change",
        summary=f"Contraseña cambiada: {user.username}",
        actor=user.username,
    )


@router.get("/users", response_model=list[UserOut], summary="Listar usuarios")
def list_users(_: Admin, session: SessionDep):
    return [_user_out(u) for u in session.scalars(select(User).order_by(User.created_at))]


@router.post("/users", response_model=UserOut, status_code=201, summary="Crear usuario")
def add_user(body: UserCreate, admin: Admin, session: SessionDep):
    user = create_user(session, body.username, body.password, body.role)
    log_change(
        session,
        entity_type="user",
        entity_id=user.id,
        action="create",
        summary=f"Usuario creado: {user.username} ({user.role})",
        actor=admin.username,
    )
    return _user_out(user)


@router.post("/users/{user_id}/deactivate", response_model=UserOut, summary="Desactivar usuario")
def deactivate_user(user_id: uuid.UUID, admin: Admin, session: SessionDep):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe el usuario.")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes desactivar tu propio usuario.")
    user.is_active = False
    log_change(
        session,
        entity_type="user",
        entity_id=user.id,
        action="deactivate",
        summary=f"Usuario desactivado: {user.username}",
        actor=admin.username,
    )
    return _user_out(user)
