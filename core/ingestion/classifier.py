"""Clasificación y etiquetado por reglas transparentes (sin modelos).

Cada decisión automática queda anotada en los metadatos del recuerdo para que
se sepa qué puso la persona y qué dedujo el sistema.
"""

from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database.models import Memory
from core.textutils import normalize, tokenize

_PREFERENCE_RE = re.compile(
    r"\b(prefiero|preferimos|me gusta|no me gusta|siempre uso|suelo usar|mi preferencia|"
    r"i prefer|i like|i always use)\b"
)
_EPISODIC_RE = re.compile(
    r"\b(hoy|ayer|anoche|esta manana|esta tarde|la semana pasada|reunion|me reuni|hable con|"
    r"conversacion con|llamada con|today|yesterday|meeting|last week)\b"
)
_DECISION_RE = re.compile(
    r"\b(decidi|decidimos|decision|se decidio|acordamos|se acordo|optamos por|elegimos|"
    r"decided|we agreed)\b"
)


def classify_type(content: str, *, source_type: str, has_project: bool) -> tuple[str, str]:
    """Devuelve ``(tipo, regla_aplicada)``."""
    text = normalize(content[:5000])
    if source_type == "conversation":
        return "episodic", "source_type=conversation"
    if source_type == "document":
        return "document", "source_type=document"
    if _PREFERENCE_RE.search(text):
        return "preference", "expresion_de_preferencia"
    if _DECISION_RE.search(text) and has_project:
        return "project", "decision_en_proyecto"
    if _EPISODIC_RE.search(text):
        return "episodic", "referencia_temporal_o_encuentro"
    if has_project:
        return "project", "asociado_a_proyecto"
    return "semantic", "por_defecto"


def detect_kind(content: str) -> str | None:
    if _DECISION_RE.search(normalize(content[:5000])):
        return "decision"
    return None


def known_tags(session: Session, limit: int = 500) -> list[str]:
    tag = func.unnest(Memory.tags).label("tag")
    subquery = select(tag).subquery()
    stmt = (
        select(subquery.c.tag, func.count().label("uses"))
        .group_by(subquery.c.tag)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [row[0] for row in session.execute(stmt)]


def suggest_tags(
    content: str, title: str | None, existing_tags: list[str], *, max_tags: int = 5
) -> list[str]:
    """Etiquetas ya usadas que aparecen en el texto y palabras muy repetidas."""
    text = normalize(f"{title or ''} {content[:20000]}")
    suggestions: list[str] = []
    for tag in existing_tags:
        normalized = normalize(tag)
        if len(normalized) >= 3 and re.search(rf"\b{re.escape(normalized)}\b", text):
            suggestions.append(tag)
        if len(suggestions) >= max_tags:
            return suggestions
    counts = Counter(t for t in tokenize(text) if len(t) >= 5 and not t.isdigit())
    for token, count in counts.most_common(10):
        if count < 3 or len(suggestions) >= max_tags:
            break
        if token not in suggestions:
            suggestions.append(token)
    return suggestions
