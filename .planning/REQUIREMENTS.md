# Requirements: BuscadorDeEmpleo — v2.0 Standalone App (Streamlit + Scheduler)

**Defined:** 2026-05-24
**Core Value:** Puntuar y filtrar ofertas con honestidad contra el perfil REAL de Jaime
(CV verdadero + ranking de puestos + preferencias); el ranking pesa graduado, los
deal-breakers filtran en duro. En v2.0 todo vive en una app autónoma y el scoring
funciona 100% offline (embeddings + reglas), con el LLM como enriquecimiento opcional.

> **Numeración de REQ-IDs:** las categorías heredadas de v1.0 continúan su numeración
> (SCORE desde 09, STORE desde 04, QA desde 05, DOC desde 04). Las categorías nuevas de
> v2.0 (MIG, SRC, SCHED, NOTIF, UI) empiezan en 01.

---

## v2.0 Requirements (este milestone)

Cada requisito mapea a una fase del roadmap (ver Traceability).

### Migración y limpieza (MIG)

- [x] **MIG-01**: FastAPI retirado — `app/api/` eliminado; el núcleo (cv/dedup/scoring/storage) se consume **en proceso** desde la UI y el worker; deps `fastapi`/`uvicorn`/`python-multipart` removidas
- [x] **MIG-02**: n8n retirado — servicio `n8n` fuera del `docker-compose`; artefactos n8n (`docs/N8N-WORKFLOW.md`, `n8n/workflow.json`) archivados fuera de la ruta activa
- [x] **MIG-03**: RapidAPI key nunca inline — `docker-compose` usa `${RAPIDAPI_KEY:-}`, `.env.example` actualizado, key antigua **rotada** (se filtró en chat)
- [x] **MIG-04**: `docker-compose` levanta **dos servicios** (UI Streamlit + worker) desde una sola imagen, compartiendo los volúmenes `data` + `hf_cache`

### Fuentes / cliente JSearch (SRC)

- [x] **SRC-01**: Cliente JSearch propio (httpx) que llama a RapidAPI con `query`/país/idioma/`date_posted`/`employment_types`/remote-only configurables; key solo desde env
- [x] **SRC-02**: Soporte de varios puestos — lista de posiciones → varias llamadas JSearch, fusionadas (patrón multi-query bilingüe de v1.1)
- [x] **SRC-03**: Fetch resiliente — 429/cuota y fallos parciales no tumban el batch; los errores por query se registran y se saltan

### Scoring local-first (SCORE — continúa desde SCORE-08) ← **núcleo del milestone**

- [x] **SCORE-09**: Todos los sub-scores numéricos (encaje_puesto/skills/ubicación/seniority) se calculan **sin ninguna llamada a OpenAI**
- [x] **SCORE-10**: `encaje_skills` vía coseno BGE-M3 (texto del CV ↔ descripción de la oferta)
- [x] **SCORE-11**: `rango_puesto` / `puesto_detectado` vía similitud BGE-M3 título↔ranking(+sinónimos), reemplazando la detección por LLM
- [x] **SCORE-12**: `encaje_seniority` determinista (detección de años/nivel en la descripción vs `CVProfile`; `anios_experiencia_total=None` tratado como neutro)
- [x] **SCORE-13**: `deal_breaker_hit` determinista (match keyword/substring) — el filtro duro se preserva sin LLM
- [x] **SCORE-14**: OpenAI es **solo enriquecimiento opcional** — nunca importado/requerido al arrancar; activado por presencia de key; añade `reasons_for`/`reasons_against` + `matched_skills`/`missing_requirements`
- [x] **SCORE-15**: Razones de **fallback basadas en reglas** cuando no hay key — la app no queda degradada (explicaciones legibles generadas desde los scores deterministas)

### Worker programado (SCHED)

- [ ] **SCHED-01**: Worker siempre activo (APScheduler, **proceso propio**, sin importar Streamlit) que ejecuta el pipeline en un schedule configurable aunque la UI esté cerrada
- [ ] **SCHED-02**: Pipeline compartido `fetch(JSearch) → normalizar → dedup (incl. cross-run contra la BD) → score → persistir`, reutilizable por el worker y por el botón "Run now" de la UI
- [x] **SCHED-03**: Schedule configurable (intervalo/cron) desde settings; zona horaria `Europe/Madrid` (zoneinfo, no pytz); manejo de misfire (coalesce/grace) que sobrevive a reinicios

