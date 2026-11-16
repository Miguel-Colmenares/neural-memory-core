# Guía de uso del panel

Todo lo que muestra el panel sale de la API en el momento de abrir cada página. No hay datos
de ejemplo: una instalación nueva aparece vacía.

## Panel

Indicadores calculados desde la base: recuerdos, proyectos, relaciones, versiones guardadas,
tareas abiertas, estado del índice vectorial, reparto por tipo, procedencia y estado, y la
actividad más reciente.

## Recuerdos

**Nuevo recuerdo.** Solo el contenido es obligatorio.

| Campo | Para qué |
| --- | --- |
| Tipo de memoria | Déjalo en «Automático» y el sistema lo decide por reglas, dejando anotada cuál aplicó. |
| Clase | Algo más concreto: `decision`, `idea`, `concept`… |
| Proyecto | Asocia el recuerdo a un proyecto. |
| Etiquetas | Separadas por comas. El sistema añade algunas automáticas. |
| Importancia | De 1 a 5. Los importantes suben en los resultados. |
| Procedencia | De dónde sale: una reunión, una URL, un libro. Aparece como fuente en las respuestas. |

Al guardar, el sistema indica si lo creó, si ya existía uno idéntico (no lo duplica) y qué
relaciones detectó con otros recuerdos.

**Explorar.** Filtra por tipo, proyecto, etiqueta y estado, y ordena por fecha o importancia.

**Detalle de un recuerdo.**

- **Editar** crea una versión nueva; la anterior queda en "Historial de versiones". Puedes
  indicar el motivo del cambio.
- **Ver contenido** de cualquier versión y **revertir** a ella. Revertir también crea una
  versión nueva: nunca se pierde historial.
- **Archivar** lo oculta de las búsquedas sin borrarlo. **Reactivar** lo devuelve.
- **Eliminar** es definitivo: borra el recuerdo y sus versiones. Queda constancia en el
  historial de que existió, sin su contenido.
- **Relaciones**: enlaza con otro recuerdo pegando su identificador y eligiendo el tipo
  (`related`, `contradicts`, `supersedes`…).

## Buscador

Dos modos:

- **Responder con fuentes.** Escribe una pregunta. La respuesta se divide en:
  - *Confirmado por tus recuerdos* (verde): hechos con su fuente numerada.
  - *Inferencias del sistema* (amarillo): deducciones, explicando en qué se basan.
  - *No encontrado* (gris): lo que preguntaste y no está en la memoria.

  Debajo aparecen las fuentes utilizadas, con enlace a cada recuerdo.

- **Listar recuerdos.** Resultados ordenados, con el motivo de cada coincidencia (texto,
  parecido, relación) y su puntuación.

Preguntas que el sistema sabe interpretar:

- «¿Qué decisiones había tomado en mi último proyecto?»
- «¿Qué cambios hice desde la última versión?»
- «¿Qué relación existe entre el proyecto A y el proyecto B?»
- «Busca información reciente sobre el riego.»
- «¿Qué tengo pendiente en el proyecto A?»

Puedes acotar por tipo de memoria, proyecto y fechas.

## Proyectos

Cada proyecto tiene su espacio: descripción, objetivos, decisiones, tareas, documentación,
conversaciones, recuerdos recientes, relaciones con otros proyectos e historial de cambios.

- **Registrar decisión** guarda un recuerdo de clase `decision` asociado al proyecto.
- **Tareas**: añádelas y márcalas como hechas desde la misma página.
- **Relaciones con otros proyectos**: indica, por ejemplo, que uno continúa otro.

## Documentos

Sube un archivo de texto o PDF, o escribe una nota. El texto se extrae, se divide en
fragmentos para la búsqueda y se guarda con los datos del archivo original (nombre, tipo,
tamaño, huella). Los PDF escaneados sin texto se rechazan: no hay OCR.

## Relaciones

Grafo de recuerdos: cada punto es un recuerdo (el color indica el tipo) y cada línea una
relación. Línea continua: la creaste tú. Línea discontinua: la detectó el sistema por
parecido. Pulsa un punto para ver sus relaciones.

## Historial

Registro de todo lo que ha cambiado (creaciones, actualizaciones, archivados, eliminaciones,
importaciones, respaldos), con fecha y autor.

## Proveedores de IA

Muestra qué proveedor de embeddings y qué modelo de lenguaje están activos, si son gratuitos
y si envían datos fuera. **Las claves nunca se muestran ni se guardan en la base**: se
configuran en `.env`. Desde aquí puedes probar la conexión y reindexar.

## Almacenamiento

Tamaño de la base y de cada tabla, y respaldos: crear, descargar y eliminar. Solo
administradores.

## Exportar e importar

Descarga toda la memoria en un archivo JSON o importa uno. Importar fusiona: nunca
sobrescribe lo existente. Ver [respaldos y recuperación](respaldos_y_recuperacion.md).
