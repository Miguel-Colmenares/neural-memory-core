# 0001. Monolito modular en lugar de microservicios

Estado: Aceptada · Fecha: 2026-11-16

## Contexto

El sistema lo opera una sola persona, con infraestructura económica. Debe poder ampliarse con
módulos nuevos sin modificar los existentes.

## Decisión

Un único servicio de API (FastAPI) que contiene el núcleo (`core/`) y los módulos
(`modules/`) en el mismo proceso, más una base de datos y un panel web. La independencia
entre módulos se consigue con un contrato (`NMCModule`), un registro y un bus de eventos en
memoria, no con servicios separados.

## Alternativas

- **Microservicios por módulo.** Descartado: multiplica despliegues, redes y puntos de fallo
  sin beneficio para un único usuario.
- **Cola de tareas (Celery, Redis) para la ingesta.** Descartado por ahora: la ingesta de un
  recuerdo tarda milisegundos con embeddings locales. Añadiría dos servicios.

## Consecuencias

- Tres contenedores en total. Un solo proceso que vigilar.
- La ingesta de documentos muy grandes con un proveedor de embeddings remoto bloquea la
  petición mientras dura. Si llega a ser un problema, el pipeline ya está aislado y puede
  moverse a un trabajador sin cambiar los módulos.
- El bus de eventos es síncrono y local: no sirve para repartir trabajo entre procesos.
