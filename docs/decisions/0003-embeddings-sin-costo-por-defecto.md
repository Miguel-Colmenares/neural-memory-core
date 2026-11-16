# 0003. Embeddings locales y gratuitos por defecto, dimensión fija de 384

Estado: Aceptada · Fecha: 2026-11-16

## Contexto

El sistema debe funcionar sin claves de API ni servicios de pago, y a la vez ofrecer
búsqueda por significado a quien la quiera. La columna vectorial de pgvector tiene una
dimensión fija.

## Decisión

Tres proveedores tras una misma interfaz (`EmbeddingProvider`), todos de 384 dimensiones:

1. `hashing` (por defecto): *feature hashing* de palabras y trigramas. Sin dependencias, sin
   red, determinista. Parecido léxico, no semántico.
2. `fastembed`: modelo multilingüe MiniLM ejecutado en local. Gratis; semántico.
3. `openai`: cualquier API compatible, solicitando 384 dimensiones. Puede costar.

Cada vector guarda su proveedor y modelo; la búsqueda solo compara vectores del proveedor
activo y existe una operación de reindexado.

## Alternativas

- **Exigir una clave de OpenAI.** Descartado: incumple "funcionar sin servicios de pago" y
  envía datos privados fuera por defecto.
- **FastEmbed como valor por defecto.** Descartado: obliga a descargar unos 220 MB en el
  primer arranque y hace que las pruebas dependan de la red.
- **Dimensión configurable.** Descartado: exigiría migraciones al cambiar de modelo.

## Consecuencias

- La instalación por defecto es honesta sobre su límite: el panel y la API indican que
  `hashing` no entiende sinónimos (`"semantic": false`).
- Las pruebas son rápidas y reproducibles.
- Un modelo que no pueda producir 384 dimensiones no es compatible.
