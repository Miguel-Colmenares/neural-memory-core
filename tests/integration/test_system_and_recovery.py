import io
import json
import shutil

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from core.backup import pg_backup
from core.database.models import Memory, MemoryEmbedding

API = "/api/v1"


def post(client, auth, path, body, expected=201):
    response = client.post(API + path, json=body, headers=auth)
    assert response.status_code == expected, response.text
    return response.json()


def seed(client, auth):
    project = post(client, auth, "/projects", {"name": "Proyecto Alfa", "objectives": ["Uno"]})
    other = post(client, auth, "/projects", {"name": "Proyecto Beta"})
    post(
        client,
        auth,
        f"/projects/{project['id']}/relations",
        {"target_project_id": other["id"], "relation_type": "related"},
    )
    first = post(
        client,
        auth,
        "/memories",
        {"content": "Alfa usará PostgreSQL", "project_id": project["id"], "tags": ["db"]},
    )["memory"]
    second = post(
        client,
        auth,
        "/memories",
        {"content": "Alfa usará MySQL, no PostgreSQL", "contradicts": [first["id"]]},
    )["memory"]
    client.patch(
        f"{API}/memories/{first['id']}",
        json={"importance": 5, "change_reason": "clave"},
        headers=auth,
    )
    post(client, auth, "/tasks", {"title": "Migrar datos", "project_id": project["id"]})
    client.put(f"{API}/preferences/formato", json={"value": "Markdown"}, headers=auth)
    return {"project": project, "first": first, "second": second}


# ---------------------------------------------------------------- indicadores
def test_stats_reflect_real_data(client, auth):
    empty = client.get(f"{API}/stats", headers=auth).json()
    assert empty["memories"]["total"] == 0 and empty["projects"]["total"] == 0
    assert empty["memories"]["last_created_at"] is None
    seed(client, auth)
    stats = client.get(f"{API}/stats", headers=auth).json()
    assert stats["memories"]["total"] == 3
    assert stats["memories"]["by_status"] == {"active": 3}
    assert sum(stats["memories"]["by_type"].values()) == 3
    assert stats["memories"]["created_last_7_days"] == 3
    assert stats["versions"] == 4 and stats["relations"] >= 1
    assert stats["projects"] == {"total": 2, "by_status": {"active": 2}}
    assert stats["index"]["memories_indexed"] == 3 and stats["index"]["memories_pending"] == 0
    assert stats["modules"]["tasks"] == {"total": 1, "open": 1, "by_status": {"pending": 1}}
    assert stats["modules"]["personal"] == {"preferences": 1}
    assert stats["changes"]["total"] > 5


def test_system_info_and_providers(client, auth):
    info = client.get(f"{API}/system/info", headers=auth).json()
    assert {m["name"] for m in info["modules"]} == {
        "personal",
        "projects",
        "conversations",
        "documents",
        "knowledge",
        "tasks",
    }
    assert info["version"]
    providers = client.get(f"{API}/system/providers", headers=auth).json()
    assert providers["embeddings"]["provider"] == "hashing"
    assert providers["embeddings"]["may_incur_cost"] is False
    assert providers["llm"] == {
        "enabled": False,
        "provider": "none",
        "model": None,
        "api_base": None,
        "api_key_configured": False,
        "may_incur_cost": False,
        "answer_mode": "extractive",
    }
    assert 'api_key"' not in json.dumps(providers)
    tested = client.post(f"{API}/system/providers/test", headers=auth).json()
    assert tested["embeddings"]["ok"] is True and tested["embeddings"]["dimensions"] == 384
    assert tested["llm"]["ok"] is None


def test_reindex_recovers_missing_embeddings(client, auth, session):
    seed(client, auth)
    session.execute(text("DELETE FROM memory_embeddings"))
    session.commit()
    before = client.get(f"{API}/stats", headers=auth).json()["index"]
    assert before["memories_pending"] == 3
    none = client.post(f"{API}/search", json={"query": "MySQL", "mode": "semantic"}, headers=auth)
    assert none.json()["results"] == []
    report = client.post(f"{API}/system/reindex", headers=auth).json()
    assert report["processed"] == 3 and report["index"]["memories_pending"] == 0
    found = client.post(f"{API}/search", json={"query": "MySQL", "mode": "semantic"}, headers=auth)
    assert found.json()["results"]
    again = client.post(f"{API}/system/reindex", headers=auth).json()
    assert again["processed"] == 0
    full = client.post(f"{API}/system/reindex?all=true", headers=auth).json()
    assert full["processed"] == 3


