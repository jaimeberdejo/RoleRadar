# Phase 5: Observabilidad, Robustez y Docs n8n - Research

**Researched:** 2026-05-23
**Domain:** Observabilidad (logging + Langfuse stub), manejo de errores por capa (FastAPI exception handlers), documentación técnica (README + n8n integration)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**OBS-01 — Logging estructurado**
- `app/obs/logging_config.py` (o `app/obs/__init__.py`): `configure_logging(level=INFO)`, llamado en el lifespan de la app.
- `/jobs/process` emite un log por run con contadores: ofertas que entran, duplicados detectados, ofertas únicas, puntuadas, errores, nº de llamadas LLM.
- Formato `clave=valor` o dict. stdlib `logging` únicamente. Sin structlog ni otras deps.

**OBS-02 — Interfaz/stub de Langfuse**
- `app/obs/tracing.py`: `trace_llm(name, **meta)` context manager/decorador.
- NO-OP transparente cuando `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` no están configurados O langfuse no está instalado.
- langfuse es una dependencia OPCIONAL: import perezoso dentro del stub, jamás se añade al `pyproject.toml`.
- Envolver `app/scoring/llm.py:assess_job` y (si es barato) `app/cv/llm_client.py:extract_cv_profile`.

**OBS-03 — Manejo de errores por capa**
- Excepciones tipadas: `CVParseError`, `NormalizationError`, `ScoringError`, `StorageError` en módulo común (`app/errors.py`) o por paquete.
- Exception handlers de FastAPI en `app/api/main.py` → JSON limpio con código HTTP claro.
- Handler genérico de fallback: envelope `{"error": {...}}` sin stack trace al cliente.
- No romper la resiliencia de batch ya existente.

**DOC-01 — README**
- Reescribir/expandir con: qué es, instalación (uv), `.env`, cómo editar `data/profile.yaml`, cómo subir el CV (`POST /cv/parse`), cómo arrancar (`uv run uvicorn app.api.main:app`), cómo correr tests, stack. Tono de portfolio.

**DOC-02 — Sección "Integración con n8n"**
- Flujo: Schedule → HTTP a APIs de empleo (Arbeitnow/JSearch/FlyByAPIs) → Merge → HTTP Request a POST /jobs/process → Filter por score → email/telegram.
- Formato EXACTO del JSON de request y response de `/jobs/process`.
- Cómo exponer el servicio para n8n (localhost dev; nota prod).

**DOC-03 — Ejemplos para probar sin n8n**
- `examples/` con ofertas crudas en formato Arbeitnow + genérico y payload completo para `POST /jobs/process`.

### Claude's Discretion
- Estructura exacta de `app/obs/` y nombres de las excepciones por capa
- Si las excepciones van en un `app/errors.py` único o por paquete
- Formato exacto del log estructurado (key=value vs JSON)
- Estructura de `examples/` y si se añade un script de prueba

### Deferred Ideas (OUT OF SCOPE)
- OBS-04 (v2): cableado completo de Langfuse con trazas reales de coste/latencia.
- STORE-04 (v2): métricas/analítica sobre el histórico.
- Autenticación de la API.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-01 | Logging estructurado (contadores por run: entradas, duplicados, únicos, puntuadas, errores, nº llamadas LLM) | stdlib logging ya presente en todas las capas; `configure_logging()` se añade en `app/obs/`; el pipeline ya loguea contadores parciales en `process_jobs` (falta nº LLM calls — counter local en el loop) |
| OBS-02 | Interfaz/stub Langfuse preparada (no-op cuando langfuse no instalado/configurado) | langfuse 4.6.1 disponible en PyPI; no instalado actualmente; patrón try/except de import lazy + contextmanager no-op verificado viable; APIs `@observe` y `start_as_current_observation` confirmadas en Context7 |
| OBS-03 | Manejo de errores por capa: excepciones tipadas + FastAPI exception handlers → JSON limpio | `@app.exception_handler(ExcClass)` con JSONResponse confirmado en Context7; handler genérico de fallback con `Exception` como tipo; ningún stack trace al cliente |
| DOC-01 | README expandido: instalación, .env, profile.yaml, CV upload, run, tests, stack | Contenido actual del README es mínimo (fase 1); `.env.example` ya existe; comandos verificados en el repo |
| DOC-02 | Sección n8n con JSON EXACTO de /jobs/process | `ProcessRequest`/`ProcessResponse` leídos del código real — shapes documentados en esta investigación |
| DOC-03 | `examples/` con payloads Arbeitnow + genérico | `arbeitnow_mapper` y `generic_mapper` leídos; fixtures `sample_arbeitnow_payload` y `sample_generic_payload` ya existen en conftest y son la referencia canónica |
</phase_requirements>

