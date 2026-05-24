# BuscadorDeEmpleo

## What This Is

Agregador inteligente de ofertas de empleo: una **aplicación Streamlit autónoma**
que busca ofertas (vía la API de **JSearch**), las **normaliza**, **deduplica
semánticamente** y las **puntúa contra el perfil real de Jaime** (CV en PDF +
ranking de puestos + preferencias). Un **worker programado (APScheduler)** ejecuta
las búsquedas de forma recurrente aunque la app esté cerrada y entrega un digest
por **Telegram o email** (a elección). El scoring corre **íntegramente con
embeddings locales (BGE-M3) + reglas deterministas**; **OpenAI es una capa de
enriquecimiento opcional** (razones honestas + skills emparejadas/faltantes) que se
activa solo si hay API key.

> **Evolución v1.x → v2.0:** v1.0/v1.1 fueron un servicio FastAPI headless orquestado
> por n8n. En **v2.0** se reconstruye como app Streamlit autónoma con scheduler propio:
> se retiran n8n y FastAPI (la lógica núcleo —cv/dedup/scoring/storage— se importa en
> proceso por la UI y por el worker).

Doble propósito: (1) herramienta real para la búsqueda activa de empleo de Jaime
(AI Engineer, base en Barcelona, abierto a remoto) y pieza de portfolio — la calidad
de ingeniería importa; (2) proyecto final que consolida las 5 fases del curso de
automatización con IA (RPA+IA/automatización, IDP/lectura de documentos,
RAG/embeddings, agentes/LLM, integración).

## Core Value

Puntuar y filtrar ofertas con **honestidad** contra el perfil REAL de Jaime (su CV
verdadero, no skills escritas a mano), de forma que el ranking de puestos pese de
forma graduada y los deal-breakers filtren en duro. Si todo lo demás falla, **la
heurística de scoring** (FASE 4) debe funcionar y ser confiable.

## Current Milestone: v2.0 Standalone App (Streamlit + Scheduler)

**Goal:** Reconstruir BuscadorDeEmpleo como una **app Streamlit autónoma** con un
**worker programado siempre activo** — sin n8n, OpenAI totalmente opcional — donde la
subida del CV, la configuración de búsqueda, el ajuste del scoring, los resultados y
los digests por Telegram/email viven dentro de la app, y el **scoring corre en local
(embeddings + reglas) con el LLM como enriquecimiento opcional**.

**Target features:**
- **UI Streamlit** para todo: subir CV, configurar búsqueda (país, idioma, puesto(s)
  + filtros), afinar parámetros del scoring (pesos/umbral/deal-breakers) y navegar las
  ofertas puntuadas.
- **Cliente JSearch propio** — la app llama a JSearch ella misma (módulo de fuente
  saliente nuevo; asume el rol que tenía n8n).
- **Worker programado (APScheduler)** que ejecuta búsquedas de forma recurrente con
  independencia de si Streamlit está abierto; comparte la BD SQLite local.
- **Scoring reposicionado:** embeddings BGE-M3 + reglas deterministas producen **todos
  los scores numéricos** (siempre disponible, gratis, testeable); **OpenAI es una capa
  de enriquecimiento opcional** (razones honestas + skills emparejadas/faltantes).
- **Digests por Telegram *o* email** (a elección), empujados automáticamente en el
  schedule aunque la app esté cerrada.
- **Limpieza de arquitectura:** retirar FastAPI (núcleo importado en proceso), archivar
  artefactos n8n, sacar el servicio n8n del `docker-compose` y arreglar/quitar la
  RapidAPI key inline.

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

<!-- v2.0 — milestone en curso. Los REQ-IDs detallados se definen en REQUIREMENTS.md. -->

**Líneas de trabajo v2.0** (Streamlit + Scheduler):
- [ ] UI Streamlit: subir CV, configurar búsqueda, afinar scoring, navegar ofertas
- [ ] Cliente JSearch propio (búsqueda saliente dentro de la app)
- [ ] Worker APScheduler siempre activo (búsquedas recurrentes + persistencia compartida)
- [ ] Scoring local-first (embeddings + reglas) con OpenAI como enriquecimiento opcional
- [ ] Entrega de digests por Telegram o email (a elección), automática en el schedule
- [ ] Retirada de n8n + FastAPI; arreglo de la RapidAPI key inline

