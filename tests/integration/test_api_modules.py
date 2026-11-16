import io

API = "/api/v1"


def post(client, auth, path, body, expected=201):
    response = client.post(API + path, json=body, headers=auth)
    assert response.status_code == expected, response.text
    return response.json()


# ------------------------------------------------------------------ recuerdos
def test_memory_lifecycle_through_the_api(client, auth):
    created = post(
        client,
        auth,
        "/memories",
        {
            "content": "El servidor de pruebas está en Hetzner",
            "memory_type": "semantic",
            "title": "Servidor de pruebas",
            "tags": ["Infra"],
            "source_ref": "nota del 3 de mayo",
        },
    )
    assert created["outcome"] == "created"
    memory_id = created["memory"]["id"]

    duplicate = client.post(
        f"{API}/memories",
        json={"content": "el servidor de pruebas está en hetzner"},
        headers=auth,
    )
    assert duplicate.status_code == 200 and duplicate.json()["outcome"] == "duplicate"
    assert duplicate.json()["memory"]["id"] == memory_id

    patched = client.patch(
        f"{API}/memories/{memory_id}",
        json={
            "content": "El servidor de pruebas está en un VPS de OVH",
            "change_reason": "Migramos de proveedor",
            "is_correction": True,
        },
        headers=auth,
    )
    assert patched.status_code == 200 and patched.json()["version"] == 2

    versions = client.get(f"{API}/memories/{memory_id}/versions", headers=auth).json()
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["change_type"] == "correction"
    assert versions[0]["change_reason"] == "Migramos de proveedor"
    assert versions[0]["changed_by"] == "admin"
    assert versions[1]["snapshot"]["content"] == "El servidor de pruebas está en Hetzner"

    reverted = client.post(f"{API}/memories/{memory_id}/revert/1", headers=auth).json()
    assert reverted["version"] == 3 and "Hetzner" in reverted["content"]

    archived = client.post(
        f"{API}/memories/{memory_id}/archive", json={"reason": "obsoleto"}, headers=auth
    ).json()
    assert archived["status"] == "archived"
    assert client.get(f"{API}/memories", headers=auth).json()["total"] == 0
    listing = client.get(f"{API}/memories?status=archived", headers=auth).json()
    assert listing["total"] == 1
    restored = client.post(f"{API}/memories/{memory_id}/restore", headers=auth).json()
    assert restored["status"] == "active" and restored["version"] == 5

    tags = client.get(f"{API}/memories/tags", headers=auth).json()
    assert tags == [{"tag": "infra", "count": 1}]

    no_confirm = client.delete(f"{API}/memories/{memory_id}?confirm=false", headers=auth)
    assert no_confirm.status_code == 422
    assert (
        client.delete(f"{API}/memories/{memory_id}?confirm=true", headers=auth).status_code == 204
    )
    assert client.get(f"{API}/memories/{memory_id}", headers=auth).status_code == 404


def test_patch_can_clear_optional_fields(client, auth):
    project = post(client, auth, "/projects", {"name": "Temporal"})
    memory = post(
        client,
        auth,
        "/memories",
        {"content": "nota con proyecto", "project_id": project["id"], "title": "T"},
    )["memory"]
    assert memory["project_name"] == "Temporal"
    cleared = client.patch(
        f"{API}/memories/{memory['id']}", json={"project_id": None, "title": None}, headers=auth
    ).json()
    assert cleared["project_id"] is None and cleared["title"] is None and cleared["version"] == 2


