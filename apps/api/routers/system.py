from __future__ import annotations

import io
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select, text

from core.backup import pg_backup
from core.backup.export_service import export_all, import_all
from core.config import read_version
from core.database.changelog import log_change
from core.database.models import (
    ChangeLog,
    Memory,
    MemoryRelation,
    MemoryVersion,
    Project,
)
from core.embeddings.base import EmbeddingError
from core.embeddings.indexer import index_status, reindex
from core.llm.client import LLMClient, LLMError, get_llm
from core.module_system.registry import registry
from core.web.deps import Admin, EmbedderDep, Reader, SessionDep, SettingsDep
from core.web.schemas import ChangeLogList, ChangeLogOut

router = APIRouter(tags=["Sistema"])


# --------------------------------------------------------------- indicadores
@router.get("/stats", summary="Indicadores reales del sistema")
def stats(session: SessionDep, embedder: EmbedderDep, _: Reader) -> dict[str, Any]:
    """Todos los valores se calculan con consultas a la base de datos en el momento."""

    def grouped(column) -> dict[str, int]:
        rows = session.execute(
            select(column, func.count()).select_from(Memory).group_by(column).order_by(column)
        )
        return {str(row[0]): row[1] for row in rows}

    week_ago = datetime.now(UTC) - timedelta(days=7)
    last_memory = session.scalar(select(func.max(Memory.created_at)))
    last_change = session.scalar(select(func.max(ChangeLog.created_at)))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "memories": {
            "total": session.scalar(select(func.count()).select_from(Memory)) or 0,
            "by_status": grouped(Memory.status),
            "by_type": grouped(Memory.memory_type),
            "by_source": grouped(Memory.source_type),
            "created_last_7_days": session.scalar(
                select(func.count()).select_from(Memory).where(Memory.created_at >= week_ago)
            )
            or 0,
            "last_created_at": last_memory.isoformat() if last_memory else None,
        },
        "versions": session.scalar(select(func.count()).select_from(MemoryVersion)) or 0,
        "relations": session.scalar(select(func.count()).select_from(MemoryRelation)) or 0,
        "projects": {
            "total": session.scalar(select(func.count()).select_from(Project)) or 0,
            "by_status": {
                str(row[0]): row[1]
                for row in session.execute(
                    select(Project.status, func.count()).group_by(Project.status)
                )
            },
        },
        "changes": {
            "total": session.scalar(select(func.count()).select_from(ChangeLog)) or 0,
            "last_7_days": session.scalar(
                select(func.count()).select_from(ChangeLog).where(ChangeLog.created_at >= week_ago)
            )
            or 0,
            "last_at": last_change.isoformat() if last_change else None,
        },
        "index": index_status(session, embedder),
        "modules": {m.manifest.name: m.stats(session) for m in registry.all()},
    }


