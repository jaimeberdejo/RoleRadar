# BuscadorDeEmpleo — Agregador inteligente de ofertas de empleo

Servicio **Python (FastAPI) headless** que recibe ofertas de empleo crudas,
las **normaliza**, las **deduplica semánticamente** (BGE-M3 local) y las
**puntúa con honestidad contra el perfil real de Jaime** (CV en PDF + ranking
de puestos + preferencias). La orquestación diaria (disparo, llamadas a las
APIs de empleo, entrega por email o Telegram) la hace **n8n por fuera**,
consumiendo este servicio vía HTTP/JSON.

**Doble propósito:** herramienta real para la búsqueda activa de empleo como
AI Engineer (base Barcelona, abierto a remoto) + pieza de portfolio que
consolida RAG/embeddings, scoring con LLM, parseo de documentos y orquestación
con n8n.

---

## Tabla de contenidos

1. [Instalación](#instalación)
2. [Configuración `.env`](#configuración-env)
3. [Editar el perfil (`data/profile.yaml`)](#editar-el-perfil)
4. [Subir el CV](#subir-el-cv)
5. [Arrancar el servicio](#arrancar-el-servicio)
6. [Correr los tests](#correr-los-tests)
7. [Endpoints](#endpoints)
8. [Observabilidad](#observabilidad)
9. [Stack](#stack)
10. [Integración con n8n](#integración-con-n8n)

---

## Instalación

**Requisitos:** Python 3.11+ y [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/jaimeberdejo/BuscadorDeEmpleo.git
cd BuscadorDeEmpleo
uv sync
```

`uv sync` instala todas las dependencias del `pyproject.toml` en el entorno
virtual gestionado por uv. No hace falta activar el venv manualmente: todos los
comandos se prefijan con `uv run`.

---

## Configuración .env

```bash
cp .env.example .env
```

Edita `.env` y establece como mínimo:

| Variable | Requerida | Descripción |
|---|---|---|
| `ANTHROPIC_API_KEY` | **Sí** | Clave de Anthropic para parseo de CV y scoring |
| `ANTHROPIC_MODEL_CV` | No | Modelo para parseo de CV (default: `claude-haiku-4-5-20251001`) |
| `ANTHROPIC_MODEL_SCORING` | No | Modelo para scoring (default: `claude-sonnet-4-6`) |
| `SQLITE_DB_PATH` | No | Ruta del fichero SQLite (default: `data/jobs.db`) |
| `LANGFUSE_PUBLIC_KEY` | No | Activa el tracing LLM con Langfuse (OBS-02) |
| `LANGFUSE_SECRET_KEY` | No | Requerida junto con `LANGFUSE_PUBLIC_KEY` |

El servicio funciona sin Langfuse. Ver la sección [Observabilidad](#observabilidad)
para activarlo.

> `.env` está en `.gitignore` y nunca se sube al repositorio.

---

## Editar el perfil

El perfil se configura en `data/profile.yaml` **sin tocar código**. Contiene:

- `datos_personales`: nombre, email, ubicación, idiomas.
- `preferencias_ubicacion`: ciudades preferidas, país, si está dispuesto a reubicarse.
- `preferencia_remoto`: modalidad ideal (`remote`/`hybrid`/`onsite`/`indiferente`),
  ciudades donde acepta presencial.
- `ranking_puestos`: lista **ordenada** de puestos a los que opta (el primero tiene
  el mayor peso en el scoring). Cada entrada incluye sinónimos para el match.
- `deal_breakers`: condiciones que descartan una oferta en duro (p. ej.
  `"exige 5+ años de experiencia"`, `"presencial fuera de Barcelona"`).
- `pesos`: ponderación del `score_total` (puesto, skills, ubicación, seniority).
  Deben sumar 1.0.
- `dedup_umbral`: similitud coseno a partir de la cual dos ofertas se consideran
  duplicadas (default: `0.85`).

Ejemplo del fichero incluido (`data/profile.yaml`):

```yaml
ranking_puestos:
  - titulo: "Ingeniero de IA / AI Engineer"
    sinonimos: ["AI Engineer", "LLM Engineer", "GenAI Engineer"]
  - titulo: "Ingeniero de ML / ML Engineer"
    sinonimos: ["ML Engineer", "Machine Learning Engineer"]

deal_breakers:
  - "exige 5+ años de experiencia"
  - "presencial fuera de Barcelona"

pesos:
  puesto: 0.35
  skills: 0.30
  ubicacion: 0.20
  seniority: 0.15
```

---

## Subir el CV

El CV en PDF se parsea una vez con el LLM y el resultado (`CVProfile`) se cachea
en disco. El scoring usa el `CVProfile` real —no una lista de skills escrita a mano.

```bash
curl -X POST http://localhost:8000/cv/parse \
  -F "file=@/ruta/a/mi_cv.pdf"
```

El endpoint devuelve el `CVProfile` extraído (experiencia, skills técnicas,
formación, años de experiencia, dominios). El caché se invalida automáticamente
si el CV cambia (hash del fichero).

---

## Arrancar el servicio

```bash
uv run uvicorn app.api.main:app --reload
```

El servicio arranca en `http://localhost:8000` por defecto. Para cambiar host/puerto:

```bash
uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8080
```

Documentación interactiva (Swagger UI): `http://localhost:8000/docs`

---

## Correr los tests

```bash
uv run pytest -q
```

La suite completa cubre: parseo de CV, normalización por fuente, deduplicación
semántica, la heurística de scoring (ranking como peso, deal-breakers, ubicación,
seniority), los endpoints FastAPI y los ejemplos de `examples/`.

---

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/cv/parse` | Sube CV (PDF), devuelve y cachea `CVProfile` |
| `GET` | `/profile` | Devuelve el `UserProfile` cargado de `data/profile.yaml` |
| `POST` | `/jobs/normalize` | Normaliza ofertas crudas de una fuente → `{jobs, errors}` |
| `POST` | `/jobs/score` | Puntúa una lista de `Job` normalizados → `[ScoredJob]` |
| `POST` | `/jobs/process` | **Endpoint principal de n8n**: normalize + dedup + score + persist → `ProcessResponse` ordenado por `score_total` DESC |
| `GET` | `/jobs/history` | Historial de ofertas guardadas (paginable: `?limit=50&offset=0`) |

Todos los endpoints son batch-resilientes: una oferta mal formada va al campo
`errors[]` de la respuesta sin tumbar el batch completo.

---

## Observabilidad

### Logging estructurado

El servicio usa `stdlib logging` con formato `key=value`. Cada run de
`/jobs/process` emite un log con los contadores:

```
process_jobs: entradas=4 unicos=3 puntuados=3 llm_calls=3 errores=0
```

### Tracing LLM con Langfuse (opcional)

Para activar el tracing de las llamadas al LLM con [Langfuse](https://langfuse.com):

1. Instalar Langfuse (no incluida en las dependencias del proyecto):
   ```bash
   uv add langfuse
   ```

2. Añadir las credenciales a `.env`:
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   ```

El servicio detecta automáticamente si Langfuse está instalado y configurado. Sin
las variables de entorno (o sin el paquete instalado), opera como no-op sin ningún
overhead.

---

## Stack

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Gestión de dependencias | uv |
| Framework web | FastAPI + uvicorn |
| Modelos de datos | Pydantic v2 + Instructor (structured outputs) |
| LLM (scoring + parseo CV) | Anthropic Claude (API key requerida) |
| Embeddings (deduplicación) | BGE-M3 local (FlagEmbedding / sentence-transformers) |
| Persistencia | SQLite local (stdlib `sqlite3`) |
| Tests | pytest |
| Tracing LLM (opcional) | Langfuse stub (no-op sin configuración) |

---

## Integración con n8n

Esta sección documenta cómo conectar n8n a este servicio. El código n8n no está
en este repositorio; aquí se describe el flujo y el contrato JSON para que la
configuración sea directa.

### Flujo completo

```
Schedule (diario)
  → HTTP Request a Arbeitnow API       → array de offers
  → HTTP Request a JSearch / FlyByAPIs → array de offers
  → Merge (un nodo que une todos los arrays)
  → HTTP Request: POST /jobs/process   → array de ofertas puntuadas y ordenadas
  → IF: score.score_total >= 70        → Filter para quedarse con las relevantes
  → Send Email / Telegram              → digest diario
```

### Prerequisito: subir el CV una vez

Antes de que n8n llame a `/jobs/process`, debe existir un `CVProfile` cacheado.
Llamar a `/cv/parse` una vez manualmente (o como primer nodo del flujo):

```bash
curl -X POST http://localhost:8000/cv/parse \
  -F "file=@/ruta/a/mi_cv.pdf"
```

Si no hay `CVProfile` cacheado, `/jobs/process` devuelve HTTP 404:
```json
{"detail": "No hay CVProfile cacheado. Llama a POST /cv/parse primero."}
```

### Contrato: POST /jobs/process

**Request** (`ProcessRequest`):

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
          "description": "<h2>About</h2><p>We build AI.</p>",
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
          "employer": "RemoteStack S.L.",
          "job_title": "MLOps Engineer",
          "city": "Remote",
          "body": "We need an MLOps Engineer.",
          "apply_url": "https://remotestack.io/jobs/mlops",
          "is_remote": true
        }
      ]
    }
  ]
}
```

El campo `source` identifica el mapper a usar. Los valores reconocidos son
`"arbeitnow"` (mapper específico con los campos reales de la API) y cualquier
otro string (usa el mapper genérico de fallback). Los campos de cada oferta
varían por fuente.

**Response** (`ProcessResponse`):

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
        "description": "We build AI.",
        "salary": null,
        "url": "https://www.arbeitnow.com/jobs/ai-engineer-techcorp-12345",
        "source": "arbeitnow",
        "posted_at": "2024-05-22T00:00:00+00:00",
        "raw": {},
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

Puntos clave del response:
- `results` viene ordenado por `score.score_total` DESC.
- `ya_visto: true` si la oferta ya estaba en el storage antes de este run (permite
  a n8n filtrar las repetidas entre días).
- `errors[]` contiene `{"job_id": str, "error": str}` para cada oferta que falló.
- `recommendation` enum: `"strong_fit"` | `"good_fit"` | `"maybe"` | `"skip"`.
- `remote` enum en `job`: `"remote"` | `"hybrid"` | `"onsite"` | `"unknown"`.

### Probar sin n8n con los ejemplos incluidos

El directorio `examples/` contiene payloads listos para usar:

```bash
# 1. Subir el CV (una vez)
curl -X POST http://localhost:8000/cv/parse \
  -F "file=@/ruta/a/mi_cv.pdf"

# 2. Procesar el batch de ejemplo
curl -X POST http://localhost:8000/jobs/process \
  -H "Content-Type: application/json" \
  -d @examples/process_request.json
```

Los ficheros `examples/arbeitnow_offers.json` y `examples/generic_offers.json`
contienen las mismas ofertas por separado, útiles para probar `/jobs/normalize`.

### Exponer el servicio para n8n

**Desarrollo local:** n8n en Docker puede alcanzar el servicio en
`http://host.docker.internal:8000` (Mac/Windows) o en la IP del host (Linux).

**Producción:** desplegar el servicio accesible (VPS, Railway, Fly.io, etc.) y
configurar las URLs de los HTTP Request de n8n con el dominio público. La
autenticación de la API (fuera del scope de este proyecto) se puede añadir con
un API Key header o con un reverse proxy (Nginx/Caddy con Basic Auth).

### Nodos n8n por endpoint

| Nodo n8n | Endpoint | Cuándo usarlo |
|---|---|---|
| HTTP Request (POST) | `/cv/parse` | Una vez, antes de arrancar el flujo diario |
| HTTP Request (GET) | `/profile` | Para debug o verificar la config activa |
| HTTP Request (POST) | `/jobs/normalize` | Si quieres normalizar por fuente antes del merge |
| HTTP Request (POST) | `/jobs/process` | **Nodo principal**: normalize + dedup + score en un solo paso |
| HTTP Request (GET) | `/jobs/history` | Para mostrar histórico en un dashboard o auditoría |
