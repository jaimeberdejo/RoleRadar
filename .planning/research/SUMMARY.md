# Project Research Summary

**Project:** BuscadorDeEmpleo v2.0 — Standalone App (Streamlit + Scheduler)
**Domain:** Personal job-aggregator — single-user, self-hosted, local-first standalone Python app
**Researched:** 2026-05-24
**Confidence:** HIGH

## Executive Summary

BuscadorDeEmpleo v2.0 is a self-hosted standalone Python app that replaces the v1.x FastAPI + n8n stack with a Streamlit UI and an APScheduler worker process sharing a local SQLite database. The core intelligence modules (CV parsing, BGE-M3 dedup, scoring heuristic, storage) built and tested in v1.0 are reused unchanged or with targeted modifications — no rewrite. The two net-new capabilities are (1) an app-owned outbound JSearch client that replaces n8n's HTTP nodes, and (2) a separate Docker worker process running BlockingScheduler that triggers the full pipeline on a cron without any browser tab being open.

The recommended architecture is two Docker services sharing one image: `ui` (Streamlit) and `worker` (BlockingScheduler), both mounting the same `data/` and `hf_cache/` named volumes. This cleanly separates the always-on scheduler from the interactive UI, avoids the well-documented APScheduler-in-Streamlit double-fire and idle-process pitfalls, and lets each service restart independently. All scoring runs fully offline via BGE-M3 + deterministic rules; OpenAI is an optional enrichment layer that adds honest prose reasons and itemized matched/missing skills, activated only when `OPENAI_API_KEY` is present.

The primary risks are: (a) the existing `scorer.py` imports OpenAI unconditionally — the highest-complexity change in v2.0, must happen before the UI or worker is wired up; (b) SQLite lacks WAL mode, which will cause `database is locked` errors the moment the worker writes while Streamlit reads — a two-line fix that must land first; (c) a RapidAPI key sits inline in the working-tree `docker-compose.yml` but is NOT in committed history — no git rewrite needed, but the key leaked in chat and must be rotated and replaced with `${RAPIDAPI_KEY:-}` before any commit. Both infrastructure fixes (WAL + key cleanup) belong in Phase 1 as prerequisites for everything else.

---

## Key Findings

### Recommended Stack

The v2.0 stack is a targeted delta on v1.x: add `streamlit>=1.57.0`, `APScheduler>=3.11.2`, `python-telegram-bot>=22.7`; remove `fastapi`, `uvicorn`, `python-multipart`. All other deps (httpx, Pydantic v2, Instructor, OpenAI, pymupdf, sentence-transformers/BGE-M3, SQLite stdlib, pytest, Docker) are reused as-is. Python is 3.13 per `pyproject.toml`. Dependency management is `uv`.

**Core technologies (v2.0 additions):**
- `streamlit>=1.57.0`: UI framework — replaces n8n as the user-facing surface; `st.cache_resource` is the correct singleton pattern for BGE-M3 and SQLiteStorage; `st.file_uploader` replaces the FastAPI multipart endpoint
- `APScheduler>=3.11.2` (v3.x stable, NOT v4 alpha): BlockingScheduler in a dedicated worker process; v4 is explicitly pre-release and must not be used
- `python-telegram-bot>=22.7`: async-native digest delivery via `telegram.Bot.send_message`; internally uses httpx so no second HTTP client is needed
- `pandas>=2.2`: explicit pin for `st.dataframe` rendering (already a transitive dep of sentence-transformers)
- Email via stdlib `smtplib` + `email.message.EmailMessage` — zero new deps

**Deps to remove:** `fastapi`, `uvicorn[standard]`, `python-multipart` — their only consumer (n8n) is retired.

**Key version constraint:** APScheduler 4.x is alpha/pre-release; use 3.11.2 stable. Always pass `ZoneInfo("Europe/Madrid")` to `CronTrigger` — never `pytz.timezone(...)` (pytz removed in v4, and pytz objects are silently misinterpreted).

### Expected Features

All v2.0 features are new; the v1.0 core (CV parse, normalize, dedup, score, store) ships unchanged as the module layer.

