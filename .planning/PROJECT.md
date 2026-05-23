# BuscadorDeEmpleo

## What This Is

Agregador inteligente de ofertas de empleo: un **servicio Python (FastAPI) headless**
que recibe ofertas crudas, las **normaliza**, **deduplica semánticamente** y las
**puntúa contra el perfil real de Jaime** (CV en PDF + ranking de puestos +
preferencias). La orquestación diaria (disparo, llamadas a APIs de empleo, entrega
por email/telegram) la hace **n8n por fuera**, consumiendo este servicio vía HTTP/JSON.

Doble propósito: (1) herramienta real para la búsqueda activa de empleo de Jaime
(AI Engineer, base en Barcelona, abierto a remoto) y pieza de portfolio — la calidad
de ingeniería importa; (2) proyecto final que consolida las 5 fases del curso de
automatización con IA (RPA+IA/n8n, IDP/lectura de documentos, RAG/embeddings,
agentes/LLM, integración).

## Core Value

Puntuar y filtrar ofertas con **honestidad** contra el perfil REAL de Jaime (su CV
verdadero, no skills escritas a mano), de forma que el ranking de puestos pese de
forma graduada y los deal-breakers filtren en duro. Si todo lo demás falla, **la
heurística de scoring** (FASE 4) debe funcionar y ser confiable.

## Requirements

### Validated

<!-- FASE 1 (andamiaje) + milestone v1.0 (FASES 2-5) — todo enviado y verificado. -->

**Andamiaje (pre-v1.0):**
- ✓ Schemas Pydantic v2 completos (`UserProfile`, `CVProfile`, `Job`, `JobScore`, `Desglose`, `ScoredJob`) — `app/models/schemas.py`
- ✓ `data/profile.yaml` configurable con perfil real de Jaime, editable sin tocar código
- ✓ Estructura modular de carpetas (`api/`, `models/`, `cv/`, `dedup/`, `scoring/`, `storage/`, `config/`, `obs/`)

**Milestone v1.0 (2026-05-23, 38 reqs, 179 tests):**
- ✓ Parseo de CV en PDF → `CVProfile` con Pydantic + Instructor, cacheado por sha256 — v1.0 (CV-01..03)
- ✓ Normalización de ofertas crudas → `Job` con id estable, mapeo aislado por fuente, batch resiliente — v1.0 (NORM-01..04)
- ✓ Deduplicación dos niveles: hash exacto + semántico BGE-M3 (lazy, torch-free al importar) — v1.0 (DEDUP-01..03)
- ✓ Heurística de scoring: determinista + juicio LLM (ranking-peso, ubicación, seniority, deal-breakers, ponderado) — v1.0 (SCORE-01..08) ← **núcleo**
- ✓ Endpoints FastAPI: `/cv/parse`, `/profile`, `/jobs/normalize`, `/jobs/process`, `/jobs/score`, `/jobs/history`, `/health` — v1.0 (API-01..07)
- ✓ Persistencia SQLite local (ON CONFLICT, histórico con fecha, control ya-vistas) — v1.0 (STORE-01..03)
- ✓ Logging estructurado + stub Langfuse opcional + excepciones por capa con handlers — v1.0 (OBS-01..03)
- ✓ README + sección integración n8n (JSON exacto) + ejemplos `examples/*.json` — v1.0 (DOC-01..03)
- ✓ Tests pytest por capa (179), énfasis en la heurística; LLM y embeddings mockeados — v1.0 (QA-01..04)

### Active

<!-- v2 — siguiente milestone. -->

- [ ] OBS-04: cableado real completo de Langfuse (más allá del stub no-op)
- [ ] STORE-04: métricas/analítica sobre el histórico (evolución de matches en el tiempo)
- [ ] Verificación manual diferida: validar CVProfile/dedup/scoring contra datos REALES (CV + ofertas + claves)

### Out of Scope

- Frontend / dashboard web propio — n8n se encarga de la entrega; el foco es el servicio inteligente headless
- Orquestación n8n (Schedule, llamadas a APIs de empleo, Merge, entrega por email/telegram) — fuera de este código; se diseña *pensando* en ello pero se construye en n8n
- Embeddings vía API (OpenAI u otros) — decisión tomada: BGE-M3 local (gratis, privado, coincide con el spec)
- Scraping/llamadas salientes a las APIs de empleo desde este servicio — las hace n8n y nos manda las ofertas crudas
- Autenticación/multi-usuario — herramienta personal de un solo usuario (Jaime)

## Context