def test_history_endpoint_filters(client, auth):
    data = seed(client, auth)
    everything = client.get(f"{API}/history?limit=200", headers=auth).json()
    assert everything["total"] == len(everything["items"]) > 5
    stamps = [h["created_at"] for h in everything["items"]]
    assert stamps == sorted(stamps, reverse=True)
    one = client.get(
        f"{API}/history?entity_type=memory&entity_id={data['first']['id']}", headers=auth
    ).json()
    assert [h["action"] for h in one["items"]] == ["update", "create"]
    assert one["items"][0]["details"]["changed_fields"] == ["importance"]
    paged = client.get(f"{API}/history?limit=2&offset=1", headers=auth).json()
    assert [h["id"] for h in paged["items"]] == [h["id"] for h in everything["items"][1:3]]


# ----------------------------------------------------- exportación/importación
def comparable(export):
    data = {k: v for k, v in export.items() if k not in ("exported_at", "change_log", "counts")}
    return json.loads(json.dumps(data, sort_keys=True))


def test_export_import_roundtrip_restores_everything(client, auth, engine):
    seed(client, auth)
    response = client.get(f"{API}/data/export", headers=auth)
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    exported = response.json()
    assert exported["format"] == "neural-memory-core-export"
    assert exported["counts"]["memories"] == 3 and exported["counts"]["memory_versions"] == 4
    assert "users" not in exported and "password" not in response.text
    assert "embedding" not in exported["memories"][0]
    assert len(exported["modules"]["tasks"]["tasks"]) == 1

    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE memories, projects, project_relations, memory_versions, "
                "memory_relations, memory_embeddings, change_log, tasks CASCADE"
            )
        )
    assert client.get(f"{API}/memories", headers=auth).json()["total"] == 0

    upload = {"file": ("export.json", io.BytesIO(response.content), "application/json")}
    report = client.post(f"{API}/data/import", files=upload, headers=auth)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["sections"]["memories"] == {"imported": 3, "skipped": 0}
    assert body["sections"]["memory_versions"]["imported"] == 4
    assert body["modules"]["tasks"] == {"imported": 1, "skipped": 0}
    assert body["reindex"]["processed"] == 3

    restored = client.get(f"{API}/data/export", headers=auth).json()
    assert comparable(restored) == comparable(exported)
    found = client.post(f"{API}/search", json={"query": "MySQL"}, headers=auth).json()
    assert found["results"], "la búsqueda debe funcionar tras importar (índices regenerados)"

    upload = {"file": ("export.json", io.BytesIO(response.content), "application/json")}
    second = client.post(f"{API}/data/import", files=upload, headers=auth).json()
    assert second["sections"]["memories"] == {"imported": 0, "skipped": 3}
    assert client.get(f"{API}/memories", headers=auth).json()["total"] == 3


def test_import_never_overwrites_existing_memories(client, auth):
    data = seed(client, auth)
    exported = client.get(f"{API}/data/export", headers=auth).content
    client.patch(
        f"{API}/memories/{data['second']['id']}",
        json={"content": "Versión local más nueva"},
        headers=auth,
    )
    upload = {"file": ("export.json", io.BytesIO(exported), "application/json")}
    client.post(f"{API}/data/import", files=upload, headers=auth)
    current = client.get(f"{API}/memories/{data['second']['id']}", headers=auth).json()
    assert current["content"] == "Versión local más nueva" and current["version"] == 2


@pytest.mark.parametrize(
    "payload",
    [b"esto no es json", b'{"format": "otro"}', b"[]"],
)
def test_import_rejects_invalid_files(client, auth, payload):
    upload = {"file": ("x.json", io.BytesIO(payload), "application/json")}
    response = client.post(f"{API}/data/import", files=upload, headers=auth)
    assert response.status_code == 422


