---
phase: 06-architecture-cleanup-storage-foundation
plan: "05"
subsystem: infrastructure
tags:
  - docker
  - apscheduler
  - worker
  - env-config
  - streamlit
dependency_graph:
  requires:
    - "06-02"
    - "06-03"
    - "06-04"
  provides:
    - docker-two-service-layout
    - worker-entrypoint-stub
    - v2-env-documentation
  affects:
    - Phase 8 (worker pipeline implementation)
    - Phase 10 (Streamlit UI in ui/)
tech_stack:
  added:
    - APScheduler 3.11.x (BlockingScheduler)
    - zoneinfo (stdlib, ZoneInfo("Europe/Madrid"))
  patterns:
    - Two-service Docker Compose from one image (ui + worker)
    - Neutral Dockerfile CMD overridden per-service in compose
    - worker.py as standalone process (never imported from Streamlit)
key_files:
  created:
    - worker.py
    - ui/.gitkeep
  modified:
    - Dockerfile
    - .env.example
decisions:
  - "Neutral Dockerfile CMD ('print Use: docker compose up') — each service defines its own command in compose, so the image has no hard-coded entrypoint"
  - "COPY worker.py + RUN mkdir -p ui in Dockerfile — ensures paths exist in image before compose command overrides run"
  - "EXPOSE 8000 removed from Dockerfile — port irrelevant in v2.0 Streamlit architecture; compose handles port mapping"
  - "All .env.example values commented out — file is documentation only; grep -vE '^#|^$' returns 0 lines (verified)"
metrics:
  duration: "~2 minutes"
  completed_date: "2026-05-24"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
  files_created: 3
---

# Phase 6 Plan 05: Docker Restructure + Worker Stub + Env Documentation Summary

**One-liner:** Two-service Docker Compose (ui+worker from one image) with APScheduler BlockingScheduler stub and v2.0 .env.example documentation replacing all FastAPI artifacts.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update Dockerfile CMD + create worker.py stub + ui/ placeholder | d2b1f30 | Dockerfile, worker.py, ui/.gitkeep |
| 2 | Rewrite .env.example for v2.0 | dc0392f | .env.example |

Note: docker-compose.yml was already restructured to the two-service ui+worker layout by plan 06-03 (commit 782e463). This plan verified that state was correct and added the remaining artifacts.

## Success Criteria Verification

- `docker compose config --services` outputs exactly `ui` and `worker` — VERIFIED
- Both services in docker-compose.yml use `image: buscadordeempleo:latest` — VERIFIED
- Both services mount `data:/app/data` and `hf_cache:/app/.cache/huggingface` — VERIFIED
- worker.py exists, importable, contains BlockingScheduler with ZoneInfo("Europe/Madrid") — VERIFIED
- Dockerfile CMD does not reference uvicorn or app.api.main — VERIFIED (0 matches)
- .env.example contains RAPIDAPI_KEY, TELEGRAM_BOT_TOKEN, SMTP_HOST — VERIFIED
- .env.example does not contain active API_KEY= line — VERIFIED (0 active non-comment lines)
- `uv run pytest tests/ -q` exits 0 — VERIFIED (163 passed)

## Deviations from Plan

### Auto-fixed Issues

None. Plan executed exactly as written.

### Observations

- docker-compose.yml was already in the target state (two services ui+worker, no n8n, no hardcoded keys) from plan 06-03. This plan's Task 1 correctly reconciled this — no overwrite needed for compose, only Dockerfile + worker.py + ui/.gitkeep changes applied.
- EXPOSE 8000 removed from Dockerfile (task action said "remove or leave" — removed for cleanliness since v2.0 uses port 8501 via compose, not direct Docker expose).

## Known Stubs

- **worker.py `run_pipeline()`** — stub function that logs a message and returns. Phase 8 will implement the actual JSearch fetch + normalize + score + notify pipeline. The BlockingScheduler is live (runs every 6 hours) but the job body is a no-op.
- **ui/.gitkeep** — placeholder directory only. Phase 10 creates `ui/app.py` (Streamlit app).

## Threat Surface Scan

No new network endpoints introduced. No new auth paths. No schema changes.

| Flag | File | Description |
|------|------|-------------|
| Verified: T-6-05-01 | .env.example | All values commented out — 0 active uncommented lines confirmed |
| Verified: T-6-05-02 | docker-compose.yml | No hardcoded RAPIDAPI_KEY literal (grep count = 0) |
| Verified: T-6-05-03 | worker.py | `if __name__ == "__main__":` guard — BlockingScheduler.start() only on direct execution |

## Self-Check

**Checking created files exist:**
- worker.py: FOUND
- ui/.gitkeep: FOUND
- .env.example (modified): FOUND
- Dockerfile (modified): FOUND

**Checking commits exist:**
- d2b1f30: FOUND (Task 1)
- dc0392f: FOUND (Task 2)

## Self-Check: PASSED
