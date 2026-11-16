# 0005. Versionado por instantáneas completas

Estado: Aceptada · Fecha: 2026-11-16

## Contexto

Ningún recuerdo puede sobrescribirse sin conservar su historial, y debe poder volverse a una
versión anterior.

## Decisión

Cada cambio guarda en `memory_versions` una copia completa del recuerdo (JSON), con el tipo
de cambio, el motivo, los campos modificados y el autor. La versión 1 se guarda al crear.
Revertir crea una versión nueva con el contenido antiguo; nunca se borra historial. Todas las
escrituras pasan por `MemoryService`, único punto que modifica recuerdos.

## Alternativas

- **Guardar solo diferencias.** Descartado: ahorra espacio pero complica leer y revertir.
- **Tablas temporales o disparadores de PostgreSQL.** Descartado: oculta la lógica fuera del
  código y dificulta las pruebas.

## Consecuencias

- Leer o restaurar cualquier versión es una sola consulta.
- Más espacio en recuerdos largos que cambian mucho; asumible en uso personal.
- La eliminación definitiva sí borra las versiones (es su propósito) y deja constancia en
  `change_log` sin el contenido.