---

## Summary

Esta es la fase de cierre del milestone. No hay nueva lógica de negocio; el trabajo es instrumentar, hacer robusto y documentar lo que ya existe. Las tres áreas se implementan de forma independiente (no hay dependencias entre OBS-02, OBS-03 y DOC) y son todas de complejidad baja-media.

El riesgo más alto es OBS-02: Langfuse 3.x (API `@observe`) y Langfuse 4.x (nuevo SDK OTel-based con `Langfuse.start_as_current_observation`) son APIs radicalmente distintas. La versión disponible en PyPI es 4.6.1 (confirmado). La fase solo necesita un STUB — un no-op que, cuando Langfuse esté instalado y configurado, pueda envolverse. El stub debe aislarse detrás de un `try/except ImportError` para que el servicio funcione perfectamente sin el paquete instalado.

El resto es trabajo de craft: el logging estructurado ya existe parcialmente en el pipeline, los exception handlers de FastAPI son simples, y el README necesita expansión pero tiene base sólida. La parte más laboriosa es DOC-02: extraer el JSON exacto de los contratos ya implementados y presentarlo de forma accionable para quien configure n8n.

**Primary recommendation:** Implementar en orden OBS-01 → OBS-03 → OBS-02 (tracing stub al final porque depende de que el punto de llamada LLM esté limpio). DOC-01/02/03 en paralelo al OBS-01.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Structured logging (configure_logging) | API / Backend — app/obs/ | — | Configuración de logging es setup de la app en el lifespan |
| Per-run counters logging | API / Backend — app/api/routes/jobs.py | — | Los contadores se acumulan dentro de process_jobs, el único orquestador |
| LLM call tracing (Langfuse stub) | API / Backend — app/obs/tracing.py | — | Envuelve los puntos LLM de las capas de scoring y CV |
| Typed domain exceptions | API / Backend — app/errors.py | Todas las capas lanzan | Módulo de errores es transversal; los handlers viven en la capa API |
| FastAPI exception handlers | API — app/api/main.py | — | Los handlers se registran en la instancia FastAPI |
| README + n8n section | Documentation | — | Archivos de texto, no lógica de ejecución |
| examples/ payloads | Documentation / DX | — | Archivos JSON estáticos de referencia |

---

## Standard Stack

### Core (ya instalado — solo se documenta)

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| FastAPI | 0.136.1 | Web framework + exception handlers | `@app.exception_handler` API verificada [VERIFIED: Context7] |
| Pydantic v2 | 2.13.4 | Modelos de error y respuesta | Ya usado en toda la app |
| stdlib `logging` | Python 3.13 built-in | Logging estructurado | Ya presente en todas las capas |
| uvicorn | 0.47.0 | ASGI server | Arranque documentado en README |

### Opcional (NO se añade a pyproject.toml)

| Library | Version | Purpose | Installation |
|---------|---------|---------|-------------|
| langfuse | 4.6.1 | Observabilidad LLM (OBS-02 stub) | `uv add langfuse` — solo si el usuario quiere activarlo |

**Version verification:**
- langfuse 4.6.1 — confirmado `pip index versions langfuse` (2026-05-23) [VERIFIED: npm/pip registry]
- FastAPI 0.136.1 — instalado en el repo [VERIFIED: uv venv]
- Langfuse NOT in pyproject.toml — confirmado ausente [VERIFIED: codebase grep]

---

## Architecture Patterns

### System Architecture Diagram

```
.env + LANGFUSE_PUBLIC_KEY?
           │
           ▼
   app/obs/tracing.py        app/obs/logging_config.py
   trace_llm() context mgr   configure_logging()
      │    (no-op if          │    (stdlib logging)
      │     not configured)   │
      │                       ▼
      │              lifespan(app) ────── registra exception handlers
      │                                          │
      │                              app/errors.py
      │                              CVParseError
      │                              ScoringError
      │                              NormalizationError
      │                              StorageError
      │                                    │
      │                              @app.exception_handler
      │                              → JSONResponse {error: {...}}
      │
      ▼
app/scoring/llm.py:assess_job()    ←── envuelto por trace_llm()
app/cv/llm_client.py:extract_cv_profile() ←── envuelto por trace_llm()
      │
      │  (llm_calls_counter++)
      ▼
process_jobs() en jobs.py
  → logger.info("run: entradas=%d unicos=%d puntuados=%d llm_calls=%d errores=%d", ...)
```

### Recommended Project Structure (nuevos ficheros)