- **Andamiaje existente:** FASE 1 ya está hecha (schemas Pydantic, `profile.yaml` con datos reales, estructura modular, README inicial). `pyproject.toml` solo tiene `pydantic` + `pyyaml`; las deps de cada fase se añaden con `uv add` según se avanza.
- **Python ≥3.13** según `pyproject.toml` (el CLAUDE.md menciona 3.11+; usamos lo que fija el repo).
- **`.env.example`** actualmente lista `ANTHROPIC_API_KEY` (scoring, necesaria) y `OPENAI_API_KEY`. Con BGE-M3 local elegido, `OPENAI_API_KEY` deja de ser necesaria para embeddings — revisar/limpiar.
- **Perfil real:** Jaime Berdejo, Barcelona, derecho a trabajar en UE/España, idiomas ES nativo / EN C1. Ranking de puestos: 1) AI Engineer, 2) ML Engineer, 3) Data Engineer, 4) MLOps. Modalidad ideal remoto; onsite solo en Barcelona; no reubicarse. Deal-breakers: "exige 5+ años", "presencial fuera de Barcelona".
- **Pesos de scoring por defecto:** puesto 35%, skills 30%, ubicación 20%, seniority 15% (en `profile.yaml`, ajustables). Umbral de dedup coseno 0.85.
- **Consumidor downstream:** n8n. Entradas/salidas JSON limpias, errores con códigos HTTP claros.

## Constraints

- **Tech stack**: Python 3.13 + uv (fallback venv+pip) — fijado por el repo
- **Tech stack**: FastAPI + uvicorn (servicio), httpx async (llamadas salientes), Pydantic v2 + Instructor (structured outputs)
- **Tech stack**: Scoring vía API de Anthropic (Claude), key desde `ANTHROPIC_API_KEY`
- **Tech stack**: Embeddings BGE-M3 local (sentence-transformers o FlagEmbedding — elegir y justificar en FASE 3)
- **Tech stack**: Parseo de PDF con pymupdf
- **Tech stack**: Persistencia SQLite local (stdlib sqlite3), ruta vía `SQLITE_DB_PATH`. Sin Supabase/nube (decisión 2026-05-23)
- **Security**: NUNCA hardcodear credenciales — `.env` + python-dotenv + `.env.example`
- **Dependencies**: no meter dependencias pesadas innecesarias (BGE-M3/torch es la excepción aceptada conscientemente)
- **Compatibility**: el servicio debe ser consumible por n8n vía HTTP con JSON simple; una oferta mal formada no debe tumbar el batch entero
- **Quality**: es pieza de portfolio — type hints en todo, manejo de errores por capa, logging estructurado, tests por capa
- **Process**: construir por fases y parar a confirmar entre cada una (ver `CLAUDE.md` § "Cómo quiero que trabajes")

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Servicio headless, sin frontend propio | n8n entrega (email/telegram); foco en la inteligencia | ✓ Good — v1.0 entregado headless |
| Embeddings BGE-M3 local (no API) | Gratis, privado, coincide con el spec; se asume el peso de torch | ✓ Good — lazy import mantiene tests torch-free |
| Solo SQLite local (Supabase eliminado, 2026-05-23) | Herramienta personal local; pgvector no se usa (dedup es en memoria por run); SQLite cubre persistencia, histórico y ya-vistas sin nube | ✓ Good |
| Construir FASES 2-5 en este milestone | Sistema completo usable de verdad, no solo un trozo | ✓ Good — 5 fases en v1.0 |
| Ranking de puestos como PESO, no filtro binario | Una oferta fuera de ranking no se descarta sola; decae graduado | ✓ Good — decay con suelo>0 |
| Scoring = lógica determinista + juicio LLM | Núcleo del proyecto; no dejarlo todo al LLM a ciegas | ✓ Good — LLM confinado a juicio; números deterministas |
| Deal-breakers = filtro duro (skip) | Único filtro binario explícito de la heurística | ✓ Good — override al final, score honesto |
| LLM no controla score_total/encaje_puesto/ubicación/recommendation | Schema `LLMJobAssessment` los omite → auditable y testeable sin LLM | ✓ Good |
| Ejecución secuencial en árbol principal (no worktrees) | Cadena de dependencias entre fases; merge-back de worktrees arriesgado sin supervisión | ✓ Good |
| Opus para planificar/verificar núcleo, Sonnet para ejecutar | Apalancamiento donde más importa | ✓ Good |

## Current State

**Shipped:** v1.0 MVP (2026-05-23) — servicio FastAPI headless completo y funcional.
- **5 fases**, 19 planes, 38 requisitos, **179 tests en verde**.
- App arranca con `uv run uvicorn app.api.main:app`; importa torch-free y langfuse-free.
- Stack: Python 3.13 · FastAPI · Pydantic v2 + Instructor · Anthropic (scoring/CV) · BGE-M3 local (dedup) · SQLite · pytest.
- Cada fase pasó por research → plan (Opus) → plan-check → ejecución TDD → verify → code-review → fix.

**Pendiente para el usuario (verificación manual diferida):** validar el parseo del CV real, la calidad del dedup BGE-M3 y del juicio LLM de scoring contra datos reales (claves + modelo + ofertas). Y construir el workflow en n8n siguiendo el README.

**Next milestone goals (v2):** Langfuse real (OBS-04), analítica de histórico (STORE-04).

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-23 after v1.0 milestone*
