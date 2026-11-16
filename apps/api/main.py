"""Aplicación FastAPI de Neural Memory Core."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from apps.api.routers import auth, memories, search, system
from core.config import get_settings, read_version
from core.database.base import get_session_factory
from core.errors import NMCError
from core.module_system.registry import registry
from core.security.auth import bootstrap_admin

API_PREFIX = "/api/v1"
logger = logging.getLogger("nmc.api")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_runtime()
    with get_session_factory()() as session:
        try:
            created = bootstrap_admin(session, settings)
            session.commit()
            if created:
                logger.info("Usuario administrador inicial creado: %s", created.username)
        except Exception:
            session.rollback()
            logger.exception("No se pudo crear el administrador inicial (¿migraciones aplicadas?)")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    # La documentación interactiva no se publica en producción.
    docs_url = None if settings.environment == "production" else f"{API_PREFIX}/docs"
    openapi_url = None if settings.environment == "production" else f"{API_PREFIX}/openapi.json"
    app = FastAPI(
        title="Neural Memory Core",
        version=read_version(),
        description=(
            "API del segundo cerebro digital: recuerdos con historial y procedencia, "
            "proyectos, búsqueda híbrida y respuestas con fuentes."
        ),
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Error no controlado [%s] %s %s", request_id, request.method, request.url.path
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Error interno. Consulta el registro del servidor.",
                    "request_id": request_id,
                },
            )
        elapsed = (time.perf_counter() - started) * 1000
        # Solo método, ruta y estado: nunca cuerpos ni cabeceras (pueden contener datos privados).
        logger.info(
            "[%s] %s %s -> %s (%.0f ms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(NMCError)
    async def domain_error(_: Request, exc: NMCError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.get("/health", tags=["Sistema"], summary="Estado del servicio (público)")
    def health():
        try:
            with get_session_factory()() as session:
                session.execute(text("SELECT 1"))
            database = "ok"
        except Exception:  # noqa: BLE001
            logger.exception("La base de datos no responde")
            database = "error"
        status_code = 200 if database == "ok" else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": database, "database": database, "version": read_version()},
        )

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(auth.router)
    api.include_router(memories.router)
    api.include_router(search.router)
    api.include_router(system.router)

    if not registry.names():
        registry.load(settings.enabled_module_list)
    for module in registry.all():
        router = module.get_router()
        if router is not None:
            api.include_router(router)
    app.include_router(api)
    return app


app = create_app()
