# Guía para crear un módulo

Un módulo es un paquete de Python que expone una variable `module`, instancia de
`core.module_system.base.NMCModule`. El núcleo no necesita ningún cambio.

Esta guía construye un módulo real, `lecturas`, para llevar una lista de libros y artículos
leídos. El código de esta página se ejecutó tal cual contra la aplicación.

## 1. Dónde ponerlo

| Ubicación | Nombre en `NMC_ENABLED_MODULES` |
| --- | --- |
| Dentro del repositorio: `modules/lecturas/` | `lecturas` |
| Fuera, en cualquier paquete importable: `mis_modulos/lecturas/` | `mis_modulos.lecturas` |

La segunda forma permite mantener módulos privados fuera de este repositorio. El ejemplo usa
esa ruta; si lo colocas en `modules/`, cambia los `import` a `modules.lecturas`.

## 2. El módulo: `__init__.py`

```python
"""Módulo de ejemplo: lista de lecturas."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from core.database.models import Memory
from core.module_system import events
from core.module_system.base import ModuleManifest, NMCModule

KIND = "reading"


class LecturasModule(NMCModule):
    manifest = ModuleManifest(
        name="lecturas",
        version="1.0.0",
        description="Libros y artículos leídos, con notas.",
        memory_types=("semantic",),
        kinds=(KIND,),
    )

    def get_router(self):
        from mis_modulos.lecturas.router import router

        return router

    def register_events(self, bus) -> None:
        bus.subscribe(events.MEMORY_CREATED, self._on_created)

    def _on_created(self, session, memory, **_: Any) -> None:
        # Reacciona a recuerdos creados por cualquier vía. Aquí solo se ignoran los ajenos.
        if memory.kind != KIND:
            return

    def stats(self, session) -> dict[str, Any]:
        total = session.scalar(
            select(func.count())
            .select_from(Memory)
            .where(Memory.kind == KIND, Memory.status == "active")
        )
        return {"readings": total or 0}

    def contribute_to_answer(self, session, analysis, filters) -> list[dict[str, Any]]:
        if not {"lecturas", "leido", "lei"} & set(analysis.terms):
            return []
        rows = session.scalars(
            select(Memory)
            .where(Memory.kind == KIND, Memory.status == "active")
            .order_by(Memory.created_at.desc())
            .limit(10)
        )
        return [
            {
                "text": f"Lectura registrada: {m.title}",
                "source_kind": "memory",
                "id": str(m.id),
                "label": m.title or "Lectura",
                "excerpt": m.content[:300],
            }
            for m in rows
        ]


module = LecturasModule()
```

Puntos clave:

- `manifest.name` debe ser único. `depends_on` lista otros módulos obligatorios.
- **Sobrescribe solo lo que necesites.** Todos los métodos tienen una implementación vacía.
- `stats` debe devolver cifras calculadas con consultas reales, nunca valores fijos.
- `contribute_to_answer` devuelve hechos que irán a la sección "confirmado" de la respuesta,
  cada uno con su fuente (`source_kind`, `id`, `label`). Devuelve una lista vacía si la
  pregunta no va contigo. Los términos de `analysis.terms` llegan en minúsculas y sin acentos.
- Un fallo en un manejador de eventos se registra y no interrumpe la operación principal.

## 3. Los endpoints: `router.py`

```python
from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from core.ingestion.pipeline import IngestionInput
from core.memory_engine.filters import MemoryFilters
from core.web.deps import Editor, IngestionDep, MemoryServiceDep, Reader
from core.web.schemas import IngestionOut, MemoryOut, StrictModel

router = APIRouter(prefix="/lecturas", tags=["Lecturas"])


class LecturaCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(min_length=1)
    author: str | None = Field(default=None, max_length=200)


@router.post("", response_model=IngestionOut, status_code=201, summary="Registrar una lectura")
def create(body: LecturaCreate, pipeline: IngestionDep, _: Editor):
    result = pipeline.ingest(
        IngestionInput(
            content=body.notes,
            title=body.title,
            memory_type="semantic",
            kind="reading",
            source_type="module",
            source_ref=body.author,
            module="lecturas",
            metadata={"author": body.author},
        )
    )
    return IngestionOut.from_result(result)


@router.get("", response_model=list[MemoryOut], summary="Listar lecturas")
def list_readings(memories: MemoryServiceDep, _: Reader):
    items, _total = memories.list(MemoryFilters(kinds=["reading"]), limit=100)
    return [MemoryOut.from_model(m) for m in items]
```