def test_relations_and_graph(client, auth):
    a = post(client, auth, "/memories", {"content": "Python es un lenguaje", "auto_relate": False})
    b = post(
        client, auth, "/memories", {"content": "FastAPI es un framework", "auto_relate": False}
    )
    a_id, b_id = a["memory"]["id"], b["memory"]["id"]
    relation = post(
        client,
        auth,
        "/relations",
        {"source_id": b_id, "target_id": a_id, "relation_type": "part_of", "note": "ecosistema"},
    )
    assert relation["origin"] == "manual" and relation["created_by"] == "admin"
    again = client.post(
        f"{API}/relations",
        json={"source_id": b_id, "target_id": a_id, "relation_type": "part_of"},
        headers=auth,
    )
    assert again.status_code == 409
    same = client.post(
        f"{API}/relations", json={"source_id": a_id, "target_id": a_id}, headers=auth
    )
    assert same.status_code == 422

    neighbors = client.get(f"{API}/memories/{a_id}/relations", headers=auth).json()
    assert [(n["memory"]["id"], n["direction"]) for n in neighbors] == [(b_id, "in")]

    graph = client.get(f"{API}/graph", headers=auth).json()
    assert {n["id"] for n in graph["nodes"]} == {a_id, b_id}
    assert [(e["source"], e["target"], e["relation_type"]) for e in graph["edges"]] == [
        (b_id, a_id, "part_of")
    ]
    assert graph["total_relations"] == 1
    focused = client.get(f"{API}/graph?focus_id={a_id}", headers=auth).json()
    assert len(focused["nodes"]) == 2

    assert client.delete(f"{API}/relations/{relation['id']}", headers=auth).status_code == 204
    assert client.get(f"{API}/graph", headers=auth).json()["nodes"] == []


# ------------------------------------------------------------------ proyectos
def test_project_space(client, auth):
    project = post(
        client,
        auth,
        "/projects",
        {
            "name": "App Móvil",
            "description": "Aplicación de notas",
            "objectives": ["Publicar en tiendas", "  "],
        },
    )
    assert project["slug"] == "app-movil" and project["objectives"] == ["Publicar en tiendas"]
    assert project["status"] == "active" and project["created_at"]
    pid = project["id"]
    clash = client.post(f"{API}/projects", json={"name": "app móvil"}, headers=auth)
    assert clash.status_code == 409

    decision = post(
        client,
        auth,
        f"/projects/{pid}/decisions",
        {"content": "Usaremos React Native", "title": "Framework"},
    )["memory"]
    assert (decision["memory_type"], decision["kind"]) == ("project", "decision")
    assert decision["project_id"] == pid and decision["module"] == "projects"
    post(
        client,
        auth,
        "/conversations",
        {"title": "Charla de diseño", "transcript": "Hablamos de colores", "project_id": pid},
    )
    post(
        client,
        auth,
        "/documents",
        {"title": "Especificación", "content": "Requisitos de la app", "project_id": pid},
    )
    task = post(client, auth, "/tasks", {"title": "Crear repositorio", "project_id": pid})

    other = post(client, auth, "/projects", {"name": "Backend"})
    relation = post(
        client,
        auth,
        f"/projects/{pid}/relations",
        {"target_project_id": other["id"], "relation_type": "depends_on", "description": "API"},
    )
    assert relation["project"]["name"] == "Backend" and relation["direction"] == "out"

    updated = client.patch(
        f"{API}/projects/{pid}", json={"status": "paused", "objectives": ["Beta"]}, headers=auth
    ).json()
    assert updated["status"] == "paused" and updated["objectives"] == ["Beta"]

    overview = client.get(f"{API}/projects/{pid}", headers=auth).json()
    assert overview["counts"]["active_memories"] == 3
    assert overview["counts"]["by_type"] == {"project": 1, "episodic": 1, "document": 1}
    assert [m["title"] for m in overview["decisions"]] == ["Framework"]
    assert [m["title"] for m in overview["conversations"]] == ["Charla de diseño"]
    assert [m["title"] for m in overview["documents"]] == ["Especificación"]
    assert overview["relations"][0]["relation_type"] == "depends_on"
    incoming = client.get(f"{API}/projects/{other['id']}/relations", headers=auth).json()
    assert incoming[0]["direction"] == "in" and incoming[0]["project"]["id"] == pid

    history = client.get(f"{API}/history?project_id={pid}", headers=auth).json()
    actions = {(h["entity_type"], h["action"]) for h in history["items"]}
    assert {
        ("project", "create"),
        ("project", "update"),
        ("memory", "create"),
        ("task", "create"),
        ("project_relation", "create"),
    } <= actions
    change = next(h for h in history["items"] if h["action"] == "update")
    assert change["details"]["changes"]["status"] == {"before": "active", "after": "paused"}
    assert change["actor"] == "admin"

    tasks = client.get(f"{API}/tasks?project_id={pid}&open_only=true", headers=auth).json()
    assert [t["id"] for t in tasks] == [task["id"]]
    listed = client.get(f"{API}/projects", headers=auth).json()
    assert {p["name"]: p["memory_count"] for p in listed} == {"App Móvil": 3, "Backend": 0}

    assert client.delete(f"{API}/projects/{pid}?confirm=true", headers=auth).status_code == 204
    orphan = client.get(f"{API}/memories/{decision['id']}", headers=auth).json()
    assert orphan["project_id"] is None and orphan["content"] == "Usaremos React Native"


