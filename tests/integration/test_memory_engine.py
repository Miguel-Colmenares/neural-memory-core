import uuid

import pytest
from sqlalchemy import func, select

from core.database.models import ChangeLog, Memory, MemoryEmbedding, MemoryVersion, Project
from core.errors import InvalidInputError, NotFoundError
from core.memory_engine.filters import MemoryFilters
from core.memory_engine.service import MemoryData, MemoryService
from core.versioning import service as versioning


@pytest.fixture
def service(session, embedder, settings):
    return MemoryService(session, embedder, settings, actor="tester")


def make(service, content="Recuerdo de prueba sobre PostgreSQL", **kwargs):
    kwargs.setdefault("memory_type", "semantic")
    return service.create(MemoryData(content=content, **kwargs))


def test_create_persists_all_required_fields(service, session):
    project = Project(slug="demo", name="Demo")
    session.add(project)
    session.flush()
    memory = make(
        service,
        title="Título",
        source_type="api",
        source_ref="https://ejemplo.test/nota",
        provenance={"autor": "yo"},
        project_id=project.id,
        tags=["Base de Datos", "base de datos", "pg"],
        importance=5,
        metadata={"clave": "valor"},
    )
    session.commit()
    session.expire_all()
    stored = session.get(Memory, memory.id)
    assert isinstance(stored.id, uuid.UUID)
    assert stored.content == "Recuerdo de prueba sobre PostgreSQL"
    assert stored.memory_type == "semantic" and stored.status == "active"
    assert stored.created_at and stored.updated_at
    assert stored.source_type == "api" and stored.source_ref.startswith("https://")
    assert stored.provenance == {"autor": "yo"}
    assert stored.project_id == project.id
    assert stored.tags == ["base de datos", "pg"]
    assert stored.importance == 5 and stored.metadata_ == {"clave": "valor"}
    assert stored.version == 1 and stored.created_by == "tester"
    assert len(stored.content_hash) == 64


def test_create_records_version_changelog_and_embedding(service, session):
    memory = make(service)
    versions = versioning.list_versions(session, memory.id)
    assert [v.version for v in versions] == [1]
    assert versions[0].change_type == "create" and versions[0].snapshot["content"] == memory.content
    log = session.scalars(select(ChangeLog).where(ChangeLog.entity_id == str(memory.id))).all()
    assert [entry.action for entry in log] == ["create"]
    embeddings = session.scalars(
        select(MemoryEmbedding).where(MemoryEmbedding.memory_id == memory.id)
    ).all()
    assert len(embeddings) == 1 and embeddings[0].provider == "hashing"


@pytest.mark.parametrize(
    "bad",
    [
        {"content": "   "},
        {"memory_type": "inventado"},
        {"importance": 9},
        {"source_type": "telepatia"},
        {"project_id": uuid.uuid4()},
    ],
)
def test_validation_rejects_bad_input(service, bad):
    with pytest.raises(InvalidInputError):
        make(service, **bad)


def test_content_length_limit(session, embedder, settings):
    limited = settings.model_copy(update={"max_content_chars": 1000})
    with pytest.raises(InvalidInputError, match="máximo"):
        MemoryService(session, embedder, limited).create(
            MemoryData(content="x" * 1001, memory_type="semantic")
        )


def test_update_keeps_previous_version(service, session):
    memory = make(service, content="La capital de Australia es Sídney")
    updated = service.update(
        memory.id,
        {"content": "La capital de Australia es Canberra", "importance": 4},
        reason="Dato corregido",
        change_type="correction",
    )
    assert updated.version == 2 and updated.updated_at > updated.created_at
    versions = versioning.list_versions(session, memory.id)
    assert [v.version for v in versions] == [2, 1]
    assert versions[1].snapshot["content"] == "La capital de Australia es Sídney"
    assert versions[0].snapshot["content"] == "La capital de Australia es Canberra"
    assert versions[0].change_type == "correction"
    assert versions[0].change_reason == "Dato corregido"
    assert sorted(versions[0].changed_fields) == ["content", "importance"]
    assert versions[0].changed_by == "tester"


def test_update_without_changes_creates_no_version(service, session):
    memory = make(service, tags=["a"])
    same = service.update(memory.id, {"content": memory.content, "tags": ["A"]})
    assert same.version == 1
    assert session.scalar(select(func.count()).select_from(MemoryVersion)) == 1


def test_update_reindexes_embeddings_only_when_text_changes(service, session):
    memory = make(service, content="texto original sobre gatos")

    def vector():
        return list(
            session.scalar(
                select(MemoryEmbedding.embedding).where(MemoryEmbedding.memory_id == memory.id)
            )
        )

    before = vector()
    service.update(memory.id, {"importance": 1})
    assert vector() == before
    service.update(memory.id, {"content": "texto nuevo sobre perros"})
    assert vector() != before


