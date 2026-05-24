---
phase: quick
plan: 260524-sg6
subsystem: auth
tags: [fastapi, starlette, middleware, api-key, authentication, security]

# Dependency graph
requires:
  - phase: quick/260523-u5d
    provides: Docker deployment setup that this auth protects in prod
provides:
  - X-API-Key authentication middleware protecting all routes except GET /health
  - Startup WARNING when API_KEY is unset (loud dev feedback)
  - .env.example + docker-compose.yml + README documentation for API_KEY
affects: [api, n8n-integration, docker-deployment]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ApiKeyMiddleware (Starlette BaseHTTPMiddleware) for auth — covers /docs, /openapi.json, /redoc as well as API routes"
    - "secrets.compare_digest for constant-time key comparison (timing-attack safe)"
    - "Same 401 body for missing and wrong key (anti-disclosure pattern)"
    - "Optional auth: API_KEY unset = auth disabled, all tests unaffected"

key-files:
  created:
    - app/api/auth.py
    - tests/api/test_auth.py
  modified:
    - app/api/main.py
    - .env.example
    - docker-compose.yml
    - README.md

key-decisions:
  - "Middleware over FastAPI global dependencies: BaseHTTPMiddleware covers /docs and Swagger assets that FastAPI dependencies= does not reach"
  - "_PUBLIC_PATHS frozenset to exempt /health without modifying profile.py"
  - "API_KEY unset = auth disabled (no-op middleware): preserves all 185 existing tests without any modification"
  - "Identical 401 response for missing and wrong key: anti information disclosure (T-sg6-02)"

patterns-established:
  - "Auth via middleware (not FastAPI Depends): add new public paths to _PUBLIC_PATHS in app/api/auth.py"
  - "Startup warnings via log_auth_startup_warning(): called in lifespan after configure_logging()"

requirements-completed: [API-AUTH-01]

# Metrics
duration: 15min
completed: 2026-05-24
---

# Quick Task 260524-sg6: API Key Authentication Summary

**Optional X-API-Key authentication via Starlette middleware: disabled when unset (tests pass unchanged), enforced with constant-time comparison when set, /health always public, /docs and Swagger assets also protected**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-24T20:30:00Z
- **Completed:** 2026-05-24T20:45:00Z
- **Tasks:** 3 (TDD: RED + GREEN + docs)
- **Files modified:** 6

## Accomplishments

- ApiKeyMiddleware (Starlette BaseHTTPMiddleware) covers all routes including /docs, /openapi.json, /redoc
- /health always public (exempt via _PUBLIC_PATHS); all other routes require X-API-Key when API_KEY is set
- secrets.compare_digest constant-time comparison prevents timing oracle attacks (T-sg6-01)
- Identical 401 body for missing/wrong key prevents client distinguishing the two cases (T-sg6-02)
- log_auth_startup_warning() emits loud WARNING at startup when API_KEY is absent
- Test suite: 185 → 195 passed (10 new auth tests, 0 regressions); no existing test modified
- .env.example, docker-compose.yml, README.md all document API_KEY with usage guidance and n8n instructions

## Task Commits

1. **Task 1 (RED gate): failing auth tests** - `cdf6993` (test)
2. **Task 1+2 (GREEN gate): ApiKeyMiddleware + wiring** - `31a053f` (feat)
3. **Task 3: documentation** - `9753539` (docs)

## Files Created/Modified

- `app/api/auth.py` - ApiKeyMiddleware + log_auth_startup_warning; _PUBLIC_PATHS frozenset
- `app/api/main.py` - wire ApiKeyMiddleware via add_middleware(); call log_auth_startup_warning in lifespan
- `tests/api/test_auth.py` - 10 tests: Mode A (auth disabled) + Mode B (auth enforced), /health exempt, /docs protected, anti-disclosure
- `.env.example` - API_KEY= (commented) with explanation and openssl generation hint
- `docker-compose.yml` - comment note about API_KEY (not as explicit key to avoid overriding .env)
- `README.md` - API_KEY row in .env table and Docker secrets table; replaced reverse-proxy auth note with native auth explanation; curl example with X-API-Key; n8n node auth instruction

## Decisions Made

- **Middleware over FastAPI `dependencies=`**: FastAPI's global `dependencies=` only applies to routes registered on the app, not to the Swagger UI assets (/docs, /openapi.json, /redoc). BaseHTTPMiddleware runs before any routing and covers everything including Starlette-mounted static assets.
- **_PUBLIC_PATHS frozenset**: Clean, explicit exemption list in one place. No changes to profile.py needed.
- **No-op when unset**: os.environ.get("API_KEY", "") at request time means all 185 existing tests pass without modification (no test sets API_KEY).
- **Identical 401 for missing and wrong key**: Anti-disclosure. Client cannot distinguish absence from incorrect value.

## Deviations from Plan

None - plan executed exactly as written. The middleware implementation path was already specified in the plan's action block as the recommended approach.

## Issues Encountered

None.

## Threat Surface Scan

No new trust boundaries introduced. The middleware closes T-sg6-01 through T-sg6-03 from the plan's threat register. T-sg6-04 (API_KEY unset in prod) is accepted with the startup WARNING. T-sg6-05 (env var leak via error body) was already mitigated by the generic error handler.

## Test Results

- **Pre-task baseline:** 185 passed
- **Post-implementation:** 195 passed (185 existing + 10 new auth tests)
- **Existing test suite with API_KEY unset:** All 185 pass unchanged (middleware is no-op)
- **Auth-specific tests:** 10 passed covering both modes

## Self-Check: PASSED

- app/api/auth.py: EXISTS
- tests/api/test_auth.py: EXISTS
- app/api/main.py: MODIFIED (ApiKeyMiddleware wired + log_auth_startup_warning called)
- Commits: cdf6993, 31a053f, 9753539 — all verified in git log
- Full suite: 195 passed, 0 failed

---
*Quick task: 260524-sg6*
*Completed: 2026-05-24*
