#!/bin/sh
# Arranque del contenedor de la API.
# 1) Como root: garantiza que el usuario sin privilegios puede escribir en las carpetas
#    montadas (Docker crea ./backups como root si no existía).
# 2) Baja a ese usuario, aplica las migraciones pendientes y arranca la API.
set -e

if [ "$(id -u)" = "0" ]; then
    for dir in "${NMC_BACKUP_DIR:-/backups}" /home/nmc/.cache; do
        mkdir -p "$dir"
        if [ "$(stat -c %u "$dir")" != "$(id -u nmc)" ]; then
            chown nmc:nmc "$dir"
        fi
    done
    exec setpriv --reuid=nmc --regid=nmc --init-groups env HOME=/home/nmc "$0" "$@"
fi

echo "Aplicando migraciones de base de datos..."
alembic upgrade head
exec "$@"