def test_update_rejects_unknown_fields_and_missing_memory(service):
    memory = make(service)
    with pytest.raises(InvalidInputError, match="no editables"):
        service.update(memory.id, {"status": "archived"})
    with pytest.raises(NotFoundError):
        service.update(uuid.uuid4(), {"content": "x"})


def test_archive_restore_are_versioned(service, session):
    memory = make(service)
    service.archive(memory.id, "ya no aplica")
    assert session.get(Memory, memory.id).status == "archived"
    items, total = service.list()
    assert total == 0 and items == []
    assert service.list(MemoryFilters(status="archived"))[1] == 1
    service.restore(memory.id)
    versions = versioning.list_versions(session, memory.id)
    assert [v.change_type for v in versions] == ["restore", "archive", "create"]
    assert versions[1].change_reason == "ya no aplica"
    assert service.archive(memory.id).version == 4
    assert service.archive(memory.id).version == 4  # idempotente


def test_revert_creates_new_version_with_old_content(service, session):
    memory = make(service, content="versión uno", tags=["uno"])
    service.update(memory.id, {"content": "versión dos", "tags": ["dos"]})
    reverted = service.revert(memory.id, 1, "me equivoqué")
    assert reverted.version == 3
    assert reverted.content == "versión uno" and reverted.tags == ["uno"]
    versions = versioning.list_versions(session, memory.id)
    assert versions[0].change_type == "revert" and "versión 1" in versions[0].change_reason
    assert versions[1].snapshot["content"] == "versión dos"  # nada se pierde
    with pytest.raises(NotFoundError):
        service.revert(memory.id, 99)


def test_delete_removes_history_but_leaves_audit_trail(service, session):
    memory = make(service, content="número secreto 12345")
    memory_id = memory.id
    service.update(memory_id, {"content": "número secreto 12345 y 67890"})
    service.delete(memory_id, "retirar información privada")
    session.commit()
    assert session.get(Memory, memory_id) is None
    assert session.scalar(select(func.count()).select_from(MemoryVersion)) == 0
    assert session.scalar(select(func.count()).select_from(MemoryEmbedding)) == 0
    entry = session.scalars(select(ChangeLog).where(ChangeLog.action == "delete")).one()
    assert entry.details["reason"] == "retirar información privada"
    for row in session.scalars(select(ChangeLog)):
        assert "12345" not in row.summary + str(row.details)


def test_list_filters_and_ordering(service, session):
    project = Project(slug="p", name="P")
    session.add(project)
    session.flush()
    a = make(service, content="uno", memory_type="semantic", tags=["x", "y"], importance=1)
    b = make(service, content="dos", memory_type="episodic", tags=["x"], importance=5)
    c = make(service, content="tres", memory_type="project", kind="decision", project_id=project.id)

    def ids(**kwargs):
        return {m.id for m in service.list(MemoryFilters(**kwargs))[0]}

    assert ids() == {a.id, b.id, c.id}
    assert ids(memory_types=["episodic"]) == {b.id}
    assert ids(tags=["x"]) == {a.id, b.id}
    assert ids(tags=["x", "y"]) == {a.id}
    assert ids(kinds=["decision"]) == {c.id}
    assert ids(project_ids=[project.id]) == {c.id}
    assert ids(min_importance=4) == {b.id}
    assert ids(date_from=b.created_at) == {b.id, c.id}
    assert ids(date_to=a.created_at) == {a.id}
    ordered, total = service.list(order="importance_desc", limit=1)
    assert total == 3 and ordered[0].id == b.id
    assert [m.id for m in service.list(order="created_asc")[0]] == [a.id, b.id, c.id]


def test_long_content_is_chunked_for_embeddings(service, session):
    text = "\n\n".join(f"Sección {i}. " + "detalle importante " * 60 for i in range(8))
    memory = make(service, content=text, memory_type="document")
    chunks = session.scalars(
        select(MemoryEmbedding)
        .where(MemoryEmbedding.memory_id == memory.id)
        .order_by(MemoryEmbedding.chunk_index)
    ).all()
    assert len(chunks) > 3
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_data_survives_a_new_connection(service, session, settings):
    """Persistencia real: otra conexión (como tras reiniciar) ve los datos confirmados."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    memory = make(service, content="esto debe sobrevivir a un reinicio")
    session.commit()
    fresh_engine = create_engine(settings.database_url)
    try:
        with Session(fresh_engine) as other:
            stored = other.get(Memory, memory.id)
            assert stored is not None and stored.content == "esto debe sobrevivir a un reinicio"
    finally:
        fresh_engine.dispose()
