# 0004. Respuestas extractivas por defecto; modelo de lenguaje opcional y verificado

Estado: Aceptada · Fecha: 2026-11-16

## Contexto

Regla central del proyecto: el sistema nunca debe inventar información, y debe distinguir lo
confirmado, lo inferido y lo no encontrado. Los modelos de lenguaje pueden inventar.

## Decisión

- La comprensión de la pregunta se hace con reglas deterministas, no con un modelo.
- La respuesta por defecto es extractiva: frases literales de los recuerdos recuperados,
  cada una con su fuente.
- El modelo de lenguaje es opcional. Recibe solo las fuentes recuperadas, debe responder en
  JSON con las tres secciones y citar fuentes. Las afirmaciones sin cita válida se descartan.
  Ante cualquier fallo se vuelve al modo extractivo y se avisa.

## Alternativas

- **Generación libre con un modelo.** Descartado: no permite garantizar que no invente.
- **Sin modo generativo.** Descartado: un modelo local (Ollama) mejora la redacción sin
  costo, y la verificación de citas limita el riesgo.

## Consecuencias

- Sin modelo, las respuestas son citas, no redacciones: correctas pero poco elaboradas.
- El análisis por reglas cubre un conjunto finito de intenciones en español.
- La verificación comprueba que cada afirmación cita una fuente existente, no que la
  paráfrasis sea fiel. Por eso las fuentes se muestran siempre.