def test_tasks_crud(client, auth):
    task = post(client, auth, "/tasks", {"title": "Escribir pruebas", "priority": 5})
    assert task["status"] == "pending" and task["completed_at"] is None
    done = client.patch(f"{API}/tasks/{task['id']}", json={"status": "done"}, headers=auth).json()
    assert done["status"] == "done" and done["completed_at"]
    reopened = client.patch(
        f"{API}/tasks/{task['id']}",
        json={"status": "in_progress", "due_date": "2030-01-31"},
        headers=auth,
    ).json()
    assert reopened["completed_at"] is None and reopened["due_date"] == "2030-01-31"
    bad = client.post(
        f"{API}/tasks",
        json={"title": "x", "project_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth,
    )
    assert bad.status_code == 422
    assert client.delete(f"{API}/tasks/{task['id']}", headers=auth).status_code == 204
    assert client.get(f"{API}/tasks", headers=auth).json() == []


# ----------------------------------------------------------------- documentos
def test_upload_text_document(client, auth):
    content = b"# Manual\n\nEl sistema guarda recuerdos con procedencia."
    response = client.post(
        f"{API}/documents/upload",
        files={"file": ("manual.md", io.BytesIO(content), "text/markdown")},
        data={"tags": "manual, guia", "importance": "4"},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    memory = response.json()["memory"]
    assert memory["memory_type"] == "document" and memory["title"] == "manual.md"
    assert memory["source_type"] == "document" and memory["source_ref"] == "manual.md"
    assert memory["provenance"]["size_bytes"] == len(content)
    assert len(memory["provenance"]["sha256"]) == 64
    assert memory["tags"][:2] == ["manual", "guia"] and memory["importance"] == 4
    listed = client.get(f"{API}/documents", headers=auth).json()
    assert listed["total"] == 1
    found = client.post(f"{API}/search", json={"query": "procedencia"}, headers=auth).json()
    assert found["results"][0]["memory"]["id"] == memory["id"]


def test_upload_pdf_document(client, auth):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 100 Td (Contrato de servicios firmado en 2024) Tj ET")
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)

    response = client.post(
        f"{API}/documents/upload",
        files={"file": ("contrato.pdf", io.BytesIO(buffer.getvalue()), "application/pdf")},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    memory = response.json()["memory"]
    assert "Contrato de servicios firmado en 2024" in memory["content"]
    assert memory["provenance"]["extraction"] == "pypdf" and memory["provenance"]["pages"] == 1


def test_upload_rejects_unsupported_empty_and_oversized(client, auth, app, settings):
    def upload(name, data):
        return client.post(
            f"{API}/documents/upload", files={"file": (name, io.BytesIO(data))}, headers=auth
        )

    assert upload("imagen.png", b"\x89PNG\r\n").status_code == 422
    assert upload("vacio.txt", b"").status_code == 422
    assert upload("falso.pdf", b"no soy un pdf").status_code == 422

    from core.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"max_upload_mb": 0}
    )
    try:
        assert upload("grande.txt", b"contenido").status_code == 413
    finally:
        app.dependency_overrides.clear()
    assert client.get(f"{API}/documents", headers=auth).json()["total"] == 0
    formats = client.get(f"{API}/documents/formats", headers=auth).json()
    assert ".pdf" in formats["extensions"] and ".md" in formats["extensions"]