**Must have (table stakes for v2.0 launch):**
- Streamlit UI with three pages: CV upload + profile status, search configuration (query/country/language/num_pages), results browser (sorted by score, expandable job detail with full score breakdown)
- JSearch client (`app/sources/jsearch.py`, httpx sync) — only outbound job-search call; `RAPIDAPI_KEY` from env only; 429 retry + partial-batch isolation; default `num_pages=1`
- APScheduler worker as a separate Docker service (BlockingScheduler, cron daily 08:00 Madrid time, `misfire_grace_time=3600`) sharing the `data/` volume with the UI
- Embeddings-first scoring: all four numeric sub-scores produced by BGE-M3 cosine + deterministic rules without any OpenAI call
- Digest delivery — one channel chosen by env: Telegram if `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` set, else email if `SMTP_*` set, else silent skip
- Docker Compose cleanup: retire `n8n` service, add `ui` and `worker` services, move `RAPIDAPI_KEY` to `${RAPIDAPI_KEY:-}`, archive `n8n/` directory

**Should have (differentiators):**
- Settings page that writes search/schedule/scoring params to a `settings` SQLite table; worker reads these before each run — no restart required for most config changes
- Scheduler status display from a `runs` table ("last run", "next run", jobs found/new)
- LLM enrichment layer when `OPENAI_API_KEY` is present: honest prose `reasons_for`, `reasons_against`, `matched_skills`, `missing_requirements`
- Fallback reason templates when OpenAI is absent

**Defer to v2.x:**
- "Run now" button (requires IPC: flag file or SQLite `commands` table)
- Fine-tune scoring weights via UI sliders (requires atomic POSIX write-back to profile.yaml or a separate config file)
- Re-score all button (expensive: BGE-M3 + optional N×LLM calls; gate with confirmation)
- Run history analytics / STORE-04; Langfuse full wiring / OBS-04; additional job sources

**Anti-features (explicitly out of scope):**
- APScheduler inside the Streamlit process; BackgroundScheduler (use BlockingScheduler in the worker)
- Authentication / multi-user; Redis / Celery / RQ; OpenAI embeddings; multiple LLM providers

### Architecture Approach

Two independent Python processes sharing one Docker image and two named volumes (`data/` for SQLite + profile + CV cache; `hf_cache/` for BGE-M3 weights). They communicate exclusively through SQLite (WAL mode), never through shared memory, sockets, or APScheduler job stores. The `settings` table acts as a cross-process config bus: the UI writes search/schedule parameters, the worker reads them at each run start.

**Major components:**
1. `app/ui/` (4 Streamlit pages) — CV upload, search config, results browser, settings; `@st.cache_resource` for SQLiteStorage + UserProfile; manual pipeline trigger via direct `run_pipeline()` call in a `threading.Thread` with `st.status`
2. `app/worker/` — `main.py` (BlockingScheduler, `ZoneInfo("Europe/Madrid")`, `misfire_grace_time=3600`), `pipeline.py` (fetch → normalize → filter-seen → dedup → score → upsert → notify)
3. `app/sources/jsearch.py` — httpx sync client; 429 retry + per-query error isolation; `RAPIDAPI_KEY` from env
4. `app/scoring/embeddings.py` (new) — BGE-M3 cosine for encaje_skills + seniority heuristic; reuses existing `BgeM3Embedder` without duplication
5. `app/scoring/scorer.py` (modified) — deterministic-first orchestrator; LLM enrichment via deferred import inside `if enrich_with_llm and _openai_key_present()` branch
6. `app/storage/sqlite.py` (modified) — WAL + `busy_timeout=5000` in `_connect()`; `settings` table
7. `app/notify/` — `telegram.py` (chunked to ≤3500 chars) and `email.py` (stdlib smtplib); seen-tracking update only after successful delivery
8. `app/api/` — DELETED entirely

**Data flow (scheduled run):** APScheduler fires `run_job()` → load profile + CV cache → `storage.get_settings()` → `jsearch.fetch_jobs()` → normalize → filter already-seen → dedup (BGE-M3) → score (embeddings + optional LLM) → `storage.upsert_scored_jobs()` → notify → mark seen.

### Critical Pitfalls

