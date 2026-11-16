from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from core.database.changelog import log_change
from core.database.models import Project, utcnow
from core.errors import InvalidInputError, NotFoundError
from core.web.deps import Editor, Reader, SessionDep
from core.web.schemas import StrictModel
from modules.tasks.models import OPEN_STATUSES, Task

router = APIRouter(prefix="/tasks", tags=["Tareas"])
TaskStatus = Literal["pending", "in_progress", "done", "cancelled"]


class TaskCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    project_id: uuid.UUID | None = None
    status: TaskStatus = "pending"
    priority: int = Field(default=3, ge=1, le=5)
    due_date: date | None = None


class TaskUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    project_id: uuid.UUID | None = None
    status: TaskStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    due_date: date | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    description: str
    status: str
    priority: int
    due_date: date | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


def _out(task: Task) -> TaskOut:
    return TaskOut.model_validate(task, from_attributes=True)


def _get(session, task_id: uuid.UUID) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"No existe la tarea {task_id}.")
    return task


def _check_project(session, project_id: uuid.UUID | None) -> None:
    if project_id is not None and session.get(Project, project_id) is None:
        raise InvalidInputError(f"No existe el proyecto {project_id}.")


@router.post("", response_model=TaskOut, status_code=201, summary="Crear tarea")
def create_task(body: TaskCreate, session: SessionDep, user: Editor):
    _check_project(session, body.project_id)
    task = Task(**body.model_dump())
    if task.status == "done":
        task.completed_at = utcnow()
    session.add(task)
    session.flush()
    log_change(
        session,
        entity_type="task",
        entity_id=task.id,
        action="create",
        summary=f"Tarea creada: {task.title}",
        actor=user.username,
        project_id=task.project_id,
    )
    return _out(task)


@router.get("", response_model=list[TaskOut], summary="Listar tareas")
def list_tasks(
    session: SessionDep,
    _: Reader,
    project_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    stmt = select(Task).order_by(Task.priority.desc(), Task.created_at.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if open_only:
        stmt = stmt.where(Task.status.in_(OPEN_STATUSES))
    return [_out(t) for t in session.scalars(stmt)]


@router.patch("/{task_id}", response_model=TaskOut, summary="Actualizar tarea")
def update_task(task_id: uuid.UUID, body: TaskUpdate, session: SessionDep, user: Editor):
    task = _get(session, task_id)
    changes = body.model_dump(exclude_unset=True)
    if "project_id" in changes:
        _check_project(session, changes["project_id"])
    diff = {}
    for key, value in changes.items():
        before = getattr(task, key)
        if before != value:
            diff[key] = {"before": str(before) if before is not None else None, "after": str(value)}
            setattr(task, key, value)
    if diff:
        if "status" in diff:
            task.completed_at = utcnow() if task.status == "done" else None
        task.updated_at = utcnow()
        log_change(
            session,
            entity_type="task",
            entity_id=task.id,
            action="update",
            summary=f"Tarea actualizada ({', '.join(diff)}): {task.title}",
            details={"changes": diff},
            actor=user.username,
            project_id=task.project_id,
        )
        session.flush()
    return _out(task)


@router.delete("/{task_id}", status_code=204, summary="Eliminar tarea")
def delete_task(task_id: uuid.UUID, session: SessionDep, user: Editor):
    task = _get(session, task_id)
    log_change(
        session,
        entity_type="task",
        entity_id=task.id,
        action="delete",
        summary=f"Tarea eliminada: {task.title}",
        actor=user.username,
        project_id=task.project_id,
    )
    session.delete(task)
