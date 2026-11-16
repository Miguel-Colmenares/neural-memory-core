# Guía de instalación

Hay dos formas de instalar Neural Memory Core. Usa Docker salvo que quieras desarrollar.

## Opción A: Docker Compose (recomendada)

### Requisitos

- Docker Engine 24 o posterior con el complemento Docker Compose.
- Unos 2 GB de disco libres (1 GB si usas la imagen ligera).

### Pasos

1. **Descarga el código.**

   ```bash
   git clone https://github.com/Miguel-Colmenares/neural-memory-core.git
   cd neural-memory-core
   ```

2. **Crea tu archivo de configuración.**

   ```bash
   cp .env.example .env
   ```

3. **Rellena los tres valores obligatorios** en `.env`:

   ```ini
   POSTGRES_PASSWORD=una-contraseña-larga-para-la-base
   NMC_SECRET_KEY=pega-aquí-la-clave-generada
   NMC_ADMIN_PASSWORD=tu-contraseña-de-acceso
   ```

   Genera la clave secreta con:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   `NMC_ADMIN_PASSWORD` debe tener al menos 10 caracteres. El archivo `.env` no se sube a
   Git; guárdalo en un gestor de contraseñas.

4. **Arranca.**

   ```bash
   docker compose up -d --build
   ```

   La primera vez tarda varios minutos porque construye las imágenes.

5. **Comprueba que funciona.**

   ```bash
   curl http://localhost:8000/health
   # {"status":"ok","database":"ok","version":"0.1.0"}
   ```

   Abre <http://localhost:3000> y entra con `admin` y tu contraseña.

### Qué se ha creado

| Servicio | Dirección | Notas |
| --- | --- | --- |
| Panel web | `127.0.0.1:3000` | |
| API | `127.0.0.1:8000` | Documentación en `/docs` |
| Base de datos | no expuesta | Solo accesible dentro de la red de Docker |

Los puertos solo escuchan en tu propio equipo. Para acceder desde otros dispositivos lee la
[guía de despliegue](despliegue.md).

Tus datos están en el volumen de Docker `neural-memory-core_nmc_pgdata` y los respaldos en
la carpeta `backups/`. Ninguno de los dos forma parte del repositorio.

### Operaciones habituales

```bash
docker compose logs -f api          # ver registros
docker compose down                 # parar (los datos se conservan)
docker compose up -d                # volver a arrancar
git pull && docker compose up -d --build   # actualizar
```

> `docker compose down -v` **borra el volumen con tus recuerdos**. No uses `-v` salvo que
> quieras empezar de cero y tengas un respaldo.

### Imagen ligera

La imagen de la API incluye FastEmbed (modelo local de embeddings). Si no vas a usarlo:

```ini
NMC_IMAGE_EXTRAS=
```

y reconstruye con `docker compose up -d --build`.

### Cambiar los puertos

```ini
NMC_API_PORT=8010
NMC_WEB_PORT=3010
NEXT_PUBLIC_API_URL=http://localhost:8010
NMC_CORS_ORIGINS=http://localhost:3010
```

`NEXT_PUBLIC_API_URL` se fija al compilar el panel, así que hay que reconstruir
(`docker compose up -d --build`). Si `NMC_CORS_ORIGINS` no coincide con la dirección desde la
que abres el panel, el inicio de sesión fallará.

## Opción B: instalación manual (desarrollo)

### Requisitos

- Python 3.11 o posterior
- Node.js 20 o posterior
- PostgreSQL 15 o posterior con la extensión [pgvector](https://github.com/pgvector/pgvector)
- Las herramientas cliente de PostgreSQL (`pg_dump`, `pg_restore`) para los respaldos

### Base de datos

Lo más simple es usar solo la base en Docker:

```bash
docker run -d --name nmc-db -p 5432:5432 \
  -e POSTGRES_USER=nmc -e POSTGRES_PASSWORD=nmc -e POSTGRES_DB=nmc \
  -v nmc_dev_data:/var/lib/postgresql/data pgvector/pgvector:pg17
```

Con un PostgreSQL propio, el usuario debe poder crear la extensión `vector`, o créala antes
como superusuario: `CREATE EXTENSION vector;`

### API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"            # añade ,local-embeddings para FastEmbed
cp .env.example .env
```

En `.env`, además de `NMC_SECRET_KEY` y `NMC_ADMIN_PASSWORD`, define la conexión:

```ini
NMC_DATABASE_URL=postgresql+psycopg://nmc:nmc@localhost:5432/nmc
```

```bash
alembic upgrade head                           # crea el esquema
uvicorn apps.api.main:app --reload --port 8000
```

### Panel web

```bash
cd apps/web
npm ci
npm run dev        # http://localhost:3000
```

### Pruebas

```bash
createdb -h localhost -U nmc nmc_test     # una base aparte; las pruebas la vacían
export NMC_TEST_DATABASE_URL=postgresql+psycopg://nmc:nmc@localhost:5432/nmc_test
pytest
```

## Variables de configuración

Todas están documentadas en [`.env.example`](../../.env.example). Resumen:

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `NMC_SECRET_KEY` | — (obligatoria) | Firma de los tokens. Mínimo 32 caracteres. |
| `NMC_ADMIN_USERNAME` / `NMC_ADMIN_PASSWORD` | — | Crea el primer administrador si no hay usuarios. |
| `NMC_DATABASE_URL` | local | Conexión a PostgreSQL. |
| `NMC_ENVIRONMENT` | `development` | `production` oculta `/docs` y endurece comprobaciones. |
| `NMC_CORS_ORIGINS` | `http://localhost:3000` | Direcciones del panel autorizadas. |
| `NMC_ACCESS_TOKEN_MINUTES` | `720` | Duración de la sesión. |
| `NMC_EMBEDDING_PROVIDER` | `hashing` | `hashing`, `fastembed` u `openai`. |
| `NMC_LLM_PROVIDER` | `none` | `none` u `openai`. |
| `NMC_ENABLED_MODULES` | todos | Módulos activos, separados por comas. |
| `NMC_BACKUP_DIR` | `./backups` | Carpeta de respaldos. |
| `NMC_MAX_UPLOAD_MB` | `20` | Tamaño máximo de archivo. |

## Problemas frecuentes

| Síntoma | Causa y solución |
| --- | --- |
| La API no arranca: «NMC_SECRET_KEY no está definida…» | Falta la clave o tiene menos de 32 caracteres. |
| `docker compose` dice «Define POSTGRES_PASSWORD en .env» | No existe `.env` o falta ese valor. |
| El panel muestra un error de red al entrar | `NEXT_PUBLIC_API_URL` o `NMC_CORS_ORIGINS` no coinciden con las direcciones reales. |
| No recuerdo la contraseña | `docker compose exec -u nmc api python scripts/manage.py create-user otro-admin` crea otro administrador. |
| Cambié `POSTGRES_PASSWORD` y la API ya no conecta | La contraseña de la base se fija al crear el volumen. Vuelve a la anterior o cámbiala dentro de PostgreSQL con `ALTER USER`. |
