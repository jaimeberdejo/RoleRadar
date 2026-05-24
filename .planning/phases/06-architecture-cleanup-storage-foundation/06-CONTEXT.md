# Phase 6: Architecture Cleanup & Storage Foundation - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — smart discuss skipped per infrastructure-detection rule)

<domain>
## Phase Boundary

Make the codebase clean, safe, and ready for multi-process (UI + worker) work:
- Remove the FastAPI/uvicorn/n8n service layer (`app/api/`) — the core is consumed in-process, not over HTTP.
- Eliminate the hardcoded `RAPIDAPI_KEY` from `docker-compose.yml` (treat the leaked key as compromised — must be rotated by the user out-of-band) and document all v2.0 env vars in `.env.example`.
- Restructure `docker-compose.yml` to two services (`ui` + `worker`) from one image, sharing `data/` and `hf_cache/` named volumes; no n8n service.
- Swap dependencies: drop `fastapi`, `uvicorn`, `python-multipart`; add `streamlit`, `APScheduler` (3.11.x, NOT v4 alpha), `python-telegram-bot`.
- Add a `settings` table in SQLite as the cross-process config bus, with `storage.get_settings()` returning defaults for all v2.0 keys.
- Make SQLite concurrency-safe: WAL mode + `busy_timeout=5000` on every connection.

This phase delivers NO user-facing behavior — it is pure plumbing/migration so phases 7–10 can build on a stable foundation.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — this is a pure infrastructure/migration phase. Use the ROADMAP phase goal, success criteria, the v2.0 architecture decisions already logged in STATE.md, and existing codebase conventions to guide decisions.

### Locked constraints (from STATE.md / PROJECT.md — not open for re-decision)
- Two Docker services (`ui` + `worker`) from a single image, shared named volumes (`data/`, `hf_cache/`).
- `BlockingScheduler` lives in the worker process — NEVER APScheduler inside Streamlit.
- APScheduler **3.11.x** (not v4 alpha); timezone via `ZoneInfo("Europe/Madrid")` — not pytz.
- `settings` table is the cross-process config bus; `profile.yaml` remains only for hand-edited identity (name, ranking, deal-breakers).
- `RAPIDAPI_KEY` must be `${RAPIDAPI_KEY:-}` interpolated, never literal. **First task of this phase.**
- Persistence stays SQLite-only (Supabase removed from scope 2026-05-23). The `app/storage/protocol.py` Protocol stays so a future network backend remains pluggable.

</decisions>

<code_context>
## Existing Code Insights

### To be removed
- `app/api/` — `main.py`, `auth.py`, `deps.py`, `routes/{cv,jobs,profile}.py`. Importing the project must stop pulling in `fastapi`/`uvicorn`/`python-multipart` afterward.

### Reusable Assets (keep + extend)
- `app/storage/sqlite.py` (~6.8 KB) — extend with the `settings` table, WAL pragma, and `busy_timeout`; add `get_settings()`/`set_setting()`.
- `app/storage/protocol.py` — storage Protocol; add settings methods to the contract.
- `app/config/loader.py` — `profile.yaml` loader (`yaml.safe_load` only); coexists with the new settings table.
- Core modules untouched by this phase but depended on downstream: `app/cv/`, `app/dedup/`, `app/scoring/`, `app/models/schemas.py`.

### Integration Points
- `pyproject.toml` — dependency swap.
- `docker-compose.yml` (working tree currently has the live secret on line ~92) + `Dockerfile` — two-service restructure.
- `.env.example` — document RAPIDAPI_KEY, TELEGRAM_*, SMTP_*, OPENAI (optional); remove any FastAPI/API-key vars.

</code_context>

<specifics>
## Specific Ideas

- Settings keys to seed with defaults (from ROADMAP success criterion 4): `search_query`, `search_country`, `schedule_interval_hours`, scoring weights (puesto/skills/ubicacion/seniority), `dedup_threshold`. Add notification threshold/channel keys here too if cheap, since phases 8–9 will read them.
- WAL + `busy_timeout=5000` must be applied on **every** connection open, not once — verify with a concurrent write/read test (success criterion 5).

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase, scope is fully bounded by the ROADMAP success criteria.

</deferred>
