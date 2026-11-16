# Decisiones técnicas (ADR)

Cada archivo registra una decisión de arquitectura: el contexto, lo decidido, las
alternativas descartadas y las consecuencias. Una decisión no se edita para cambiarla: se
añade otra que la sustituye y se marca la antigua como «Sustituida por NNNN».

| N.º | Decisión | Estado |
| --- | --- | --- |
| [0001](0001-monolito-modular.md) | Monolito modular en lugar de microservicios | Aceptada |
| [0002](0002-postgresql-pgvector.md) | PostgreSQL con pgvector como único almacén | Aceptada |
| [0003](0003-embeddings-sin-costo-por-defecto.md) | Embeddings locales y gratuitos por defecto, dimensión fija de 384 | Aceptada |
| [0004](0004-respuestas-extractivas.md) | Respuestas extractivas por defecto; modelo de lenguaje opcional y verificado | Aceptada |
| [0005](0005-versionado-por-instantaneas.md) | Versionado por instantáneas completas | Aceptada |
| [0006](0006-una-tabla-de-recuerdos.md) | Una sola tabla de recuerdos para todos los tipos de memoria | Aceptada |
| [0007](0007-autenticacion-jwt-y-roles.md) | Autenticación con JWT y tres roles | Aceptada |
| [0008](0008-dos-mecanismos-de-respaldo.md) | Dos mecanismos de respaldo: `pg_dump` y exportación JSON | Aceptada |

Plantilla: copia cualquiera de ellos y conserva los apartados Contexto, Decisión,
Alternativas y Consecuencias.
