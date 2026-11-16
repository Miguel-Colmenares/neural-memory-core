#!/bin/sh
# Aplica las migraciones pendientes antes de arrancar la API.
set -e
echo "Aplicando migraciones de base de datos..."
alembic upgrade head
exec "$@"
