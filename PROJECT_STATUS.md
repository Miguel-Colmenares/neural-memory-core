# Estado del proyecto

> Lee este archivo antes de continuar el trabajo. Actualízalo en cada cambio que modifique el
> estado: fase, tareas, errores conocidos o decisiones.

Última actualización: 2026-11-16 · Versión: 0.1.0

## Fase actual

**Las nueve fases de desarrollo están completas.** El proyecto está en mantenimiento y
ampliación: lo siguiente es verificar en un equipo real los puntos marcados abajo como «sin
verificar» y decidir las mejoras de la sección «Próximos pasos».

| Fase | Contenido | Estado |
| --- | --- | --- |
| 1 | Arquitectura y estructura base | Completada |
| 2 | Base de datos y migraciones | Completada |
| 3 | CRUD de recuerdos con historial | Completada |
| 4 | Embeddings | Completada (FastEmbed sin verificar, ver abajo) |
| 5 | Recuperación semántica y respuestas con fuentes | Completada |
| 6 | Interfaz (panel web) | Completada |
| 7 | Seguridad y respaldos | Completada |
| 8 | Pruebas e integración continua | Completada (la CI aún no se ha ejecutado en GitHub) |
| 9 | Documentación y despliegue | Completada |

## Criterios de aceptación

| Criterio | Cómo se comprobó |
| --- | --- |
| Crear y guardar recuerdos | Pruebas de integración y e2e; a mano en el panel |
| Consultarlos después | Ídem |
| Buscar por texto y por significado | Pruebas de `tests/integration/test_retrieval.py`. «Por significado» se probó con el proveedor `hashing` (parecido léxico); el proveedor semántico real está sin verificar |
| Crear y administrar proyectos | Pruebas de `test_api_modules.py`; a mano en el panel |
| Asociar recuerdos con proyectos | Ídem |
| Actualizar conservando historial | `test_memory_engine.py`; a mano (editar, ver v2, revertir) |
| Mostrar las fuentes de las respuestas | `test_retrieval.py`; a mano en el buscador |
| Exportar la información | `test_system_and_recovery.py`; a mano (descarga JSON) |
| Restaurar una copia de seguridad | `test_system_and_recovery.py` con `pg_dump` y `pg_restore` reales |
| Ejecutar pruebas automatizadas | `pytest`: 163 pruebas pasan |
| Arrancar con la instalación documentada | Docker Compose arrancado y probado con una salvedad (ver «Docker») |

`tests/e2e/test_acceptance.py` recorre todos estos criterios por HTTP en una sola prueba.

## Tareas completadas

- Núcleo: memoria, versionado, ingesta en 9 pasos, grafo de relaciones, búsqueda híbrida,
  análisis de preguntas, respuestas con fuentes, resumen extractivo.
- Tres proveedores de embeddings y cliente opcional de modelo de lenguaje.
- Sistema de módulos y seis módulos: `personal`, `projects`, `conversations`, `documents`,
  `knowledge`, `tasks`.
- API con autenticación, roles, validación y registro de errores.
- Panel web con las diez secciones pedidas.
- Respaldos (`pg_dump`), exportación e importación JSON, herramienta `scripts/manage.py`.
- Docker Compose, migraciones, CI, plantillas de GitHub.
- Documentación completa en `docs/`.

## Qué se verificó y cómo

| Elemento | Verificación |
| --- | --- |
| API y núcleo | 163 pruebas automáticas (49 unitarias, 113 de integración, 1 e2e) contra PostgreSQL 16 con pgvector |
| Lint | `ruff check` y `ruff format --check` sin errores |
| Migraciones | `alembic upgrade head` y `alembic check` sin diferencias |
| Panel web | `npm run lint`, `npm run typecheck` y `npm run build` sin errores. Recorrido en Chromium contra la API real: inicio de sesión (correcto e incorrecto), crear proyecto, recuerdos, edición con nueva versión, relación manual, grafo, subida de documento, decisión y tarea de proyecto, preguntas con y sin respuesta, respaldo, exportación e importación, y las diez páginas sin errores de consola ni de red |
| Docker Compose | Imágenes construidas y los tres servicios arrancados con `docker-compose.yml`; inicio de sesión, creación de un recuerdo y pregunta desde el panel; los datos siguen ahí tras `docker compose down` y `up` |
| Guía de módulos | El módulo de ejemplo `lecturas` se cargó desde un paquete externo y respondió por HTTP |

## Sin verificar

Estos puntos están implementados pero **no se han podido ejecutar** en el entorno donde se
desarrolló. No deben darse por probados hasta comprobarlos.

