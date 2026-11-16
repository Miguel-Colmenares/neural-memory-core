"""Contraseñas (bcrypt), tokens de acceso (JWT HS256) y gestión de usuarios."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import bcrypt
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import Settings
from core.database.models import USER_ROLES, User
from core.errors import ConflictError, InvalidInputError

ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("ascii"))
    except ValueError:
        return False


@lru_cache
def _dummy_hash() -> str:
    return hash_password("nmc-dummy-password")


def create_access_token(user: User, settings: Settings) -> tuple[str, datetime]:
    expires = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user.id), "usr": user.username, "role": user.role, "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), expires


def decode_access_token(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def create_user(session: Session, username: str, password: str, role: str = "admin") -> User:
    username = username.strip().lower()
    if not 3 <= len(username) <= 80 or not username.replace("_", "").replace(".", "").isalnum():
        raise InvalidInputError("Nombre de usuario no válido (3-80 letras, números, '_' o '.').")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidInputError(
            f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
        )
    if role not in USER_ROLES:
        raise InvalidInputError(f"Rol no válido. Opciones: {USER_ROLES}.")
    if session.scalar(select(User).where(User.username == username)) is not None:
        raise ConflictError(f"El usuario '{username}' ya existe.")
    user = User(username=username, password_hash=hash_password(password), role=role)
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        # Mismo coste con usuario inexistente: no revela qué usuarios existen.
        verify_password(password, _dummy_hash())
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    return user


def bootstrap_admin(session: Session, settings: Settings) -> User | None:
    """Crea el primer administrador desde el entorno si aún no hay usuarios."""
    if not settings.admin_username or not settings.admin_password:
        return None
    if (session.scalar(select(func.count()).select_from(User)) or 0) > 0:
        return None
    return create_user(session, settings.admin_username, settings.admin_password, "admin")


class LoginThrottle:
    """Límite de intentos fallidos por clave (usuario+IP), en memoria del proceso."""

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key, time.monotonic())) >= self.max_attempts

    def failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures[key] = [*self._recent(key, now), now]

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
