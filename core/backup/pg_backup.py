"""Copias de seguridad físicas con ``pg_dump`` / ``pg_restore``.

El respaldo en formato *custom* contiene toda la base de datos (incluidos
usuarios y embeddings). Guárdalo fuera del servidor y nunca en el repositorio.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from core.config import Settings
from core.errors import InvalidInputError, NotFoundError, ServiceUnavailableError

_NAME_RE = re.compile(r"^nmc-backup-[0-9A-Za-z_.-]+\.dump$")


def _connection_env(database_url: str) -> tuple[dict[str, str], str]:
    url = make_url(database_url)
    env = dict(os.environ)
    if url.host:
        env["PGHOST"] = url.host
    if url.port:
        env["PGPORT"] = str(url.port)
    if url.username:
        env["PGUSER"] = url.username
    if url.password:
        env["PGPASSWORD"] = url.password  # por entorno: no aparece en la lista de procesos
    return env, url.database or ""


def backup_dir(settings: Settings) -> Path:
    path = Path(settings.backup_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _require(tool: str) -> str:
    found = shutil.which(tool)
    if not found:
        raise ServiceUnavailableError(
            f"No se encontró '{tool}'. Instala el cliente de PostgreSQL en este equipo."
        )
    return found


def create_backup(settings: Settings, label: str = "") -> dict[str, Any]:
    tool = _require("pg_dump")
    env, database = _connection_env(settings.database_url)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "-" + re.sub(r"[^0-9A-Za-z_-]+", "-", label).strip("-")[:40] if label else ""
    target = backup_dir(settings) / f"nmc-backup-{stamp}{suffix}.dump"
    partial = target.with_suffix(".partial")
    result = subprocess.run(  # noqa: S603
        [tool, "--format=custom", "--no-owner", "--no-privileges", f"--file={partial}", database],
        env=env,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if result.returncode != 0:
        partial.unlink(missing_ok=True)
        raise ServiceUnavailableError(f"pg_dump falló: {result.stderr.strip()[:500]}")
    os.chmod(partial, 0o600)
    partial.rename(target)
    return describe(target)


def describe(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
    }


def list_backups(settings: Settings) -> list[dict[str, Any]]:
    files = sorted(backup_dir(settings).glob("nmc-backup-*.dump"), reverse=True)
    return [describe(f) for f in files]


def resolve_backup(settings: Settings, name: str) -> Path:
    """Valida el nombre para impedir salir del directorio de respaldos."""
    if not _NAME_RE.match(name):
        raise InvalidInputError("Nombre de respaldo no válido.")
    path = backup_dir(settings) / name
    if not path.is_file():
        raise NotFoundError(f"No existe el respaldo '{name}'.")
    return path


def delete_backup(settings: Settings, name: str) -> None:
    resolve_backup(settings, name).unlink()


def restore_backup(settings: Settings, path: Path) -> None:
    """Restaura un respaldo sobre la base configurada (reemplaza su contenido)."""
    tool = _require("pg_restore")
    if not path.is_file():
        raise NotFoundError(f"No existe el archivo {path}.")
    env, database = _connection_env(settings.database_url)
    result = subprocess.run(  # noqa: S603
        [
            tool,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--single-transaction",
            f"--dbname={database}",
            str(path),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if result.returncode != 0:
        raise ServiceUnavailableError(f"pg_restore falló: {result.stderr.strip()[:1000]}")
