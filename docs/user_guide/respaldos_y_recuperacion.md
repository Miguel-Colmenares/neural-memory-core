# Respaldos y recuperación

Tu memoria está en la base de datos, no en el repositorio. Si pierdes el servidor y no tienes
un respaldo fuera de él, pierdes los recuerdos. Esta guía explica cómo evitarlo.

## Dos formas de copiar tus datos

| | Respaldo de base (`pg_dump`) | Exportación JSON |
| --- | --- | --- |
| Archivo | `nmc-backup-AAAAMMDD-HHMMSS.dump` | `nmc-export-….json` |
| Contiene | Todo: recuerdos, versiones, relaciones, proyectos, tareas, historial, **usuarios** y vectores | Recuerdos, versiones, relaciones, proyectos, historial y datos de módulos. **Sin usuarios ni vectores** |
| Al restaurar | **Reemplaza** el contenido de la base | **Fusiona**: añade lo que falta y nunca sobrescribe |
| Legible | No (formato de PostgreSQL) | Sí (texto JSON) |
| Úsalo para | Recuperación ante desastres, copias periódicas | Migrar, combinar instalaciones, conservar una copia legible a largo plazo |

Recomendación: respaldo de base diario y una exportación JSON de vez en cuando.

Ambos archivos contienen **todos tus recuerdos sin cifrar**. Trátalos como información
privada: no los subas al repositorio (el `.gitignore` ya los excluye) y cífralos si los
guardas en la nube.

## Crear un respaldo

**Desde el panel:** Almacenamiento → "Crear respaldo ahora". Desde ahí también se descarga.

**Desde la terminal:**

```bash
# Docker
docker compose exec -u nmc api python scripts/manage.py backup --label antes-de-actualizar
# Instalación manual
python scripts/manage.py backup
```

Los archivos quedan en `backups/` (carpeta `NMC_BACKUP_DIR`), con permisos solo para el
propietario.

## Automatizar

Ejemplo con `cron` en el servidor, cada día a las 3:00, conservando 14 días y copiando fuera:

```cron
0 3 * * * cd /ruta/a/neural-memory-core && docker compose exec -T -u nmc api python scripts/manage.py backup --label diario && find backups -name 'nmc-backup-*.dump' -mtime +14 -delete
30 3 * * * rsync -a /ruta/a/neural-memory-core/backups/ usuario@otro-equipo:/copias/nmc/
```

Sustituye la segunda línea por la herramienta que uses (`rclone`, `restic`, un disco
externo…). **Un respaldo que vive en el mismo servidor no protege ante la pérdida del
servidor.** Hay un guion de ejemplo en
[`infrastructure/deployment/backup-cron.sh`](../../infrastructure/deployment/backup-cron.sh).

## Restaurar un respaldo en la misma instalación

```bash
docker compose exec -u nmc api python scripts/manage.py restore /backups/nmc-backup-20261116-030000.dump
docker compose restart api
```

El comando pide escribir `restaurar` para confirmar, porque **reemplaza todo el contenido
actual**. Si dudas, crea antes un respaldo del estado actual.

## Recuperación ante la pérdida del servidor

Necesitas tres cosas guardadas **fuera** del servidor:

1. Un archivo de respaldo (`.dump`) reciente.
2. Tu archivo `.env` (o al menos `NMC_SECRET_KEY`; el resto se puede volver a escribir).
3. El código, que está en GitHub.

Pasos en un servidor nuevo:

```bash
# 1. Código
git clone https://github.com/Miguel-Colmenares/neural-memory-core.git
cd neural-memory-core

# 2. Configuración: copia tu .env guardado, o crea uno nuevo desde .env.example
cp /ruta/segura/.env .env

# 3. Arranca. Se crea una base vacía con el esquema actual.
docker compose up -d --build

# 4. Copia el respaldo a la carpeta backups/ y restáuralo
cp /ruta/segura/nmc-backup-20261116-030000.dump backups/
docker compose exec -u nmc api python scripts/manage.py restore /backups/nmc-backup-20261116-030000.dump

# 5. Aplica migraciones (por si el respaldo es de una versión anterior) y reinicia
docker compose exec -u nmc api alembic upgrade head
docker compose restart api

# 6. Comprueba
docker compose exec -u nmc api python scripts/manage.py status
```

Entra al panel con tu usuario y contraseña de siempre (los usuarios vienen en el respaldo).
Si creaste un `.env` nuevo con otra `NMC_SECRET_KEY`, solo cambia que las sesiones abiertas
dejan de valer y hay que volver a iniciar sesión.

Si en `.env` usas un proveedor de embeddings distinto al del servidor anterior, regenera los
vectores: `docker compose exec -u nmc api python scripts/manage.py reindex --all`.

### Si solo tienes una exportación JSON

```bash
docker compose up -d --build
docker compose cp nmc-export.json api:/tmp/nmc-export.json
docker compose exec -u nmc api python scripts/manage.py import /tmp/nmc-export.json
```

o desde el panel: Exportar e importar → "Importar archivo". Los vectores se regeneran durante
la importación. Los usuarios no están en la exportación: se usa el administrador definido en
`.env`.

## Exportar e importar

**Exportar:** panel → Exportar e importar → "Descargar exportación JSON", o:

```bash
docker compose exec -u nmc api python scripts/manage.py export /backups/nmc-export.json
```

**Importar** es seguro de repetir: lo que ya existe (mismo identificador) se omite, y un
recuerdo existente nunca se sobrescribe. El informe final indica cuántos elementos se
importaron y cuántos se omitieron.

## Probar que tus respaldos sirven

Un respaldo que nunca se ha restaurado es una suposición. De vez en cuando, restáuralo en
otra carpeta con otro nombre de proyecto para no tocar la instalación real:

```bash
git clone https://github.com/Miguel-Colmenares/neural-memory-core.git prueba-restauracion
cd prueba-restauracion && cp ../neural-memory-core/.env .env
# Usa otros puertos (ver guía de instalación) y arranca con otro nombre de proyecto
docker compose -p nmc-prueba up -d --build
```

y sigue los pasos 4 a 6 de arriba añadiendo `-p nmc-prueba` a cada comando. Al terminar:
`docker compose -p nmc-prueba down -v`.

## Qué se ha verificado

La suite de pruebas (`tests/integration/test_system_and_recovery.py` y
`tests/e2e/test_acceptance.py`) crea datos, hace un respaldo con `pg_dump`, destruye el
contenido, restaura con `pg_restore` y comprueba que todo vuelve; y hace lo mismo con el
ciclo exportar → vaciar → importar.
