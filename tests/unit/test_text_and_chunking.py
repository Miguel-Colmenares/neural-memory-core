from core.embeddings.chunking import chunk_text
from core.summarization.extractive import best_sentences, summarize
from core.textutils import (
    clean_content,
    content_hash,
    excerpt,
    normalize,
    slugify,
    split_sentences,
    stem,
    tokenize,
)


def test_normalize_strips_accents_and_case():
    assert normalize("Decisión ÚLTIMA") == "decision ultima"


def test_tokenize_drops_stopwords():
    assert tokenize("¿Qué decisiones había tomado sobre la base de datos?") == [
        "decisiones",
        "tomado",
        "base",
        "datos",
    ]


def test_stem_unifies_plurals():
    assert stem("decisiones") == stem("decision")
    assert stem("proyectos") == stem("proyecto")


def test_content_hash_ignores_spacing_and_case():
    assert content_hash("Hola   Mundo\n") == content_hash("hola mundo")
    assert content_hash("hola mundo") != content_hash("hola mundos")


def test_clean_content_keeps_text():
    assert clean_content("  línea 1  \r\n\r\n\r\n\r\nlínea 2\x00 ") == "línea 1\n\nlínea 2"


def test_slugify():
    assert slugify("Neural Memory Core: versión 2!") == "neural-memory-core-version-2"
    assert slugify("¿¡!?") == "item"


def test_excerpt_cuts_on_word_boundary():
    text = "palabra " * 100
    result = excerpt(text, 50)
    assert len(result) <= 51 and result.endswith("…")


def test_split_sentences():
    assert split_sentences("Uno. Dos! ¿Tres?\nCuatro") == ["Uno.", "Dos!", "¿Tres?", "Cuatro"]


def test_chunk_short_text_is_single_chunk():
    assert chunk_text("texto corto", 100, 10) == ["texto corto"]
    assert chunk_text("   ", 100, 10) == []


def test_chunks_respect_limit_and_cover_content():
    paragraphs = [f"Párrafo {i}. " + "contenido relevante " * 20 for i in range(12)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, 600, 80)
    assert len(chunks) > 3
    assert all(len(c) <= 600 for c in chunks)
    joined = " ".join(chunks)
    for i in range(12):
        assert f"Párrafo {i}." in joined


def test_chunk_splits_very_long_sentence():
    chunks = chunk_text("x" * 5000, 500, 50)
    assert all(len(c) <= 500 for c in chunks)
    assert sum(len(c) for c in chunks) >= 5000


def test_best_sentences_are_literal_quotes():
    text = "El cielo es azul. Decidimos usar PostgreSQL. Mañana lloverá."
    quote = best_sentences(text, ["postgresql"])
    assert quote == "Decidimos usar PostgreSQL."
    assert quote in text


def test_best_sentences_falls_back_to_start():
    assert best_sentences("Primera. Segunda. Tercera.", ["inexistente"], max_sentences=1) == (
        "Primera."
    )


def test_summarize_only_uses_original_sentences():
    text = (
        "PostgreSQL guarda los datos. El gato duerme. PostgreSQL usa pgvector para vectores. "
        "Los datos de PostgreSQL persisten. Hace sol."
    )
    summary = summarize(text, max_sentences=2)
    for sentence in split_sentences(summary):
        assert sentence in text
