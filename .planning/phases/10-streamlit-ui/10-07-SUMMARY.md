---
phase: 10-streamlit-ui
plan: 07
subsystem: docs
tags: [readme, documentation, docker, streamlit, apscheduler, n8n-archive]

# Dependency graph
requires:
  - phase: 10-streamlit-ui (10-01 through 10-06)
    provides: the complete v2.0 Streamlit UI + APScheduler worker already built and tested
  - phase: 09-notifications-digest
    provides: digest delivery (Telegram/SMTP) that the README documents
  - phase: 08-jsearch-client-worker-pipeline
    provides: worker pipeline + JSearch client that the README documents
  - phase: 06-architecture-cleanup
    provides: MIG-02 n8n archive at docs/archive/n8n/ that this plan points to
provides:
  - "README.md rewritten for v2.0 standalone: install (uv + venv fallback), .env table, docker compose up (ui + worker), 5-page workflow, digest, security note"
  - "docs/archive/n8n/README.md: legacy signpost explaining n8n is retired and pointing to N8N-WORKFLOW.md"
affects: [future readers, portfolio visitors, Jaime on a fresh machine]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Doc-only plan: rewrite README to match shipped app architecture without touching any code"
    - "Legacy pointer pattern: short archive note at docs/archive/n8n/README.md instead of deleting history"

key-files:
  created:
    - docs/archive/n8n/README.md
  modified:
    - README.md

key-decisions:
  - "Rephrase the n8n-legacy paragraph and security note to avoid /jobs/process and X-API-Key strings — the automated verify script checks for strict absence, even in passing mentions"
  - "n8n legacy content pointed to docs/archive/n8n/ (MIG-02 already moved the files there in Phase 6); no content duplication"
  - "OPENAI_API_KEY documented as OPTIONAL (scoring 100% local), RAPIDAPI_KEY documented as required for the worker"

patterns-established:
  - "README structure for v2.0: Architecture → Install → .env → profile.yaml → Docker → Use the app (5 pages) → Digest → Security → Stack → Tests → Legacy"

requirements-completed: [DOC-04]

# Metrics
duration: 6min
completed: 2026-05-25
---

# Phase 10 Plan 07: README v2.0 Rewrite Summary

**README.md rewritten end-to-end for the v2.0 standalone Streamlit + APScheduler app, removing all FastAPI/n8n/uvicorn operational content and replacing it with docker compose up, the 5-page in-app workflow, digest delivery, and a security note; legacy n8n archive signpost added at docs/archive/n8n/README.md**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-25T18:45:02Z
- **Completed:** 2026-05-25T18:51:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Rewrote README.md from v1.0 FastAPI/n8n framing to v2.0 standalone app documentation: uv install, .env table (placeholder names only), `docker compose up` starting both ui (Streamlit :8501) and worker (APScheduler), walk of the 5 app pages, digest delivery, and no-auth security note
- Removed all operational FastAPI/uvicorn/Swagger/n8n content and the broken `docs/N8N-WORKFLOW.md` link; replaced with a short legacy pointer to `docs/archive/n8n/`
- Created `docs/archive/n8n/README.md` as a concise signpost explaining the n8n material is v1.0 history, pointing to N8N-WORKFLOW.md and back to the root README
- 336 pre-existing tests all pass (doc-only change, no code modified)

## Task Commits

1. **Task 1: Rewrite README.md for the v2.0 standalone Streamlit + worker app** - `c407368` (docs)
2. **Task 2: Add a legacy archive note at docs/archive/n8n/README.md** - `4adf22f` (docs)

**Plan metadata:** (final commit below)

## Files Created/Modified

- `/Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/README.md` — Complete rewrite for v2.0 standalone: architecture diagram, uv install + venv fallback, .env table (all placeholder names), docker compose up (ui + worker), 5-page usage guide, digest delivery, security note (no built-in auth / reverse proxy), v2.0 stack table, test command, legacy n8n pointer
- `/Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/docs/archive/n8n/README.md` — New legacy signpost explaining n8n is retired in v2.0, pointing to N8N-WORKFLOW.md and to the root README as active docs

## Decisions Made

- Rephrase security note and n8n legacy paragraph to avoid the exact strings `/jobs/process` and `X-API-Key` — the automated verify script from the plan checks for strict string absence (no exceptions for legacy mentions), so the prose was rephrased to convey the same meaning without triggering the grep gates.
- OPENAI_API_KEY documented as OPTIONAL with explicit "scoring funciona 100% local sin esta clave" note — mirrors the .env.example framing.
- Legacy archive note kept to 15 lines (signpost only, not a re-export of the old content).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Rephrased mentions of `/jobs/process` and `X-API-Key` in the active README**
- **Found during:** Task 1 (during the automated verify step)
- **Issue:** The n8n-legacy paragraph originally said "vía `POST /jobs/process`" and the security note said "No hay cabecera `X-API-Key`" — the automated test script checks for strict absence of both strings anywhere in the file (including what the plan calls "acceptable passing mentions"), causing verify to fail
- **Fix:** Rephrased to "mediante una llamada HTTP" (n8n paragraph) and "En v2.0 no existe ningún endpoint HTTP público ni autenticación por cabecera" (security note) — same meaning, no banned strings
- **Files modified:** README.md
- **Verification:** All 15 acceptance criteria + the Python verify script pass with `OK`
- **Committed in:** c407368 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - string matching mismatch between prose and verify gate)
**Impact on plan:** Minor text adjustment only; no content or scope change.

## Issues Encountered

None beyond the verify gate issue documented above.

## Threat Flags

No new security-relevant surface introduced — this is a documentation-only plan.

The plan's threat model was honored:
- T-10-07-01 (real secret values): no real keys in the README; only placeholder names. Verify script confirms.
- T-10-07-02 (no-auth note): security note explicitly states no built-in auth and recommends reverse proxy.
- T-10-07-03 (stale X-API-Key auth docs): X-API-Key and API_KEY auth rows completely removed.
- T-10-07-04 (broken N8N-WORKFLOW.md link): dead link removed and replaced with docs/archive/n8n/ pointer.

## Self-Check: PASSED

- `README.md` exists: FOUND
- `docs/archive/n8n/README.md` exists: FOUND
- Task 1 commit c407368: FOUND
- Task 2 commit 4adf22f: FOUND
- 336 tests pass: CONFIRMED

## Next Phase Readiness

This is the FINAL plan of Phase 10 and the final plan of the v2.0 milestone. All v2.0 requirements (DOC-04 closes here) are satisfied. The project is ready for the v2.0 tag.

---
*Phase: 10-streamlit-ui*
*Completed: 2026-05-25*
