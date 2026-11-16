import json
from datetime import timedelta

import httpx
import pytest

from core.database.models import Project, ProjectRelation, utcnow
from core.ingestion.pipeline import IngestionInput, IngestionPipeline
from core.knowledge_graph.service import KnowledgeGraph
from core.llm.client import LLMClient
from core.memory_engine.filters import MemoryFilters
from core.retrieval.answer import AnswerEngine
from core.retrieval.engine import HybridRetriever
from core.retrieval.query_analysis import analyze
from core.retrieval.text_search import text_search


@pytest.fixture
def world(session, embedder, settings, modules):
    """Una memoria pequeña pero realista con dos proyectos."""
    pipeline = IngestionPipeline(session, embedder, settings, actor="tester")
    core = Project(
        slug="neural-memory-core",
        name="Neural Memory Core",
        description="Segundo cerebro digital con memoria persistente.",
        objectives=["Guardar recuerdos", "Recuperarlos con fuentes"],
        updated_at=utcnow() - timedelta(days=30),
    )
    shop = Project(
        slug="tienda-online",
        name="Tienda Online",
        description="Comercio electrónico de café de especialidad.",
        updated_at=utcnow() - timedelta(days=60),
    )
    session.add_all([core, shop])
    session.flush()

    def add(content, **kwargs):
        kwargs.setdefault("auto_relate", False)
        return pipeline.ingest(IngestionInput(content=content, **kwargs)).memory

    items = {
        "db": add(
            "Decidimos usar PostgreSQL con pgvector como base de datos vectorial.",
            memory_type="project",
            kind="decision",
            project_id=core.id,
            tags=["postgresql", "arquitectura"],
            source_ref="reunión de arquitectura",
        ),
        "frontend": add(
            "Decidimos construir el panel con Next.js y Tailwind CSS.",
            memory_type="project",
            kind="decision",
            project_id=core.id,
            tags=["frontend"],
        ),
        "payments": add(
            "Decidimos cobrar con Stripe en la tienda y guardar los pedidos en PostgreSQL.",
            memory_type="project",
            kind="decision",
            project_id=shop.id,
            tags=["postgresql", "pagos"],
        ),
        "bread": add(
            "Receta de pan: harina integral, agua, sal y masa madre. Hornear 45 minutos.",
            memory_type="semantic",
            tags=["cocina"],
        ),
        "graph": add(
            "Un grafo de conocimiento representa conceptos como nodos unidos por relaciones.",
            memory_type="semantic",
            kind="concept",
            title="Grafo de conocimiento",
            importance=5,
        ),
        "chat": add(
            "user: ¿Y si añadimos un módulo financiero?\n\nassistant: Buena idea, registraría "
            "ingresos y gastos mensuales.",
            memory_type="episodic",
            kind="conversation",
            title="Idea del módulo financiero",
            source_type="conversation",
            project_id=core.id,
        ),
    }
    session.flush()
    return {"core": core, "shop": shop, "pipeline": pipeline, **items}


@pytest.fixture
def retriever(session, embedder):
    return HybridRetriever(session, embedder)


def ids(response):
    return [r.memory.id for r in response.results]


# ------------------------------------------------------------------- búsqueda
def test_text_search_matches_stems_and_accents(session, world):
    hits = text_search(session, "decidir")  # la raíz coincide con «Decidimos»
    assert {h.memory_id for h in hits} >= {world["db"].id, world["frontend"].id}
    assert text_search(session, "modulos financieros")[0].memory_id == world["chat"].id
    assert text_search(session, "conceptos")[0].memory_id == world["graph"].id
    assert text_search(session, "xyzzy inexistente") == []
    assert text_search(session, "el la de") == []  # solo palabras vacías


def test_hybrid_search_ranks_the_relevant_memory_first(retriever, world):
    response = retriever.search("base de datos vectorial")
    assert ids(response)[0] == world["db"].id
    top = response.results[0]
    assert top.matched_by == ["text", "semantic"]
    assert top.text_rank > 0 and top.semantic_similarity > 0.2
    assert "**" in top.excerpt
    assert set(top.score_breakdown) == {"relevance", "importance", "recency"}
    assert world["bread"].id not in ids(response)


