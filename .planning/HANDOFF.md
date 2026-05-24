# HANDOFF — BuscadorDeEmpleo (post-/clear)

**Fecha:** 2026-05-25 · **Estado:** v1.1 enviado (tag `v1.1`). Integración n8n FUNCIONANDO end-to-end.

Lee esto primero al retomar. Es lo que NO está obvio en el código/git.

---

## TL;DR de dónde estamos
El sistema **funciona de punta a punta de verdad**: n8n (workflow diario) → servicio FastAPI dockerizado → scoring real (gpt-4o-mini) → filtro → **digest entregado a Telegram** (verificado). v1.0 (MVP, el servicio) y v1.1 (deploy + integración n8n) están cerrados y tagueados.

El usuario lanzó `/gsd-new-milestone 2.0` pero lo pausó para guardar este handoff. **Próximo paso: `/gsd-new-milestone 2.0`** (planificar v2).

## Cómo arrancar / verificar (rápido)
```bash
cd ~/projects/BuscadorDeEmpleo
# Tests (recordar limpiar cache antes, ver gotcha):
rm -f data/.cache/_current data/.cache/*.json 2>/dev/null; uv run pytest -p no:warnings -q   # 195 passed

# El servicio ya corre en Docker (ver "Estado en ejecución"). Para arrancarlo si no:
docker compose up -d buscadordeempleo     # SOLO ese servicio (no el n8n del compose, ver gotcha)
docker compose ps                          # debe estar healthy
curl http://localhost:8000/health          # 200 · /docs en http://localhost:8000/jobs ... /docs
```

## Estado en ejecución (esta máquina, ahora)
- **Contenedor `buscadordeempleo-buscadordeempleo-1`**: running/healthy en `:8000`. `OPENAI_MODEL_SCORING=gpt-4o-mini`. BGE-M3 **precargado** (~3.6 GB en el volumen `hf_cache`). BD **limpia** (0 ofertas). **CV REAL de Jaime cacheado** (43 skills; `años_experiencia_total=None` ⚠️).
- **n8n**: contenedor **standalone** `n8n` (`n8nio/n8n:2.21.5`) en `:5678` — **NO es el del compose**. Tiene el workflow "BuscadorDeEmpleo — Digest diario" montado y **funcionando** (probado: llegó digest a Telegram, chat id 216573280). Está `active: false` (el cron diario 08:00 NO está activado todavía).
- **Supabase `*_ARMARIO_DIGITAL`**: contenedores PARADOS por petición del usuario (otro proyecto, sin relación). Recuperar con `docker start $(docker ps -aq --filter name=ARMARIO_DIGITAL)`.

## Qué se hizo en v1.1 (esta sesión)
Todo vía quick tasks (detalle en STATE.md → "Quick Tasks Completed"):
1. **Docker:** `Dockerfile` (uv, py3.13) + `docker-compose.yml` (servicio n8n incluido) + `.dockerignore` (fix: excluir `data/jobs.db` y `data/.cache/` — los patrones raíz `*.db`/`.cache` NO matchean rutas anidadas, por eso la BD de test se horneaba en la imagen).
2. **Auth API-key:** `app/api/auth.py` (middleware `X-API-Key`, opcional/no-op sin `API_KEY`, `/health` pública). 185→195 tests.
3. **Integración n8n:** `docs/N8N-WORKFLOW.md` (guía paso a paso) + `n8n/workflow.json` (importable). Patrón multi-query, detección primer-run/backfill (1 mes), sub-flujo "Subir CV", umbral filtro 50.
4. **Modelo:** scoring a **gpt-4o-mini** vía `OPENAI_MODEL_SCORING` en `.env` (~15× más barato).

## ⚠️ GOTCHAS / cabos sueltos
- 🔴 **`docker-compose.yml` tiene la RapidAPI key INLINE y está SIN COMMITEAR.** Se dejó fuera del commit de v1.1 a propósito (la key NO está en git ni en el tag). PERO es un fichero versionado: si se commitea, la key entra en el historial. **Pendiente:** dejar esa línea como `RAPIDAPI_KEY: ${RAPIDAPI_KEY:-}` (lee de `.env`) o usar credencial. **La RapidAPI key se ha filtrado en el chat varias veces → ROTARLA.**
- **n8n es STANDALONE, no el del compose.** Por eso `$env.X` NO funciona en sus nodos (var ausente + `N8N_BLOCK_ENV_ACCESS_IN_NODE` sin poner). Solución usada: valores literales / **credenciales Header Auth** (recomendado para la RapidAPI key). El servicio `n8n` del compose existe pero nunca se arrancó (chocaría en :5678).
- **`docker compose restart` NO relee `.env`** — hay que `docker compose up -d` para recrear y coger vars nuevas.
- **Fragilidad de tests (latente):** `test_score_sin_cv_profile_404` y `test_process_sin_cv_profile_404` leen `data/.cache` por defecto → limpiar antes de la suite (`rm -f data/.cache/_current data/.cache/*.json`).
- **n8n iteración:** `Modo de búsqueda` y `ProcessRequest` son Code "Run Once for All Items" → colapsan los N items de JSearch en 1 llamada a `/jobs/process`. No tocar ese modo.

## QUÉ FALTA / ideas v2
| Tema | Nota |
|---|---|
| **Pre-filtrado server-side** | Descartar onsite-fuera-de-España (manteniendo remoto) ANTES del scoring → ahorra OpenAI. Propuesto, no implementado. Es buena pieza de portfolio. |
| **`años_experiencia_total=None`** | El parseo del CV real no lo estimó → afecta `encaje_seniority`. Afinar prompt/modelo. |
| OBS-04 / STORE-04 | Langfuse real + analítica del histórico (diferidos a v2 desde v1.0). |
| Activar cron n8n | El workflow está `active: false`. Activarlo cuando esté afinado. |
| Calidad scoring | Con umbral 50, de 63 ofertas pasó 1 (y era `skip` por deal-breaker). Revisar pesos en `profile.yaml`, deal-breakers, o filtrar `recommendation != skip`. |
| Variantes ES en queries | Los `puestos` del Code son solo inglés; añadir "Ingeniero de IA", etc. para cazar ofertas en español. |

## Mapa de ficheros clave (añadidos en v1.1)
- Docker: `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- n8n: `docs/N8N-WORKFLOW.md`, `n8n/workflow.json`
- Auth: `app/api/auth.py` (+ wiring en `app/api/main.py`), tests en `tests/api/test_auth.py`
- (v1.0 sigue válido: LLM `app/cv/llm_client.py` + `app/scoring/llm.py`, scoring `app/scoring/`, dedup `app/dedup/`, API `app/api/`, storage `app/storage/`)
- Docs/estado: `README.md`, `CLAUDE.md` (spec), `.planning/MILESTONES.md` (entradas v1.0 + v1.1)
