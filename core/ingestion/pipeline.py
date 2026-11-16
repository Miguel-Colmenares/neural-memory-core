"""Proceso de incorporación de información nueva.

Pasos (cada uno deja rastro en ``IngestionResult.steps``):

1. Recibir  2. Validar  3. Duplicados  4. Relaciones  5. Embeddings
6. Clasificar y etiquetar  7. Guardar  8. Registrar cambios  9. Actualizar índices

La información contradictoria nunca borra la anterior: ambas versiones se
conservan y se enlazan con una relación ``contradicts``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from core.config import Settings, get_settings
from core.database.models import Memory
from core.embeddings.base import EmbeddingError, EmbeddingProvider
from core.embeddings.indexer import embed_content
from core.errors import InvalidInputError
from core.ingestion import classifier
from core.knowledge_graph.service import KnowledgeGraph
from core.memory_engine.filters import MemoryFilters
from core.memory_engine.service import MemoryData, MemoryService, normalize_tags
from core.retrieval.semantic_search import semantic_search
from core.textutils import clean_content, content_hash

MAX_AUTO_RELATIONS = 5


@dataclass
class IngestionInput:
    content: str
    memory_type: str | None = None  # None = clasificar automáticamente
    kind: str | None = None
    title: str | None = None
    source_type: str = "manual"
    source_ref: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    project_id: uuid.UUID | None = None
    module: str | None = None
    tags: list[str] = field(default_factory=list)
    importance: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime | None = None
    #: Recuerdos existentes a los que esta información contradice o reemplaza.
    contradicts: list[uuid.UUID] = field(default_factory=list)
    supersedes: list[uuid.UUID] = field(default_factory=list)
    auto_tag: bool = True
    auto_relate: bool = True
    #: Guardar aunque exista un duplicado exacto.
    allow_duplicate: bool = False


@dataclass
class DetectedRelation:
    memory_id: uuid.UUID
    relation_type: str
    confidence: float | None
    origin: str


@dataclass
class IngestionResult:
    outcome: str  # "created" | "duplicate"
    memory: Memory
    duplicate_of: uuid.UUID | None = None
    relations: list[DetectedRelation] = field(default_factory=list)
    auto_tags: list[str] = field(default_factory=list)
    classification: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    steps: list[dict[str, str]] = field(default_factory=list)


class IngestionPipeline:
    def __init__(
        self,
        session: Session,
        embedder: EmbeddingProvider,
        settings: Settings | None = None,
        actor: str | None = None,
    ):
        self.session = session
        self.embedder = embedder
        self.settings = settings or get_settings()
        self.actor = actor
        self.memories = MemoryService(session, embedder, self.settings, actor)
        self.graph = KnowledgeGraph(session, actor)

    def ingest(self, item: IngestionInput) -> IngestionResult:
        steps: list[dict[str, str]] = []

        def step(name: str, detail: str) -> None:
            steps.append({"step": name, "detail": detail})

        # 1-2. Recibir y validar -------------------------------------------------
        content = clean_content(item.content or "")
        if not content:
            raise InvalidInputError("El contenido del recuerdo no puede estar vacío.")
        step("recibir", f"{len(content)} caracteres desde '{item.source_type}'")

        # 6a. Clasificar (necesario antes de validar el tipo) --------------------
        classification: dict[str, Any] = {}
        memory_type = item.memory_type
        if not memory_type:
            memory_type, rule = classifier.classify_type(
                content, source_type=item.source_type, has_project=item.project_id is not None
            )
            classification["memory_type"] = {"method": "rules", "rule": rule}
        kind = item.kind
        if not kind:
            detected = classifier.detect_kind(content)
            kind = detected or "note"
            if detected:
                classification["kind"] = {"method": "rules", "rule": "expresion_de_decision"}

        data = MemoryData(
            content=content,
            memory_type=memory_type,
            kind=kind,
            title=item.title,
            source_type=item.source_type,
            source_ref=item.source_ref,
            provenance=dict(item.provenance or {}),
            project_id=item.project_id,
            module=item.module,
            tags=list(item.tags or []),
            importance=item.importance,
            metadata=dict(item.metadata or {}),
            occurred_at=item.occurred_at,
        )
        data = self.memories.validate(data)
        for target in [*item.contradicts, *item.supersedes]:
            self.memories.get(target)  # 404 si no existe
        step("validar", f"tipo '{data.memory_type}', clase '{data.kind}'")

        # 3. Duplicados exactos --------------------------------------------------
        digest = content_hash(data.content)
        existing = self.memories.find_by_hash(digest)
        if existing is not None and not item.allow_duplicate:
            step("duplicados", f"contenido idéntico al recuerdo {existing.id}; no se duplica")
            return IngestionResult(
                outcome="duplicate",
                memory=existing,
                duplicate_of=existing.id,
                steps=steps,
                warnings=[
                    "Ya existía un recuerdo con el mismo contenido; no se creó uno nuevo. "
                    "Usa allow_duplicate=true si quieres guardarlo igualmente."
                ],
            )
        step("duplicados", "sin duplicado exacto")

        # 5. Embeddings ----------------------------------------------------------
        warnings: list[str] = []
        vectors: list[list[float]] | None
        try:
            vectors = embed_content(self.embedder, data.title, data.content, self.settings)
            step("embeddings", f"{len(vectors)} fragmento(s) con '{self.embedder.name}'")
        except EmbeddingError as exc:
            vectors = None
            step("embeddings", f"no disponibles: {exc}")

        # 4. Relaciones con recuerdos existentes ---------------------------------
        candidates: dict[uuid.UUID, float] = {}
        if vectors and item.auto_relate:
            for vector in vectors[:3]:
                for hit in semantic_search(
                    self.session,
                    self.embedder,
                    vector,
                    MemoryFilters(status="active"),
                    limit=MAX_AUTO_RELATIONS * 2,
                ):
                    if hit.similarity >= self.embedder.related_threshold:
                        candidates[hit.memory_id] = max(
                            candidates.get(hit.memory_id, 0.0), hit.similarity
                        )
        explicit = set(item.contradicts) | set(item.supersedes)
        ranked = sorted(
            ((mid, sim) for mid, sim in candidates.items() if mid not in explicit),
            key=lambda pair: pair[1],
            reverse=True,
        )[:MAX_AUTO_RELATIONS]
        step("relaciones", f"{len(ranked)} candidata(s) automáticas, {len(explicit)} explícita(s)")

        # 6b. Etiquetar ----------------------------------------------------------
        auto_tags: list[str] = []
        if item.auto_tag:
            suggestions = classifier.suggest_tags(
                data.content, data.title, classifier.known_tags(self.session)
            )
            auto_tags = [t for t in normalize_tags(suggestions) if t not in data.tags]
            data.tags = normalize_tags([*data.tags, *auto_tags])
        if auto_tags:
            data.metadata["auto_tags"] = auto_tags
        if classification:
            data.metadata["classification"] = classification
        step("clasificar", f"etiquetas automáticas: {', '.join(auto_tags) or 'ninguna'}")

        # 7-9. Guardar, registrar e indexar --------------------------------------
        memory = self.memories.create(data, validated=True, vectors=vectors)
        warnings.extend(self.memories.warnings)
        step("guardar", f"recuerdo {memory.id} versión 1")

        relations: list[DetectedRelation] = []
        for target_id, similarity in ranked:
            relation_type = (
                "possible_duplicate"
                if similarity >= self.embedder.duplicate_threshold
                else "related"
            )
            self.graph.relate(
                memory.id,
                target_id,
                relation_type,
                origin="auto",
                confidence=round(similarity, 4),
                log=False,
            )
            relations.append(DetectedRelation(target_id, relation_type, similarity, "auto"))
            if relation_type == "possible_duplicate":
                warnings.append(
                    f"Se parece mucho al recuerdo {target_id} "
                    f"(similitud {similarity:.2f}). Revisa si es un duplicado."
                )
        for relation_type, targets in (
            ("contradicts", item.contradicts),
            ("supersedes", item.supersedes),
        ):
            for target_id in dict.fromkeys(targets):
                self.graph.relate(
                    memory.id,
                    target_id,
                    relation_type,
                    origin="manual",
                    note="Indicada al incorporar el recuerdo; se conservan ambas versiones.",
                )
                relations.append(DetectedRelation(target_id, relation_type, None, "manual"))
        step("registrar", "versión, historial de cambios e índices actualizados")
        self.session.flush()

        return IngestionResult(
            outcome="created",
            memory=memory,
            relations=relations,
            auto_tags=auto_tags,
            classification=classification,
            warnings=warnings,
            steps=steps,
        )
