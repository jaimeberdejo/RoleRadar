# Roadmap: BuscadorDeEmpleo

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-05-23) — [archivo](milestones/v1.0-ROADMAP.md)
- **v2.0 Standalone App (Streamlit + Scheduler)** — Phases 6-10

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-05-23</summary>

- [x] Phase 1: Parseo de CV (4/4 plans) — PDF → CVProfile cacheado (Instructor)
- [x] Phase 2: Normalización y Deduplicación (4/4 plans) — Jobs únicos, dedup exacto + BGE-M3
- [x] Phase 3: Heurística de Scoring — núcleo (4/4 plans) — JobScore honesto, determinista + LLM
- [x] Phase 4: API y Persistencia (4/4 plans) — endpoints FastAPI + SQLite + ya-vistas
- [x] Phase 5: Observabilidad, Robustez y Docs n8n (3/3 plans) — logging, stub Langfuse, README + n8n

Detalle completo en `milestones/v1.0-ROADMAP.md`. 38 requisitos, 179 tests.

</details>

### v2.0 Standalone App (Streamlit + Scheduler)

- [ ] **Phase 6: Architecture Cleanup & Storage Foundation** - Remove FastAPI/n8n, fix secrets, add settings/WAL
- [ ] **Phase 7: Embeddings-First Scoring Refactor** - All numeric scores deterministic; OpenAI becomes optional enrichment
- [ ] **Phase 8: JSearch Client & Worker Pipeline** - App-owned fetch + APScheduler worker + runs table
- [ ] **Phase 9: Notifications & Digest** - Telegram/email digest after each worker run
- [ ] **Phase 10: Streamlit UI** - Full interactive app: CV upload, search config, results, settings, scheduler status

## Phase Details

### Phase 6: Architecture Cleanup & Storage Foundation
**Goal**: The codebase is clean, safe, and ready for multi-process work — no FastAPI layer, no inline secrets, no n8n service, and SQLite is concurrency-safe with a settings table the worker can read
**Depends on**: Nothing (v1.1 codebase)
**Requirements**: MIG-01, MIG-02, MIG-03, MIG-04, STORE-04, STORE-06, DOC-05
**Success Criteria** (what must be TRUE):
  1. Running `docker compose up` starts only the `ui` and `worker` services (no n8n service); both mount the same `data/` and `hf_cache/` named volumes
  2. The `docker-compose.yml` and every committed file contain no hardcoded `RAPIDAPI_KEY` value; `.env.example` documents all v2.0 env vars (RAPIDAPI_KEY, TELEGRAM_*, SMTP_*, OPENAI optional) without any FastAPI/API-key vars
  3. The `app/api/` directory is gone; importing the project does not pull in `fastapi`, `uvicorn`, or `python-multipart`; `pyproject.toml` has those deps removed and `streamlit`, `APScheduler`, `python-telegram-bot` added
  4. A `settings` table exists in SQLite; calling `storage.get_settings()` returns defaults for all v2.0 config keys (`search_query`, `search_country`, `schedule_interval_hours`, scoring weights, `dedup_threshold`, etc.) without crashing
  5. A concurrent worker write and UI read on SQLite do not produce `database is locked` — WAL mode and `busy_timeout=5000` are active on every connection
**Plans**: 5 plans (Wave 0: 1 plan; Wave 1: 3 plans parallel; Wave 2: 1 plan)
Plans:
**Wave 1**
- [x] 06-01-PLAN.md — Wave 0: Test stubs (STORE-04/06, MIG-01, MIG-03 guards)
- [x] 06-02-PLAN.md — Wave 1: Secret removal (docker-compose.yml RAPIDAPI_KEY → env_file)
- [x] 06-03-PLAN.md — Wave 1: FastAPI/n8n removal + dep swap (app/api/ delete, pyproject.toml)
- [x] 06-04-PLAN.md — Wave 1: SQLite WAL + settings table (sqlite.py, protocol.py)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 06-05-PLAN.md — Wave 2: Docker restructure + worker.py stub + .env.example rewrite
**UI hint**: yes

### Phase 7: Embeddings-First Scoring Refactor
**Goal**: The scorer produces all four numeric sub-scores (encaje_puesto, encaje_skills, encaje_ubicacion, encaje_seniority) and a full `JobScore` without any OpenAI call; when an `OPENAI_API_KEY` is present it adds honest prose reasons and itemized matched/missing skills as optional enrichment
**Depends on**: Phase 6
**Requirements**: SCORE-09, SCORE-10, SCORE-11, SCORE-12, SCORE-13, SCORE-14, SCORE-15, QA-05, QA-07
**Success Criteria** (what must be TRUE):
  1. Calling `score_job(job, user_profile, cv_profile, embedder)` with no `OPENAI_API_KEY` in the environment returns a complete `JobScore` with all four numeric sub-scores and a `recommendation` — no import error, no `None` sub-scores
  2. `encaje_skills` is computed by BGE-M3 cosine similarity between the CV text and the job description — removing the `BgeM3Embedder` raises a clear error, not a silent zero
  3. `rango_puesto` and `puesto_detectado` are resolved by BGE-M3 cosine between the job title and the ranking entries (+synonyms), not by an LLM call
  4. A `deal_breaker_hit` is detected by deterministic keyword/substring matching and forces `recommendation=skip` regardless of the numeric score — this works with OpenAI absent
  5. When `OPENAI_API_KEY` is present, `reasons_for`, `reasons_against`, `matched_skills`, and `missing_requirements` are populated; when absent, rule-based fallback strings are present in their place
  6. The full test suite passes with LLM and embeddings mocked; at least one test exercises the complete "no API key" path end-to-end