1. **BGE-M3 reloaded on every Streamlit rerun** — wrap `BgeM3Embedder()` in `@st.cache_resource`; never at script top-level; NOT `@st.cache_data` (fails for PyTorch objects). Address in Phase 6 before any integration test.

2. **APScheduler in the wrong process (Streamlit) causes double-fire or idle-kill** — worker is the sole owner of BlockingScheduler; UI never touches APScheduler; UI calls `run_pipeline()` directly for manual runs. Address in Phase 4 as an architectural constraint before any scheduler code.

3. **SQLite `database is locked` under concurrent worker-write + UI-read** — add `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` to every `_connect()` call; keep write transactions short. Address in Phase 2 before any multi-process work.

4. **`scorer.py` imports OpenAI unconditionally, crashes offline** — restructure `score_job()` so all numeric scores are computed first, then gate LLM behind `if enrich_with_llm and _openai_key_present(): from app.scoring.llm import ...`; never import `openai`/`instructor` at module level in the scorer. Address in Phase 3.

5. **RapidAPI key inline in working-tree `docker-compose.yml`** — NOT in committed history (no git rewrite needed), but leaked in chat: rotate immediately, replace with `${RAPIDAPI_KEY:-}` before any commit. Address as first task of Phase 1.

6. **Seen-tracking broken by delivery failure ordering** — mark `seen=1` ONLY after successful delivery; wrap delivery in retry loop (3 attempts, exponential backoff); chunk Telegram to ≤3500 chars to avoid `MESSAGE_TOO_LONG`. Address in Phase 5.

7. **JSearch 429 kills the entire pipeline batch** — catch per-query (not per-batch); retry up to 3 times; return partial results from other queries; default `num_pages=1`. Address in Phase 4.

---

## Implications for Roadmap

All four research files converged on the same 6-phase build order. The ordering is dependency-driven: infrastructure cleanup and storage hardening must precede any multi-process work; the scorer must be made offline-capable before it is wired into either the worker or the UI; the UI is built last because it consumes all other modules.

### Phase 1: Architecture Cleanup

**Rationale:** Two security/infrastructure issues block everything else: the inline RapidAPI key and the FastAPI layer removal. Pure cleanup — no new logic, lowest risk, highest leverage.

**Delivers:** Clean working tree with no hardcoded secrets; `app/api/` deleted; `docker-compose.yml` restructured toward `ui` + `worker` services sharing named volumes; `pyproject.toml` updated (remove fastapi/uvicorn/python-multipart, add streamlit/apscheduler/python-telegram-bot); `n8n/` archived (not deleted); Dockerfile CMD removed.

**Addresses:** Docker Compose cleanup (P1); security fix for RAPIDAPI_KEY inline.

**Avoids:** Pitfall 7 (key committed); prevents inline key ever landing in git history.

**Research flag:** Standard patterns — no additional research needed.

---

### Phase 2: Storage Extension

**Rationale:** Both worker and UI depend on SQLite concurrency being safe. WAL + `busy_timeout` are two-line additions to `_connect()` but must land before any two-process scenario. The `settings` table is the config bus the worker reads before each run.

**Delivers:** `SQLiteStorage._connect()` with WAL + `busy_timeout=5000`; `settings` table with `get_settings()` / `update_setting()` / `init_settings_defaults()`; default rows seeded by `init_db` (`search_query`, `search_country`, `search_language`, `search_num_pages`, `schedule_interval_hours`, `openai_enrichment_enabled`, `dedup_umbral`); Storage Protocol updated.

**Avoids:** Pitfall 6 (SQLite locked); Pitfall 10 (weight drift via session_state only).

**Research flag:** Standard — SQLite WAL is a two-liner with official docs. Can run in parallel with Phase 3.

---

### Phase 3: Embeddings-First Scoring Refactor

**Rationale:** The highest-complexity change in v2.0. `scorer.py` calls `build_instructor_client()` unconditionally — this must be fixed before the scoring module is imported by either the UI or the worker. This phase also delivers the core v2.0 value proposition: deterministic, testable, always-available scores without a cloud dependency.