```
app/
├── obs/
│   ├── __init__.py          # vacío o re-exports
│   ├── logging_config.py    # configure_logging(level=INFO) 
│   └── tracing.py           # trace_llm() no-op stub
├── errors.py                # CVParseError, NormalizationError, ScoringError, StorageError
examples/
├── arbeitnow_offers.json    # 2 ofertas en formato Arbeitnow real
├── generic_offers.json      # 2 ofertas en formato genérico  
└── process_request.json     # payload completo para POST /jobs/process
```

### Pattern 1: Optional Import No-Op Stub (OBS-02)

**What:** `trace_llm` es un context manager que es un no-op transparente cuando langfuse no está instalado o no está configurado. Cuando SÍ está instalado y configurado (LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY en el entorno), crea una span de observación.

**When to use:** Cualquier punto de llamada LLM donde se quiera trazabilidad futura sin penalizar la app hoy.

**Canonical implementation:**

```python
# app/obs/tracing.py
# Source: Context7 /langfuse/langfuse-python — @observe and start_as_current_observation
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

_LANGFUSE_CONFIGURED = (
    bool(os.environ.get("LANGFUSE_PUBLIC_KEY"))
    and bool(os.environ.get("LANGFUSE_SECRET_KEY"))
)

@contextmanager
def trace_llm(name: str, **meta: Any) -> Generator[None, None, None]:
    """Context manager que traza una llamada LLM con Langfuse (si está disponible).

    No-op silencioso cuando:
    - langfuse no está instalado (ImportError)
    - LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY no están en el entorno

    Uso:
        with trace_llm("assess_job", job_id=job.id, model=model):
            result = client.messages.create(...)
    """
    if not _LANGFUSE_CONFIGURED:
        yield
        return

    try:
        from langfuse import Langfuse  # noqa: PLC0415 — import perezoso/opcional
    except ImportError:
        yield
        return

    # Langfuse 4.x API (OTel-based): start_as_current_observation como context manager
    lf = Langfuse()
    with lf.start_as_current_observation(name=name, as_type="generation", metadata=meta):
        yield
```

**Key design notes:**
- `_LANGFUSE_CONFIGURED` se evalúa UNA VEZ al importar el módulo (variables de entorno no cambian en runtime).
- El `try/except ImportError` dentro del bloque de ejecución es el segundo nivel de protección: si langfuse está configurado pero no instalado, el no-op actúa igual.
- El flag se puede re-evaluar en tests con `monkeypatch.setenv` + `importlib.reload` si se necesita.
- Esta es la interfaz stub (OBS-02); el cableado completo (flush, shutdown, uso de `update_current_generation` para coste) es OBS-04.

**IMPORTANTE — Langfuse v4 vs v3:** La API ha cambiado radicalmente entre versiones. En v3 existía `@observe` como decorador simple con módulo-level Langfuse singleton. En v4 (4.x, versión actual 4.6.1) el cliente es OTel-based y la API recomendada para envolver código es `langfuse.start_as_current_observation(name=..., as_type="generation")` como context manager. El decorador `@observe` sigue existiendo en v4 pero el context manager es más flexible para este caso (no modifica la firma de `assess_job`). [VERIFIED: Context7 /langfuse/langfuse-python]

### Pattern 2: FastAPI Exception Handlers (OBS-03)

**What:** Registrar handlers para las excepciones de dominio + un fallback genérico. Todos devuelven JSONResponse con envelope consistente `{"error": {"type": str, "message": str}}`.

**When to use:** Cualquier excepción que las capas lanzan y que no está ya siendo capturada batch-resiliente.

**Implementation:**

```python
# En app/api/main.py — añadir ANTES de include_router
# Source: Context7 /fastapi/fastapi — exception_handler
from fastapi import Request
from fastapi.responses import JSONResponse
from app.errors import CVParseError, NormalizationError, ScoringError, StorageError

@app.exception_handler(CVParseError)
async def cv_parse_error_handler(request: Request, exc: CVParseError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"type": "CVParseError", "message": str(exc)}})

@app.exception_handler(ScoringError)
async def scoring_error_handler(request: Request, exc: ScoringError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"type": "ScoringError", "message": str(exc)}})

@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": {"type": "StorageError", "message": str(exc)}})

@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Fallback: no filtrar stack trace al cliente. Solo tipo y mensaje.
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"error": {"type": type(exc).__name__, "message": "Internal server error"}})
```

**CRITICAL — ordering:** Los handlers más específicos deben registrarse ANTES del genérico (`Exception`). FastAPI/Starlette usa el primer handler que coincida con el tipo (exacto o subclase). Si el handler genérico se registra primero, nunca se alcanzarán los específicos. [VERIFIED: Context7 /fastapi/fastapi]

