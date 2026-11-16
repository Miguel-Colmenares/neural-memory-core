"""Configuración de pruebas.

Las pruebas de integración usan un PostgreSQL real con pgvector. La base se
indica con ``NMC_TEST_DATABASE_URL`` y su esquema se recrea con las
migraciones de Alembic, de modo que estas también quedan probadas.
"""

from __future__ import annotations

import os

TEST_DATABASE_URL = os.environ.get(
    "NMC_TEST_DATABASE_URL", "postgresql+psycopg://nmc:nmc@localhost:5432/nmc_test"
)
os.environ["NMC_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["NMC_ENVIRONMENT"] = "test"
os.environ["NMC_SECRET_KEY"] = "clave-solo-para-pruebas-automatizadas-0123456789"
os.environ["NMC_EMBEDDING_PROVIDER"] = "hashing"
os.environ["NMC_LLM_PROVIDER"] = "none"
os.environ["NMC_ADMIN_USERNAME"] = ""
os.environ["NMC_ADMIN_PASSWORD"] = ""
os.environ["NMC_MAX_LOGIN_ATTEMPTS"] = "5"

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from core.config import get_settings  # noqa: E402

ADMIN = {"username": "admin", "password": "contraseña-segura-123"}


@pytest.fixture(scope="session")
def settings(tmp_path_factory):
    os.environ["NMC_BACKUP_DIR"] = str(tmp_path_factory.mktemp("backups"))
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture(scope="session")
def engine(settings):
    from alembic import command
    from alembic.config import Config

    engine = create_engine(settings.database_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    except Exception as exc:  # pragma: no cover - depende del entorno
        pytest.skip(f"PostgreSQL de pruebas no disponible ({exc}).")
    config = Config("alembic.ini")
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def clean_db(engine):
    with engine.begin() as connection:
        tables = connection.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version'"
            )
        ).scalars()
        names = ", ".join(f'"{t}"' for t in tables)
        connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def session(engine, clean_db) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with factory() as session:
        yield session
        session.rollback()


@pytest.fixture(scope="session")
def embedder():
    from core.embeddings.hashing import HashingEmbeddingProvider

    return HashingEmbeddingProvider()


@pytest.fixture(scope="session")
def modules(settings):
    from core.module_system.registry import registry

    if not registry.names():
        registry.load(settings.enabled_module_list)
    return registry


@pytest.fixture(scope="session")
def app(engine, modules):
    from apps.api.main import create_app

    return create_app()


@pytest.fixture
def client(app, clean_db):
    from fastapi.testclient import TestClient

    from apps.api.routers.auth import reset_throttle

    reset_throttle()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_user(engine, clean_db):
    from core.security.auth import create_user

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        user = create_user(session, ADMIN["username"], ADMIN["password"], "admin")
        session.commit()
        return user


@pytest.fixture
def auth(client, admin_user) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json=ADMIN)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
