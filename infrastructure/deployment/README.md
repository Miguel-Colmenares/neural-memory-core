# Despliegue

Archivos de apoyo para desplegar en un servidor propio. La guía paso a paso está en
[`docs/user_guide/despliegue.md`](../../docs/user_guide/despliegue.md).

| Archivo | Para qué |
| --- | --- |
| `Caddyfile.example` | Proxy inverso con HTTPS delante del panel y de la API |
| `backup-cron.sh` | Respaldo diario con rotación y copia fuera del servidor |

Estos archivos son ejemplos: no contienen dominios, usuarios ni secretos reales, y no se han
ejecutado como parte de las pruebas automáticas.
