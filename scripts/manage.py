#!/usr/bin/env python
"""Herramienta de administración por línea de comandos.

Uso:  python scripts/manage.py <comando> [opciones]

Comandos:
  create-user   Crea un usuario (pide la contraseña sin mostrarla).
  reindex       Regenera embeddings (--all para rehacer todos).
  export        Exporta toda la memoria a un archivo JSON.
  import        Importa un archivo JSON exportado (fusiona, no sobrescribe).
  backup        Crea un respaldo completo con pg_dump.
  restore       Restaura un respaldo con pg_restore (REEMPLAZA la base actual).
  status        Muestra el estado de la base, el índice y los módulos.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backup import pg_backup  # noqa: E402
from core.backup.export_service import export_all, import_all  # noqa: E402
from core.config import get_settings, read_version  # noqa: E402
from core.database.base import get_session_factory  # noqa: E402
from core.embeddings.factory import get_embedder  # noqa: E402
from core.embeddings.indexer import index_status, reindex  # noqa: E402
from core.errors import NMCError  # noqa: E402
from core.module_system.registry import registry  # noqa: E402
from core.security.auth import create_user  # noqa: E402


def _load_modules() -> None:
    if not registry.names():
        registry.load(get_settings().enabled_module_list)


def cmd_create_user(args) -> int:
    password = args.password or getpass.getpass("Contraseña: ")
    if not args.password and password != getpass.getpass("Repite la contraseña: "):
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 1
    with get_session_factory()() as session:
        user = create_user(session, args.username, password, args.role)
        session.commit()
    print(f"Usuario creado: {user.username} ({user.role})")
    return 0


def cmd_reindex(args) -> int:
    embedder = get_embedder()
    with get_session_factory()() as session:
        report = reindex(session, embedder, only_pending=not args.all)
        session.commit()
        status = index_status(session, embedder)
    print(json.dumps({"reindex": report, "index": status}, indent=2, ensure_ascii=False))
    return 1 if report["failed"] else 0


def cmd_export(args) -> int:
    _load_modules()
    with get_session_factory()() as session:
        data = export_all(session)
    target = Path(args.output)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    target.chmod(0o600)
    print(f"Exportación escrita en {target}: {data['counts']}")
    return 0


def cmd_import(args) -> int:
    _load_modules()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    with get_session_factory()() as session:
        report = import_all(session, data, get_embedder(), actor="cli")
        session.commit()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_backup(args) -> int:
    backup = pg_backup.create_backup(get_settings(), args.label)
    print(f"Respaldo creado: {Path(get_settings().backup_dir).resolve() / backup['name']}")
    print(f"Tamaño: {backup['size_bytes']} bytes")
    return 0


def cmd_restore(args) -> int:
    path = Path(args.file)
    if not args.yes:
        answer = input(
            "Esto REEMPLAZA el contenido de la base de datos configurada. Escribe 'restaurar': "
        )
        if answer.strip().lower() != "restaurar":
            print("Cancelado.")
            return 1
    pg_backup.restore_backup(get_settings(), path)
    print("Respaldo restaurado. Ejecuta 'alembic upgrade head' si actualizaste la aplicación.")
    return 0


def cmd_status(_args) -> int:
    _load_modules()
    settings = get_settings()
    embedder = get_embedder()
    with get_session_factory()() as session:
        status = index_status(session, embedder)
    print(
        json.dumps(
            {
                "version": read_version(),
                "environment": settings.environment,
                "embeddings": embedder.describe(),
                "llm": settings.llm_provider,
                "index": status,
                "modules": registry.names(),
                "backups": len(pg_backup.list_backups(settings)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Administración de Neural Memory Core")
    commands = parser.add_subparsers(dest="command", required=True)

    user = commands.add_parser("create-user", help="Crear un usuario")
    user.add_argument("username")
    user.add_argument("--role", choices=["admin", "editor", "reader"], default="admin")
    user.add_argument("--password", help="Evítalo: queda en el historial de la terminal.")
    user.set_defaults(handler=cmd_create_user)

    index = commands.add_parser("reindex", help="Regenerar embeddings")
    index.add_argument("--all", action="store_true", help="Rehacer todos, no solo los pendientes")
    index.set_defaults(handler=cmd_reindex)

    export = commands.add_parser("export", help="Exportar a JSON")
    export.add_argument("output")
    export.set_defaults(handler=cmd_export)

    import_ = commands.add_parser("import", help="Importar desde JSON")
    import_.add_argument("input")
    import_.set_defaults(handler=cmd_import)

    backup = commands.add_parser("backup", help="Crear respaldo con pg_dump")
    backup.add_argument("--label", default="")
    backup.set_defaults(handler=cmd_backup)

    restore = commands.add_parser("restore", help="Restaurar respaldo con pg_restore")
    restore.add_argument("file")
    restore.add_argument("--yes", action="store_true", help="No pedir confirmación")
    restore.set_defaults(handler=cmd_restore)

    status = commands.add_parser("status", help="Estado del sistema")
    status.set_defaults(handler=cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except NMCError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
