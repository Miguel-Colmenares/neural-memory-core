# Cómo contribuir

## Flujo de trabajo

1. **Una rama por funcionalidad**, creada desde `main`:

   | Prefijo | Uso |
   | --- | --- |
   | `feat/` | Función nueva (`feat/modulo-lecturas`) |
   | `fix/` | Corrección (`fix/busqueda-acentos`) |
   | `docs/` | Solo documentación |
   | `chore/` | Mantenimiento, dependencias, CI |

2. **Commits descriptivos** con el formato [Conventional Commits](https://www.conventionalcommits.org/es/):

   ```
   feat(retrieval): añadir filtro por importancia mínima

   Explica el porqué del cambio cuando no sea evidente.
   ```

   Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`. Un commit, un cambio lógico.

3. **Pull request hacia `main`.** La integración continua (GitHub Actions) ejecuta el lint,
   las pruebas de la API y la compilación del panel. No se fusiona con la CI en rojo.

4. **Actualiza la documentación en el mismo cambio**: `CHANGELOG.md` (sección «Sin
   publicar»), `docs/` si cambia el comportamiento y `PROJECT_STATUS.md` si cambia el estado.

## Reglas del proyecto

- **Nada se declara terminado sin probar.** Toda función nueva lleva pruebas.
- **Sin funciones simuladas**: nada de datos falsos, endpoints vacíos o botones que no hacen
  nada. Si algo no está hecho, no se muestra.
- **Sin tecnologías nuevas sin justificar.** Una dependencia o servicio nuevo requiere un ADR
  en `docs/decisions/`.
- **Sin servicios de pago obligatorios.** Lo que necesite una clave de API debe ser opcional,
  estar documentado y avisar del posible costo.
- **Los recuerdos nunca se sobrescriben sin historial.** Toda modificación pasa por
  `core/memory_engine/service.py`.
- **El núcleo no depende de los módulos.** `core/` nunca importa de `modules/`.

## Nunca subas al repositorio

- Archivos `.env`, claves, tokens o contraseñas.
- Respaldos (`*.dump`), exportaciones (`nmc-export-*.json`) ni cualquier recuerdo real.
- Datos personales en pruebas, ejemplos o capturas. Usa datos inventados.

Si subes un secreto por error, considéralo comprometido: cámbialo de inmediato. Borrarlo en
un commit posterior no lo elimina del historial.

## Entorno de desarrollo

Ver [`docs/user_guide/instalacion.md`](docs/user_guide/instalacion.md), opción B.

```bash
make lint      # ruff check + ruff format --check + eslint + tipos
make format    # corrige el formato de Python
make test      # pytest (necesita PostgreSQL con pgvector)
```

Las pruebas usan la base indicada en `NMC_TEST_DATABASE_URL` y **la vacían**: nunca apuntes
esa variable a una base con datos reales.

## Estructura de las pruebas

| Carpeta | Qué prueba | Necesita base |
| --- | --- | --- |
| `tests/unit` | Funciones puras: texto, troceado, embeddings, análisis de preguntas | No |
| `tests/integration` | Núcleo y API contra PostgreSQL real | Sí |
| `tests/e2e` | Los criterios de aceptación de principio a fin, por HTTP | Sí |

## Cambios en la base de datos

1. Modifica los modelos (`core/database/models.py` o `modules/<módulo>/models.py`).
2. `alembic revision --autogenerate -m "descripción"` y **revisa** el archivo generado.
3. `alembic upgrade head` y `alembic check`.
4. Actualiza `docs/architecture/modelo_de_datos.md`.

Las migraciones ya publicadas no se editan: se añade una nueva.

## Versiones

[Versionado semántico](https://semver.org/lang/es/) en el archivo `VERSION`:

- **MAYOR**: cambios incompatibles en la API, en el formato de exportación o en el contrato
  de módulos.
- **MENOR**: funciones nuevas compatibles.
- **PARCHE**: correcciones.

Para publicar: actualiza `VERSION`, mueve «Sin publicar» a una sección con número y fecha en
`CHANGELOG.md`, fusiona en `main` y etiqueta (`git tag v0.2.0 && git push --tags`).

## Módulos nuevos

Sigue [`docs/modules/crear_modulo.md`](docs/modules/crear_modulo.md).
