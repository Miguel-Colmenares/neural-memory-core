"""Extracción de texto de archivos subidos. Sin OCR ni conversiones inventadas."""

from __future__ import annotations

import io
from pathlib import PurePath

from core.errors import InvalidInputError

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml", ".log",
    ".html", ".htm", ".xml", ".py", ".js", ".ts", ".sql", ".tex",
}  # fmt: skip
SUPPORTED = sorted(TEXT_EXTENSIONS | {".pdf"})


def extract_text(filename: str, data: bytes) -> tuple[str, dict]:
    """Devuelve ``(texto, detalles)``. Lanza error si el formato no es legible."""
    extension = PurePath(filename).suffix.lower()
    if extension == ".pdf":
        return _pdf(data)
    if extension in TEXT_EXTENSIONS or not extension:
        return _plain(data), {"extraction": "texto plano"}
    raise InvalidInputError(
        f"Formato '{extension}' no admitido. Formatos admitidos: {', '.join(SUPPORTED)}."
    )


def _plain(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" not in text:
            return text
    raise InvalidInputError("No se pudo leer el archivo como texto.")


def _pdf(data: bytes) -> tuple[str, dict]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise InvalidInputError("El PDF está protegido con contraseña.")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except PyPdfError as exc:
        raise InvalidInputError(f"No se pudo leer el PDF: {exc}") from exc
    text = "\n\n".join(p for p in pages if p)
    if not text.strip():
        raise InvalidInputError(
            "El PDF no contiene texto extraíble (probablemente es un escaneo; no hay OCR)."
        )
    return text, {
        "extraction": "pypdf",
        "pages": len(pages),
        "pages_without_text": sum(1 for p in pages if not p),
    }
