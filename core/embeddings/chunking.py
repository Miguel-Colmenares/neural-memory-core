"""División de textos largos en fragmentos para generar embeddings."""

from __future__ import annotations

import re

_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")


def _split_long(piece: str, max_chars: int) -> list[str]:
    """Parte un bloque que excede el máximo, primero por oraciones y luego por palabras."""
    parts: list[str] = []
    current = ""
    for sentence in _SENTENCE_END_RE.split(piece):
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            head, sentence = sentence[:cut], sentence[cut:].lstrip()
            if current:
                parts.append(current)
                current = ""
            parts.append(head)
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                parts.append(current)
            current = sentence
    if current:
        parts.append(current)
    return parts


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Devuelve fragmentos de como máximo ``max_chars`` respetando párrafos y oraciones.

    Cada fragmento (salvo el primero) empieza con la cola del anterior para no
    perder contexto en los cortes.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    overlap = min(overlap, max_chars // 2)
    budget = max_chars - overlap - 1
    blocks: list[str] = []
    for paragraph in _PARAGRAPH_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= budget:
            blocks.append(paragraph)
        else:
            blocks.extend(_split_long(paragraph, budget))

    chunks: list[str] = []
    current = ""
    for block in blocks:
        if current and len(current) + len(block) + 2 > budget:
            chunks.append(current)
            current = block
        else:
            current = f"{current}\n\n{block}".strip()
    if current:
        chunks.append(current)

    if overlap <= 0:
        return chunks
    with_overlap = [chunks[0]]
    for previous, chunk in zip(chunks, chunks[1:], strict=False):
        tail = previous[-overlap:]
        if " " in tail:
            tail = tail[tail.index(" ") + 1 :]
        with_overlap.append(f"{tail} {chunk}".strip())
    return with_overlap
