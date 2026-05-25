# Phase 8: JSearch Client & Worker Pipeline - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning
**Mode:** Streamlined + focused research (novel external API; defaults reused from archived n8n workflow)

<domain>
## Phase Boundary

The app fetches job offers from JSearch (RapidAPI) under its own power, and a background worker runs the full pipeline on a schedule. The pipeline is a single shared function so a manual UI trigger (Phase 10) and the scheduled worker produce identical results.

Deliverables:
- **JSearch client** (`app/sources/jsearch.py`): app-owned fetch over httpx; multi-query (one call per ranking query); per-query error isolation (429/network on one query does NOT abort the others); returns raw payloads for normalization.
- **Shared pipeline** (`app/pipeline.py`): `run_pipeline()` = fetch → normalize → dedup (incl. against already-stored jobs) → score → persist → record a run. NO Streamlit and NO APScheduler import inside this module (success criterion 5).
- **Worker** (`worker.py`, already scaffolded in Phase 6): the BlockingScheduler calls `run_pipeline()` on the configured interval. Runs without the UI container.
- **Storage additions**: a `runs` table (STORE-05) recording per-run counts (fetched, deduped, scored, new_seen, errors, timestamps); `mark_seen(job_id)` (STORE-07) persisting across process restarts.

</domain>

<decisions>
## Implementation Decisions (pinned — reuse archived n8n workflow patterns + sensible defaults)

### JSearch client
- HTTP via **httpx**. The worker runs a synchronous BlockingScheduler job; prefer a **sync `httpx.Client`** in the client for reliability (no event loop inside the scheduler). CLAUDE.md states a preference for async httpx — if the planner uses async, it MUST wrap with `asyncio.run()` at the pipeline boundary, never leak a loop into the scheduler. Sync is the recommended default here.
- Endpoint: JSearch `/search` (RapidAPI). Auth via `RAPIDAPI_KEY` header (`X-RapidAPI-Key` + `X-RapidAPI-Host: jsearch.p.rapidapi.com`), read from env — never hardcoded.
- **Multi-query**: iterate over the search queries (default = the user's `ranking_puestos` titles, or a `search_query` settings value). One JSearch call per query.
- **Params** (from settings + n8n defaults): `date_posted` = `month` on first run (empty DB → backfill ~1 month) else `3days`; `num_pages` = `1`; `country` from `search_country` setting (default `es`; remote-friendly). `query` per the multi-query list.
- **Per-query error isolation** (SRC-02 / success criterion 2): wrap each query call in try/except. On 429 or network error, log it per-query and continue; persist whatever other queries returned. Never let one bad query abort the batch.
- **Field mapping** (SRC-03): reuse/verify `app/dedup/mappers.py::jsearch_mapper`. STATE blocker: that mapper was written against n8n-transformed data, not the raw JSearch `/search` response — RESEARCH must confirm the raw response shape (`{"data": [ {job_title, employer_name, job_description, job_city/job_country, job_apply_link, job_posted_at_timestamp, ...} ]}`) and the planner must verify the mapper field-by-field before integration tests.

### Shared pipeline (`app/pipeline.py`)
- `run_pipeline(*, storage=None, embedder=None, ...)` — dependency-injectable for tests. Steps: fetch (JSearch client) → `normalize_jobs` (app/dedup) → `deduplicate` (incl. against already-stored jobs, not just within the batch) → `score_job` per unique job (inject embedder; OpenAI optional) → `upsert_scored_jobs` → write a `runs` row. Returns a structured result (counts + the scored jobs) so UI and tests can consume it.
- **No Streamlit / no APScheduler import** in pipeline.py (success criterion 5). Importing it from a plain Python context (unit test, worker, future UI button) must work and produce identical output.
- Dedup against stored: a job already in the DB from a prior run is recognized (by stable id) and not re-scored/re-counted as new.

### Worker
- `worker.py` already reads `schedule_interval_hours` from settings and starts a BlockingScheduler (Phase 6). Phase 8 wires `run_pipeline()` as the real job body (replace the stub log). Keep `coalesce`, `misfire_grace_time`, `max_instances=1`, `ZoneInfo("Europe/Madrid")`.

### Storage
- **`runs` table** (STORE-05): columns e.g. `id INTEGER PK, started_at, finished_at, fetched, deduped, scored, new_seen, errors TEXT`. Add `record_run(...)` / `get_recent_runs(limit)` methods to SQLiteStorage + the Protocol. Queryable by the UI status panel (Phase 10).
- **`mark_seen(job_id)`** (STORE-07): set `seen=1` for a job; persists across restarts (jobs table already has `seen`). `was_seen()` already exists. Note: in Phase 9 `mark_seen` is only called AFTER successful delivery — but Phase 8 just needs the method + persistence; the pipeline records jobs (seen stays 0 until notified).

### Defaults seeded in settings (extend Phase 6 settings if missing)
- `search_country` (default `es`), `search_query` (default derived from ranking), `date_posted` handled by first-run logic, `num_pages` = 1.

</decisions>

<code_context>
## Existing Code Insights

- `app/dedup/mappers.py::jsearch_mapper` (line 138) — maps a JSearch `/search` data element to `Job`. VERIFY field-by-field against raw API (STATE blocker). `SOURCE_MAPPERS["jsearch"]` registry exists.
- `app/dedup/__init__.py` — `normalize_jobs(...)` (line 28), `deduplicate(...)` (line 63). Pipeline calls these.
- `app/scoring/scorer.py::score_job(job, user_profile, cv_profile, embedder, *, client=None)` — new v2 signature (Phase 7).
- `app/storage/sqlite.py` — `upsert_scored_jobs` (preserves first_seen/seen), `was_seen`, `get_settings`/`set_setting`. ADD: runs table + record_run/get_recent_runs + mark_seen. Apply WAL/busy_timeout factory already in place.
- `app/storage/protocol.py` — extend Protocol with the new methods.
- `worker.py` — scaffolded BlockingScheduler; wire run_pipeline as the job body.
- `app/config/loader.py` — loads profile.yaml (UserProfile incl. ranking_puestos) for the pipeline.
- BGE-M3 embedder: `app/dedup/embedder.py::BgeM3Embedder` (real) / `FakeEmbedder` (tests). The pipeline constructs/receives ONE embedder instance (RAM: worker + UI each load ~2-4GB — STATE note; pipeline should accept an injected embedder, construct once).

</code_context>

<specifics>
## Specific Ideas

- Tests (QA-06): mock the JSearch HTTP layer (httpx — use respx or monkeypatch the client), mock embeddings (FakeEmbedder) and LLM. Cover: per-query 429 isolation (one query 429s, others persist), runs row written with correct counts, mark_seen persists across a simulated restart (new storage instance, same db file), run_pipeline importable with NO Streamlit/APScheduler in sys.modules, dedup-against-stored (a prior-run job is not re-counted as new).
- Confirm `import app.pipeline` does NOT pull streamlit or apscheduler into sys.modules (success criterion 5) — add a test asserting this.

</specifics>

<deferred>
## Deferred Ideas

- Notifications/digest delivery → Phase 9 (mark_seen-after-delivery semantics live there).
- UI status panel consuming runs table → Phase 10.
- num_pages exposed in UI (UI-11) — deferred to v2.x.

</deferred>
