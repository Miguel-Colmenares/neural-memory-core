# 0006. Una sola tabla de recuerdos para todos los tipos de memoria

Estado: Aceptada · Fecha: 2026-11-16

## Contexto

Hay cinco tipos de memoria con campos parcialmente distintos, y los módulos futuros
añadirán más clases de información.

## Decisión

Una tabla `memories` con los campos comunes (contenido, procedencia, proyecto, etiquetas,
importancia, fechas, versión), un discriminador `memory_type`, una clase libre `kind` y dos
columnas JSONB (`metadata`, `provenance`) para lo específico. Las tablas aparte se reservan
para lo que no es un recuerdo (proyectos, tareas).

## Alternativas

- **Una tabla por tipo.** Descartado: la búsqueda, el versionado, las relaciones y los
  embeddings tendrían que implementarse cinco veces, y cada módulo nuevo exigiría migración.

## Consecuencias

- Buscar, versionar, relacionar y exportar funciona igual para cualquier tipo, incluidos los
  que añadan módulos futuros.
- Los campos específicos en JSONB no tienen restricciones de esquema: los valida la API.
