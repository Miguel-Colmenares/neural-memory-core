# 0002. PostgreSQL con pgvector como único almacén

Estado: Aceptada · Fecha: 2026-11-16

## Contexto

Hacen falta datos relacionales (proyectos, versiones, relaciones), búsqueda de texto y
búsqueda vectorial, con respaldos sencillos.

## Decisión

Todo en PostgreSQL: tablas relacionales, búsqueda de texto completo nativa (columna
`tsvector` generada, configuración `spanish`) y vectores con la extensión pgvector (índice
HNSW, distancia coseno).

## Alternativas

- **Base vectorial dedicada (Qdrant, Chroma, Pinecone).** Descartado: un segundo almacén que
  respaldar y mantener coherente con el primero; algunas son de pago.
- **Elasticsearch / OpenSearch para texto.** Descartado: demasiado pesado para una persona;
  la búsqueda de PostgreSQL es suficiente.
- **SQLite.** Descartado: el requisito pide PostgreSQL con pgvector.

## Consecuencias

- Un solo `pg_dump` respalda absolutamente todo de forma coherente.
- Los filtros (proyecto, fechas, tipo) se aplican en la misma consulta que la búsqueda.
- La dimensión del vector forma parte del esquema (ver ADR 0003).
- pgvector rinde bien hasta cientos de miles de fragmentos, de sobra para uso personal.
