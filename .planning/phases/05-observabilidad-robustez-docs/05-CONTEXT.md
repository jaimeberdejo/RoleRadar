# Phase 5: Observabilidad, Robustez y Docs n8n - Context

**Gathered:** 2026-05-23
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, defaults auto-accepted — user hands-off)

> Fase FINAL del milestone. Deja el servicio listo para portfolio y uso real:
> visible (logging + stub Langfuse), resiliente por capas, y documentado para que
> cualquiera lo instale, configure y conecte a n8n sin leer el código.

<domain>
## Phase Boundary

Cerrar el milestone con: (1) logging estructurado del flujo de cada run, (2) interfaz/stub
de Langfuse preparada para trazar el scoring, (3) manejo de errores aislado por capa, y
(4) documentación: README completo + sección dedicada a integración con n8n + ejemplos
(profile.yaml ya existe; añadir ofertas de ejemplo JSON) para probar /jobs/process sin n8n.

Fuera de boundary: cableado real completo de Langfuse (eso es OBS-04, v2 — aquí solo la
interfaz/stub). No se cambian la heurística ni los endpoints (solo se instrumentan/documentan).
</domain>

<decisions>
## Implementation Decisions

### OBS-01 — Logging estructurado
- Helper de configuración de logging en `app/obs/logging_config.py` (o `app/obs/__init__.py`):
  `configure_logging(level=INFO)` con formato consistente (timestamp, nivel, logger, mensaje).
  Llamado en el lifespan de la app.
- El pipeline de `/jobs/process` debe emitir un log estructurado por run con los CONTADORES:
  ofertas que entran, duplicados detectados (entrada vs únicas), ofertas puntuadas, errores, y
  nº de llamadas LLM (coste aproximado si se puede). Parte ya existe (Fase 4 loguea
  entradas/únicos/puntuados/errores); completar con nº de llamadas LLM.
- Mensajes en formato `clave=valor` o dict para que sean grep-ables/parseables. Sin librerías
  pesadas (stdlib `logging`). structlog opcional NO (evitar dep extra salvo que aporte).

### OBS-02 — Interfaz/stub de Langfuse
- `app/obs/tracing.py`: una abstracción fina para trazar la llamada de scoring (y CV) sin
  acoplar el código a Langfuse. Diseño: un context manager / decorador `trace_llm(name, **meta)`
  que, si `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` están en el entorno Y langfuse está
  instalado, crea un span; si no, es un **no-op** transparente. Langfuse NO se añade como
  dependencia obligatoria (import perezoso/opcional dentro del stub).
- Envolver el punto único de llamada al LLM de scoring (`app/scoring/llm.py:assess_job`) y, si
  es barato, el de CV (`app/cv/llm_client.py`) con esta interfaz. Gracias al fix de DI de Fase 4,
  el cliente es inyectable y el punto de llamada está aislado → fácil de envolver.
- Cero comportamiento nuevo cuando Langfuse no está configurado (que es el caso por defecto).

### OBS-03 — Manejo de errores por capa
- Excepciones de dominio tipadas por capa (p.ej. `CVParseError`, `NormalizationError`,
  `ScoringError`, `StorageError`) en un módulo común (`app/errors.py`) o por paquete. Las capas
  lanzan estas en vez de excepciones genéricas crudas donde aporte claridad.
- Exception handlers de FastAPI en `app/api/main.py` que mapean estas excepciones a respuestas
  JSON limpias con código HTTP claro (sobre lo ya hecho en Fase 4). Un handler genérico de
  fallback que devuelve un envelope `{error: {...}}` sin filtrar trazas internas al cliente.
- No romper la resiliencia de batch ya existente (una oferta mala → errors, no 500).

### DOC-01 — README
- Reescribir/expandir `README.md` (ya existe uno inicial) con: qué es, instalación (uv),
  `.env` (`cp .env.example .env`, claves), cómo editar `data/profile.yaml`, cómo subir el CV
  (POST /cv/parse), cómo arrancar el servicio (`uv run uvicorn app.api.main:app`), cómo correr
  tests, y el stack. Tono de portfolio (la calidad de ingeniería importa).

### DOC-02 — Sección "Integración con n8n" (en el README)
- Documentar (NO implementar en n8n): qué nodos de n8n llaman a qué endpoints; el flujo
  `Schedule → HTTP a APIs de empleo (Arbeitnow/JSearch/FlyByAPIs) → Merge → HTTP Request a
  POST /jobs/process → Filter por score → entregar (email/telegram)`; el **formato exacto del
  JSON** que n8n manda a `/jobs/process` y el que recibe (ejemplos reales con campos); y cómo
  exponer el servicio para que n8n lo alcance (localhost en dev; nota sobre desplegarlo en prod).

### DOC-03 — Ejemplos para probar sin n8n
- `examples/` con un par de ofertas crudas de ejemplo en JSON (formato Arbeitnow + genérico) y
  un ejemplo de payload completo para `POST /jobs/process`. Idealmente un comando curl o un
  pequeño script en el README para probar el flujo de inmediato. `profile.yaml` de ejemplo ya
  existe en `data/`.

### Tests
- Tests para el stub de tracing (no-op cuando Langfuse no configurado; no rompe el scoring).
- Tests para los exception handlers (una excepción de capa → JSON limpio + código correcto).
- Test de que el logging del pipeline emite los contadores esperados (caplog).
- Validar que los JSON de ejemplo de `examples/` son válidos y que /jobs/process los acepta
  (con LLM/embedder mockeados).
- Mantener verde toda la suite (162 tests actuales). Cero red.

### Claude's Discretion
- Estructura exacta de `app/obs/` y nombres de las excepciones por capa
- Si las excepciones van en un `app/errors.py` único o por paquete
- Formato exacto del log estructurado (key=value vs JSON)
- Estructura de `examples/` y si se añade un script de prueba
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/api/main.py` lifespan: punto natural para `configure_logging()`.
- `app/api/routes/jobs.py` `/jobs/process`: ya loguea contadores parciales — completar con nº LLM.
- `app/scoring/llm.py:assess_job` y `app/cv/llm_client.py`: puntos únicos de llamada LLM (envolver con tracing). El cliente es inyectable (fix DI Fase 4).
- `README.md` inicial y `data/profile.yaml` ya existen.
- Patrón de import perezoso/opcional para deps pesadas/opcionales (BGE-M3, Fase 2) → aplicar a langfuse.

### Established Patterns
- stdlib `logging` ya usado en todas las capas (logger = logging.getLogger(__name__)).
- Pydantic v2, type hints, Spanish naming. `uv add` solo si imprescindible (langfuse es opcional, NO obligatorio).
- Tests mockean LLM/embedder; cero red; app torch-free al importar.

### Integration Points
- El stub de Langfuse se cablea de verdad en OBS-04 (v2). Aquí solo la interfaz.
- La doc de n8n describe el contrato de /jobs/process ya implementado en Fase 4.
</code_context>

<specifics>
## Specific Ideas

- Es pieza de portfolio: el README debe lucir y la sección n8n debe ser accionable (JSON exacto).
- Honestidad y claridad por encima de features: el valor es que se entienda y se pueda usar/enseñar.
- Langfuse OPCIONAL: el servicio funciona perfecto sin él; el stub no debe añadir fricción.
</specifics>

<deferred>
## Deferred Ideas

- OBS-04 (v2): cableado completo de Langfuse con trazas reales de coste/latencia.
- STORE-04 (v2): métricas/analítica sobre el histórico.
- Autenticación de la API (fuera de scope — herramienta personal en red privada/localhost).
</deferred>
