# HANDOFF — BuscadorDeEmpleo (post-/clear)

**Fecha:** 2026-05-23 · **Estado:** v1.0 MVP completo y tag `v1.0`. 185 tests verdes.

Lee esto primero al retomar. Lo de abajo es lo que NO está obvio en el código/git.

---

## Cómo arrancar / verificar (rápido)
```bash
cd ~/projects/BuscadorDeEmpleo
uv run pytest -p no:warnings -q          # debe dar 185 passed
uv run uvicorn app.api.main:app --port 8000   # arranca el servicio (carga .env solo)
# http://127.0.0.1:8000/docs  ·  GET /health
```
- `.env` (gitignored) ya tiene `OPENAI_API_KEY`. La app carga `.env` sola (load_dotenv en main.py).
- LLM = **OpenAI** vía Instructor. Defaults: `gpt-4o-mini` (CV), `gpt-4o` (scoring); override con `OPENAI_MODEL_CV`/`OPENAI_MODEL_SCORING`.

## Qué se hizo después de cerrar el milestone v1.0
1. **Anthropic → OpenAI** (commit `c6d532a`): `instructor.from_openai`, `chat.completions.create`, env `OPENAI_*`, deps (`uv add openai`/`remove anthropic`), tests y docs actualizados.
2. **load_dotenv en main.py** (`e8ecf6c`): el SDK ve `OPENAI_API_KEY` del `.env` sin exportar a mano.
3. **Supabase eliminado** (antes): persistencia = **solo SQLite local** (`SQLITE_DB_PATH`, default `data/jobs.db`).
4. **Mapper JSearch** (`adba6ac`): `MAPPER_REGISTRY = [arbeitnow, jsearch, generic]`. Validado contra la API REAL `/search-v2`.

## ⚠️ GOTCHAS (importante)
- **Milestone v1.0 está cerrado.** `.planning/REQUIREMENTS.md` fue archivado a `milestones/v1.0-REQUIREMENTS.md` (NO existe en raíz — es normal). Fases archivadas en `milestones/v1.0-phases/`. Para trabajo nuevo: `/gsd-new-milestone` (cambio grande) o `/gsd-quick` (cambio pequeño).
- **GSD enforcement:** CLAUDE.md pide pasar por comandos GSD antes de editar. En esta sesión el usuario usó `/sc:task` y peticiones directas; está bien si el usuario lo pide explícitamente.
- **Fragilidad de tests (latente, NO arreglada):** `tests/api/test_jobs.py::test_score_sin_cv_profile_404` y `tests/api/test_process.py::test_process_sin_cv_profile_404` leen el `data/.cache` POR DEFECTO. Si alguien hace `/cv/parse` contra el cache por defecto (no tmp_path), queda un `_current` y esos 2 tests fallan (esperan 404). **Fix:** `rm -f data/.cache/_current data/.cache/*.json` antes de correr la suite. Mejora pendiente: aislar `CV_CACHE_DIR` en esos 2 tests.
- **BGE-M3 (~2.3GB)** ya está en `~/.cache/huggingface` (se descargó al probar `/jobs/process`). La 1ª llamada a `/jobs/process` en una máquina limpia es lenta por esa descarga; aquí ya es rápida.
- 🔐 **SEGURIDAD:** el usuario pegó una **clave de RapidAPI (JSearch) en el chat** — debe **rotarla**. Esa clave va en **n8n**, NO en este repo (el servicio no llama a JSearch; n8n sí).

## Verificado funcionando con datos/key reales
- `/cv/parse` (CV de ejemplo) → CVProfile real vía OpenAI.
- `/jobs/process` con `examples/process_request.json` → 4 ofertas normalizadas+deduplicadas (BGE-M3 real)+puntuadas (OpenAI real)+persistidas. La heurística se comportó bien (deal-breaker de ubicación → skip preservando score honesto; decay del ranking visible).

## QUÉ FALTA (priorizado) — el usuario preguntó esto
| # | Falta | Importancia |
|---|-------|-------------|
| 1 | **Dockerfile + despliegue** (host accesible) para que n8n alcance el servicio | 🔴 bloqueante para n8n en prod |
| 2 | **Construir el workflow en n8n** (Schedule→HTTP a JSearch/Arbeitnow→Merge→POST /jobs/process→Filter→entrega). Externo por diseño; el README tiene el JSON exacto | 🔴 es "la integración" en sí |
| 3 | Parsear el **CV REAL** de Jaime (se usó uno de ejemplo) | 🟠 |
| 4 | **Auth por API-key** en la API (hoy abierta, sin auth) si se expone a internet | 🟠 |
| 5 | Langfuse real (OBS-04) y analítica de histórico (STORE-04) — diferidos a v2 | 🟡 |
| 6 | Afinar mappers con datos reales (moneda de JSearch `/search-v2` usa `job_salary_string`/`job_salary_period`, no `job_salary_currency`); mapper FlyByAPIs (stub) | 🟡 |

## Siguiente paso recomendado
El usuario estaba decidiendo entre **(A) Dockerfile + despliegue** o **(B) auth por API-key**. Empezar por **(A)** desbloquea la integración n8n. Sugerencia: `/gsd-quick` "crear Dockerfile + docker-compose + nota de despliegue y dónde van OPENAI_API_KEY / la key de n8n". Considerar incluir (B) si se va a exponer públicamente.

## Mapa de ficheros clave
- LLM: `app/cv/llm_client.py`, `app/scoring/llm.py` (OpenAI vía Instructor)
- Scoring núcleo: `app/scoring/scorer.py` (orquestador 7 pasos), `ranking.py`, `location.py`
- Dedup: `app/dedup/{normalize,mappers,embedder,exact,semantic,merger}.py` + `__init__.py` (facade)
- API: `app/api/main.py` (lifespan, exception handlers), `deps.py`, `routes/{cv,jobs,profile}.py`
- Storage: `app/storage/{protocol,sqlite}.py`
- Obs: `app/obs/{logging_config,tracing}.py`, `app/errors.py`
- Schemas: `app/models/schemas.py` · Perfil: `data/profile.yaml` · Ejemplos: `examples/`
- Docs: `README.md` (incl. sección n8n), `CLAUDE.md` (spec autoritativo)