**CRITICAL — batch resilience:** Los exception handlers SOLO interceptan excepciones que propaguen hasta el nivel del router. Las excepciones dentro del loop de scoring en `process_jobs` ya están capturadas por `try/except Exception` internamente (batch-resiliente). Los handlers de capa son para errores que NO deben caer en ese catch interno (ej. fallo de storage al leer, configuración rota). No romper ese invariante.

### Pattern 3: Structured Logging (OBS-01)

**What:** `configure_logging()` establece un formatter consistente. El pipeline de `/jobs/process` emite un log final con todos los contadores.

**Implementation:**

```python
# app/obs/logging_config.py
import logging
import sys

def configure_logging(level: int = logging.INFO) -> None:
    """Configura el logging de la aplicación con formato key=value consistente.
    
    Llamado en el lifespan de la app (app/api/main.py).
    Idempotente: si el root logger ya tiene handlers, no duplica.
    """
    root = logging.getLogger()
    if root.handlers:
        return  # ya configurado (ej. en tests con caplog)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(handler)
    root.setLevel(level)
```

**Counter pattern para LLM calls en process_jobs:**

```python
# En app/api/routes/jobs.py, en process_jobs()
llm_calls = 0
for job in unique_jobs:
    ya_visto = storage.was_seen(job.id)
    try:
        score = score_job(job, cv_profile, user_profile, client=scoring_client)
        llm_calls += 1  # score_job hace exactamente 1 llamada LLM por job
        scored.append(ScoredJobConVisto(job=job, score=score, ya_visto=ya_visto))
    except Exception as exc:
        all_errors.append({"job_id": job.id, "error": str(exc)})
        logger.warning("process_jobs: error puntuando job=%s: %s", job.id, exc)

logger.info(
    "process_jobs: entradas=%d unicos=%d puntuados=%d llm_calls=%d errores=%d",
    sum(len(b.offers) for b in body.sources),
    len(unique_jobs),
    len(scored),
    llm_calls,
    len(all_errors),
)
```

**Note:** El log actual en `process_jobs` (línea 237-243 de jobs.py) ya existe pero falta el contador `llm_calls`. Este es el único campo que añadir.

### Anti-Patterns to Avoid

- **Hacer langfuse una dependencia hard:** No añadir `langfuse` a `pyproject.toml`. La instalación opcional debe ser un paso manual documentado en el README.
- **Evaluar env vars langfuse en cada llamada:** Evaluar `_LANGFUSE_CONFIGURED` al importar el módulo (una vez) en lugar de en cada invocación de `trace_llm`. Reduce overhead a cero cuando está desactivado.
- **Handler genérico antes que los específicos:** Registrar `Exception` primero silencia todos los handlers específicos.
- **Filtrar stack trace al cliente:** El handler genérico logea el stack completo (`logger.exception`) pero al cliente solo devuelve tipo y mensaje.
- **Llamar a `langfuse.flush()` en cada traza:** En producción, el SDK de Langfuse 4.x gestiona el flush automáticamente con un background thread. No llamar a `flush()` en cada span (performance). El flush en shutdown pertenece a OBS-04.
- **Crear instancia `Langfuse()` en cada llamada a `trace_llm`:** Para la fase stub (v1) es aceptable dado que es el path lento (solo si configurado). Para OBS-04 se moverá a singleton.
- **`configure_logging()` duplica handlers en tests:** Verificar `if root.handlers: return` hace la función idempotente.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Context manager no-op | Clase con `__enter__`/`__exit__` manual | `@contextlib.contextmanager` + `yield` | stdlib, más limpio, manejador de excepciones incluido |
| JSON error envelopes | Serialización manual | `fastapi.responses.JSONResponse(content={...})` | FastAPI ya serializa el `content` dict a JSON correctamente |
| Exception class hierarchy | Herencia compleja | Simple `class CVParseError(Exception): pass` | No necesitan campos extras para esta fase; str(exc) es suficiente |
| Log format parsing | Regex sobre logs en texto libre | Formato `key=value` en el mensaje | grep-able sin parser extra; compatible con cualquier log aggregator |

**Key insight:** Esta fase es instrumentación, no nuevo código de negocio. Todas las piezas son stdlib + FastAPI builtin. No se añaden dependencias (salvo langfuse opcional).

---

## Common Pitfalls

### Pitfall 1: Langfuse v3 vs v4 API incompatible
**What goes wrong:** Usar la API de langfuse v2/v3 (decorador `@observe` con import `from langfuse.decorators import observe`) que muchos tutoriales muestran, cuando la versión instalada es 4.x. En v4 la API ha cambiado a OTel-based.
**Why it happens:** La documentación online tiene mucho contenido de v2/v3.
**How to avoid:** Usar la API de v4: `Langfuse().start_as_current_observation(name=..., as_type="generation")` como context manager. [VERIFIED: Context7 /langfuse/langfuse-python]
**Warning signs:** `ImportError: cannot import name 'observe' from 'langfuse'` o comportamiento diferente al esperado.