# -------------------------------------------------------------- conversaciones
def test_conversation_from_messages(client, auth):
    body = {
        "title": "Planificación del módulo financiero",
        "origin": "claude",
        "external_id": "conv-123",
        "messages": [
            {
                "role": "user",
                "content": "Quiero registrar gastos",
                "timestamp": "2026-03-01T10:00:00Z",
            },
            {"role": "assistant", "content": "Podemos crear un módulo financiero"},
        ],
    }
    memory = post(client, auth, "/conversations", body)["memory"]
    assert (memory["memory_type"], memory["kind"]) == ("episodic", "conversation")
    assert memory["source_type"] == "conversation" and memory["source_ref"] == "conv-123"
    assert memory["provenance"]["message_count"] == 2
    assert memory["provenance"]["participants"] == ["assistant", "user"]
    assert memory["occurred_at"].startswith("2026-03-01T10:00:00")
    assert "user [2026-03-01 10:00]: Quiero registrar gastos" in memory["content"]
    assert client.get(f"{API}/conversations", headers=auth).json()["total"] == 1

    both = {**body, "transcript": "texto"}
    assert client.post(f"{API}/conversations", json=both, headers=auth).status_code == 422
    neither = {"title": "vacía"}
    assert client.post(f"{API}/conversations", json=neither, headers=auth).status_code == 422


# ---------------------------------------------------------------- preferencias
def test_preferences_keep_history(client, auth):
    first = client.put(
        f"{API}/preferences/editor.tema",
        json={"value": "Tema claro", "category": "editor"},
        headers=auth,
    )
    assert first.status_code == 201
    second = client.put(
        f"{API}/preferences/editor.tema",
        json={"value": "Tema oscuro", "reason": "Trabajo de noche"},
        headers=auth,
    )
    assert second.status_code == 200
    body = second.json()
    assert body["value"] == "Tema oscuro" and body["version"] == 2
    assert body["category"] == "editor" and body["memory_id"] == first.json()["memory_id"]

    versions = client.get(f"{API}/memories/{body['memory_id']}/versions", headers=auth).json()
    assert versions[1]["snapshot"]["content"] == "Tema claro"
    assert versions[0]["change_reason"] == "Trabajo de noche"

    client.put(f"{API}/preferences/idioma", json={"value": "Español"}, headers=auth)
    listed = client.get(f"{API}/preferences", headers=auth).json()
    assert [p["key"] for p in listed] == ["editor.tema", "idioma"]
    only = client.get(f"{API}/preferences?category=editor", headers=auth).json()
    assert [p["key"] for p in only] == ["editor.tema"]
    assert client.get(f"{API}/preferences/idioma", headers=auth).json()["value"] == "Español"
    assert client.get(f"{API}/preferences/nada", headers=auth).status_code == 404
    bad = client.put(f"{API}/preferences/Clave Mala!", json={"value": "x"}, headers=auth)
    assert bad.status_code == 422


# ----------------------------------------------------------------- conocimiento
def test_concepts_and_links(client, auth):
    vector = post(
        client,
        auth,
        "/knowledge/concepts",
        {"name": "Embedding", "definition": "Vector numérico que representa un texto."},
    )["memory"]
    assert (vector["memory_type"], vector["kind"], vector["title"]) == (
        "semantic",
        "concept",
        "Embedding",
    )
    rag = post(
        client,
        auth,
        "/knowledge/concepts",
        {
            "name": "RAG",
            "definition": "Generación aumentada por recuperación de documentos.",
            "related_to": [vector["id"]],
            "source_ref": "curso de IA",
        },
    )["memory"]
    neighbors = client.get(f"{API}/memories/{rag['id']}/relations", headers=auth).json()
    assert [(n["memory"]["title"], n["relation"]["relation_type"]) for n in neighbors] == [
        ("Embedding", "related")
    ]
    listed = client.get(f"{API}/knowledge/concepts", headers=auth).json()
    assert {m["title"] for m in listed["items"]} == {"Embedding", "RAG"}
    missing = client.post(
        f"{API}/knowledge/concepts",
        json={
            "name": "X",
            "definition": "y",
            "related_to": ["00000000-0000-0000-0000-000000000000"],
        },
        headers=auth,
    )
    assert missing.status_code == 404
    assert client.get(f"{API}/knowledge/concepts", headers=auth).json()["total"] == 2
