import uuid

import pytest
from sqlalchemy import func, select

from core.database.models import Memory, MemoryRelation, Project
from core.embeddings.base import EmbeddingError, EmbeddingProvider
from core.errors import InvalidInputError, NotFoundError
from core.ingestion.pipeline import IngestionInput, IngestionPipeline
from core.knowledge_graph.service import KnowledgeGraph


@pytest.fixture
def pipeline(session, embedder, settings):
    return IngestionPipeline(session, embedder, settings, actor="tester")


def test_pipeline_reports_every_step(pipeline):
    result = pipeline.ingest(IngestionInput(content="Un grafo relaciona nodos mediante aristas."))
    assert result.outcome == "created"
    assert [s["step"] for s in result.steps] == [
        "recibir",
        "validar",
        "duplicados",
        "embeddings",
        "relaciones",
        "clasificar",
        "guardar",
        "registrar",
    ]


def test_exact_duplicate_is_not_stored_twice(pipeline, session):
    first = pipeline.ingest(IngestionInput(content="El servidor de producción usa Ubuntu 24.04"))
    second = pipeline.ingest(
        IngestionInput(content="  el servidor de producción   usa ubuntu 24.04 ")
    )
    assert second.outcome == "duplicate"
    assert second.duplicate_of == first.memory.id and second.memory.id == first.memory.id
    assert session.scalar(select(func.count()).select_from(Memory)) == 1
    forced = pipeline.ingest(
        IngestionInput(content="El servidor de producción usa Ubuntu 24.04", allow_duplicate=True)
    )
    assert forced.outcome == "created"
    assert session.scalar(select(func.count()).select_from(Memory)) == 2


def test_near_duplicate_is_kept_and_flagged(pipeline, session):
    first = pipeline.ingest(
        IngestionInput(content="La reunión con el equipo será el lunes a las diez de la mañana")
    )
    second = pipeline.ingest(
        IngestionInput(content="La reunión con el equipo será el lunes a las diez de la mañana!!")
    )
    assert second.outcome == "created"
    assert [(r.memory_id, r.relation_type) for r in second.relations] == [
        (first.memory.id, "possible_duplicate")
    ]
    assert any("duplicado" in w for w in second.warnings)
    relation = session.scalars(select(MemoryRelation)).one()
    assert relation.origin == "auto" and relation.confidence >= 0.9


def test_related_memories_are_linked_automatically(pipeline, session):
    a = pipeline.ingest(
        IngestionInput(content="PostgreSQL con pgvector guarda los embeddings del proyecto")
    )
    pipeline.ingest(IngestionInput(content="Receta de pan con masa madre y harina integral"))
    c = pipeline.ingest(
        IngestionInput(content="Los embeddings se guardan en PostgreSQL usando pgvector")
    )
    assert [(r.memory_id, r.relation_type, r.origin) for r in c.relations] == [
        (a.memory.id, "related", "auto")
    ]
    neighbors = KnowledgeGraph(session).neighbors([a.memory.id])[a.memory.id]
    assert [n.memory.id for n in neighbors] == [c.memory.id]


def test_auto_relate_can_be_disabled(pipeline):
    pipeline.ingest(IngestionInput(content="PostgreSQL con pgvector guarda los embeddings"))
    result = pipeline.ingest(
        IngestionInput(content="Los embeddings se guardan en PostgreSQL", auto_relate=False)
    )
    assert result.relations == []


def test_contradiction_keeps_both_versions(pipeline, session):
    old = pipeline.ingest(
        IngestionInput(content="El despliegue se hará en Railway", source_ref="reunión marzo")
    )
    new = pipeline.ingest(
        IngestionInput(
            content="El despliegue se hará en un VPS propio, no en Railway",
            source_ref="reunión abril",
            contradicts=[old.memory.id],
        )
    )
    assert session.get(Memory, old.memory.id).status == "active"
    assert session.get(Memory, old.memory.id).content == "El despliegue se hará en Railway"
    relation = session.scalars(
        select(MemoryRelation).where(MemoryRelation.relation_type == "contradicts")
    ).one()
    assert (relation.source_id, relation.target_id) == (new.memory.id, old.memory.id)
    assert relation.origin == "manual"
    assert old.memory.created_at <= new.memory.created_at
    assert {old.memory.source_ref, new.memory.source_ref} == {"reunión marzo", "reunión abril"}


def test_contradicts_must_reference_existing_memory(pipeline, session):
    with pytest.raises(NotFoundError):
        pipeline.ingest(IngestionInput(content="algo", contradicts=[uuid.uuid4()]))
    assert session.scalar(select(func.count()).select_from(Memory)) == 0


def test_automatic_classification_is_recorded(pipeline, session):
    project = Project(slug="p", name="P")
    session.add(project)
    session.flush()
    preference = pipeline.ingest(IngestionInput(content="Prefiero los informes en Markdown"))
    assert preference.memory.memory_type == "preference"
    assert preference.memory.metadata_["classification"]["memory_type"]["method"] == "rules"
    decision = pipeline.ingest(
        IngestionInput(content="Decidimos lanzar la beta en junio", project_id=project.id)
    )
    assert (decision.memory.memory_type, decision.memory.kind) == ("project", "decision")
    explicit = pipeline.ingest(
        IngestionInput(content="Prefiero el té al café", memory_type="semantic", kind="dato")
    )
    assert explicit.memory.memory_type == "semantic" and explicit.memory.kind == "dato"
    assert "classification" not in explicit.memory.metadata_


def test_auto_tags_are_marked_as_automatic(pipeline):
    pipeline.ingest(IngestionInput(content="Notas del backend", tags=["backend"]))
    result = pipeline.ingest(
        IngestionInput(content="Hay que refactorizar el backend esta semana", tags=["urgente"])
    )
    assert result.memory.tags == ["urgente", "backend"]
    assert result.auto_tags == ["backend"]
    assert result.memory.metadata_["auto_tags"] == ["backend"]
    manual = pipeline.ingest(
        IngestionInput(content="El backend necesita más pruebas", auto_tag=False)
    )
    assert manual.memory.tags == [] and "auto_tags" not in manual.memory.metadata_


def test_empty_content_is_rejected(pipeline):
    with pytest.raises(InvalidInputError):
        pipeline.ingest(IngestionInput(content=" \n "))


class BrokenEmbedder(EmbeddingProvider):
    name = "roto"
    model = "ninguno"

    def embed(self, texts):
        raise EmbeddingError("servicio caído")


def test_memory_is_saved_even_if_embeddings_fail(session, settings):
    from core.embeddings.indexer import index_status

    broken = BrokenEmbedder()
    result = IngestionPipeline(session, broken, settings).ingest(
        IngestionInput(content="Esto no debe perderse aunque falle el proveedor")
    )
    assert result.outcome == "created"
    assert any("embeddings" in w for w in result.warnings)
    assert session.get(Memory, result.memory.id) is not None
    assert index_status(session, broken)["memories_pending"] == 1
