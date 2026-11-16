# Guía de despliegue

Neural Memory Core está pensado para que lo mantenga una sola persona con poco gasto. Estas
son las opciones, de menor a mayor exposición.

## Opción 1: en tu propio equipo (sin costo)

Es la instalación de la [guía de instalación](instalacion.md). Los servicios solo escuchan en
`127.0.0.1`, así que nadie más en la red puede acceder. Suficiente si solo lo usas desde ese
equipo.

## Opción 2: red privada (sin costo de infraestructura adicional)

Para usarlo desde tu teléfono u otros equipos sin abrirlo a Internet, instala una VPN de
malla como Tailscale o WireGuard en el servidor y en tus dispositivos, y accede por la
dirección privada. Es la opción recomendada para uso personal: no hay nada expuesto
públicamente.

Ajusta en `.env` las direcciones que usará el navegador y reconstruye:

```ini
NEXT_PUBLIC_API_URL=http://NOMBRE-O-IP-PRIVADA:8000
NMC_CORS_ORIGINS=http://NOMBRE-O-IP-PRIVADA:3000
```

Como `docker-compose.yml` publica los puertos solo en `127.0.0.1`, necesitas un proxy en el
servidor que escuche en la interfaz privada (por ejemplo Caddy, como en la opción 3) o
`tailscale serve`.

## Opción 3: servidor con dominio y HTTPS

**Aviso de costo:** un servidor virtual (VPS) y un dominio son servicios de pago. El proyecto
no los necesita para funcionar; valora primero las opciones 1 y 2. Un VPS pequeño (1 vCPU,
2 GB de RAM) basta con el proveedor `hashing`; con `fastembed` conviene tener 2 GB libres.

1. **Prepara el servidor.** Instala Docker, crea un usuario sin privilegios para la
   aplicación y activa un cortafuegos que solo permita los puertos 22, 80 y 443.

2. **Instala la aplicación** siguiendo la [guía de instalación](instalacion.md), con estos
   valores en `.env`:

   ```ini
   NMC_ENVIRONMENT=production
   NEXT_PUBLIC_API_URL=https://api.memoria.ejemplo.com
   NMC_CORS_ORIGINS=https://memoria.ejemplo.com
   ```

   `production` oculta la documentación de la API y rechaza configuraciones inseguras de CORS.

3. **Pon un proxy inverso con HTTPS delante.** Con Caddy, que obtiene los certificados solo:

   ```bash
   sudo cp infrastructure/deployment/Caddyfile.example /etc/caddy/Caddyfile
   # edita los dominios
   sudo systemctl reload caddy
   ```

   Los contenedores siguen escuchando solo en `127.0.0.1`; el único punto de entrada es el
   proxy.

4. **Programa los respaldos y su copia fuera del servidor.** Ver
   [respaldos y recuperación](respaldos_y_recuperacion.md).

## Lista de comprobación de seguridad

- [ ] `NMC_SECRET_KEY` generada al azar, de 32 caracteres o más, y guardada fuera del servidor.
- [ ] Contraseña de administrador única y larga. Tras el primer arranque puedes borrar
      `NMC_ADMIN_PASSWORD` de `.env`.
- [ ] `NMC_ENVIRONMENT=production`.
- [ ] `NMC_CORS_ORIGINS` contiene solo la dirección real del panel.
- [ ] El acceso desde fuera pasa por HTTPS o por una VPN; nunca HTTP directo.
- [ ] El puerto de PostgreSQL no está publicado (así viene por defecto).
- [ ] `.env` con permisos restringidos: `chmod 600 .env`.
- [ ] Respaldos automáticos y copiados fuera del servidor, con una restauración probada.
- [ ] Usuarios adicionales con el rol mínimo necesario (`reader` o `editor`).

## Actualizar

```bash
docker compose exec -u nmc api python scripts/manage.py backup --label antes-de-actualizar
git pull
docker compose up -d --build
```

Las migraciones de base de datos se aplican solas al arrancar la API. Lee antes el
[`CHANGELOG.md`](../../CHANGELOG.md) por si la versión indica pasos manuales.

## Usuarios adicionales

```bash
docker compose exec -u nmc api python scripts/manage.py create-user ana --role reader
```

Pide la contraseña sin mostrarla. También se pueden crear desde la API (`POST /auth/users`).

## Estado de verificación

La opción 1 se probó de principio a fin (ver `PROJECT_STATUS.md`). Las opciones 2 y 3
describen una configuración estándar pero **no se han ejecutado** como parte del desarrollo:
el `Caddyfile` es un ejemplo sin probar contra un dominio real.
