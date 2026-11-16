"""Respuestas a preguntas en lenguaje natural con fuentes.

Cada respuesta separa tres cosas:

* ``confirmed``  : afirmaciones respaldadas literalmente por una fuente guardada.
* ``inferences`` : deducciones del sistema (o del modelo), con la base que las sustenta.
* ``not_found``  : lo que se pidió y no está en la memoria.

Sin modelo de lenguaje configurado la respuesta es extractiva: solo citas
textuales. Con modelo, este redacta usando únicamente las fuentes numeradas y
se descarta cualquier afirmación que no cite una fuente válida.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from core.database.models import ChangeLog, Memory, MemoryRelation, Project, ProjectRelation
from core.embeddings.base import EmbeddingProvider
from core.llm.client import LLMClient, LLMError
from core.memory_engine.filters import MemoryFilters
from core.module_system.registry import registry
from core.retrieval.engine import HybridRetriever, SearchResult
from core.retrieval.query_analysis import QueryAnalysis, analyze
from core.summarization.extractive import best_sentences
from core.textutils import excerpt

logger = logging.getLogger("nmc.answer")

SYSTEM_PROMPT = """Eres el motor de respuestas de una memoria personal.
Responde SOLO con la información de las FUENTES numeradas. No uses conocimiento externo.
Devuelve exclusivamente un objeto JSON con esta forma:
{"answer": "respuesta breve en el idioma de la pregunta, citando fuentes como [1]",
 "confirmed": [{"text": "hecho que una fuente afirma explícitamente", "sources": [1]}],
 "inferences": [{"text": "deducción que ninguna fuente afirma tal cual", "sources": [1, 2]}],
 "not_found": ["parte de la pregunta que las fuentes no responden"]}
