import pytest
from sqlalchemy.orm import sessionmaker

from core.security.auth import bootstrap_admin, create_user

API = "/api/v1"

PROTECTED = [
    ("get", "/memories"),
    ("post", "/memories"),
    ("get", "/memories/tags"),
    ("post", "/search"),
    ("post", "/ask"),
    ("get", "/graph"),
    ("post", "/relations"),
    ("get", "/stats"),
    ("get", "/history"),
    ("get", "/system/info"),
    ("get", "/system/providers"),
    ("post", "/system/providers/test"),
    ("post", "/system/reindex"),
    ("get", "/storage"),
    ("post", "/storage/backups"),
    ("get", "/data/export"),
    ("post", "/data/import"),
    ("get", "/projects"),
    ("post", "/projects"),
    ("get", "/tasks"),
    ("get", "/documents"),
    ("post", "/documents/upload"),
    ("get", "/conversations"),
    ("get", "/preferences"),
    ("get", "/knowledge/concepts"),
    ("get", "/auth/me"),
    ("get", "/auth/users"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_endpoints_require_authentication(client, method, path):
    response = getattr(client, method)(API + path)
    assert response.status_code == 401, path
    assert "content" not in response.text.lower()


def test_every_route_is_protected_except_login_and_health(app, client):
    """Protección contra exposición accidental: recorre todas las rutas publicadas."""
    public = {"/health", f"{API}/auth/login"}
    zero = "00000000-0000-0000-0000-000000000000"
    checked = 0
    for path, operations in app.openapi()["paths"].items():
        if path in public:
            continue
        url = path
        for name in ("memory_id", "project_id", "task_id", "relation_id", "user_id"):
            url = url.replace("{" + name + "}", zero)
        url = url.replace("{version}", "1").replace("{name}", "x").replace("{key}", "x")
        assert "{" not in url, path
        for method in operations:
            response = client.request(method.upper(), url)
            assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
            checked += 1
    assert checked > 50


def test_login_and_me(client, admin_user):
    bad = client.post(f"{API}/auth/login", json={"username": "admin", "password": "incorrecta"})
    assert bad.status_code == 401
    unknown = client.post(f"{API}/auth/login", json={"username": "nadie", "password": "x"})
    assert unknown.status_code == 401 and unknown.json() == bad.json()
    ok = client.post(
        f"{API}/auth/login", json={"username": "ADMIN", "password": "contraseña-segura-123"}
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["token_type"] == "bearer" and body["role"] == "admin"
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["username"] == "admin" and "password" not in me.text


def test_invalid_tokens_are_rejected(client, auth):
    for header in ("Bearer nada", "Bearer " + auth["Authorization"][7:] + "x", "Basic abc"):
        assert client.get(f"{API}/memories", headers={"Authorization": header}).status_code == 401


def test_login_is_throttled_after_repeated_failures(client, admin_user):
    payload = {"username": "admin", "password": "incorrecta"}
    codes = [client.post(f"{API}/auth/login", json=payload).status_code for _ in range(6)]
    assert codes == [401, 401, 401, 401, 401, 429]
    good = {"username": "admin", "password": "contraseña-segura-123"}
    assert client.post(f"{API}/auth/login", json=good).status_code == 429


def test_roles_limit_what_each_user_can_do(client, auth):
    for name, role in (("lectora", "reader"), ("editor1", "editor")):
        created = client.post(
            f"{API}/auth/users",
            json={"username": name, "password": "otra-contraseña-123", "role": role},
            headers=auth,
        )
        assert created.status_code == 201, created.text

    def login(name):
        token = client.post(
            f"{API}/auth/login", json={"username": name, "password": "otra-contraseña-123"}
        ).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    reader, editor = login("lectora"), login("editor1")
    memory = {"content": "nota de prueba de roles"}
    assert client.get(f"{API}/memories", headers=reader).status_code == 200
    assert client.post(f"{API}/search", json={"query": "x"}, headers=reader).status_code == 200
    assert client.post(f"{API}/memories", json=memory, headers=reader).status_code == 403
    assert client.post(f"{API}/projects", json={"name": "P"}, headers=reader).status_code == 403
    assert client.post(f"{API}/memories", json=memory, headers=editor).status_code == 201
    for headers in (reader, editor):
        assert client.get(f"{API}/data/export", headers=headers).status_code == 403
        assert client.get(f"{API}/storage", headers=headers).status_code == 403
        assert client.post(f"{API}/storage/backups", headers=headers).status_code == 403
        assert client.get(f"{API}/auth/users", headers=headers).status_code == 403
        assert client.post(f"{API}/system/reindex", headers=headers).status_code == 403


def test_deactivated_user_loses_access(client, auth):
    created = client.post(
        f"{API}/auth/users",
        json={"username": "temporal", "password": "otra-contraseña-123", "role": "editor"},
        headers=auth,
    ).json()
    token = client.post(
        f"{API}/auth/login", json={"username": "temporal", "password": "otra-contraseña-123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get(f"{API}/memories", headers=headers).status_code == 200
    done = client.post(f"{API}/auth/users/{created['id']}/deactivate", headers=auth)
    assert done.status_code == 200 and done.json()["is_active"] is False
    assert client.get(f"{API}/memories", headers=headers).status_code == 401
    again = client.post(
        f"{API}/auth/login", json={"username": "temporal", "password": "otra-contraseña-123"}
    )
    assert again.status_code == 401


def test_password_change(client, auth):
    wrong = client.post(
        f"{API}/auth/password",
        json={"current_password": "no-es", "new_password": "nueva-contraseña-456"},
        headers=auth,
    )
    assert wrong.status_code == 400
    short = client.post(
        f"{API}/auth/password",
        json={"current_password": "contraseña-segura-123", "new_password": "corta"},
        headers=auth,
    )
    assert short.status_code == 422
    ok = client.post(
        f"{API}/auth/password",
        json={"current_password": "contraseña-segura-123", "new_password": "nueva-contraseña-456"},
        headers=auth,
    )
    assert ok.status_code == 204
    old = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "contraseña-segura-123"}
    )
    new = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "nueva-contraseña-456"}
    )
    assert (old.status_code, new.status_code) == (401, 200)


def test_input_validation_rejects_malformed_requests(client, auth):
    cases = [
        ("post", "/memories", {"content": ""}),
        ("post", "/memories", {"content": "x", "importance": 6}),
        ("post", "/memories", {"content": "x", "memory_type": "otro"}),
        ("post", "/memories", {"content": "x", "campo_desconocido": 1}),
        ("post", "/memories", {"content": "x", "project_id": "no-es-uuid"}),
        ("post", "/search", {"query": ""}),
        ("post", "/search", {"query": "x", "limit": 1000}),
        ("post", "/search", {"query": "x", "mode": "magia"}),
        ("post", "/relations", {"source_id": "x", "target_id": "y"}),
        ("post", "/projects", {"name": ""}),
        ("post", "/tasks", {"title": "x", "priority": 0}),
    ]
    for method, path, body in cases:
        response = getattr(client, method)(API + path, json=body, headers=auth)
        assert response.status_code == 422, (path, body, response.text)
    assert client.get(f"{API}/memories/no-es-uuid", headers=auth).status_code == 422
    missing = client.get(f"{API}/memories/00000000-0000-0000-0000-000000000000", headers=auth)
    assert missing.status_code == 404


def test_sql_injection_attempts_are_treated_as_text(client, auth):
    hostile = "'; DROP TABLE memories; -- | & ! ( ) :* <->"
    assert (
        client.post(f"{API}/memories", json={"content": hostile}, headers=auth).status_code == 201
    )
    for mode in ("hybrid", "text", "semantic"):
        response = client.post(f"{API}/search", json={"query": hostile, "mode": mode}, headers=auth)
        assert response.status_code == 200, response.text
    assert client.post(f"{API}/ask", json={"question": hostile}, headers=auth).status_code == 200
    assert client.get(f"{API}/memories", headers=auth).json()["total"] == 1


def test_bootstrap_admin_only_runs_on_empty_database(engine, settings, clean_db):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    configured = settings.model_copy(
        update={"admin_username": "root", "admin_password": "contraseña-inicial-1"}
    )
    with factory() as session:
        assert bootstrap_admin(session, settings) is None  # sin credenciales no crea nada
        first = bootstrap_admin(session, configured)
        assert first is not None and first.role == "admin"
        assert bootstrap_admin(session, configured) is None
        create_user(session, "otro", "contraseña-segura-9", "reader")
        session.commit()


def test_errors_do_not_leak_internals(client, auth, monkeypatch):
    from core.memory_engine.service import MemoryService

    def boom(self, *args, **kwargs):
        raise RuntimeError("detalle interno secreto: postgresql://usuario:clave@host/db")

    monkeypatch.setattr(MemoryService, "list", boom)
    from fastapi.testclient import TestClient

    with TestClient(client.app, raise_server_exceptions=False) as safe_client:
        response = safe_client.get(f"{API}/memories", headers=auth)
    assert response.status_code == 500
    assert "secreto" not in response.text and "clave" not in response.text
    assert response.json()["request_id"]