### Pitfall 2: ImportError cuando langfuse instalado pero env vars ausentes
**What goes wrong:** El import funciona pero `Langfuse()` lanza `AuthenticationError` al inicializar sin credenciales.
**Why it happens:** El constructor intenta conectar/validar con la plataforma.
**How to avoid:** El doble-check: primero evaluar `_LANGFUSE_CONFIGURED` (env vars presentes), LUEGO intentar el import. Si el check falla, yield inmediato sin tocar Langfuse.
**Warning signs:** Tests que mockean env vars fallan con AuthenticationError.

### Pitfall 3: configure_logging() añade handlers duplicados
**What goes wrong:** Si `configure_logging()` se llama más de una vez (en tests, en reload), cada llamada añade un StreamHandler al root logger, duplicando cada línea de log.
**Why it happens:** `logging.basicConfig` tiene protección incorporada, pero un setup manual no.
**How to avoid:** Verificar `if root.handlers: return` al inicio de `configure_logging()`.
**Warning signs:** Líneas de log aparecen duplicadas en stdout.

### Pitfall 4: Exception handler genérico rompe batch resilience
**What goes wrong:** Registrar un handler genérico que convierte cualquier `Exception` en un 500 puede interactuar mal con las rutas donde las excepciones ya están siendo capturadas en batch loops.
**Why it happens:** Si dentro de `process_jobs` una excepción escapa del try/except interno y llega al handler genérico, devuelve 500 en lugar de seguir procesando.
**How to avoid:** El handler genérico solo alcanza lo que el código no captura. Los loops de batch ya capturan con `except Exception`. Los handlers de capa son para errores de configuración/infraestructura que NO deben ser silenciados (fallo de storage, rota la config).
**Warning signs:** Tests de `POST /jobs/process` que esperan `errors: [...]` en lugar de 500 empiezan a fallar.

### Pitfall 5: Filtrar información en el handler de fallback
**What goes wrong:** Exponer `str(exc)` completo o el traceback en la respuesta JSON del handler genérico.
**Why it happens:** Por conveniencia en debug.
**How to avoid:** El handler genérico devuelve solo `{"error": {"type": ..., "message": "Internal server error"}}`. El traceback completo va al log (`logger.exception`) pero NO al cliente. [ASSUMED — buena práctica de seguridad; no verificado contra OWASP para este proyecto concreto]
**Warning signs:** Respuestas JSON contienen paths de fichero o nombres de variables internas.

### Pitfall 6: README desactualiza el stack (Supabase eliminado)
**What goes wrong:** El README actual (fondo de fase 1) menciona "Supabase(pgvector)+fallback SQLite". Supabase fue eliminado del alcance (decisión 2026-05-23).
**Why it happens:** README no se actualizó cuando se tomó la decisión.
**How to avoid:** La sección "Stack" del README debe decir "SQLite local (stdlib sqlite3)" sin mencionar Supabase.
**Warning signs:** README menciona pgvector, Supabase, OPENAI_API_KEY.

### Pitfall 7: .env.example menciona OPENAI_API_KEY (ya no necesaria)
**What goes wrong:** El `.env.example` actual lista `OPENAI_API_KEY`. Con BGE-M3 local no se usa OpenAI para embeddings.
**Why it happens:** Configuración inicial de fase 1 antes de tomar la decisión de BGE-M3.
**How to avoid:** Eliminar `OPENAI_API_KEY` del `.env.example`. Añadir `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY` como variables opcionales comentadas.
**Warning signs:** Un usuario sigue `cp .env.example .env` y cree que necesita una clave de OpenAI.

---

## Exact /jobs/process Contract (for DOC-02)

Esta sección documenta el contrato REAL leyendo el código implementado. Es la fuente de verdad para DOC-02.

### Request: POST /jobs/process

**Type:** `ProcessRequest` (app/api/routes/jobs.py L62-65)

```json
{
  "sources": [
    {
      "source": "arbeitnow",
      "offers": [
        {
          "slug": "ai-engineer-techcorp-12345",
          "company_name": "TechCorp GmbH",
          "title": "AI Engineer",
          "description": "<h2>About</h2><p>We need an AI Engineer with Python expertise.</p>",
          "remote": false,
          "url": "https://www.arbeitnow.com/jobs/ai-engineer-techcorp-12345",
          "tags": ["Engineering"],
          "job_types": ["berufserfahren"],
          "location": "Berlin",
          "created_at": 1716350400
        }
      ]
    },
    {
      "source": "generic",
      "offers": [
        {
          "employer": "OpenAI Inc.",
          "job_title": "ML Engineer",
          "city": "Remote",
          "body": "We are looking for a motivated ML Engineer.",
          "apply_url": "https://openai.com/careers/ml-engineer",
          "is_remote": true
        }
      ]
    }
  ]
}
```

