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

<!-- FASE 1 ya implementada (andamiaje existente en el repo). -->

- ✓ Schemas Pydantic v2 completos (`UserProfile`, `CVProfile`, `Job`, `JobScore`, `Desglose`, `ScoredJob`) — existing (`app/models/schemas.py`)
- ✓ `data/profile.yaml` configurable con perfil real de Jaime, editable sin tocar código — existing
- ✓ Estructura modular de carpetas (`api/`, `models/`, `cv/`, `dedup/`, `scoring/`, `storage/`, `config/`) — existing

### Active

<!-- FASES 2-5. Hipótesis hasta que estén construidas y validadas. -->

- [ ] Parseo de CV en PDF → `CVProfile` con Pydantic + Instructor (LLM), cacheado (FASE 2)
- [ ] Normalización de ofertas crudas heterogéneas → `Job`, con mapeo aislado por fuente (FASE 3)
- [ ] Deduplicación en dos niveles: hash exacto + semántico con embeddings BGE-M3 (FASE 3)
- [ ] Heurística de scoring: lógica determinista + juicio LLM (ranking como peso, ubicación/remoto, seniority, deal-breakers, score ponderado) (FASE 4) ← **núcleo**
- [ ] Endpoints FastAPI: `/cv/parse`, `/profile`, `/jobs/normalize`, `/jobs/process`, `/jobs/score`, `/jobs/history` (FASE 5)
- [ ] Persistencia SQLite-first con upgrade a Supabase (pgvector) y control de "ya-vistas" (FASE 5)
- [ ] Logging estructurado, manejo de errores por capa, batch resiliente (una oferta mala no tumba el lote) (FASE 5)
- [ ] Interfaz de observabilidad Langfuse preparada (stub) para trazar llamadas de scoring (FASE 5)
- [ ] README con sección dedicada a integración con n8n + ofertas de ejemplo para probar `/jobs/process` (FASE 5)
- [ ] Tests pytest por capa, con énfasis en la heurística de scoring; LLM y embeddings mockeados donde toque

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
- **Tech stack**: Persistencia SQLite-first → Supabase (Postgres + pgvector), credenciales desde entorno
- **Security**: NUNCA hardcodear credenciales — `.env` + python-dotenv + `.env.example`
- **Dependencies**: no meter dependencias pesadas innecesarias (BGE-M3/torch es la excepción aceptada conscientemente)
- **Compatibility**: el servicio debe ser consumible por n8n vía HTTP con JSON simple; una oferta mal formada no debe tumbar el batch entero
- **Quality**: es pieza de portfolio — type hints en todo, manejo de errores por capa, logging estructurado, tests por capa
- **Process**: construir por fases y parar a confirmar entre cada una (ver `CLAUDE.md` § "Cómo quiero que trabajes")

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Servicio headless, sin frontend propio | n8n entrega (email/telegram); foco en la inteligencia | — Pending |
| Embeddings BGE-M3 local (no API) | Gratis, privado, coincide con el spec; se asume el peso de torch | — Pending |
| SQLite primero, Supabase como upgrade | Arrancar local sin deps externas, testeable ya | — Pending |
| Construir FASES 2-5 en este milestone | Sistema completo usable de verdad, no solo un trozo | — Pending |
| Ranking de puestos como PESO, no filtro binario | Una oferta fuera de ranking no se descarta sola; decae graduado | — Pending |
| Scoring = lógica determinista + juicio LLM | Núcleo del proyecto; no dejarlo todo al LLM a ciegas | — Pending |
| Deal-breakers = filtro duro (skip) | Único filtro binario explícito de la heurística | — Pending |

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
*Last updated: 2026-05-22 after initialization*
