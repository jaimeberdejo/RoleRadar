# Milestones

## v1.0 MVP (Shipped: 2026-05-23)

**Phases completed:** 5 phases, 19 plans, 33 tasks

**Key accomplishments:**

- One-liner:
- One-liner:
- One-liner:
- One-liner:
- One-liner:
- One-liner:
- decay lineal encaje_puesto_desde_rango (100/85/70/55/suelo=20) y loader YAML -> UserProfile con errores claros
- Evaluador determinista de ubicación/remoto: `evaluar_ubicacion(job, profile)` con NFD substring city matching, 8 ramas booleanas puras, y deal-breaker de ubicación para presencial/híbrido fuera de ciudades aceptadas
- Hybrid scoring heuristic: assess_job() using Instructor+Anthropic with fixed honest system prompt + score_job() 6-step orchestrator combining deterministic layers (location, ranking decay, weighted sum, bands) with LLM judgment (skills, seniority, puesto, deal-breakers), deal-breaker override applied last to preserve honest score_total
- 1. [Rule 3 - Blocking] `uv add` failed due to network unavailability
- SQLiteStorage verified complete with 10 pytest tests covering upsert-ON-CONFLICT first_seen preservation, was_seen, paginated history, and Pydantic v2 JobScore round-trip — all STORE-01/02/03 requirements green
- FastAPI routers cv y jobs con tres endpoints granulares (UploadFile PDF→CVProfile, normalize batch-resiliente, score con CVProfile cacheado) y 9 tests TDD verdes (154 total)
- One-liner:
- One-liner:
- Domain exception hierarchy (app/errors.py) + FastAPI exception handlers with anti-leak 500 fallback + configure_logging() in lifespan + trace_llm wired on both LLM call sites + llm_calls counter in process_jobs
- One-liner:

---

## v1.1 — Deployment & n8n Integration (Shipped: 2026-05-25)

**Tipo:** incremento post-MVP vía quick tasks (no roadmapped). Detalle por tarea en STATE.md → "Quick Tasks Completed".

**Key accomplishments:**

- LLM provider migrado de Anthropic a **OpenAI** (Instructor); scoring configurable vía `OPENAI_MODEL_SCORING`, por defecto **gpt-4o-mini** (~15× más barato que gpt-4o).
- Servicio **dockerizado**: Dockerfile (uv, Python 3.13) + **docker-compose** con servicio n8n, volúmenes persistentes (SQLite + caché BGE-M3) y healthcheck.
- **Autenticación por API-key** (middleware `X-API-Key`, opcional, `/health` pública); suite 185 → 195 tests.
- **Integración n8n end-to-end FUNCIONANDO y verificada**: workflow diario (Schedule → JSearch → /jobs/process → Filter → Telegram) entregando un digest real a Telegram. Guía paso a paso `docs/N8N-WORKFLOW.md` + `n8n/workflow.json` importable (detección de primer-run/backfill, multi-query bilingüe, sub-flujo "subir CV").
- Mapper JSearch (RapidAPI) y tuning del pipeline (backfill 1 mes, umbral del filtro 50).

**Conocido / pendiente:** OBS-04 (Langfuse real) y STORE-04 (analítica del histórico) → diferidos a v2. Pre-filtrado server-side (descartar onsite-fuera-de-España antes del scoring) propuesto, no implementado. CV real parseado con `años_experiencia_total = None` (mejora pendiente).

---