**Notes:**
- `sources` es un array de `SourceBlock`; cada bloque tiene un `source` (string identificador del mapper) y `offers` (array de dicts heterogéneos).
- `source` acepta: `"arbeitnow"` (mapper específico) o cualquier otro string (usa `generic_mapper`).
- Los campos de cada oferta varían por fuente. El mapper correspondiente hace la normalización.
- Una oferta mal formada va a `errors[]` en la respuesta; el batch continúa (NORM-04).

### Response: POST /jobs/process

**Type:** `ProcessResponse` (app/api/routes/jobs.py L80-84)

```json
{
  "results": [
    {
      "job": {
        "id": "abc123...",
        "title": "AI Engineer",
        "company": "TechCorp GmbH",
        "location": "Berlin",
        "remote": "unknown",
        "description": "We need an AI Engineer with Python expertise.",
        "salary": null,
        "url": "https://www.arbeitnow.com/jobs/ai-engineer-techcorp-12345",
        "source": "arbeitnow",
        "posted_at": "2024-05-22T00:00:00+00:00",
        "raw": { "...payload original..." },
        "urls_alternativas": []
      },
      "score": {
        "score_total": 82,
        "recommendation": "good_fit",
        "desglose": {
          "encaje_puesto": 90,
          "encaje_skills": 85,
          "encaje_ubicacion": 40,
          "encaje_seniority": 75
        },
        "puesto_detectado": "Ingeniero de IA / AI Engineer",
        "rango_puesto": 1,
        "reasons_for": ["Match en skills principales: Python, LLMs"],
        "reasons_against": ["Presencial en Berlin, fuera de Barcelona"],
        "matched_skills": ["Python", "LLMs"],
        "missing_requirements": [],
        "deal_breaker_hit": false,
        "deal_breaker_cual": null
      },
      "ya_visto": false
    }
  ],
  "errors": []
}
```

**Notes:**
- `results` ordenados por `score.score_total` DESC.
- `ya_visto: true` si la oferta ya estaba en el storage ANTES de este run (control de ya-vistas para n8n).
- `errors[]` contiene `{"job_id": str, "error": str}` para cada oferta que falló al puntuar o normalizar.
- `recommendation` enum: `"strong_fit"` | `"good_fit"` | `"maybe"` | `"skip"`.
- `remote` enum en job: `"remote"` | `"hybrid"` | `"onsite"` | `"unknown"`.

### Prerequisite: POST /cv/parse

n8n debe llamar a `/cv/parse` una vez antes de `/jobs/process`. Si no hay CVProfile cacheado, `/jobs/process` devuelve HTTP 404:

```json
{"detail": "No hay CVProfile cacheado. Llama a POST /cv/parse primero."}
```

**curl para probar:**
```bash
curl -X POST http://localhost:8000/cv/parse \
  -F "file=@ruta/a/mi_cv.pdf"
```

---

## Code Examples

### configure_logging() en lifespan
```python
# Source: stdlib logging docs + patrón idempotente verificado en codebase
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.obs.logging_config import configure_logging  # noqa: PLC0415
    configure_logging()
    # ... resto del lifespan existente
    from app.storage.sqlite import SQLiteStorage  # noqa: PLC0415
    ...
```

### app/errors.py — excepciones tipadas por capa
```python
# Source: patrón simple — no se necesita herencia compleja para esta fase
class BuscadorError(Exception):
    """Base exception para todos los errores de dominio de BuscadorDeEmpleo."""

class CVParseError(BuscadorError):
    """Error durante el parseo del CV (extracción de texto o llamada LLM)."""

class NormalizationError(BuscadorError):
    """Error durante la normalización de una oferta."""

class ScoringError(BuscadorError):
    """Error durante el scoring de una oferta."""

class StorageError(BuscadorError):
    """Error durante operaciones de persistencia (SQLite)."""
```

