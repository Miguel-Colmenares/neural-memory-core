"""Interpretación de preguntas en lenguaje natural mediante reglas explícitas.

No hay un modelo adivinando: cada intención detectada corresponde a un patrón
documentado y se devuelve en la respuesta para que el usuario vea cómo se
interpretó su pregunta.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import Project
from core.textutils import STOPWORDS, normalize

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Palabras propias de formular la pregunta, no del tema buscado.
QUESTION_FILLER = frozenset(
    """
    que cual cuales como cuando donde quien por porque dime muestrame mostrar muestra dame
    lista listar ensename busca buscar encuentra informacion datos tengo tenia tenemos hay
    habia hablado hable dicho dije anteriormente antes previamente estaba estuve desarrollando
    haciendo trabajando realizado realizados realizadas hecho hechos tomado tomadas tome
    determinado determinada cierto cierta tema temas idea sobre acerca respecto existe existen
    relacion relaciones relacionado relacionados entre estos estas mi mis mio proyecto proyectos
    what which tell show give list find information have had about there exist know
    """.split()
)

_RECENCY_RE = re.compile(
    r"\b(ultim[oa]s?|recientes?|recientemente|mas nuev[oa]s?|latest|last|recent|recently|newest)\b"
)
_CHANGES_RE = re.compile(
    r"\b(cambios?|actualizacion(es)?|modificacion(es)?|novedades|changes?|updates?)\b"
)
_DECISION_RE = re.compile(r"\b(decision(es)?|decidi|decidimos|acuerdos?|decisions?|decided)\b")
_TASK_RE = re.compile(r"\b(tareas?|pendientes?|por hacer|tasks?|to-?dos?)\b")
_PREFERENCE_RE = re.compile(r"\b(preferencias?|prefiero|preferences?)\b")
_RELATION_RE = re.compile(r"\b(relacion(es)?|relacionad[oa]s?|vinculos?|conexion(es)?|related)\b")
_PROJECT_WORD_RE = re.compile(r"\b(proyectos?|projects?)\b")
_DOCUMENT_RE = re.compile(r"\b(documentos?|archivos?|documents?|files?)\b")
_CONVERSATION_RE = re.compile(
    r"\b(conversacion(es)?|hablado|hable|hablamos|charla|conversations?|talked|discussed)\b"
)

_INTENT_WORDS = frozenset(
    """
    ultimo ultima ultimos ultimas reciente recientes recientemente latest last recent recently
    cambio cambios actualizacion actualizaciones modificacion modificaciones novedades changes
    decision decisiones decisions tarea tareas pendiente pendientes tasks preferencia
    preferencias preferences documento documentos archivo archivos conversacion conversaciones
    """.split()
)


@dataclass
class QueryAnalysis:
    question: str
    intents: list[str] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    project_resolution: str | None = None  # cómo se identificó el proyecto
    kinds: list[str] = field(default_factory=list)
    memory_types: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)  # normalizados, para mostrar
    fts_terms: list[str] = field(default_factory=list)  # con acentos, para PostgreSQL
    notes: list[str] = field(default_factory=list)

    @property
    def project_ids(self) -> list[uuid.UUID]:
        return [p.id for p in self.projects]

    def has(self, intent: str) -> bool:
        return intent in self.intents

    def describe(self) -> dict:
        return {
            "intents": self.intents,
            "projects": [{"id": str(p.id), "name": p.name} for p in self.projects],
            "project_resolution": self.project_resolution,
            "kinds": self.kinds,
            "memory_types": self.memory_types,
            "search_terms": self.terms,
            "notes": self.notes,
        }


def _mentioned_projects(text: str, projects: list[Project]) -> list[Project]:
    found: list[tuple[int, Project]] = []
    for project in projects:
        for candidate in {normalize(project.name), project.slug.replace("-", " ")}:
            if len(candidate) < 3:
                continue
            match = re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", text)
            if match:
                found.append((match.start(), project))
                break
    found.sort(key=lambda pair: pair[0])
    return [p for _, p in found]


def analyze(session: Session, question: str) -> QueryAnalysis:
    analysis = QueryAnalysis(question=question)
    text = normalize(question)

    all_projects = list(session.scalars(select(Project)))
    analysis.projects = _mentioned_projects(text, all_projects)
    if analysis.projects:
        analysis.project_resolution = "nombre mencionado en la pregunta"

    recency = bool(_RECENCY_RE.search(text))
    if recency:
        analysis.intents.append("recent")
    if _CHANGES_RE.search(text):
        analysis.intents.append("changes")
    if _DECISION_RE.search(text):
        analysis.intents.append("decisions")
        analysis.kinds.append("decision")
    if _TASK_RE.search(text):
        analysis.intents.append("tasks")
    if _PREFERENCE_RE.search(text):
        analysis.intents.append("preferences")
        analysis.memory_types.append("preference")
    if _DOCUMENT_RE.search(text):
        analysis.intents.append("documents")
        analysis.memory_types.append("document")
    if _CONVERSATION_RE.search(text):
        analysis.intents.append("conversations")
    if _RELATION_RE.search(text) and (_PROJECT_WORD_RE.search(text) or len(analysis.projects) >= 2):
        analysis.intents.append("project_relation")

    # "mi último proyecto": el de actividad más reciente.
    if not analysis.projects and recency and _PROJECT_WORD_RE.search(text):
        analysis.intents.append("latest_project")

    # Términos de búsqueda: lo que queda al quitar relleno, intención y nombres de proyecto.
    project_words: set[str] = set()
    for project in analysis.projects:
        project_words.update(_WORD_RE.findall(normalize(project.name)))
        project_words.update(project.slug.split("-"))
    seen: set[str] = set()
    for raw in _WORD_RE.findall(question.lower()):
        token = normalize(raw)
        if (
            len(token) < 2
            or token in STOPWORDS
            or token in QUESTION_FILLER
            or token in _INTENT_WORDS
            or token in project_words
            or token in seen
        ):
            continue
        seen.add(token)
        analysis.terms.append(token)
        analysis.fts_terms.append(raw)
    return analysis