def test_semantic_mode_finds_morphological_variants_without_exact_words(retriever, world):
    response = retriever.search("hornear panes integrales", mode="semantic")
    assert ids(response)[0] == world["bread"].id
    assert response.results[0].matched_by == ["semantic"]
    assert response.embedding["provider"] == "hashing"


def test_text_mode_does_not_use_embeddings(retriever, world):
    response = retriever.search("Stripe", mode="text")
    assert ids(response) == [world["payments"].id]
    assert response.results[0].semantic_similarity is None


def test_search_returns_nothing_for_unknown_topics(retriever, world):
    response = retriever.search("astrofísica de agujeros negros supermasivos")
    assert response.results == []


def test_filters_apply_to_both_search_methods(retriever, world):
    query = "decisiones PostgreSQL"
    everything = ids(retriever.search(query))
    assert {world["db"].id, world["payments"].id} <= set(everything)
    only_shop = retriever.search(query, MemoryFilters(project_ids=[world["shop"].id]))
    assert ids(only_shop) == [world["payments"].id]
    tagged = retriever.search(query, MemoryFilters(tags=["arquitectura"]))
    assert ids(tagged) == [world["db"].id]
    typed = retriever.search("grafo nodos", MemoryFilters(memory_types=["episodic"]))
    assert ids(typed) == []
    future = retriever.search(query, MemoryFilters(date_from=utcnow() + timedelta(days=1)))
    assert ids(future) == []


def test_archived_memories_are_excluded_by_default(retriever, world, session):
    world["pipeline"].memories.archive(world["bread"].id)
    assert ids(retriever.search("receta de pan")) == []
    assert ids(retriever.search("receta de pan", MemoryFilters(status=None))) == [world["bread"].id]


def test_related_memories_are_added_with_lower_score(retriever, world, session):
    KnowledgeGraph(session).relate(world["bread"].id, world["graph"].id, "references")
    response = retriever.search("receta de pan con masa madre")
    assert ids(response)[0] == world["bread"].id
    related = next(r for r in response.results if r.memory.id == world["graph"].id)
    assert related.matched_by == ["relation"]
    assert related.via_relation["relation_type"] == "references"
    assert related.via_relation["from_memory_id"] == str(world["bread"].id)
    assert related.score < response.results[0].score
    without = retriever.search("receta de pan con masa madre", include_related=False)
    assert world["graph"].id not in ids(without)


def test_importance_and_recency_reorder_ties(retriever, world, session):
    pipeline = world["pipeline"]
    low = pipeline.ingest(
        IngestionInput(content="Kubernetes orquesta contenedores", importance=1, auto_relate=False)
    ).memory
    high = pipeline.ingest(
        IngestionInput(
            content="Kubernetes orquesta contenedores.",
            importance=5,
            allow_duplicate=True,
            auto_relate=False,
        )
    ).memory
    assert ids(retriever.search("Kubernetes contenedores", include_related=False)) == [
        high.id,
        low.id,
    ]


# ------------------------------------------------------- análisis de preguntas
def test_query_analysis_detects_intents_and_projects(session, world):
    analysis = analyze(session, "¿Qué decisiones había tomado en Neural Memory Core?")
    assert analysis.intents == ["decisions"] and analysis.kinds == ["decision"]
    assert [p.name for p in analysis.projects] == ["Neural Memory Core"]
    assert analysis.terms == []

    analysis = analyze(session, "¿Qué información tengo sobre grafos de conocimiento?")
    assert analysis.intents == [] and analysis.terms == ["grafos", "conocimiento"]

    analysis = analyze(session, "¿Qué estaba desarrollando en mi último proyecto?")
    assert set(analysis.intents) == {"recent", "latest_project"}

    analysis = analyze(session, "¿Qué relación existe entre Tienda Online y Neural Memory Core?")
    assert "project_relation" in analysis.intents
    assert [p.name for p in analysis.projects] == ["Tienda Online", "Neural Memory Core"]


