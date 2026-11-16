#!/bin/sh
# Respaldo diario de Neural Memory Core. Ejemplo para cron:
#   0 3 * * * /ruta/a/neural-memory-core/infrastructure/deployment/backup-cron.sh >> /var/log/nmc-backup.log 2>&1
#
# Variables opcionales:
#   NMC_KEEP_DAYS   días que se conservan los respaldos locales (14 por defecto)
#   NMC_OFFSITE     destino de rsync fuera del servidor, p. ej. usuario@equipo:/copias/nmc/
set -eu

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
KEEP_DAYS="${NMC_KEEP_DAYS:-14}"

cd "$REPO_DIR"
docker compose exec -T -u nmc api python scripts/manage.py backup --label diario
find "$REPO_DIR/backups" -name 'nmc-backup-*.dump' -mtime +"$KEEP_DAYS" -delete

if [ -n "${NMC_OFFSITE:-}" ]; then
    rsync -a "$REPO_DIR/backups/" "$NMC_OFFSITE"
else
    echo "AVISO: NMC_OFFSITE no está definida; el respaldo solo existe en este servidor." >&2
fi