**Delivers:** `app/scoring/embeddings.py` (new) — BGE-M3 cosine for encaje_skills + seniority keyword heuristic; `scorer.py` restructured — all four numeric sub-scores deterministic first, LLM via deferred import; `_openai_key_present()` helper; `LLMJobAssessment` schema narrowed to prose-only fields; fallback reason templates for offline mode; ranking title match via BGE-M3 cosine against ranking entries + synonyms. Updated scorer tests with `FakeEmbedder`.

**Avoids:** Pitfall 9 (OpenAI import at module level); establishes `@st.cache_resource` pattern for BGE-M3 early.

**Research flag:** Well-documented — the lazy-import gate already exists in `app/dedup/embedder.py`. Can run in parallel with Phase 2.

---

### Phase 4: JSearch Client + Worker Pipeline

**Rationale:** With storage and scoring complete, the worker pipeline can be assembled. JSearch client must include retry/partial-result logic from day one. The `BlockingScheduler`-in-separate-process topology is an architectural constraint that must be established before a single line of scheduler code exists.

**Delivers:** `app/sources/jsearch.py` — httpx sync client, `RAPIDAPI_KEY` from env, 429 retry (exponential backoff, per-query isolation), `num_pages=1` default; `app/worker/pipeline.py` — `run_pipeline(storage, user_profile, cv_profile)` synchronous, callable from both worker and UI manual trigger; `app/worker/main.py` — BlockingScheduler with `ZoneInfo("Europe/Madrid")`, `misfire_grace_time=3600`, `coalesce=latest`, reads `schedule_interval_hours` from settings; end-to-end pipeline test with mocked JSearch + `FakeEmbedder`.

**Avoids:** Pitfall 3 (scheduler in wrong process); Pitfall 4 (double-fire); Pitfall 5 (timezone/misfire); Pitfall 8 (JSearch 429 kills batch).

**Research flag:** Standard patterns confirmed. Verify existing `jsearch` mapper in `app/dedup/mappers.py` matches real JSearch response fields before Phase 4 integration tests.

---

### Phase 5: Notifications (Telegram + Email)

**Rationale:** Short to implement but has a subtle ordering constraint — seen-tracking must update only after successful delivery — that must be designed alongside the delivery code.

**Delivers:** `app/notify/telegram.py` — `telegram.Bot.send_message`, Markdown chunked to ≤3500 chars, retry on failure; `app/notify/email.py` — smtplib + MIMEMultipart HTML table; `mark_seen()` called only after successful delivery; `notify_channel` setting in settings table; `DIGEST_MIN_SCORE` and `DIGEST_NOTIFY_EMPTY` env vars; integration test verifying `seen=1` set only on success.

**Avoids:** Pitfall 11 (delivery failures / duplicates / `MESSAGE_TOO_LONG`).

**Research flag:** Standard patterns confirmed. No additional research needed.

---

### Phase 6: Streamlit UI

**Rationale:** Built last because it consumes all other modules. The pages are relatively simple once the underlying modules exist; the main constraint is applying `@st.cache_resource` correctly and offloading the pipeline to a thread for manual "Run now".

**Delivers:** `app/ui/main.py` (st.navigation entry + `@st.cache_resource` for SQLiteStorage + UserProfile); four pages: `01_cv.py` (PDF upload → `parse_cv_from_bytes()` → display CVProfile), `02_search.py` (search params form + manual "Run now" in `threading.Thread` with `st.status`), `03_results.py` (job list sort/filter, expandable score breakdown, mark-seen toggle), `04_settings.py` (search/schedule/scoring params → `update_setting()`); `app/ui/components/job_card.py`; `.streamlit/config.toml`.

**Avoids:** Pitfall 1 (blocking UI — thread + st.status); Pitfall 2 (BGE-M3 reload — `@st.cache_resource`); Pitfall 3 (no APScheduler in UI process); Pitfall 10 (weights persist via settings table).

**Research flag:** Standard Streamlit patterns. Verify `st.navigation` API (added Streamlit 1.36) matches the multipage pattern.

---

### Phase Ordering Rationale