# ----------------------------------------------------------------- respuestas
@pytest.fixture
def engine_(session, embedder):
    return AnswerEngine(session, embedder)


def source_ids(answer, kind="memory"):
    return {s["id"] for s in answer.sources if s["source_kind"] == kind}


def test_ask_about_a_topic_quotes_sources_literally(engine_, world):
    answer = engine_.ask("¿Qué información tengo sobre grafos de conocimiento?")
    assert answer.answer_mode == "extractive"
    assert str(world["graph"].id) in source_ids(answer)
    cited = {s["index"]: s for s in answer.sources}
    for item in answer.confirmed:
        assert item["sources"] and all(i in cited for i in item["sources"])
    quote = next(c["text"] for c in answer.confirmed if "grafo" in c["text"].lower())
    assert quote in world["graph"].content
    source = next(s for s in answer.sources if s["id"] == str(world["graph"].id))
    assert source["source_type"] == "manual" and source["created_at"]
    assert answer.not_found == []


def test_ask_for_decisions_of_a_named_project(engine_, world):
    answer = engine_.ask("¿Qué decisiones había tomado en Neural Memory Core?")
    assert source_ids(answer) == {str(world["db"].id), str(world["frontend"].id)}
    assert answer.interpretation["filters"]["kinds"] == ["decision"]
    assert "PostgreSQL" in answer.answer and "Stripe" not in answer.answer


def test_ask_about_last_project_explains_the_inference(engine_, world, session):
    world["pipeline"].ingest(
        IngestionInput(
            content="Estoy desarrollando el carrito de compra de la tienda.",
            project_id=world["shop"].id,
            memory_type="project",
        )
    )
    session.flush()
    answer = engine_.ask("¿Qué estaba desarrollando en mi último proyecto?")
    assert answer.interpretation["projects"][0]["name"] == "Tienda Online"
    assert any("actividad más reciente" in i["text"] for i in answer.inferences)
    assert any("carrito" in c["text"] for c in answer.confirmed)
    assert str(world["db"].id) not in source_ids(answer)


def test_ask_relation_between_projects(engine_, world, session):
    answer = engine_.ask("¿Qué relación existe entre Tienda Online y Neural Memory Core?")
    assert answer.confirmed == []
    shared = next(i for i in answer.inferences if "comparten etiquetas" in i["text"])
    assert "postgresql" in shared["text"] and "no una relación registrada" in shared["text"]

    session.add(
        ProjectRelation(
            source_project_id=world["shop"].id,
            target_project_id=world["core"].id,
            relation_type="uses",
            description="La tienda usará la memoria para atención al cliente.",
        )
    )
    session.flush()
    answer = engine_.ask("¿Qué relación existe entre Tienda Online y Neural Memory Core?")
    assert any(
        "«uses»" in c["text"] and "atención al cliente" in c["text"] for c in answer.confirmed
    )


def test_ask_relation_needs_two_known_projects(engine_, world):
    answer = engine_.ask("¿Qué relación existe entre estos dos proyectos?")
    assert answer.confirmed == [] and len(answer.not_found) == 1
    assert "necesito identificar dos" in answer.not_found[0]


def test_ask_previous_conversations_about_an_idea(engine_, world):
    answer = engine_.ask("¿Qué había hablado anteriormente sobre el módulo financiero?")
    assert str(world["chat"].id) in source_ids(answer)
    quote = next(c["text"] for c in answer.confirmed if "módulo financiero" in c["text"])
    assert quote in world["chat"].content


def test_ask_latest_changes_uses_the_change_log(engine_, world, session):
    world["pipeline"].memories.update(
        world["frontend"].id, {"content": "Decidimos construir el panel con Next.js 15."}
    )
    session.flush()
    answer = engine_.ask("¿Cuáles son los últimos cambios realizados?")
    assert source_ids(answer) == set()
    changes = [s for s in answer.sources if s["source_kind"] == "change_log"]
    assert changes and "actualizado" in changes[0]["excerpt"]
    assert "(v2)" in answer.confirmed[0]["text"]


