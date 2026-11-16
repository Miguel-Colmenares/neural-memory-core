# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). El proyecto
sigue [versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

## [0.1.0] - 2026-11-16

Primera versión funcional.

### Añadido

- **Núcleo de memoria.** Cinco tipos de memoria (episódica, semántica, de proyecto, de
  preferencias y documental) con procedencia, etiquetas, importancia y estado.
- **Historial.** Cada cambio guarda una versión completa; consulta de versiones, reversión,
  archivado y reactivación. Registro de cambios de todo el sistema.
- **Ingesta en nueve pasos**: análisis, clasificación por reglas, detección de duplicados,
  relación con recuerdos existentes, guardado, embeddings, etiquetado, asociación a proyecto
  y registro. Las contradicciones conservan ambas versiones enlazadas.
- **Embeddings** con tres proveedores intercambiables de 384 dimensiones: `hashing` (local,
  por defecto), `fastembed` (modelo multilingüe local) y `openai` (API compatible). Troceado
  de textos largos y reindexado.
- **Búsqueda híbrida**: texto completo de PostgreSQL y vectores de pgvector fusionados con
  RRF, filtros, expansión por relaciones y reordenado por relevancia, importancia y recencia.
- **Respuestas con fuentes** que separan lo confirmado, las inferencias y lo no encontrado.
  Modo extractivo por defecto y modo opcional con modelo de lenguaje, con verificación de
  citas.
- **Módulos**: `personal`, `projects`, `conversations`, `documents` (texto y PDF),
  `knowledge` y `tasks`, sobre un sistema de módulos con registro, eventos y contrato
  versionado.
- **API REST** (FastAPI) con autenticación JWT, roles `admin`, `editor` y `reader`, límite de
  intentos de acceso y validación estricta de entradas.
- **Panel web** (Next.js): panel de indicadores, buscador, explorador de recuerdos y de
  proyectos, documentos, grafo de relaciones, historial, proveedores de IA, almacenamiento y
  exportación e importación.
- **Respaldos**: `pg_dump` / `pg_restore` y exportación e importación en JSON, desde el
  panel, la API y la línea de comandos (`scripts/manage.py`).
- **Infraestructura**: Docker Compose con PostgreSQL + pgvector, API y panel; migraciones con
  Alembic; integración continua en GitHub Actions; plantillas de incidencias y de pull
  request.
- **Documentación**: arquitectura, modelo de datos, API, guías de instalación, uso,
  despliegue y recuperación, guía para crear módulos y decisiones técnicas.

### Limitaciones conocidas

Ver la sección «Errores y limitaciones conocidas» de [`PROJECT_STATUS.md`](PROJECT_STATUS.md).

[Sin publicar]: https://github.com/Miguel-Colmenares/neural-memory-core/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Miguel-Colmenares/neural-memory-core/releases/tag/v0.1.0