### Wrapping assess_job with trace_llm
```python
# En app/scoring/llm.py — envolver el return de client.messages.create
# Source: Context7 /langfuse/langfuse-python + patrón contextmanager del stub
from app.obs.tracing import trace_llm

def assess_job(job, cv_profile, user_profile, client):
    model = os.getenv("ANTHROPIC_MODEL_SCORING", "claude-sonnet-4-6")
    with trace_llm("assess_job", job_id=job.id, model=model):
        return client.messages.create(
            model=model,
            ...
        )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Langfuse v2/v3 `@observe` decorator | Langfuse v4 OTel-based `start_as_current_observation` context manager | v4.0.0 (2024) | API completamente diferente — los tutoriales viejos no aplican |
| Langfuse v3 decorador module-level singleton | Langfuse v4 instancia `Langfuse()` explícita | v4.0.0 | El stub debe instanciar explícitamente |

**Deprecated/outdated:**
- `from langfuse.decorators import observe` (v2/v3): no usar con langfuse 4.x
- Supabase/pgvector como backend: eliminado del proyecto (decisión 2026-05-23)
- `OPENAI_API_KEY` en `.env.example`: ya no necesaria (BGE-M3 local)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | El handler genérico `Exception` no exponer stack traces es solo buena práctica — no hay requisito de seguridad formal para este proyecto (herramienta personal local) | Common Pitfalls #5 | Bajo: herramienta personal, no expuesta a internet |
| A2 | `Langfuse()` constructor sin credenciales lanza excepción (no simplemente opera en no-op) | Common Pitfalls #2 | Medio: si no lanza, el doble-check de env vars sigue siendo correcto pero no imprescindible |
| A3 | El decorador `@observe` de langfuse v4 sigue disponible (aunque la preferencia es el context manager) | Pattern 1 | Bajo: no lo usamos; usamos context manager |

**Si este tabla está vacía:** Todos los claims de esta investigación fueron verificados o citados. Las 3 entradas son de bajo riesgo.

---

## Open Questions

1. **Nº de llamadas LLM en process_jobs: ¿uno por oferta exactamente?**
   - What we know: `score_job` llama a `assess_job` que hace exactamente un `client.messages.create`. El scorer también tiene lógica determinista (ranking, ubicación, seniority) pero esa no llama al LLM.
   - What's unclear: Si en algún escenario futuro `score_job` hace retry interno y eso cuenta como 2 llamadas.
   - Recommendation: Contar `llm_calls += 1` por cada `score_job` exitoso es correcto y simple. Si en el futuro se añaden retries, se puede refinar. El contador de hoy no debe depender de la implementación interna de assess_job.

2. **¿Wrappear también extract_cv_profile con trace_llm?**
   - What we know: El CONTEXT.md dice "si es barato". Es una sola llamada en toda la vida del servicio (el CV se cachea). Barato de instrumentar.
   - What's unclear: Si añade complejidad de test sin valor práctico.
   - Recommendation: Sí wrappear. Es trivial (misma interfaz que assess_job) y la consistencia de "todos los puntos LLM están instrumentados" tiene valor para OBS-04.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Todo | ✓ | 3.13 (uv venv) | — |
| FastAPI | OBS-03 handlers | ✓ | 0.136.1 | — |
| Pydantic v2 | app/errors.py, models | ✓ | 2.13.4 | — |
| stdlib logging | OBS-01 | ✓ | built-in | — |
| langfuse | OBS-02 stub (opcional) | ✗ | — | No-op stub (diseño objetivo) |
| uvicorn | DOC-01 run command | ✓ | 0.47.0 | — |
| uv | DOC-01 install instructions | ✓ | disponible en PATH | pip + venv |
| pytest | Tests | ✓ | 9.x (dev dep) | — |

**Missing dependencies with no fallback:** Ninguna — langfuse es intencionalmente opcional.

**Missing dependencies with fallback:** langfuse — el servicio funciona perfectamente sin él (diseño objetivo del stub).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run python -m pytest tests/obs/ tests/api/test_jobs.py -x -q` |
| Full suite command | `uv run python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OBS-01 | `configure_logging()` no añade handlers duplicados | unit | `uv run python -m pytest tests/obs/test_logging.py -x` | ❌ Wave 0 |
| OBS-01 | `process_jobs` log final incluye campo `llm_calls=N` | unit (caplog) | `uv run python -m pytest tests/api/test_process.py::test_process_log_counters -x` | ❌ Wave 0 |
| OBS-02 | `trace_llm` es no-op cuando langfuse no configurado | unit | `uv run python -m pytest tests/obs/test_tracing.py::test_trace_llm_noop -x` | ❌ Wave 0 |
| OBS-02 | `trace_llm` no lanza si langfuse no instalado (ImportError) | unit | `uv run python -m pytest tests/obs/test_tracing.py::test_trace_llm_no_install -x` | ❌ Wave 0 |
| OBS-02 | `assess_job` funciona con trace_llm envuelto (scoring no se rompe) | integration | `uv run python -m pytest tests/scoring/ -x` | ✅ existentes — deben seguir pasando |
| OBS-03 | CVParseError → JSONResponse 422 `{"error": {...}}` | unit | `uv run python -m pytest tests/api/test_exception_handlers.py::test_cv_parse_error -x` | ❌ Wave 0 |
| OBS-03 | ScoringError → JSONResponse 422 | unit | `uv run python -m pytest tests/api/test_exception_handlers.py::test_scoring_error -x` | ❌ Wave 0 |
| OBS-03 | StorageError → JSONResponse 503 | unit | `uv run python -m pytest tests/api/test_exception_handlers.py::test_storage_error -x` | ❌ Wave 0 |
| OBS-03 | Exception genérica → JSONResponse 500, sin stack trace en body | unit | `uv run python -m pytest tests/api/test_exception_handlers.py::test_generic_fallback -x` | ❌ Wave 0 |
| OBS-03 | `process_jobs` batch resilience no rota por los nuevos handlers | regression | `uv run python -m pytest tests/api/test_process.py -x` | ✅ existente — debe seguir pasando |
| DOC-03 | examples/*.json son JSON válido y POST /jobs/process los acepta (LLM+embedder mockeados) | integration | `uv run python -m pytest tests/api/test_examples.py -x` | ❌ Wave 0 |

**Suite baseline:** 162 tests pasando antes de esta fase (confirmado con `uv run python -m pytest`).

### Sampling Rate
- **Per task commit:** `uv run python -m pytest tests/obs/ tests/api/ -q --tb=short`
- **Per wave merge:** `uv run python -m pytest tests/ -q`
- **Phase gate:** Full suite green (162 + nuevos) antes de `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/obs/__init__.py` — paquete de tests de observabilidad
- [ ] `tests/obs/test_logging.py` — cubre OBS-01: idempotencia de configure_logging, caplog de contadores
- [ ] `tests/obs/test_tracing.py` — cubre OBS-02: no-op sin env vars, no-op sin langfuse instalado
- [ ] `tests/api/test_exception_handlers.py` — cubre OBS-03: cada excepción de capa → JSON correcto
- [ ] `tests/api/test_examples.py` — cubre DOC-03: validar ejemplos JSON + /jobs/process con mocks

---

## Security Domain

> security_enforcement no está explícitamente en config.json → tratado como habilitado.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Herramienta personal local, sin auth en scope |
| V3 Session Management | No | API stateless |
| V4 Access Control | No | Sin multi-usuario |
| V5 Input Validation | Yes | Pydantic v2 en todos los endpoints; exception handlers no exponen inputs crudos |
| V6 Cryptography | No | No hay crypto en esta fase |

### Known Threat Patterns (para esta fase)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Stack trace en respuesta de error | Information Disclosure | Handler genérico devuelve "Internal server error", traceback solo en logs |
| Langfuse credentials en código | Information Disclosure | Solo env vars (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`), nunca hardcoded |
| README expone .env.example con claves reales | Information Disclosure | `.env.example` solo tiene placeholders (`sk-ant-...`); `.env` en .gitignore |

