"""Resumen extractivo: selecciona oraciones textuales, nunca redacta contenido nuevo."""

from __future__ import annotations

from core.textutils import excerpt, split_sentences, stem, tokenize


def _stems(text: str) -> set[str]:
    return {stem(t) for t in tokenize(text)}


def best_sentences(
    text: str, query_terms: list[str], *, max_sentences: int = 2, max_chars: int = 400
) -> str:
    """Oraciones del texto que mejor responden a los términos, en su orden original.

    Si ninguna oración comparte términos con la consulta, devuelve el inicio del
    texto. El resultado siempre es una cita literal (recortada si es muy larga).
    """
    sentences = split_sentences(text)
    if not sentences:
        return ""
    wanted = {stem(t) for t in query_terms}
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        overlap = len(wanted & _stems(sentence)) if wanted else 0
        scored.append((overlap, index, sentence))
    if not wanted or max(s[0] for s in scored) == 0:
        return excerpt(" ".join(sentences[:max_sentences]), max_chars)
    chosen = sorted(scored, key=lambda s: (-s[0], s[1]))[:max_sentences]
    chosen = [s for s in chosen if s[0] > 0]
    chosen.sort(key=lambda s: s[1])
    return excerpt(" ".join(s[2] for s in chosen), max_chars)


def summarize(text: str, *, max_sentences: int = 3, max_chars: int = 600) -> str:
    """Resumen sin consulta: oraciones con más términos frecuentes del propio texto."""
    sentences = split_sentences(text)
    if len(sentences) <= max_sentences:
        return excerpt(text, max_chars)
    frequency: dict[str, int] = {}
    for token in tokenize(text):
        key = stem(token)
        frequency[key] = frequency.get(key, 0) + 1
    scored = []
    for index, sentence in enumerate(sentences):
        stems = _stems(sentence)
        if not stems:
            continue
        score = sum(frequency.get(s, 0) for s in stems) / (len(stems) ** 0.5)
        scored.append((score, index, sentence))
    chosen = sorted(scored, key=lambda s: -s[0])[:max_sentences]
    chosen.sort(key=lambda s: s[1])
    return excerpt(" ".join(s[2] for s in chosen), max_chars)