def test_ask_about_pending_tasks_uses_the_tasks_module(engine_, world, session):
    from modules.tasks.models import Task

    session.add_all(
        [
            Task(title="Escribir la guía de despliegue", project_id=world["core"].id, priority=5),
            Task(title="Tarea ya hecha", project_id=world["core"].id, status="done"),
        ]
    )
    session.flush()
    answer = engine_.ask("¿Qué tareas pendientes tengo en Neural Memory Core?")
    texts = [c["text"] for c in answer.confirmed]
    assert any("Escribir la guía de despliegue" in t for t in texts)
    assert not any("Tarea ya hecha" in t for t in texts)
    assert any(s["source_kind"] == "task" for s in answer.sources)


def test_ask_never_invents_when_nothing_is_stored(engine_, world):
    answer = engine_.ask("¿Qué información tengo sobre astrofísica de agujeros negros?")
    assert answer.confirmed == [] and answer.inferences == [] and answer.sources == []
    assert "astrofisica" in answer.not_found[0]
    assert answer.answer.startswith("No encontrado")


# ------------------------------------------------------------------------ LLM
def llm_returning(payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        content = payload if isinstance(payload, str) else json.dumps(payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return LLMClient("https://llm.test/v1", "modelo", transport=httpx.MockTransport(handler))


def test_llm_answer_only_keeps_statements_with_valid_sources(session, embedder, world):
    seen = []
    llm = llm_returning(
        {
            "answer": "Un grafo de conocimiento une conceptos mediante relaciones [1].",
            "confirmed": [
                {"text": "Representa conceptos como nodos.", "sources": [1]},
                {"text": "Fue inventado en 1850.", "sources": [99]},
                {"text": "Sin fuente."},
            ],
            "inferences": [{"text": "Sirve para navegar ideas.", "sources": [1]}],
            "not_found": ["quién lo inventó"],
        },
        seen,
    )
    answer = AnswerEngine(session, embedder, llm).ask("¿Qué es un grafo de conocimiento?")
    assert answer.answer_mode == "llm"
    assert [c["text"] for c in answer.confirmed] == ["Representa conceptos como nodos."]
    assert any("Sirve para navegar" in i["text"] for i in answer.inferences)
    assert "quién lo inventó" in answer.not_found
    assert any("descartaron 2" in w for w in answer.warnings)
    prompt = seen[0]["messages"]
    assert "SOLO con la información de las FUENTES" in prompt[0]["content"]
    assert "[1]" in prompt[1]["content"] and "nodos unidos por relaciones" in prompt[1]["content"]


def test_llm_citing_unknown_sources_falls_back_to_extractive(session, embedder, world):
    llm = llm_returning({"answer": "Según [42] es así.", "confirmed": [], "inferences": []})
    answer = AnswerEngine(session, embedder, llm).ask("¿Qué es un grafo de conocimiento?")
    assert answer.answer_mode == "extractive"
    assert any("fuentes inexistentes" in w for w in answer.warnings)


def test_llm_failure_falls_back_to_extractive(session, embedder, world):
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    llm = LLMClient("https://llm.test/v1", "modelo", transport=transport)
    answer = AnswerEngine(session, embedder, llm).ask("¿Qué es un grafo de conocimiento?")
    assert answer.answer_mode == "extractive" and answer.confirmed
    assert any("modelo de lenguaje" in w for w in answer.warnings)


def test_llm_is_not_called_without_sources(session, embedder, world):
    seen = []
    llm = llm_returning({"answer": "inventado"}, seen)
    answer = AnswerEngine(session, embedder, llm).ask("¿Qué sé sobre astrofísica cuántica?")
    assert seen == [] and answer.answer_mode == "extractive" and answer.confirmed == []