### Notificaciones / digest (NOTIF)

- [ ] **NOTIF-01**: Tras cada run, entrega un digest de las nuevas ofertas strong_fit/good_fit (título, empresa, score, recomendación, top reasons, URL)
- [ ] **NOTIF-02**: Canal **Telegram O email** según config; skip silencioso si ninguno está configurado; secretos solo desde env
- [ ] **NOTIF-03**: Umbral mínimo de score configurable; solo ofertas **nuevas** (no vistas); marcar como vista **después** de la entrega exitosa (evita duplicados y pérdidas)

### UI Streamlit (UI)

- [ ] **UI-01**: Subir CV (PDF) en la app → parsea y cachea `CVProfile`; muestra estado del parseo + perfil extraído
- [ ] **UI-02**: Configurar condiciones de búsqueda (país, idioma, puesto(s), `date_posted`, `employment_types`, remote-only) — persistidas en settings; el worker las lee
- [ ] **UI-03**: Navegar **todas** las ofertas puntuadas dentro de la app (lista: título, empresa, score, recomendación; ordenar/filtrar por score y recomendación)
- [ ] **UI-04**: Vista de detalle de oferta — desglose completo del score, `reasons_for`/`reasons_against`, skills emparejadas/faltantes
- [ ] **UI-05**: Afinar pesos del scoring (puesto/skills/ubicación/seniority) + umbral en la app, **persistidos** para que el worker los use
- [ ] **UI-06**: Editar la lista de **deal-breakers** en la app, persistida (no solo a mano en `profile.yaml`)
- [ ] **UI-07**: Botón **"Run now"** — dispara una búsqueda + scoring inmediata desde la UI (reutiliza el pipeline compartido)
- [ ] **UI-08**: **Re-puntuar** ofertas existentes de la BD con los pesos actuales (sin re-fetch), con aviso de coste
- [ ] **UI-09**: **Panel de estado del scheduler** — último run / próximo run / nuevas ofertas encontradas (desde la tabla runs)
- [ ] **UI-10**: La UI sigue respondiendo durante operaciones largas y el modelo de embeddings **no se recarga** en cada interacción (`@st.cache_resource`)

### Persistencia (STORE — continúa desde STORE-03)

- [x] **STORE-04**: Tabla `settings` (clave-valor) — config operativa editable desde la UI (búsqueda, pesos, umbral, deal-breakers, schedule); el worker la lee al inicio del run; `profile.yaml` sigue siendo identidad editada a mano
- [x] **STORE-05**: Tabla `runs` — registra cada run (timestamp, fetched/duped/scored/new, canal + nº del digest); alimenta el panel de estado y la analítica *(cubre el STORE-04 «analítica» diferido de v1.0)*
- [x] **STORE-06**: SQLite **WAL + busy_timeout** para lectura-UI / escritura-worker concurrentes seguras; transacciones de escritura cortas
- [x] **STORE-07**: `mark_seen(id)` + marcado de vistas tras la entrega (dedup cross-run / no re-notificar)

### Calidad / tests (QA — continúa desde QA-04)

- [x] **QA-05**: Tests del scorer local-first (scores numéricos deterministas y testeables **sin LLM**; enriquecimiento LLM mockeado)
- [x] **QA-06**: Tests del cliente JSearch (httpx mockeado), del pipeline del worker, de notificaciones (envío mockeado) y del storage settings/runs
- [x] **QA-07**: Test del camino **"sin `OPENAI_API_KEY`"** (sin error de import, scores presentes y digest funcional)

### Documentación (DOC — continúa desde DOC-03)

- [ ] **DOC-04**: README reescrito para v2.0 standalone (instalación, `.env`, arrancar UI Streamlit + worker vía Docker, configurar búsqueda, subir CV); la sección de integración n8n se archiva/retira
- [x] **DOC-05**: `.env.example` actualizado (RAPIDAPI_KEY, OPENAI opcional, TELEGRAM_*, SMTP_*, schedule; vars de FastAPI/API eliminadas)

---

## Future Requirements (diferidas — no en este roadmap)

### Observabilidad (OBS)
- **OBS-04**: Cableado real de Langfuse para trazar el enriquecimiento LLM (más allá del stub) — diferido a v3; solo aporta con el LLM en uso estable

### Notificaciones (NOTIF)
- **NOTIF-04**: Mensaje de digest en runs vacíos ("ran OK, 0 nuevas hoy") — descartado para v2.0