**Plans**: TBD

### Phase 8: JSearch Client & Worker Pipeline
**Goal**: The app fetches job offers from JSearch under its own power and a background worker process runs the full pipeline on a schedule; the pipeline function is shared so a manual UI trigger and the scheduled worker produce identical results
**Depends on**: Phase 6, Phase 7
**Requirements**: SRC-01, SRC-02, SRC-03, SCHED-01, SCHED-02, SCHED-03, STORE-05, STORE-07, QA-06
**Success Criteria** (what must be TRUE):
  1. Starting the `worker` Docker service causes it to fetch from JSearch, normalize, dedup (including against already-stored jobs), score, and persist results on the configured schedule — without the UI container running
  2. A 429 or network error on one JSearch query does not abort results from other queries; partial results are persisted and the error is logged per-query
  3. Each run creates a row in the `runs` table recording how many jobs were fetched, deduped, scored, and newly seen — queryable by the UI for the status panel
  4. `mark_seen(job_id)` persists across process restarts; a job stored in a previous run is treated as already-seen by the next run and is not re-scored or re-notified
  5. Calling `run_pipeline()` from any Python context (worker cron, unit test, future UI button) produces the same output — no Streamlit or APScheduler import required inside `pipeline.py`
**Plans**: TBD

### Phase 9: Notifications & Digest
**Goal**: After each pipeline run, new strong_fit/good_fit jobs above the configured threshold are delivered to a single chosen channel (Telegram or email) without duplicates; if no channel is configured, the run completes silently
**Depends on**: Phase 8
**Requirements**: NOTIF-01, NOTIF-02, NOTIF-03
**Success Criteria** (what must be TRUE):
  1. When `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set, a Telegram message is sent after each run containing job title, company, score, recommendation, top reasons, and URL for each new qualifying offer
  2. When only `SMTP_*` vars are set (no Telegram), a digest email is sent instead; when neither is set, the run completes with no error and a log entry noting no channel is configured
  3. A job is marked `seen=1` in SQLite only after the delivery succeeds — if the Telegram/email call fails, the job remains unseen and will be included in the next run's digest
  4. A job that was already delivered in a previous run never appears in a subsequent digest, even after the worker restarts
**Plans**: TBD

### Phase 10: Streamlit UI
**Goal**: Jaime can run the entire tool from a browser tab: upload his CV, configure search parameters and scoring weights, browse and filter all scored offers with full score breakdowns, trigger an immediate run, and inspect the scheduler status — with all settings persisted so the worker respects them
**Depends on**: Phase 6, Phase 7, Phase 8, Phase 9
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05, UI-06, UI-07, UI-08, UI-09, UI-10, DOC-04
**Success Criteria** (what must be TRUE):
  1. Uploading a PDF in the CV page parses and displays the extracted `CVProfile` (experience, skills, education) and persists the cache — a page reload does not re-parse the same file
  2. Changing search parameters (country, language, position, `date_posted`, remote-only) and saving them in the UI causes the next scheduled worker run to use those parameters — no Docker restart needed
  3. The results page lists all scored offers sortable and filterable by score and recommendation; expanding any row shows the full score breakdown (all four sub-scores plus reasons and skills)
  4. Clicking "Run now" triggers the shared pipeline in a non-blocking thread; the UI shows a live status indicator and does not freeze; when the run finishes the results page refreshes with new offers
  5. Adjusting scoring weights or deal-breakers in the Settings page persists them to the `settings` table; clicking "Re-score" applies the new weights to existing stored jobs without re-fetching
  6. The scheduler status panel shows the timestamp of the last run, the next scheduled run, and the count of new offers found — data comes from the `runs` table
  7. Loading or interacting with the UI never triggers a reload of the BGE-M3 model; the model is initialized once per Streamlit process lifetime via `@st.cache_resource`
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Parseo de CV | v1.0 | 4/4 | Complete | 2026-05-22 |
| 2. Normalización y Deduplicación | v1.0 | 4/4 | Complete | 2026-05-22 |
| 3. Heurística de Scoring (núcleo) | v1.0 | 4/4 | Complete | 2026-05-22 |
| 4. API y Persistencia | v1.0 | 4/4 | Complete | 2026-05-23 |
| 5. Observabilidad, Robustez y Docs n8n | v1.0 | 3/3 | Complete | 2026-05-23 |
| 6. Architecture Cleanup & Storage Foundation | v2.0 | 4/5 | In Progress|  |
| 7. Embeddings-First Scoring Refactor | v2.0 | 0/? | Not started | - |
| 8. JSearch Client & Worker Pipeline | v2.0 | 0/? | Not started | - |
| 9. Notifications & Digest | v2.0 | 0/? | Not started | - |
| 10. Streamlit UI | v2.0 | 0/? | Not started | - |
