---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Standalone App (Streamlit + Scheduler)
status: completed
stopped_at: Completed 10-01-PLAN.md (Wave 0 RED guards)
last_updated: "2026-05-25T19:33:15.548Z"
last_activity: 2026-05-25
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 27
  completed_plans: 27
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-24)

**Core value:** Puntuar y filtrar ofertas con honestidad contra el perfil REAL de Jaime (CV verdadero + ranking de puestos + preferencias); el ranking pesa graduado, los deal-breakers filtran en duro. En v2.0 el scoring es local-first (BGE-M3 + reglas), OpenAI es enriquecimiento opcional, y todo vive en una app Streamlit autónoma con worker APScheduler.
**Current focus:** Phase 10 — Streamlit UI

## Current Position

Phase: 10
Plan: Not started
Status: Milestone complete
Last activity: 2026-05-25

Progress bar: [######----] 60% (3/5 phases)

## Performance Metrics

**Velocity (v1.0 reference):**

- Total plans completed: 42 (v1.0)
- Average duration: ~15-30 min/plan
- Total execution time: ~5-7 hours

**v2.0 phases:**

| Phase | Plans | Milestone |
|-------|-------|-----------|
| 6. Architecture Cleanup & Storage Foundation | TBD | v2.0 |
| 7. Embeddings-First Scoring Refactor | TBD | v2.0 |
| 8. JSearch Client & Worker Pipeline | TBD | v2.0 |
| 9. Notifications & Digest | TBD | v2.0 |
| 10. Streamlit UI | TBD | v2.0 |

*Updated after each plan completion*
| Phase 09-notifications-digest P04 | 2 | 1 tasks | 2 files |
| Phase 09-notifications-digest P03 | 15 | 3 tasks | 5 files |
| Phase 10-streamlit-ui P01 | 390s | 3 tasks | 7 files |
| Phase 10-streamlit-ui P02 | 187s | 3 tasks | 4 files |
| Phase 10-streamlit-ui P04 | 720 | 3 tasks | 6 files |
| Phase 10-streamlit-ui P05 | 169 | 2 tasks | 3 files |
| Phase 10-streamlit-ui P06 | 254 | 3 tasks | 5 files |
| Phase 10-streamlit-ui P07 | 342 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v1.0 Setup]: Servicio headless, sin frontend propio — n8n entrega; foco en la inteligencia
- [v1.0 Setup]: Embeddings BGE-M3 LOCAL (no API) — gratis, privado, coincide con el spec
- [v1.0 Setup]: SQLite primero, Supabase eliminado del alcance (2026-05-23)
- [v1.0 Roadmap]: Scoring (FASE 4) tiene su propia fase dedicada por ser el núcleo
- [v1.0 Phase ?]: Use pymupdf for in-memory PDF fixture generation instead of reportlab
- [v1.0 Phase ?]: Cache-first ordering: hash+cache check before any extraction or LLM call
- [v1.0 Phase ?]: Mock at import site: patch app.cv.parser.build_instructor_client
- [v1.0 Phase ?]: NFD not NFC for accent normalization
- [v1.0 Phase ?]: stable_job_id returns full 64-char sha256 hex
- [v1.0 Phase ?]: arbeitnow remote=False maps to RemoteJob.unknown — not onsite
- [v1.0 Phase ?]: Parametros de decay (paso, suelo, maximo) como defaults en codigo
- [v1.0 Phase ?]: yaml.safe_load exclusivamente en loader
- [v1.0 Phase ?]: NFD replicado localmente en scoring/location.py — no importar app.dedup
- [v1.0 Phase ?]: deal-breaker override last: score_total stays honest, only recommendation→skip
- [v1.0 Phase ?]: fixed system prompt (anti prompt-injection): offer in XML <oferta> section
- [v1.0 Phase ?]: scoring module never imports app.dedup
- [v1.0 Phase 4 P04]: was_seen computed BEFORE upsert
- [v1.0 Phase 4 P04]: ScoredJobConVisto wraps ScoredJob+ya_visto without mutating core schema
- [v2.0 Architecture]: Retirar FastAPI/uvicorn/python-multipart; importar núcleo en proceso
- [v2.0 Architecture]: Dos servicios Docker (ui + worker) desde una sola imagen, volúmenes compartidos
- [v2.0 Architecture]: BlockingScheduler en proceso worker separado — NUNCA APScheduler dentro de Streamlit
- [v2.0 Architecture]: scorer.py — todos los números primero (deterministas), LLM deferred import en rama `if key_present`
- [v2.0 Architecture]: @st.cache_resource para BgeM3Embedder — nunca al nivel de módulo en Streamlit
- [v2.0 Architecture]: mark_seen solo tras entrega exitosa — evita pérdida de notificaciones
- [v2.0 Architecture]: settings table como bus de config cross-process; profile.yaml solo para identidad editada a mano
- [v2.0 Architecture]: APScheduler 3.11.x (NO v4 alpha); ZoneInfo("Europe/Madrid") — no pytz
- [v2.0 Phase 6 P02]: RAPIDAPI_KEY literal removal satisfied transitively by 06-03 (commit 782e463) — n8n block removed; no duplicate 06-02 commit
- [v2.0 Phase 6 P02]: Key rotation checkpoint SKIPPED — user accepts residual risk on a free-tier RapidAPI key (no billing exposure); key will not be rotated
- [v2.0 Phase 6 P05]: Neutral Dockerfile CMD ('print Use: docker compose up') — each service overrides via compose command; no hard-coded entrypoint in image
- [v2.0 Phase 6 P05]: EXPOSE 8000 removed from Dockerfile — v2.0 uses Streamlit port 8501 via compose; removing EXPOSE is cleaner than leaving a misleading port declaration
- [v2.0 Phase 7 P05]: score_job signature v2.0: (job, user_profile, cv_profile, embedder, *, client=None) — user_profile 2nd per CONTEXT.md spec
- [v2.0 Phase 7 P05]: LLMEnrichment local to llm.py (not schemas.py) — it is an implementation detail of enrichment step
- [v2.0 Phase 7 P06]: puesto_match corpus text = titulo+sinonimos joined (SC3 spec) — CORRECTION from P05 which wrongly used titulo-only; tests now key on full corpus text via _corpus_text() helper
- [Phase ?]: python-telegram-bot removed from pyproject.toml: Phase 9 Telegram uses raw httpx.Client (sync); PTB v22.7 async-first and never imported — manifest now honest
- [Phase ?]: Wave 0 RED guards use deferred import pattern (import inside test body) so --collect-only passes while tests still fail with ImportError/KeyError
- [v2.0 Phase 10 P04]: resolve_cv_profile in ui/cv_logic.py: pure Python no Streamlit — testable without runtime (SC1/D-12)
- [v2.0 Phase 10 P04]: search.py render body gated by streamlit.runtime.exists() so save_search_settings is importable by pytest (SC2)
- [Phase ?]: Rephrase README to avoid banned strings while preserving meaning

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- ~~RAPIDAPI_KEY inline en working-tree docker-compose.yml~~ — RESUELTO (06-02/06-03, commit 782e463): literal retirado, inyección vía `env_file: .env`, `test_no_secrets.py` GREEN. Rotación de la clave OMITIDA por decisión del usuario (clave free-tier, sin exposición de facturación).
- CVProfile cacheado con `anios_experiencia_total=None` — la heurística de seniority en Phase 7 debe tratar None como "desconocido" (valor neutro ~50/100), no como 0 años
- JSearch mapper en `app/dedup/mappers.py` fue escrito contra datos de n8n, no contra respuesta directa de JSearch API — verificar campo por campo antes de los tests de integración de Phase 8 (budget 1-2 horas)
- BGE-M3 dual-process RAM (~2-4 GB cada instancia): en una máquina de 8 GB, un run manual desde la UI concurrent con el worker puede ser ajustado. Sin acción hasta observar OOM en la práctica

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260523-u5d | Dockerfile + docker-compose + nota de despliegue Docker | 2026-05-24 | aa08eb1 | [260523-u5d](./quick/260523-u5d-crear-dockerfile-docker-compose-nota-de-/) |
| 260524-sg6 | Autenticación opcional X-API-Key; /health pública; 185→195 tests | 2026-05-24 | 9753539 | [260524-sg6](./quick/260524-sg6-anadir-autenticacion-por-api-key-cabecer/) |
| 260524-sv8 | docs/N8N-WORKFLOW.md guía paso a paso | 2026-05-24 | b17770c | [260524-sv8](./quick/260524-sv8-crear-docs-n8n-workflow-md-guia-paso-a-p/) |
| fast | N8N-WORKFLOW.md: patrón multi-query JSearch | 2026-05-24 | 2f99fd5 | — |
| 260524-tgs | N8N-WORKFLOW.md: backfill automático 2 meses primer run | 2026-05-24 | ef4a9b5 | [260524-tgs](./quick/260524-tgs-ampliar-docs-n8n-workflow-md-con-backfil/) |
| fast | n8n/workflow.json importable (11 nodos) | 2026-05-24 | 323dafd | — |
| fast | servicio n8n añadido al docker-compose.yml | 2026-05-24 | fc2877e | — |
| fast | sub-flujo "Subir CV (una vez)" en workflow.json | 2026-05-24 | d34fae9 | — |
| fast | fix .dockerignore: excluir data/jobs.db y data/.cache/ | 2026-05-24 | 7a04c37 | — |
| fast | backfill por defecto a 1 mes + num_pages 1 | 2026-05-24 | ed8a41b | — |
| fast | bajar umbral del Filter de score 70→50 | 2026-05-24 | 4f2150e | — |

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Observabilidad | OBS-04: Cableado completo de Langfuse (más allá del stub) | v3 | v2.0 requirements |
| Scoring | SCORE-16: Extracción y filtrado por salario | v2.x | v2.0 requirements |
| UI | UI-11: `num_pages` expuesto en la UI | v2.x | v2.0 requirements |
| verification_gap | Phase 01 (parseo CV): verificación manual del CVProfile contra el CV real | human_needed | v1.0 close |
| manual_check | Calidad real del dedup BGE-M3 y del juicio LLM de scoring con ofertas reales | human_needed | v1.0 close |

## Session Continuity

Last session: 2026-05-25T18:51:52.466Z
Stopped at: Completed 10-01-PLAN.md (Wave 0 RED guards)
Resume file: None
Next: Phase 9 — Notifications & Digest