---

## Sources

### Primary (HIGH confidence)
- Context7 `/langfuse/langfuse-python` — APIs `@observe`, `start_as_current_observation`, parámetros del constructor, env vars `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`
- Context7 `/fastapi/fastapi` — `@app.exception_handler`, `JSONResponse`, ordering de handlers, `RequestValidationError`
- Codebase directo (`app/api/routes/jobs.py`, `app/scoring/llm.py`, `app/cv/llm_client.py`, `app/dedup/__init__.py`, `pyproject.toml`, `tests/conftest.py`) — shapes de contratos, patrones de import perezoso, contadores existentes

### Secondary (MEDIUM confidence)
- `pip index versions langfuse` — versión 4.6.1 confirmada como latest (2026-05-23)
- `pyproject.toml` — langfuse ausente de dependencias, confirmado

### Tertiary (LOW confidence)
- Ninguna — todos los claims críticos verificados en fuentes primarias o secundarias

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — versiones verificadas contra pyproject.toml y pip registry
- Architecture (Langfuse stub pattern): HIGH — API verificada en Context7, versión confirmada
- Architecture (FastAPI handlers): HIGH — verificado en Context7
- /jobs/process contract: HIGH — leído directamente del código implementado
- Common Pitfalls: HIGH (1-4) / ASSUMED (5 — convención de seguridad no documentada formalmente para este proyecto)

**Research date:** 2026-05-23
**Valid until:** 2026-06-23 (FastAPI/Pydantic muy estables; langfuse cambia frecuentemente — re-verificar si se activa OBS-04)