**Arrastrados (a valorar si entran en v2.0 o se difieren):**
- [ ] OBS-04: cableado real completo de Langfuse (más allá del stub no-op)
- [ ] STORE-04: métricas/analítica sobre el histórico (evolución de matches)
- [ ] Verificación manual diferida: validar CVProfile/dedup/scoring contra datos REALES

### Out of Scope

- Embeddings vía API (OpenAI u otros) — decisión tomada: BGE-M3 local (gratis, privado, coincide con el spec)
- Autenticación/multi-usuario — herramienta personal de un solo usuario (Jaime); la UI Streamlit corre en local/self-hosted
- Despliegue cloud con scheduler gestionado (GitHub Actions / Streamlit Cloud) — descartado: BGE-M3 (~3.6GB) + SQLite local hacen mejor un worker APScheduler en Docker self-hosted
- Otras fuentes de ofertas además de JSearch — v2.0 se centra en JSearch; el mapeo por fuente queda aislado para añadir más después
- Múltiples APIs de LLM / proveedores — solo OpenAI (opcional); el resto del scoring es local

> **Revertido en v2.0** (antes Out of Scope en v1.x): el **frontend propio** (ahora UI
> Streamlit), las **llamadas salientes a APIs de empleo desde la propia app** (ahora
> cliente JSearch propio) y la **orquestación/scheduling** (ahora worker APScheduler
> interno en vez de n8n).

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
- **Tech stack**: Scoring + parseo CV vía API de OpenAI, key desde `OPENAI_API_KEY` (Instructor; defaults gpt-4o-mini/gpt-4o). Cambiado de Anthropic a OpenAI el 2026-05-23
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
| **v2.0:** App Streamlit autónoma; retirar n8n y FastAPI (núcleo importado en proceso) | Para un standalone local, importar la lógica es más simple que mantener una capa HTTP cuyo único consumidor (n8n) desaparece | Decidido v2.0 |
| **v2.0:** Scheduler = worker APScheduler en Docker (no cron/GitHub Actions) | Debe correr aunque la UI esté cerrada; self-hosted encaja con SQLite local + BGE-M3 (~3.6GB); GH Actions sería incómodo con ese peso | Decidido v2.0 |
| **v2.0:** Scoring reposicionado — embeddings+reglas dan TODOS los números; OpenAI es enriquecimiento opcional (no scorer) | Hace los scores deterministas/testeables y la app 100% funcional offline; el LLM aporta solo prosa honesta + skills itemizadas. gpt-4o-mini cuesta ~$0.02/run, así que borrarlo no ahorra y mataría la Fase 4 (juicio LLM) | Decidido v2.0 |
| **v2.0:** La app llama a JSearch ella misma (cliente de fuente propio) | Sin n8n, la búsqueda saliente vuelve a la app; mapeo por fuente aislado para añadir fuentes después | Decidido v2.0 |
| **v2.0:** Digests por Telegram o email a elección del usuario | Flexibilidad de entrega sin depender de un orquestador externo | Decidido v2.0 |
| **v2.0:** Archivar artefactos n8n + arreglar RapidAPI key inline | Repo limpio para v2.0; la key inline en docker-compose es un riesgo aunque esté sin commitear (rotarla) | Decidido v2.0 |

## Current State

**Shipped:** v1.0 MVP (2026-05-23) + v1.1 Deploy & n8n Integration (2026-05-25).
- v1.0: servicio FastAPI headless completo — **5 fases**, 19 planes, 38 requisitos, **179 tests**.
- v1.1: dockerizado, auth `X-API-Key`, migración a OpenAI `gpt-4o-mini`, integración n8n end-to-end verificada (digest real a Telegram). **195 tests**. Vía quick tasks, sin roadmap.
- Stack v1.x: Python 3.13 · FastAPI · Pydantic v2 + Instructor · OpenAI (scoring/CV) · BGE-M3 local (dedup) · SQLite · pytest · Docker.

**Iniciando:** v2.0 Standalone App (Streamlit + Scheduler) — ver `## Current Milestone` arriba.
- Reaprovecha el núcleo v1.x (cv/dedup/scoring/storage) importándolo en proceso.
- Retira n8n + FastAPI; añade UI Streamlit, cliente JSearch propio, worker APScheduler, scoring local-first y entrega Telegram/email.

**Pendiente del usuario (heredado):** sacar/rotar la RapidAPI key inline del `docker-compose.yml`; el CV real se parseó con `años_experiencia_total=None` (a afinar).

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
*Last updated: 2026-05-24 — starting v2.0 milestone (Standalone App: Streamlit + Scheduler)*