| Elemento | Motivo | Cómo comprobarlo |
| --- | --- | --- |
| Proveedor `fastembed` (búsqueda por significado real) | La descarga del modelo desde Hugging Face estaba bloqueada por la red. La librería sí se instala en la imagen | Poner `NMC_EMBEDDING_PROVIDER=fastembed`, reiniciar, pulsar «Probar conexión» y «Reindexar todo» en el panel |
| Línea `apt-get install postgresql-client curl` de `api.Dockerfile` | Los repositorios de Debian estaban bloqueados. La imagen se probó sin ese paso; por tanto, **dentro de Docker** no se probaron los respaldos ni la comprobación de salud del contenedor | El trabajo `docker` de la CI lo cubre: construye la imagen completa y crea un respaldo |
| Integración continua en GitHub Actions | El repositorio aún no se ha podido publicar | Se ejecuta sola al publicar en `main` |
| Proveedor `openai` de embeddings y modelo de lenguaje contra un servicio real | No se usan servicios de pago ni claves. Probado solo con un servidor simulado | Configurar una clave propia o un Ollama local y usar «Probar conexión» |
| Despliegue con dominio, HTTPS y VPN | No se ha desplegado en ningún servidor | Seguir `docs/user_guide/despliegue.md` |
| PostgreSQL 17 | Las pruebas corrieron sobre PostgreSQL 16; Docker Compose usa la imagen `pgvector/pgvector:pg17`, que arrancó y funcionó en la prueba manual | La CI ejecuta la suite completa sobre pg17 |

## Errores y limitaciones conocidas

No hay errores conocidos sin corregir. Limitaciones de diseño:

1. **El proveedor por defecto (`hashing`) no entiende sinónimos ni paráfrasis.** Encuentra
   textos con palabras parecidas. Para búsqueda por significado hay que activar `fastembed`.
2. **Respuestas extractivas.** Sin modelo de lenguaje, la respuesta son citas literales, no
   una redacción.
3. **Análisis de preguntas por reglas y en español.** Cubre un conjunto finito de
   intenciones; otras preguntas se resuelven como búsqueda normal.
4. **Sin OCR.** Los PDF escaneados se rechazan. No se procesan imágenes, audio ni formatos
   de ofimática (`.docx`, `.xlsx`).
5. **Clasificación y etiquetado automáticos por reglas simples.** Pueden equivocarse; la
   regla aplicada queda anotada y todo es editable.
6. **Detección de contradicciones manual.** El sistema enlaza dos recuerdos como
   contradictorios cuando se le indica (`contradicts`, `supersedes`); no las detecta solo.
   Sí detecta duplicados exactos y parecidos.
7. **Sin revocación de tokens individuales** y límite de intentos de acceso en memoria del
   proceso (ver ADR 0007).
8. **Ingesta síncrona.** Un documento muy grande con un proveedor de embeddings remoto
   mantiene la petición abierta hasta terminar.
9. **Respaldos sin cifrar.** Protegerlos y copiarlos fuera del servidor es tarea de quien
   opera (hay un guion de ejemplo).
10. **El panel no gestiona usuarios.** Se crean por API o con `scripts/manage.py`.
11. **Relacionar recuerdos en el panel requiere pegar el identificador** del otro recuerdo;
    no hay buscador en ese formulario.
12. **`next lint` está obsoleto** en Next.js 15 y desaparecerá en la 16; habrá que migrar a
    la CLI de ESLint.

## Próximos pasos

1. Publicar el repositorio en GitHub y confirmar que la CI pasa (cubre varios puntos «sin
   verificar»).
2. Probar `fastembed` en un equipo con acceso a Hugging Face y, si funciona bien, valorar
   hacerlo el proveedor recomendado en la guía.
3. Etiquetar la versión `v0.1.0`.
4. Mejoras candidatas, por orden sugerido: selector de recuerdo al crear relaciones;
   gestión de usuarios en el panel; detección automática de posibles contradicciones;
   soporte de `.docx`; cifrado opcional de respaldos.

## Decisiones técnicas importantes

Resumen; el detalle está en [`docs/decisions/`](docs/decisions/).

| Decisión | Motivo |
| --- | --- |
| Monolito modular, tres contenedores | Lo opera una persona; sin microservicios ni colas |
| PostgreSQL + pgvector como único almacén | Un solo respaldo coherente; filtros y búsqueda en la misma consulta |
| Embeddings de 384 dimensiones, `hashing` por defecto | Funciona sin claves, sin descargas y sin costo; cambiar de proveedor no cambia el esquema |
| Respuestas extractivas; modelo de lenguaje opcional con verificación de citas | Garantiza que no se inventa información |
| Versionado por instantáneas; toda escritura pasa por `MemoryService` | Nunca se sobrescribe sin historial |
| Una tabla `memories` para todos los tipos | Buscar, versionar y relacionar funciona igual para módulos futuros |
| JWT + roles; la app no arranca sin clave secreta | Protección de todos los endpoints sin servicios externos |
| `pg_dump` y exportación JSON | Copia exacta para desastres y copia legible que fusiona sin sobrescribir |
| El contenedor de la API arranca como root solo para ajustar permisos y baja a un usuario sin privilegios | Docker crea `./backups` como root y la API no podía escribir en ella |

## Entorno de desarrollo usado

Python 3.12, Node.js 22, PostgreSQL 16 + pgvector (pruebas), imagen `pgvector/pgvector:pg17`
(Docker), Next.js 15.5, FastAPI, SQLAlchemy 2.