def test_import_rejects_damaged_export_without_partial_writes(client, auth, engine):
    seed(client, auth)
    exported = client.get(f"{API}/data/export", headers=auth).json()
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE memories, projects, tasks, change_log CASCADE"))
    del exported["memories"][1]["content"]
    upload = {"file": ("x.json", io.BytesIO(json.dumps(exported).encode()), "application/json")}
    response = client.post(f"{API}/data/import", files=upload, headers=auth)
    assert response.status_code == 422
    assert client.get(f"{API}/memories?status=any", headers=auth).json()["total"] == 0
    assert client.get(f"{API}/projects", headers=auth).json() == []


# ------------------------------------------------------------------- respaldos
needs_pg_tools = pytest.mark.skipif(
    not (shutil.which("pg_dump") and shutil.which("pg_restore")),
    reason="requiere pg_dump y pg_restore",
)


@needs_pg_tools
def test_backup_create_list_download_delete(client, auth, settings):
    seed(client, auth)
    created = client.post(f"{API}/storage/backups?label=antes de migrar", headers=auth)
    assert created.status_code == 201, created.text
    backup = created.json()
    assert backup["name"].startswith("nmc-backup-") and backup["name"].endswith(
        "-antes-de-migrar.dump"
    )
    assert backup["size_bytes"] > 1000

    storage = client.get(f"{API}/storage", headers=auth).json()
    assert storage["backups"]["count"] == 1
    assert storage["backups"]["total_bytes"] == backup["size_bytes"]
    assert storage["database"]["size_bytes"] > 0
    rows = {t["name"]: t["rows"] for t in storage["database"]["tables"]}
    assert rows["memories"] == 3 and rows["projects"] == 2 and rows["tasks"] == 1

    download = client.get(f"{API}/storage/backups/{backup['name']}", headers=auth)
    assert download.status_code == 200 and download.content[:5] == b"PGDMP"
    for bad in ("..%2F..%2Fetc%2Fpasswd", "otro.dump", "nmc-backup-x.txt"):
        assert client.get(f"{API}/storage/backups/{bad}", headers=auth).status_code in (404, 422)

    assert client.delete(f"{API}/storage/backups/{backup['name']}", headers=auth).status_code == 204
    assert client.get(f"{API}/storage", headers=auth).json()["backups"]["count"] == 0


@needs_pg_tools
def test_backup_can_be_restored_into_an_empty_database(client, auth, settings):
    """Recuperación ante pérdida del servidor: respaldo -> base nueva -> mismos datos."""
    data = seed(client, auth)
    backup = client.post(f"{API}/storage/backups", headers=auth).json()
    path = pg_backup.resolve_backup(settings, backup["name"])

    url = make_url(settings.database_url)
    restore_name = f"{url.database}_restore"
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{restore_name}"'))
            connection.execute(text(f'CREATE DATABASE "{restore_name}"'))
    except Exception as exc:  # pragma: no cover - depende de los permisos del entorno
        admin.dispose()
        pytest.skip(f"no se puede crear una base de datos temporal: {exc}")

    restore_url = url.set(database=restore_name).render_as_string(hide_password=False)
    restored_engine = create_engine(restore_url)
    try:
        with restored_engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        pg_backup.restore_backup(settings.model_copy(update={"database_url": restore_url}), path)
        with restored_engine.connect() as connection:
            assert connection.execute(select(func.count()).select_from(Memory)).scalar() == 3
            assert (
                connection.execute(select(func.count()).select_from(MemoryEmbedding)).scalar() == 3
            )
            content = connection.execute(
                select(Memory.content).where(Memory.id == data["first"]["id"])
            ).scalar()
            assert content == "Alfa usará PostgreSQL"
            assert connection.execute(text("SELECT count(*) FROM memory_versions")).scalar() == 4
            assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 1
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            hits = connection.execute(
                text(
                    "SELECT count(*) FROM memories WHERE search_vector @@ "
                    "to_tsquery('spanish', 'mysql')"
                )
            ).scalar()
            assert hits == 1
    finally:
        restored_engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{restore_name}"'))
        admin.dispose()
