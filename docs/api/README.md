# API

API REST en JSON bajo el prefijo `/api/v1`. La referencia completa y siempre actualizada la
genera la propia aplicación:

- Interfaz interactiva: `http://localhost:8000/docs`
- Especificación OpenAPI: `http://localhost:8000/openapi.json`

Ambas se desactivan cuando `NMC_ENVIRONMENT=production`, para no exponer el mapa de la API.

## Autenticación

Todos los endpoints exigen un token, salvo `GET /health` y `POST /api/v1/auth/login`.

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username": "admin", "password": "TU_CONTRASEÑA"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8000/api/v1/stats -H "Authorization: Bearer $TOKEN"
```

El token es un JWT firmado con `NMC_SECRET_KEY` y caduca a los `NMC_ACCESS_TOKEN_MINUTES`
minutos (720 por defecto). Tras varios intentos fallidos seguidos desde la misma dirección,
el inicio de sesión se bloquea temporalmente (respuesta 429).

### Roles

| Rol | Puede |
| --- | --- |
| `reader` | Consultar, buscar y preguntar |
| `editor` | Lo anterior, y crear, modificar, archivar y eliminar recuerdos, proyectos, tareas y relaciones |
| `admin` | Lo anterior, y usuarios, respaldos, exportación e importación, reindexado y prueba de proveedores |

## Errores

```json
{"detail": "Recuerdo no encontrado."}
```

| Código | Significado |
| --- | --- |
| 400 / 422 | Datos de entrada inválidos (422 incluye el detalle por campo) |
| 401 | Falta el token, es inválido o caducó |
| 403 | Tu rol no permite la operación |
| 404 | No existe |
| 409 | Conflicto (por ejemplo, nombre duplicado) |
| 413 | Archivo demasiado grande (`NMC_MAX_UPLOAD_MB`) |
| 429 | Demasiados intentos de inicio de sesión |
| 500 | Error interno. La respuesta trae un `request_id` para buscarlo en los registros; nunca incluye detalles internos |

## Endpoints

### Autenticación

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| POST | `/auth/login` | público | Iniciar sesión |
| GET | `/auth/me` | reader | Usuario actual |
| POST | `/auth/password` | reader | Cambiar la contraseña propia |
| GET | `/auth/users` | admin | Listar usuarios |
| POST | `/auth/users` | admin | Crear usuario |
| POST | `/auth/users/{user_id}/deactivate` | admin | Desactivar usuario |

### Recuerdos

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| POST | `/memories` | editor | Incorporar un recuerdo (pipeline de ingesta) |
| GET | `/memories` | reader | Explorar con filtros y paginación |
| GET | `/memories/tags` | reader | Etiquetas en uso |
| GET | `/memories/{id}` | reader | Obtener un recuerdo |
| PATCH | `/memories/{id}` | editor | Actualizar creando una versión nueva |
| GET | `/memories/{id}/versions` | reader | Historial de versiones |
| POST | `/memories/{id}/revert/{version}` | editor | Volver a una versión anterior |
| POST | `/memories/{id}/archive` | editor | Archivar (deja de aparecer en búsquedas) |
| POST | `/memories/{id}/restore` | editor | Reactivar |
| GET | `/memories/{id}/relations` | reader | Recuerdos relacionados |
| DELETE | `/memories/{id}` | editor | Eliminar definitivamente |

### Búsqueda y conocimiento

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| POST | `/search` | reader | Búsqueda híbrida |
| POST | `/ask` | reader | Pregunta en lenguaje natural con fuentes |
| POST | `/relations` | editor | Crear relación entre dos recuerdos |
| DELETE | `/relations/{id}` | editor | Eliminar relación |
| GET | `/graph` | reader | Nodos y aristas para la visualización |

### Proyectos y tareas

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| POST / GET | `/projects` | editor / reader | Crear y listar |
| GET / PATCH / DELETE | `/projects/{id}` | reader / editor / editor | Espacio del proyecto, actualizar, eliminar |
| POST | `/projects/{id}/decisions` | editor | Registrar una decisión |
| GET / POST | `/projects/{id}/relations` | reader / editor | Relaciones con otros proyectos |
| DELETE | `/projects/relations/{relation_id}` | editor | Eliminar relación entre proyectos |
| POST / GET | `/tasks` | editor / reader | Crear y listar tareas |
| PATCH / DELETE | `/tasks/{id}` | editor | Actualizar y eliminar |

### Otros módulos

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| POST / GET | `/conversations` | editor / reader | Guardar y listar conversaciones (memoria episódica) |
| POST / GET | `/documents` | editor / reader | Guardar una nota y ver documentos |
| POST | `/documents/upload` | editor | Subir un archivo (texto o PDF) |
| GET | `/documents/formats` | reader | Formatos admitidos |
| GET | `/preferences`, `/preferences/{key}` | reader | Consultar preferencias |
| PUT | `/preferences/{key}` | editor | Definir o cambiar una preferencia (conserva la anterior en el historial) |
| POST / GET | `/knowledge/concepts` | editor / reader | Registrar y listar conceptos |

### Sistema

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| GET | `/health` (sin prefijo) | público | Estado del servicio y de la base |
| GET | `/stats` | reader | Indicadores reales para el panel |
| GET | `/history` | reader | Historial de actualizaciones |
| GET | `/system/info` | reader | Versión y módulos activos |
| GET | `/system/providers` | reader | Configuración de IA (sin claves) |
| POST | `/system/providers/test` | admin | Probar los proveedores configurados |
| POST | `/system/reindex` | admin | Regenerar embeddings |
| GET | `/storage` | admin | Uso de almacenamiento y lista de respaldos |
| POST | `/storage/backups` | admin | Crear un respaldo |
| GET / DELETE | `/storage/backups/{name}` | admin | Descargar o eliminar un respaldo |
| GET | `/data/export` | admin | Exportar toda la memoria en JSON |
| POST | `/data/import` | admin | Importar una exportación |

## Ejemplos

### Guardar un recuerdo

```bash
curl -s http://localhost:8000/api/v1/memories \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "content": "Decidimos usar riego por goteo en el huerto porque ahorra agua.",
    "title": "Riego por goteo",
    "tags": ["riego"],
    "source_ref": "Reunión del 3 de mayo"
  }'
