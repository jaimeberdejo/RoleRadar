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
