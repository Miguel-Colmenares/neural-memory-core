from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import Field, model_validator

from core.ingestion.pipeline import IngestionInput
from core.memory_engine.filters import MemoryFilters
from core.web.deps import Editor, IngestionDep, MemoryServiceDep, Reader
from core.web.schemas import IngestionOut, MemoryList, MemoryOut, StrictModel

router = APIRouter(prefix="/conversations", tags=["Conversaciones"])


class Message(StrictModel):
    role: str = Field(min_length=1, max_length=50, description="Quién habla: user, assistant...")
    content: str = Field(min_length=1)
    timestamp: datetime | None = None


class ConversationCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    messages: list[Message] = Field(default_factory=list, max_length=5000)
    transcript: str | None = Field(
        default=None, description="Alternativa a 'messages': la conversación como texto."
    )
    origin: str | None = Field(
        default=None, max_length=200, description="Dónde ocurrió: chatgpt, claude, reunión..."
    )
    external_id: str | None = Field(default=None, max_length=300)
    project_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    importance: int = Field(default=3, ge=1, le=5)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _one_source(self):
        if bool(self.messages) == bool(self.transcript and self.transcript.strip()):
            raise ValueError("Indica 'messages' o 'transcript' (uno de los dos).")
        return self


def render_transcript(messages: list[Message]) -> str:
    lines = []
    for message in messages:
        stamp = f" [{message.timestamp:%Y-%m-%d %H:%M}]" if message.timestamp else ""
        lines.append(f"{message.role}{stamp}: {message.content.strip()}")
    return "\n\n".join(lines)


@router.post("", response_model=IngestionOut, status_code=201, summary="Guardar una conversación")
def create_conversation(body: ConversationCreate, pipeline: IngestionDep, _: Editor):
    content = render_transcript(body.messages) if body.messages else (body.transcript or "")
    timestamps = [m.timestamp for m in body.messages if m.timestamp]
    occurred_at = body.occurred_at or (min(timestamps) if timestamps else None)
    result = pipeline.ingest(
        IngestionInput(
            content=content,
            memory_type="episodic",
            kind="conversation",
            title=body.title,
            source_type="conversation",
            source_ref=body.external_id or body.origin,
            provenance={
                "origin": body.origin,
                "external_id": body.external_id,
                "message_count": len(body.messages) or None,
                "participants": sorted({m.role for m in body.messages}) or None,
            },
            project_id=body.project_id,
            module="conversations",
            tags=body.tags,
            importance=body.importance,
            occurred_at=occurred_at,
        )
    )
    return IngestionOut.from_result(result)


@router.get("", response_model=MemoryList, summary="Listar conversaciones")
def list_conversations(
    service: MemoryServiceDep,
    _: Reader,
    project_id: uuid.UUID | None = None,
    status: Literal["active", "archived", "any"] = "active",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters = MemoryFilters(
        kinds=["conversation"],
        project_ids=[project_id] if project_id else [],
        status=None if status == "any" else status,
    )
    items, total = service.list(filters, limit=limit, offset=offset)
    return MemoryList(
        items=[MemoryOut.from_model(m, max_content=500) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )
