# Módulos

Un módulo añade una capacidad al sistema sin tocar el núcleo. Se activan con la variable
`NMC_ENABLED_MODULES` (lista separada por comas); quitar un nombre de la lista lo desactiva
sin borrar sus datos.

## Módulos incluidos

| Módulo | Qué aporta | Endpoints | Datos |
| --- | --- | --- | --- |
| `personal` | Preferencias con clave estable (formato de fechas, editor, estilo…). Cambiar una conserva la anterior en el historial. | `/preferences` | Recuerdos de tipo `preference` |
| `projects` | Proyectos con objetivos, decisiones, historial y relaciones entre proyectos. Resuelve "mi último proyecto" en las preguntas. | `/projects` | Tablas del núcleo `projects`, `project_relations` |
| `conversations` | Guarda conversaciones (mensajes o transcripción) como memoria episódica, con fecha y participantes. | `/conversations` | Recuerdos de tipo `episodic` |
| `documents` | Ingesta de archivos de texto y PDF, y notas. Conserva nombre, tipo, tamaño y huella del original. | `/documents` | Recuerdos de tipo `document` |
| `knowledge` | Conceptos y definiciones, con relaciones `related` y `part_of`. | `/knowledge/concepts` | Recuerdos `semantic` de clase `concept` |
| `tasks` | Tareas pendientes asociables a proyectos. Responde "qué tengo pendiente". Depende de `projects`. | `/tasks` | Tabla propia `tasks` |

### Formatos de documento

Texto plano y derivados (`.txt`, `.md`, `.csv`, `.json`, código fuente…) y PDF con texto.
La lista exacta la devuelve `GET /api/v1/documents/formats`. Los PDF escaneados (solo imagen)
no contienen texto extraíble y se rechazan con un mensaje claro: el sistema no hace OCR.

## Qué puede hacer un módulo

| Capacidad | Método de `NMCModule` |
| --- | --- |
| Añadir endpoints bajo `/api/v1` | `get_router()` |
| Reaccionar a lo que ocurre en la memoria | `register_events(bus)` |
| Aportar indicadores al panel | `stats(session)` |
| Aportar hechos a las respuestas | `contribute_to_answer(session, analysis, filters)` |
| Incluir sus tablas en la exportación | `export_data(session)`, `import_data(session, data)` |
| Tener tablas propias | Archivo `models.py` en el paquete |

Guía paso a paso: [`crear_modulo.md`](crear_modulo.md).
