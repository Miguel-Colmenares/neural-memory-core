# 0007. Autenticación con JWT y tres roles

Estado: Aceptada · Fecha: 2026-11-16

## Contexto

La memoria es privada. Hace falta autenticación, protección de endpoints y control de acceso,
sin depender de un proveedor de identidad externo.

## Decisión

Usuarios locales con contraseña (bcrypt), tokens JWT HS256 firmados con `NMC_SECRET_KEY` y
tres roles: `reader`, `editor`, `admin`. Todos los endpoints declaran el rol mínimo; una
prueba recorre la especificación y falla si alguno queda abierto. Límite de intentos de
inicio de sesión por dirección. La aplicación no arranca sin una clave de 32 caracteres.

## Alternativas

- **OAuth con un proveedor externo.** Descartado: dependencia y configuración innecesarias
  para una persona.
- **Sesiones con cookies.** Descartado por simplicidad: la API también se usa desde scripts.

## Consecuencias

- El panel guarda el token en `localStorage`; un fallo de XSS podría exponerlo. Se mitiga
  con React (escapa el contenido por defecto) y sin cargar código de terceros.
- No hay revocación de tokens individuales: caducan solos, y cambiar `NMC_SECRET_KEY` los
  invalida todos. Desactivar un usuario surte efecto de inmediato.
- El límite de intentos vive en memoria del proceso: se reinicia con la API.