Reglas: cada elemento de confirmed e inferences debe citar al menos una fuente existente.
Si las fuentes no responden la pregunta, dilo en not_found y no inventes nada."""


@dataclass
class Source:
    index: int
    source_kind: str  # memory | project | project_relation | change_log | task | ...
    id: str
    label: str
    excerpt: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "source_kind": self.source_kind,
            "id": self.id,
            "label": self.label,
            "excerpt": self.excerpt,
            **self.details,
        }


@dataclass
class Answer:
    question: str
    answer: str
    answer_mode: str  # extractive | llm
    confirmed: list[dict[str, Any]]
    inferences: list[dict[str, Any]]
    not_found: list[str]
    sources: list[dict[str, Any]]
    interpretation: dict[str, Any]
    warnings: list[str]


class AnswerEngine:
    def __init__(
        self,
        session: Session,
        embedder: EmbeddingProvider,
        llm: LLMClient | None = None,
    ):
        self.session = session
        self.embedder = embedder
        self.llm = llm
        self.retriever = HybridRetriever(session, embedder)

    # ------------------------------------------------------------------ público
    def ask(
        self,
        question: str,
        filters: MemoryFilters | None = None,
        *,
        limit: int = 8,
        use_llm: bool = True,
    ) -> Answer:
        question = question.strip()
        analysis = analyze(self.session, question)
        filters = filters or MemoryFilters()
        sources: list[Source] = []
        confirmed: list[dict[str, Any]] = []
        inferences: list[dict[str, Any]] = []
        not_found: list[str] = []
        warnings: list[str] = []

        def add_source(source_kind: str, id_: Any, label: str, text: str = "", /, **details):
            for existing in sources:
                if existing.source_kind == source_kind and existing.id == str(id_):
                    return existing
            source = Source(len(sources) + 1, source_kind, str(id_), label, text, details)
            sources.append(source)
            return source

        # --- Proyecto de referencia -------------------------------------------
        if analysis.has("latest_project"):
            latest = self._latest_project()
            if latest is None:
                not_found.append("No hay proyectos registrados.")
            else:
                project, moment = latest
                analysis.projects = [project]
                analysis.project_resolution = "proyecto con actividad más reciente"
                src = add_source(
                    "project", project.id, project.name, excerpt(project.description, 200)
                )
                inferences.append(
                    {
                        "text": f"Interpreté «último proyecto» como «{project.name}» porque es el "
                        f"que tiene la actividad más reciente ({moment:%Y-%m-%d %H:%M} UTC).",
                        "sources": [src.index],
                    }
                )
        if not filters.project_ids and analysis.projects and not analysis.has("project_relation"):
            filters.project_ids = analysis.project_ids
        for project in analysis.projects:
            if analysis.has("project_relation"):
                continue
            src = add_source("project", project.id, project.name, excerpt(project.description, 200))
            if project.description:
                confirmed.append(
                    {
                        "text": f"Proyecto «{project.name}» ({project.status}): "
                        f"{excerpt(project.description, 300)}",
                        "sources": [src.index],
                    }
                )
            if project.objectives and not analysis.terms:
                confirmed.append(
                    {
                        "text": f"Objetivos de «{project.name}»: " + "; ".join(project.objectives),
                        "sources": [src.index],
                    }
                )

        # --- Relación entre proyectos -----------------------------------------
        if analysis.has("project_relation"):
            self._project_relation(analysis, add_source, confirmed, inferences, not_found)

        # --- Últimos cambios ---------------------------------------------------
        if analysis.has("changes"):
            self._changes(analysis, filters, add_source, confirmed, not_found, limit)

        # --- Aportes de los módulos (p. ej. tareas) ---------------------------
        for module in registry.all():
            try:
                for fact in module.contribute_to_answer(self.session, analysis, filters):
                    src = add_source(
                        fact["source_kind"], fact["id"], fact["label"], fact.get("excerpt", "")
                    )
                    confirmed.append({"text": fact["text"], "sources": [src.index]})
            except Exception:  # noqa: BLE001
                logger.exception("El módulo %s falló al aportar contexto", module.manifest.name)

        # --- Recuerdos ---------------------------------------------------------
        skip_memories = analysis.has("project_relation") or (
            analysis.has("changes") and not analysis.terms and not analysis.kinds
        )
        if not skip_memories:
            if analysis.kinds and not filters.kinds:
                filters.kinds = list(analysis.kinds)
            if analysis.memory_types and not filters.memory_types:
                filters.memory_types = list(analysis.memory_types)
            results, search_warnings = self._retrieve(analysis, filters, limit)
            warnings.extend(search_warnings)
            for result in results:
                memory = result.memory
                quote = best_sentences(memory.content, analysis.terms)
                src = add_source(
                    "memory",
                    memory.id,
                    memory.title or excerpt(memory.content, 70),
                    quote,
                    **memory_source_details(result),
                )
                if result.via_relation:
                    parent = next(
                        (
                            s
                            for s in sources
                            if s.id == result.via_relation["from_memory_id"]
                            and s.source_kind == "memory"
                        ),
                        None,
                    )
                    basis = [src.index] + ([parent.index] if parent else [])
                    inferences.append(
                        {
                            "text": "Podría ser relevante por su relación "
                            f"«{result.via_relation['relation_type']}» "
                            f"({result.via_relation['origin']}) con otra fuente: {quote}",
                            "sources": basis,
                        }
                    )
                else:
                    confirmed.append({"text": quote, "sources": [src.index]})
            if not results:
                scope = self._scope_text(analysis, filters)
                subject = ", ".join(analysis.terms) if analysis.terms else "esa consulta"
                not_found.append(f"No encontré recuerdos sobre «{subject}»{scope}.")

        interpretation = analysis.describe()
        interpretation["filters"] = filters.describe()
        answer_text = self._compose(confirmed, inferences, not_found)
        answer = Answer(
            question=question,
            answer=answer_text,
            answer_mode="extractive",
            confirmed=confirmed,
            inferences=inferences,
            not_found=not_found,
            sources=[s.to_dict() for s in sources],
            interpretation=interpretation,
            warnings=warnings,
        )
        if use_llm and self.llm is not None and sources:
            self._apply_llm(answer, sources)
        return answer

    # ----------------------------------------------------------------- recuperar
    def _retrieve(
        self, analysis: QueryAnalysis, filters: MemoryFilters, limit: int
    ) -> tuple[list[SearchResult], list[str]]:
        recent = analysis.has("recent") or analysis.has("latest_project")
        if analysis.terms:
            query = analysis.question if self.embedder.semantic else " ".join(analysis.terms)
            response = self.retriever.search(
                query,
                filters,
                limit=limit,
                recency_weight=0.4 if recent else 0.08,
                fts_terms=analysis.fts_terms,
            )
            return response.results, response.warnings
        has_scope = bool(
            filters.project_ids or filters.kinds or filters.memory_types or filters.tags or recent
        )
        if not has_scope and not analysis.has("conversations"):
            return [], []
        if analysis.has("conversations") and not filters.kinds:
            filters.kinds = ["conversation"]
        # Pregunta estructural (sin tema): se listan los más recientes que cumplen el filtro.
        stmt = filters.apply(select(Memory)).order_by(Memory.updated_at.desc()).limit(limit)
        return [
            SearchResult(memory=m, score=0.0, matched_by=["filter"], excerpt=excerpt(m.content))
            for m in self.session.scalars(stmt)
        ], []

    def _latest_project(self):
        activity = (
            select(Memory.project_id, func.max(Memory.updated_at).label("last"))
            .where(Memory.project_id.is_not(None))
            .group_by(Memory.project_id)
            .subquery()
        )
        moment = func.greatest(
            Project.updated_at, func.coalesce(activity.c.last, Project.updated_at)
        )
        row = self.session.execute(
            select(Project, moment)
            .outerjoin(activity, activity.c.project_id == Project.id)
            .order_by(moment.desc())
            .limit(1)
        ).first()
        return (row[0], row[1]) if row else None

    def _scope_text(self, analysis: QueryAnalysis, filters: MemoryFilters) -> str:
        parts = []
        if analysis.projects and filters.project_ids:
            parts.append("en el proyecto «" + "», «".join(p.name for p in analysis.projects) + "»")
        if filters.kinds:
            parts.append("de clase " + ", ".join(filters.kinds))
        if filters.memory_types:
            parts.append("de tipo " + ", ".join(filters.memory_types))
        return (" " + " ".join(parts)) if parts else ""

    # ------------------------------------------------------- relación de proyectos
    def _project_relation(self, analysis, add_source, confirmed, inferences, not_found) -> None:
        if len(analysis.projects) < 2:
            names = ", ".join(p.name for p in analysis.projects) or "ninguno"
            not_found.append(
                "Para relacionar proyectos necesito identificar dos por su nombre; "
                f"en la pregunta reconocí: {names}."
            )
            return
        a, b = analysis.projects[0], analysis.projects[1]
        src_a = add_source("project", a.id, a.name, excerpt(a.description, 200))
        src_b = add_source("project", b.id, b.name, excerpt(b.description, 200))
        found = False

        explicit = self.session.scalars(
            select(ProjectRelation).where(
                or_(
                    (ProjectRelation.source_project_id == a.id)
                    & (ProjectRelation.target_project_id == b.id),
                    (ProjectRelation.source_project_id == b.id)
                    & (ProjectRelation.target_project_id == a.id),
                )
            )
        )
        for relation in explicit:
            found = True
            origin, target = (a, b) if relation.source_project_id == a.id else (b, a)
            src = add_source(
                "project_relation",
                relation.id,
                f"{origin.name} → {target.name}",
                relation.description,
                relation_type=relation.relation_type,
            )
            text = f"Relación registrada «{relation.relation_type}»: {origin.name} → {target.name}."
            if relation.description:
                text += f" {relation.description}"
            confirmed.append({"text": text, "sources": [src.index, src_a.index, src_b.index]})

        ma, mb = Memory.__table__.alias("ma"), Memory.__table__.alias("mb")
        cross = self.session.execute(
            select(MemoryRelation, ma.c.id, mb.c.id)
            .join(ma, ma.c.id == MemoryRelation.source_id)
            .join(mb, mb.c.id == MemoryRelation.target_id)
            .where(
                or_(
                    (ma.c.project_id == a.id) & (mb.c.project_id == b.id),
                    (ma.c.project_id == b.id) & (mb.c.project_id == a.id),
                )
            )
            .limit(10)
        ).all()
        for relation, source_id, target_id in cross:
            found = True
            first = self.session.get(Memory, source_id)
            second = self.session.get(Memory, target_id)
            s1 = add_source(
                "memory",
                first.id,
                first.title or excerpt(first.content, 70),
                excerpt(first.content, 240),
                **memory_details(first),
            )
            s2 = add_source(
                "memory",
                second.id,
                second.title or excerpt(second.content, 70),
                excerpt(second.content, 240),
                **memory_details(second),
            )
            entry = {
                "text": f"Hay recuerdos de ambos proyectos enlazados por una relación "
                f"«{relation.relation_type}» ({relation.origin}).",
                "sources": [s1.index, s2.index],
            }
            (confirmed if relation.origin == "manual" else inferences).append(entry)

        tags_a = self._project_tags(a.id)
        tags_b = self._project_tags(b.id)
        shared = sorted(tags_a & tags_b)
        if shared:
            found = True
            inferences.append(
                {
                    "text": "Ambos proyectos comparten etiquetas en sus recuerdos: "
                    + ", ".join(shared[:15])
                    + ". Es una coincidencia temática, no una relación registrada.",
                    "sources": [src_a.index, src_b.index],
                }
            )
        if not found:
            not_found.append(
                f"No hay relaciones registradas ni coincidencias entre «{a.name}» y «{b.name}»."
            )

    def _project_tags(self, project_id) -> set[str]:
        tag = func.unnest(Memory.tags)
        return set(
            self.session.scalars(
                select(tag).where(Memory.project_id == project_id, Memory.status == "active")
            )
        )

    # ------------------------------------------------------------------- cambios
    def _changes(self, analysis, filters, add_source, confirmed, not_found, limit) -> None:
        stmt = select(ChangeLog).order_by(ChangeLog.created_at.desc(), ChangeLog.id.desc())
        project_ids = filters.project_ids or analysis.project_ids
        if project_ids:
            stmt = stmt.where(ChangeLog.project_id.in_(project_ids))
        entries = list(self.session.scalars(stmt.limit(limit)))
        if not entries:
            not_found.append("No hay cambios registrados para esa consulta.")
            return
        for entry in entries:
            src = add_source(
                "change_log",
                entry.id,
                f"{entry.action} · {entry.entity_type}",
                entry.summary,
                created_at=entry.created_at.isoformat(),
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                actor=entry.actor,
            )
            confirmed.append(
                {
                    "text": f"{entry.created_at:%Y-%m-%d %H:%M} UTC — {entry.summary}",
                    "sources": [src.index],
                }
            )

    # -------------------------------------------------------------- composición
    @staticmethod
    def _compose(confirmed, inferences, not_found) -> str:
        lines: list[str] = []
        if confirmed:
            lines.append("Información confirmada en tu memoria:")
            for item in confirmed:
                refs = "".join(f"[{i}]" for i in item["sources"])
                lines.append(f"- {item['text']} {refs}")
        if inferences:
            lines.append("")
            lines.append("Inferencias (no afirmadas literalmente por ninguna fuente):")
            for item in inferences:
                refs = "".join(f"[{i}]" for i in item["sources"])
                lines.append(f"- {item['text']} {refs}")
        if not_found:
            lines.append("")
            lines.append("No encontrado:")
            lines.extend(f"- {text}" for text in not_found)
        return (
            "\n".join(lines).strip() or "No encontré información en tu memoria para esa pregunta."
        )

    # ----------------------------------------------------------------------- LLM
    def _apply_llm(self, answer: Answer, sources: list[Source]) -> None:
        context = "\n\n".join(
            f"[{s.index}] ({s.source_kind}) {s.label}\n{s.excerpt or s.label}" for s in sources
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"FUENTES:\n{context}\n\nPREGUNTA: {answer.question}"},
        ]
        try:
            raw = self.llm.chat(messages)
            parsed = parse_llm_json(raw)
        except (LLMError, ValueError) as exc:
            answer.warnings.append(
                f"No se pudo usar el modelo de lenguaje ({exc}); se muestra la respuesta "
                "extractiva."
            )
            return
        valid = {s.index for s in sources}

        def clean(items: Any) -> tuple[list[dict[str, Any]], int]:
            kept, dropped = [], 0
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    dropped += 1
                    continue
                cited = [i for i in item.get("sources", []) if isinstance(i, int) and i in valid]
                text = str(item.get("text", "")).strip()
                if text and cited:
                    kept.append({"text": text, "sources": cited})
                else:
                    dropped += 1
            return kept, dropped

        llm_confirmed, dropped_a = clean(parsed.get("confirmed"))
        llm_inferences, dropped_b = clean(parsed.get("inferences"))
        text = str(parsed.get("answer", "")).strip()
        if not text:
            answer.warnings.append("El modelo no devolvió una respuesta; se muestra la extractiva.")
            return
        cited_in_text = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
        if cited_in_text - valid:
            answer.warnings.append(
                "El modelo citó fuentes inexistentes; se muestra la respuesta extractiva."
            )
            return
        if dropped_a or dropped_b:
            answer.warnings.append(
                f"Se descartaron {dropped_a + dropped_b} afirmaciones del modelo sin fuente válida."
            )
        answer.answer = text
        answer.answer_mode = "llm"
        answer.confirmed = llm_confirmed or answer.confirmed
        answer.inferences = [*answer.inferences, *llm_inferences]
        extra = [str(x) for x in parsed.get("not_found", []) if str(x).strip()]
        answer.not_found = list(dict.fromkeys([*answer.not_found, *extra]))


def parse_llm_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("el modelo no devolvió JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("el JSON del modelo no es un objeto")
    return data


def memory_details(memory: Memory) -> dict[str, Any]:
    return {
        "memory_type": memory.memory_type,
        "kind": memory.kind,
        "project_id": str(memory.project_id) if memory.project_id else None,
        "source_type": memory.source_type,
        "source_ref": memory.source_ref,
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
        "version": memory.version,
    }


def memory_source_details(result: SearchResult) -> dict[str, Any]:
    return {
        **memory_details(result.memory),
        "score": result.score,
        "matched_by": result.matched_by,
        "semantic_similarity": result.semantic_similarity,
        "text_rank": result.text_rank,
    }