Reglas:

- **Crea recuerdos con el pipeline de ingesta** (`IngestionDep`), no insertando filas. Así
  obtienes gratis duplicados, embeddings, etiquetas, relaciones, versión inicial e historial.
- **Modifica recuerdos con `MemoryServiceDep`** (`update`, `archive`…). Es lo que garantiza
  que nunca se sobrescribe sin dejar versión.
- **Todo endpoint declara un rol**: `Reader`, `Editor` o `Admin`. Una prueba del repositorio
  recorre todas las rutas y falla si alguna queda sin protección.
- Hereda los esquemas de entrada de `StrictModel`: rechaza campos desconocidos.
- Marca tus recuerdos con `module="…"` y un `kind` propio para poder filtrarlos.

## 4. Activarlo

```ini
NMC_ENABLED_MODULES=personal,projects,conversations,documents,knowledge,tasks,mis_modulos.lecturas
```

Reinicia la API. Compruébalo en el panel (Proveedores de IA → Módulos activos) o con
`GET /api/v1/system/info`. Si el módulo no puede cargarse, la API se niega a arrancar y
explica el motivo en el registro.

## 5. Tablas propias (opcional)

Si los recuerdos no bastan, añade un archivo `models.py` al paquete. Usa la misma `Base` que
el núcleo:

```python
import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database.base import Base


class Autor(Base):
    __tablename__ = "lecturas_autores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
```

Con el módulo activado en `NMC_ENABLED_MODULES`, genera y aplica la migración:

```bash
alembic revision --autogenerate -m "lecturas: tabla de autores"
alembic upgrade head
```

Prefija los nombres de tabla con el del módulo. Si tiene tablas propias, implementa también
`export_data` e `import_data` para que entren en la exportación JSON; `modules/tasks` es el
ejemplo completo (tabla, migración, exportación, importación y aportación a respuestas).

## 6. Eventos disponibles

| Evento | Cuándo | Argumentos |
| --- | --- | --- |
| `memory.created` | Se creó un recuerdo | `session`, `memory` |
| `memory.updated` | Se actualizó (nueva versión) | `session`, `memory` |
| `memory.archived` | Se archivó | `session`, `memory` |
| `memory.restored` | Se reactivó | `session`, `memory` |
| `memory.deleted` | Se eliminó definitivamente | `session`, `memory` |

Las constantes están en `core/module_system/events.py`. Los manejadores se ejecutan en la
misma transacción: no hagas `commit` dentro.

## 7. Pruebas

Añade pruebas en `tests/integration/`. Las utilidades de `tests/conftest.py` te dan una base
limpia (`clean_db`), un cliente HTTP (`client`) y cabeceras de administrador (`auth`).
`tests/integration/test_api_modules.py` sirve de plantilla.

## 8. Lista de comprobación

- [ ] `module = MiModulo()` al final de `__init__.py`.
- [ ] `manifest` con nombre único, versión y descripción.
- [ ] Todos los endpoints exigen un rol.
- [ ] Los recuerdos se crean con el pipeline y se modifican con `MemoryService`.
- [ ] Sin datos de ejemplo ni indicadores inventados.
- [ ] Si hay tablas propias: migración, `export_data` e `import_data`.
- [ ] Pruebas, entrada en `docs/modules/README.md` y en `CHANGELOG.md`.

## Compatibilidad

El contrato tiene un número de versión (`MODULE_API_VERSION`, hoy 1) que cada manifiesto
declara. Si el contrato cambia de forma incompatible, ese número sube y el registro rechaza
los módulos escritos para una versión anterior con un mensaje explícito, en lugar de fallar
de forma imprevisible.