```

Solo `content` es obligatorio. Campos opcionales: `memory_type`, `kind`, `title`,
`source_type`, `source_ref`, `provenance`, `project_id`, `tags`, `importance` (1 a 5),
`metadata`, `occurred_at`, `contradicts` y `supersedes` (listas de identificadores),
`auto_tag`, `auto_relate`, `allow_duplicate`.

La respuesta indica qué pasó: `outcome` (`created` o `duplicate`), el recuerdo, las etiquetas
automáticas, las relaciones detectadas y los avisos.

### Corregir un recuerdo

```bash
curl -s -X PATCH http://localhost:8000/api/v1/memories/ID \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content": "Texto corregido.", "change_reason": "La fecha estaba mal", "is_correction": true}'
```

La versión anterior queda en `GET /memories/ID/versions`.

### Preguntar

```bash
curl -s http://localhost:8000/api/v1/ask \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question": "¿Qué decidimos sobre el riego?"}'
```

```json
{
  "question": "¿Qué decidimos sobre el riego?",
  "answer": "Información confirmada en tu memoria:\n- Decidimos usar riego por goteo en el huerto porque ahorra agua y evita hongos en las hojas. [1]",
  "answer_mode": "extractive",
  "confirmed": [
    {"text": "Decidimos usar riego por goteo en el huerto porque ahorra agua y evita hongos en las hojas.", "sources": [1]}
  ],
  "inferences": [],
  "not_found": [],
  "sources": [
    {
      "index": 1,
      "source_kind": "memory",
      "id": "356a1878-b173-4b9d-86d6-398edb0bf739",
      "label": "Riego por goteo",
      "memory_type": "semantic",
      "kind": "decision",
      "source_type": "manual",
      "version": 1,
      "score": 0.94,
      "matched_by": ["text", "semantic"]
    }
  ],
  "interpretation": {"intents": ["decisions"], "search_terms": ["decidimos", "riego"]},
  "warnings": []
}
```

(Salida real, recortada.) Si la memoria no contiene la respuesta, `confirmed` llega vacío y
`not_found` lo dice: `"No encontré recuerdos sobre «capital, mongolia»."`

### Buscar

```bash
curl -s http://localhost:8000/api/v1/search \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query": "riego", "limit": 5}'
```

Cada resultado trae `memory`, `score`, `matched_by`, `text_rank`, `semantic_similarity`,
`excerpt` y `score_breakdown`. Consulta los filtros disponibles en `/docs`.
