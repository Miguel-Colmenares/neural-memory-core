# 0008. Dos mecanismos de respaldo: pg_dump y exportación JSON

Estado: Aceptada · Fecha: 2026-11-16

## Contexto

Toda la memoria debe poder exportarse y restaurarse, y hay que poder recuperarse de la
pérdida del servidor.

## Decisión

- **Respaldo de base** con `pg_dump` (formato personalizado) y restauración con
  `pg_restore`: copia exacta, incluidos usuarios y vectores. Reemplaza al restaurar.
- **Exportación JSON** con formato versionado: legible, independiente de PostgreSQL. Al
  importar fusiona y nunca sobrescribe. Excluye usuarios (contienen hashes de contraseñas) y
  vectores (se regeneran).

## Alternativas

- **Solo `pg_dump`.** Descartado: binario, atado a la versión de PostgreSQL, no permite
  fusionar dos instalaciones.
- **Solo JSON.** Descartado: no es una copia exacta ni la vía más rápida ante un desastre.

## Consecuencias

- La imagen de la API incluye el cliente de PostgreSQL.
- Los módulos con tablas propias deben implementar `export_data` e `import_data`.
- Los archivos resultantes no van cifrados: protegerlos es responsabilidad de quien opera.
