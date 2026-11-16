# API de Neural Memory Core
FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Cliente de PostgreSQL (pg_dump / pg_restore) para los respaldos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl \
    && apt-get clean

WORKDIR /app

# "local-embeddings" instala FastEmbed (modelo semántico local). Para una imagen
# más ligera: --build-arg EXTRAS=""
ARG EXTRAS="local-embeddings"

COPY pyproject.toml VERSION README.md ./
COPY core ./core
COPY modules ./modules
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
RUN if [ -n "$EXTRAS" ]; then pip install ".[${EXTRAS}]"; else pip install .; fi

COPY alembic.ini ./
COPY infrastructure/database ./infrastructure/database
COPY scripts ./scripts
COPY infrastructure/docker/api-entrypoint.sh /usr/local/bin/api-entrypoint.sh

RUN useradd --create-home --uid 1000 nmc \
    && mkdir -p /backups /home/nmc/.cache \
    && chown -R nmc:nmc /backups /home/nmc/.cache /app \
    && chmod +x /usr/local/bin/api-entrypoint.sh
USER nmc

ENV NMC_BACKUP_DIR=/backups \
    FASTEMBED_CACHE_PATH=/home/nmc/.cache/fastembed

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["api-entrypoint.sh"]
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
