from __future__ import annotations

import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import Field

from core.ingestion.pipeline import IngestionInput
from core.memory_engine.filters import MemoryFilters
from core.web.deps import Editor, IngestionDep, MemoryServiceDep, Reader, SettingsDep
from core.web.schemas import IngestionOut, MemoryList, MemoryOut, StrictModel
from modules.documents.extract import SUPPORTED, extract_text

router = APIRouter(prefix="/documents", tags=["Documentos"])


class DocumentText(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    kind: str = Field(default="document", max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    project_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    importance: int = Field(default=3, ge=1, le=5)
    source_ref: str | None = Field(default=None, max_length=500)


@router.get("/formats", summary="Formatos de archivo admitidos")
def formats(_: Reader) -> dict:
    return {"extensions": SUPPORTED, "note": "Los PDF escaneados no se leen: no hay OCR."}


@router.post("/upload", response_model=IngestionOut, status_code=201, summary="Subir un archivo")
async def upload_document(
    pipeline: IngestionDep,
    settings: SettingsDep,
    _: Editor,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=300)] = None,
    project_id: Annotated[uuid.UUID | None, Form()] = None,
    tags: Annotated[str, Form(description="Etiquetas separadas por comas")] = "",
    importance: Annotated[int, Form(ge=1, le=5)] = 3,
):
    """Extrae el texto del archivo y lo guarda como recuerdo documental. El
    archivo original no se almacena: solo su texto, nombre, tamaño y huella."""
    data = await file.read()
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(413, f"El archivo supera el máximo de {settings.max_upload_mb} MB.")
    if not data:
        raise HTTPException(422, "El archivo está vacío.")
    filename = (file.filename or "documento").replace("\\", "/").split("/")[-1][:255]
    text, details = extract_text(filename, data)
    result = pipeline.ingest(
        IngestionInput(
            content=text,
            memory_type="document",
            kind="document",
            title=title or filename,
            source_type="document",
            source_ref=filename,
            provenance={
                "filename": filename,
                "content_type": file.content_type,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                **details,
            },
            project_id=project_id,
            module="documents",
            tags=[t for t in tags.split(",") if t.strip()],
            importance=importance,
        )
    )
    return IngestionOut.from_result(result)


@router.post("", response_model=IngestionOut, status_code=201, summary="Guardar una nota o texto")
def create_document(body: DocumentText, pipeline: IngestionDep, _: Editor):
    result = pipeline.ingest(
        IngestionInput(
            content=body.content,
            memory_type="document",
            kind=body.kind,
            title=body.title,
            source_type="manual",
            source_ref=body.source_ref,
            project_id=body.project_id,
            module="documents",
            tags=body.tags,
            importance=body.importance,
        )
    )
    return IngestionOut.from_result(result)


@router.get("", response_model=MemoryList, summary="Vista de documentos")
def list_documents(
    service: MemoryServiceDep,
    _: Reader,
    project_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters = MemoryFilters(
        memory_types=["document"], project_ids=[project_id] if project_id else []
    )
    items, total = service.list(filters, limit=limit, offset=offset)
    return MemoryList(
        items=[MemoryOut.from_model(m, max_content=500) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )
