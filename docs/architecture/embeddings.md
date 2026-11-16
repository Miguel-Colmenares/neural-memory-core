# Embeddings

Un *embedding* es un vector numérico que representa un texto, de forma que textos parecidos
tienen vectores cercanos. Neural Memory Core guarda uno por fragmento de cada recuerdo en la
tabla `memory_embeddings` y los compara con pgvector (distancia coseno, índice HNSW).

Todos los proveedores producen vectores de **384 dimensiones**, para que cambiar de proveedor
no exija cambiar el esquema.

## Proveedores

| `NMC_EMBEDDING_PROVIDER` | Costo | Entiende significado | Envía datos fuera | Requisitos |
| --- | --- | --- | --- | --- |
| `hashing` (por defecto) | Gratis | No, solo palabras parecidas | No | Ninguno |
| `fastembed` | Gratis | Sí | No (tras la descarga del modelo) | Extra `local-embeddings`; descarga ~220 MB una vez |
| `openai` | **Puede costar** | Sí | **Sí** | `NMC_EMBEDDING_API_KEY`, modelo que admita 384 dimensiones |

### `hashing`

Convierte palabras (con una raíz simple en español) y trigramas de caracteres en posiciones
de un vector. Encuentra textos que comparten vocabulario, aunque tengan erratas o variantes
("decidimos" / "decisión" no coinciden; "riego" / "riegos" sí). **No** relaciona sinónimos ni
paráfrasis. Es determinista, instantáneo y no necesita red, por eso es el valor por defecto y
el que usan las pruebas.

Combinado con la búsqueda de texto completo de PostgreSQL da buenos resultados cuando la
pregunta usa palabras parecidas a las del recuerdo.

### `fastembed`

Usa el modelo multilingüe `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
ejecutado en tu propia máquina (ONNX, sin GPU). Ofrece búsqueda por significado real.

```bash
# Instalación manual
pip install ".[local-embeddings]"
# Docker: la imagen ya lo incluye salvo que definas NMC_IMAGE_EXTRAS vacío
```

```ini
NMC_EMBEDDING_PROVIDER=fastembed
```

La primera vez descarga el modelo desde Hugging Face (unos 220 MB) y lo guarda en el volumen
`nmc_models`. Después funciona sin conexión.

> **Estado de verificación:** el código de este proveedor está implementado, pero no pudo
> ejecutarse en el entorno donde se desarrolló el proyecto porque la descarga del modelo
> estaba bloqueada por la red. Compruébalo con el botón "Probar conexión" del panel
> (Proveedores de IA) tras activarlo. Ver `PROJECT_STATUS.md`.

### `openai` (API compatible)

Sirve para OpenAI y para cualquier servidor con el mismo formato (`/v1/embeddings`).

```ini
NMC_EMBEDDING_PROVIDER=openai
NMC_EMBEDDING_MODEL=text-embedding-3-small
NMC_EMBEDDING_API_BASE=https://api.openai.com/v1
NMC_EMBEDDING_API_KEY=...
```

**Aviso de costo y privacidad:** un proveedor en la nube cobra por uso y recibe el texto de
tus recuerdos. El sistema pide 384 dimensiones; el modelo debe admitir el parámetro
`dimensions` o devolver vectores de ese tamaño.

## Cambiar de proveedor

Los vectores de proveedores distintos no son comparables. Cada fila guarda `provider` y
`model`, y la búsqueda solo usa las del proveedor activo. Después de cambiarlo hay que
regenerar los vectores:

```bash
python scripts/manage.py reindex --all
# o en Docker
docker compose exec api python scripts/manage.py reindex --all
```

También desde el panel: Proveedores de IA → "Reindexar todo". Mientras tanto, la búsqueda por
texto sigue funcionando y el panel muestra cuántos recuerdos faltan por indexar.

## Textos largos

Los textos se dividen en fragmentos de `NMC_CHUNK_CHARS` caracteres (1200 por defecto) con un
solape de `NMC_CHUNK_OVERLAP` (150), cortando por párrafos y frases cuando es posible. Un
recuerdo aparece en los resultados si cualquiera de sus fragmentos se parece a la consulta, y
el resultado indica qué fragmento coincidió.

## Umbrales

Cada proveedor declara sus propios umbrales, porque la escala de parecido es distinta:

| Umbral | Para qué | `hashing` |
| --- | --- | --- |
| `min_relevance` | Por debajo, un resultado vectorial se descarta | 0,20 |
| `related_threshold` | Por encima, se crea una relación automática `related` | 0,40 |
| `duplicate_threshold` | Por encima, se marca `possible_duplicate` | 0,90 |

Las relaciones automáticas se guardan con `origin = auto` y su confianza, y el panel las
dibuja con línea discontinua para distinguirlas de las que creas tú.
