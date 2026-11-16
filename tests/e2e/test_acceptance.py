"""Criterios de aceptación de la versión 0.1 recorridos de principio a fin por la API."""

import io

API = "/api/v1"


def test_acceptance_flow(client, admin_user, engine):
    # Arrancar desde una instalación limpia e iniciar sesión.
    assert client.get("/health").json()["status"] == "ok"
    login = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "contraseña-segura-123"}
    )
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def post(path, body, expected=201):
        response = client.post(API + path, json=body, headers=auth)
        assert response.status_code == expected, response.text
        return response.json()

    # Crear y administrar proyectos.
    project = post(
        "/projects",
        {
            "name": "Segundo Cerebro",
            "description": "Sistema de memoria personal",
            "objectives": ["Recordar decisiones", "Buscar por significado"],
        },
    )
    client.patch(f"{API}/projects/{project['id']}", json={"status": "active"}, headers=auth)

    # Crear y guardar recuerdos, asociándolos al proyecto.
    decision = post(
        "/memories",
        {
            "content": "Decidimos que la base de datos será PostgreSQL con la extensión pgvector.",
            "project_id": project["id"],
            "source_ref": "reunión de arquitectura del lunes",
            "tags": ["arquitectura"],
            "importance": 5,
        },
    )["memory"]
    post(
        "/memories",
        {"content": "Receta de gazpacho: tomate, pepino, pimiento, ajo y aceite de oliva."},
    )
    assert decision["project_name"] == "Segundo Cerebro" and decision["kind"] == "decision"

    # Consultar recuerdos almacenados.
    listed = client.get(f"{API}/memories?project_id={project['id']}", headers=auth).json()
    assert [m["id"] for m in listed["items"]] == [decision["id"]]

    # Buscar por texto y por significado (similitud de embeddings).
    by_text = post("/search", {"query": "pgvector", "mode": "text"}, 200)
    assert by_text["results"][0]["memory"]["id"] == decision["id"]
    by_vector = post("/search", {"query": "bases de datos postgres", "mode": "semantic"}, 200)
    assert by_vector["results"][0]["memory"]["id"] == decision["id"]
    assert by_vector["results"][0]["semantic_similarity"] > 0.2

    # Actualizar conservando el historial.
    client.patch(
        f"{API}/memories/{decision['id']}",
        json={
            "content": "Decidimos que la base de datos será PostgreSQL 17 con pgvector.",
            "change_reason": "Se fijó la versión",
        },
        headers=auth,
    )
    versions = client.get(f"{API}/memories/{decision['id']}/versions", headers=auth).json()
    assert len(versions) == 2 and "extensión pgvector" in versions[1]["snapshot"]["content"]

    # Preguntar en lenguaje natural mostrando las fuentes.
    answer = post("/ask", {"question": "¿Qué decisiones había tomado en Segundo Cerebro?"}, 200)
    memory_sources = [s for s in answer["sources"] if s["source_kind"] == "memory"]
    assert [s["id"] for s in memory_sources] == [decision["id"]]
    assert memory_sources[0]["source_ref"] == "reunión de arquitectura del lunes"
    assert any("PostgreSQL 17" in c["text"] for c in answer["confirmed"])
    unknown = post("/ask", {"question": "¿Qué sé sobre física de partículas?"}, 200)
    assert unknown["confirmed"] == [] and unknown["not_found"]

    # Exportar la información.
    export = client.get(f"{API}/data/export", headers=auth)
    assert export.status_code == 200 and export.json()["counts"]["memories"] == 2

    # Restaurar una copia: se borra todo y se recupera desde la exportación.
    from sqlalchemy import text

    with engine.begin() as connection:
        connection.execute(text("TRUNCATE memories, projects, change_log CASCADE"))
    assert client.get(f"{API}/memories", headers=auth).json()["total"] == 0
    upload = {"file": ("copia.json", io.BytesIO(export.content), "application/json")}
    report = client.post(f"{API}/data/import", files=upload, headers=auth).json()
    assert report["sections"]["memories"]["imported"] == 2

    recovered = client.get(f"{API}/memories/{decision['id']}", headers=auth).json()
    assert recovered["version"] == 2 and "PostgreSQL 17" in recovered["content"]
    assert len(client.get(f"{API}/memories/{decision['id']}/versions", headers=auth).json()) == 2
    again = post("/search", {"query": "bases de datos postgres"}, 200)
    assert again["results"][0]["memory"]["id"] == decision["id"]