- Phases 1 → 2 → 3 are prerequisites for Phases 4, 5, 6. The scorer must be offline-capable and storage must support WAL before the worker can be tested safely.
- Phases 2 and 3 can run in parallel (no dependency between them; both depend only on Phase 1's clean codebase).
- Phase 4 requires both Phase 2 (settings table) and Phase 3 (offline-capable scorer).
- Phase 5 requires Phase 4 (delivery integrated into pipeline.py).
- Phase 6 requires Phases 2, 3, and 4 (imports storage, scorer, and run_pipeline).
- No phase needs external API research — all library patterns confirmed via Context7 + official docs.

### Research Flags

All phases use standard, well-documented patterns. No phase needs `/gsd-research-phase` during planning.

Needs manual verification (integration testing, not research):
- **JSearch mapper field names** — confirm `app/dedup/mappers.py` jsearch mapper matches real JSearch API response before Phase 4 integration tests (budget 1-2 hours).
- **`anios_experiencia_total=None` in cached CVProfile** — seniority heuristic in Phase 3 must treat `None` as "unknown" and default `encaje_seniority` to a neutral value (e.g., 50/100).

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions confirmed via `pip index versions`; Python 3.13 compatibility verified via PyPI classifiers; APScheduler v4 alpha warning confirmed via Context7 |
| Features | HIGH | Feature set derived from direct analysis of existing v1.x codebase + official Streamlit/APScheduler docs; scoring refactor scope well-understood from `scorer.py` code inspection |
| Architecture | HIGH | All claims verified against official docs (SQLite WAL, APScheduler FAQ, Streamlit threading, Docker Compose); two-service topology is the explicit recommendation in both APScheduler FAQ and Streamlit threading docs |
| Pitfalls | HIGH | All critical pitfalls sourced from official docs or verified via community issues with reproducible symptoms; RAPIDAPI_KEY status confirmed by direct `git log --all -p` inspection |

**Overall confidence:** HIGH

### Gaps to Address

- **JSearch mapper field alignment:** The existing mapper was written against the n8n workflow's data shape, not a direct JSearch API call. Make one real API call in Phase 4 and compare response fields. Budget 1-2 hours for corrections.

- **`anios_experiencia_total=None`:** The CV was parsed with this field as `None`. The Phase 3 seniority heuristic must handle `None` as "unknown" — not 0 years — and default `encaje_seniority` to a neutral value with a note in `reasons_against`.

- **Scoring weights precedence:** Phase 6 can expose weight sliders writing to the `settings` table. Define explicitly (in Phase 3 or Phase 6) whether `settings` table weights take precedence over `profile.yaml` weights, or vice versa.

- **BGE-M3 dual-process RAM usage:** Both `ui` and `worker` load BGE-M3 independently (~2-4 GB each). On an 8 GB machine, concurrent UI manual run + scheduled worker run may be tight. No action needed unless OOM is observed in practice.

---

## Sources

### Primary (HIGH confidence)
- APScheduler 3.x user guide — BlockingScheduler, CronTrigger, misfire_grace_time, multi-process FAQ
- SQLite WAL official documentation — sqlite.org/wal.html; concurrent reader/writer model
- Streamlit `st.cache_resource` official docs — ML model caching, process lifetime guarantee
- Streamlit threading docs (Context7 `/streamlit/docs`) — thread + main-thread st.write pattern, st.status
- python-telegram-bot 22.7 (Context7 `/python-telegram-bot/python-telegram-bot`) — Bot.send_message push-only pattern
- Existing codebase (`app/scoring/scorer.py`, `app/storage/sqlite.py`, `app/dedup/embedder.py`, `docker-compose.yml`) — direct inspection

### Secondary (MEDIUM confidence)
- APScheduler migration guide v3 → v4 (Context7) — pytz → zoneinfo, add_job → add_schedule API changes
- SQLite concurrent writes blog (tenthousandmeters.com) — BEGIN IMMEDIATE for write-after-read upgrade
- Streamlit + APScheduler ReportContext warning (community discuss) — confirms BackgroundScheduler inside Streamlit is unreliable
- JSearch RapidAPI parameter docs — query, page, num_pages, date_posted, X-RapidAPI-Key header

### Tertiary (LOW confidence — verify during implementation)
- BGE-M3 cosine similarity thresholds — community practice suggests 0.75 for strong match; validate against real job data after first runs
- JSearch response field names in existing mapper — written against n8n data; needs live API verification before Phase 4

---
*Research completed: 2026-05-24*
*Ready for roadmap: yes*
