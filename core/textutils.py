"""Utilidades de texto compartidas (normalización, tokens, oraciones)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+|\n+")

# Palabras vacías en español e inglés. Lista corta y explícita a propósito.
STOPWORDS = frozenset(
    """
    a al algo ante antes aquel aquella como con contra cual cuales cuando de del desde donde
    dos el ella ellas ellos en entre era eran es esa esas ese eso esos esta estaba estaban
    estan estar estas este esto estos fue fueron ha habia han hasta hay he la las le les lo
    los mas me mi mis muy ni no nos o os otra otro para pero por que quien se sea ser si sin
    sobre son su sus te tiene tienen todo todos tu tus un una unas uno unos y ya yo
    the of and to in is it that for on with as was were be by at an or from this these those
    are have has had not but what which who when where how do does did i you he she we they
    my your our their its been can could would should will about into than then there
    """.split()
)


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def normalize(text: str) -> str:
    """Minúsculas y sin acentos; para comparar, nunca para almacenar."""
    return strip_accents(text).lower()


def tokenize(text: str, *, drop_stopwords: bool = True) -> list[str]:
    tokens = _WORD_RE.findall(normalize(text))
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    return tokens


def stem(token: str) -> str:
    """Raíz ligera (plurales y sufijos frecuentes en español/inglés)."""
    for suffix in ("aciones", "iciones", "amente", "mente", "acion", "icion", "ando", "iendo"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    # Plurales: consonante + "es" (decisiones, papeles) o vocal + "s" (bases, proyectos).
    if token.endswith("es") and len(token) >= 5 and token[-3] in "dlnrjyc":
        return token[:-2]
    if token.endswith("s") and len(token) >= 4 and not token.endswith("ss"):
        return token[:-1]
    return token


def clean_content(text: str) -> str:
    """Normaliza saltos de línea y espacios sobrantes sin alterar el contenido."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    """Huella para detectar duplicados exactos (insensible a espacios y mayúsculas)."""
    canonical = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s and s.strip()]


def slugify(text: str, max_length: int = 100) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize(text)).strip("-")
    return slug[:max_length].strip("-") or "item"


def excerpt(text: str, max_chars: int = 320) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    if " " in cut[max_chars // 2 :]:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(",;: ") + "…"