### Fuentes (SRC)
- **SRC-04**: Fuentes adicionales además de JSearch (Arbeitnow, LinkedIn, etc.) — el mapper por fuente está aislado para añadirlas después

### Scoring (SCORE)
- **SCORE-16**: Extracción y filtrado por salario (JSearch devuelve salario estructurado)

### UI (UI)
- **UI-11**: `num_pages` expuesto en la UI (por ahora valor por defecto en settings, no editable desde la UI)

---

## Out of Scope

Exclusiones explícitas (anti-features de la investigación, con su razón).

| Feature | Reason |
|---------|--------|
| Autenticación / login / multi-usuario | Herramienta personal de un solo usuario; corre en local/self-hosted (VPN si se expone) |
| Múltiples proveedores LLM (Anthropic/Gemini) | Solo OpenAI **opcional**; interfaz estrecha; abstracción no aporta |
| Embeddings vía API (OpenAI u otros) | BGE-M3 local ya decidido: gratis, privado, offline |
| Telegram **y** email a la vez por defecto | Doble notificación molesta para un solo usuario; se elige un canal |
| Bot de Telegram interactivo (/comandos) | Requiere polling/webhook; usar el botón "Run now" de la UI |
| Push del navegador (Web Push) / WhatsApp | Infra desproporcionada; el digest Telegram/email basta |
| Export a Excel/PDF | `st.dataframe` ya copia al portapapeles; evitar dep bloat |
| Cloud cron / GitHub Actions / Streamlit Cloud | BGE-M3 (~3.6GB) + SQLite local → mejor worker APScheduler en Docker self-hosted |
| Hilo en segundo plano dentro de Streamlit para el scheduler | Anti-patrón (sin ScriptRunContext, SQLite cross-thread); usar proceso worker separado |
| Re-escritura del historial git por la RapidAPI key | Innecesaria: el valor nunca se commiteó (solo en working tree) — basta editar + rotar |

---

## Traceability

Mapeo de requisitos a fases.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MIG-01 | Phase 6 | Complete |
| MIG-02 | Phase 6 | Complete |
| MIG-03 | Phase 6 | Complete |
| MIG-04 | Phase 6 | Complete |
| STORE-04 | Phase 6 | Complete |
| STORE-06 | Phase 6 | Complete |
| DOC-05 | Phase 6 | Complete |
| SCORE-09 | Phase 7 | Complete |
| SCORE-10 | Phase 7 | Complete |
| SCORE-11 | Phase 7 | Complete |
| SCORE-12 | Phase 7 | Complete |
| SCORE-13 | Phase 7 | Complete |
| SCORE-14 | Phase 7 | Complete |
| SCORE-15 | Phase 7 | Complete |
| QA-05 | Phase 7 | Complete |
| QA-07 | Phase 7 | Complete |
| SRC-01 | Phase 8 | Complete |
| SRC-02 | Phase 8 | Complete |
| SRC-03 | Phase 8 | Complete |
| SCHED-01 | Phase 8 | Pending |
| SCHED-02 | Phase 8 | Pending |
| SCHED-03 | Phase 8 | Complete |
| STORE-05 | Phase 8 | Complete |
| STORE-07 | Phase 8 | Complete |
| QA-06 | Phase 8 | Complete |
| NOTIF-01 | Phase 9 | Pending |
| NOTIF-02 | Phase 9 | Pending |
| NOTIF-03 | Phase 9 | Pending |
| UI-01 | Phase 10 | Pending |
| UI-02 | Phase 10 | Pending |
| UI-03 | Phase 10 | Pending |
| UI-04 | Phase 10 | Pending |
| UI-05 | Phase 10 | Pending |
| UI-06 | Phase 10 | Pending |
| UI-07 | Phase 10 | Pending |
| UI-08 | Phase 10 | Pending |
| UI-09 | Phase 10 | Pending |
| UI-10 | Phase 10 | Pending |
| DOC-04 | Phase 10 | Pending |

**Coverage:**
- v2.0 requirements: **39** total (MIG 4 · SRC 3 · SCORE 7 · SCHED 3 · NOTIF 3 · UI 10 · STORE 4 · QA 3 · DOC 2)
- Mapped to phases: **39** (Phase 6: 7 · Phase 7: 9 · Phase 8: 9 · Phase 9: 3 · Phase 10: 11)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-24*
*Last updated: 2026-05-24 — traceability filled (roadmap created)*