# ------------------------------------------------------------------ historial
@router.get("/history", response_model=ChangeLogList, summary="Historial de actualizaciones")
def history(
    session: SessionDep,
    _: Reader,
    entity_type: str | None = None,
    entity_id: str | None = None,
    project_id: uuid.UUID | None = None,
    action: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    conditions = []
    if entity_type:
        conditions.append(ChangeLog.entity_type == entity_type)
    if entity_id:
        conditions.append(ChangeLog.entity_id == entity_id)
    if project_id:
        conditions.append(ChangeLog.project_id == project_id)
    if action:
        conditions.append(ChangeLog.action == action)
    total = session.scalar(select(func.count()).select_from(ChangeLog).where(*conditions)) or 0
    rows = session.scalars(
        select(ChangeLog)
        .where(*conditions)
        .order_by(ChangeLog.created_at.desc(), ChangeLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return ChangeLogList(
        items=[ChangeLogOut.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------- proveedores
@router.get("/system/info", summary="Versión y módulos activos")
def system_info(_: Reader, settings: SettingsDep) -> dict[str, Any]:
    return {
        "name": "Neural Memory Core",
        "version": read_version(),
        "environment": settings.environment,
        "modules": [
            {
                "name": m.manifest.name,
                "version": m.manifest.version,
                "description": m.manifest.description,
                "memory_types": list(m.manifest.memory_types),
                "kinds": list(m.manifest.kinds),
                "depends_on": list(m.manifest.depends_on),
                "has_endpoints": m.get_router() is not None,
            }
            for m in registry.all()
        ],
    }


@router.get("/system/providers", summary="Configuración de proveedores de IA")
def providers(
    session: SessionDep,
    embedder: EmbedderDep,
    settings: SettingsDep,
    _: Reader,
    llm: Annotated[LLMClient | None, Depends(get_llm)],
) -> dict[str, Any]:
    """Muestra qué está configurado. Las claves nunca se devuelven: solo si existen.
    La configuración se cambia con variables de entorno (ver ``.env.example``)."""
    return {
        "embeddings": {
            **embedder.describe(),
            "api_base": settings.embedding_api_base if embedder.external else None,
            "api_key_configured": bool(settings.embedding_api_key),
            "may_incur_cost": embedder.external,
            "index": index_status(session, embedder),
            "available_providers": [
                {
                    "id": "hashing",
                    "description": "Local, sin descargas. Parecido léxico, no entiende sinónimos.",
                    "cost": "gratis",
                },
                {
                    "id": "fastembed",
                    "description": "Modelo multilingüe local (descarga ~220 MB una vez). "
                    "Búsqueda por significado.",
                    "cost": "gratis",
                },
                {
                    "id": "openai",
                    "description": "API compatible con OpenAI (nube o servidor propio).",
                    "cost": "puede tener costo según el proveedor",
                },
            ],
        },
        "llm": {
            "enabled": llm is not None,
            "provider": settings.llm_provider,
            "model": settings.llm_model or None,
            "api_base": settings.llm_api_base if llm is not None else None,
            "api_key_configured": bool(settings.llm_api_key),
            "may_incur_cost": llm is not None,
            "answer_mode": "llm" if llm is not None else "extractive",
        },
        "configured_via": "variables de entorno NMC_* (archivo .env)",
    }


@router.post("/system/providers/test", summary="Probar los proveedores configurados")
def test_providers(
    embedder: EmbedderDep, _: Admin, llm: Annotated[LLMClient | None, Depends(get_llm)]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    started = time.perf_counter()
    try:
        vector = embedder.embed_one("prueba de conexión del proveedor de embeddings")
        result["embeddings"] = {
            "ok": True,
            "dimensions": len(vector),
            "milliseconds": round((time.perf_counter() - started) * 1000),
        }
    except EmbeddingError as exc:
        result["embeddings"] = {"ok": False, "error": str(exc)}
    if llm is None:
        result["llm"] = {"ok": None, "detail": "No hay modelo de lenguaje configurado."}
    else:
        started = time.perf_counter()
        try:
            reply = llm.chat([{"role": "user", "content": "Responde únicamente: ok"}])
            result["llm"] = {
                "ok": True,
                "reply": reply[:100],
                "milliseconds": round((time.perf_counter() - started) * 1000),
            }
        except LLMError as exc:
            result["llm"] = {"ok": False, "error": str(exc)}
    return result


@router.post("/system/reindex", summary="Regenerar embeddings")
def reindex_embeddings(
    session: SessionDep,
    embedder: EmbedderDep,
    settings: SettingsDep,
    admin: Admin,
    all_memories: Annotated[
        bool, Query(alias="all", description="true: rehace todo; false: solo lo pendiente.")
    ] = False,
) -> dict[str, Any]:
    report = reindex(session, embedder, settings, only_pending=not all_memories)
    log_change(
        session,
        entity_type="system",
        entity_id="index",
        action="reindex",
        summary=f"Reindexación con {embedder.name}: {report['processed']} recuerdos",
        details={**report, **embedder.describe()},
        actor=admin.username,
    )
    return {**report, "index": index_status(session, embedder)}


# -------------------------------------------------------------- almacenamiento
@router.get("/storage", summary="Uso de almacenamiento y respaldos")
def storage(session: SessionDep, settings: SettingsDep, _: Admin) -> dict[str, Any]:
    database_bytes = session.scalar(text("SELECT pg_database_size(current_database())"))
    names = session.execute(
        text(
            """
            SELECT c.relname, pg_total_relation_size(c.oid)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname = current_schema()
            ORDER BY pg_total_relation_size(c.oid) DESC
            """
        )
    ).all()
    tables = []
    for name, size in names:
        quoted = '"' + name.replace('"', '""') + '"'  # nombre tomado del catálogo
        rows = session.scalar(text(f"SELECT count(*) FROM {quoted}"))  # noqa: S608
        tables.append({"name": name, "size_bytes": size, "rows": rows})
    backups = pg_backup.list_backups(settings)
    return {
        "database": {
            "size_bytes": database_bytes,
            "tables": tables,
        },
        "backups": {
            "directory": str(pg_backup.backup_dir(settings)),
            "count": len(backups),
            "total_bytes": sum(b["size_bytes"] for b in backups),
            "items": backups,
        },
    }


@router.post("/storage/backups", status_code=201, summary="Crear un respaldo (pg_dump)")
def create_backup(
    session: SessionDep,
    settings: SettingsDep,
    admin: Admin,
    label: Annotated[str, Query(max_length=40)] = "",
) -> dict[str, Any]:
    backup = pg_backup.create_backup(settings, label)
    log_change(
        session,
        entity_type="system",
        entity_id="backup",
        action="backup",
        summary=f"Respaldo creado: {backup['name']}",
        details=backup,
        actor=admin.username,
    )
    return backup


@router.get("/storage/backups/{name}", summary="Descargar un respaldo")
def download_backup(name: str, settings: SettingsDep, _: Admin):
    path = pg_backup.resolve_backup(settings, name)
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@router.delete("/storage/backups/{name}", status_code=204, summary="Eliminar un respaldo")
def remove_backup(name: str, session: SessionDep, settings: SettingsDep, admin: Admin):
    pg_backup.delete_backup(settings, name)
    log_change(
        session,
        entity_type="system",
        entity_id="backup",
        action="backup_delete",
        summary=f"Respaldo eliminado: {name}",
        actor=admin.username,
    )


# ----------------------------------------------------- exportación/importación
@router.get("/data/export", summary="Exportar toda la memoria en JSON")
def export_data(session: SessionDep, admin: Admin):
    data = export_all(session)
    log_change(
        session,
        entity_type="system",
        entity_id="export",
        action="export",
        summary="Exportación completa de datos",
        details=data["counts"],
        actor=admin.username,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="nmc-export-{stamp}.json"'},
    )


@router.post("/data/import", summary="Importar una exportación (fusiona, no sobrescribe)")
async def import_data(
    session: SessionDep,
    embedder: EmbedderDep,
    admin: Admin,
    file: Annotated[UploadFile, File(description="Archivo JSON generado por /data/export")],
) -> dict[str, Any]:
    raw = await file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(422, "El archivo no es un JSON válido.") from exc
    return import_all(session, data, embedder, actor=admin.username)
