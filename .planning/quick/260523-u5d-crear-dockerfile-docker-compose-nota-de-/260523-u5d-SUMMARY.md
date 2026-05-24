---
phase: quick
plan: 260523-u5d
subsystem: infrastructure
tags: [docker, deployment, containerization]
dependency_graph:
  requires: []
  provides: [docker-image, compose-stack, docker-docs]
  affects: [README.md]
tech_stack:
  added:
    - ghcr.io/astral-sh/uv:python3.13-bookworm-slim (base image)
    - Docker Compose v2 named volumes
  patterns:
    - Single-stage build with uv (canonical Astral approach)
    - Named volumes for SQLite + HF model cache persistence
    - env_file injection (no secrets baked in image)
key_files:
  created:
    - Dockerfile
    - .dockerignore
    - docker-compose.yml
  modified:
    - README.md
decisions:
  - "Single-stage build on ghcr.io/astral-sh/uv:python3.13-bookworm-slim (Python 3.13 + uv pre-installed, canonical Astral production approach)"
  - "BGE-M3 NOT pre-downloaded in build: would add 2.3GB to image and require network during build; downloaded lazily on first /jobs/process call to hf_cache volume"
  - "Named volumes over bind mounts: portable, Docker-managed, no host directory creation needed"
  - "HF_HOME=/app/.cache/huggingface set in both Dockerfile and compose: deterministic path, overridable from shell without rebuild"
metrics:
  duration: "~40min (including docker build ~34min for uv sync with ML deps)"
  completed_date: "2026-05-24"
  tasks_completed: 3
  files_created_or_modified: 4
---

# Quick 260523-u5d: Dockerfile, Docker Compose y nota de despliegue

Single-stage Docker containerization with uv on Python 3.13-bookworm-slim, two named volumes for SQLite and BGE-M3 cache persistence, and a Docker deployment section added to README with explicit security note that RAPIDAPI_KEY/JSearch credentials belong to n8n, not this service.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Dockerfile + .dockerignore | fb15fb5 | Dockerfile, .dockerignore |
| 2 | docker-compose.yml | 038ad39 | docker-compose.yml |
| 3 | Sección "Despliegue (Docker)" en README | aa08eb1 | README.md |

## Design Decisions

### 1. Base image: ghcr.io/astral-sh/uv:python3.13-bookworm-slim

Chosen over `python:3.13-slim + RUN pip install uv` because:
- It's the canonical production approach recommended by Astral.
- Python 3.13 and uv are pre-installed, no extra layer needed.
- Matches `requires-python = ">=3.13"` in pyproject.toml exactly.

### 2. BGE-M3 model NOT pre-baked in image

Alternative considered: `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"` during build.

Rejected because:
- Adds ~2.3GB to the image (already 3.06GB with ML deps; would be ~5.5GB).
- Requires network access during `docker build` (breaks air-gapped or CI builds).
- The `hf_cache` named volume achieves the same "download once" behavior.

The `NOTE:` comment in the Dockerfile documents this decision for future maintainers.

### 3. Named volumes vs bind mounts

Named volumes chosen because:
- Portable between machines and OSes (no host path dependencies).
- Docker manages creation; user doesn't need to `mkdir -p`.
- Inspectable via `docker volume inspect` for backup purposes.

### 4. SQLITE_DB_PATH overridden in compose environment

The app defaults to `data/jobs.db` (relative path). In the container, this would write inside `/app/data` which is the mounted `data` volume — so it actually works. However, setting `SQLITE_DB_PATH: /app/data/jobs.db` explicitly makes the path absolute and unambiguous regardless of where uvicorn is called from.

### 5. Healthcheck uses python -c (not curl)

`curl`/`wget` not guaranteed to exist in bookworm-slim. Using `python -c "import urllib.request; ..."` avoids adding an extra package layer. `/health` responds immediately without loading BGE-M3.

## Verification Results

| Check | Result |
|-------|--------|
| `docker build -t buscadordeempleo:test .` | SUCCESS — exit 0, image e8510d29 built |
| Image exposes port 8000 | VERIFIED — `map[8000/tcp:{}]` |
| `.env` not in build context | VERIFIED — not found in any COPY step |
| `docker compose config --quiet` | SUCCESS — "compose config OK" |
| `grep -c "Despliegue (Docker)" README.md` | 2 (TOC entry + section header) |

**Build performed:** Yes, real `docker build` executed and succeeded. Build duration: ~34 minutes (uv sync installs all ML dependencies including PyTorch and sentence-transformers). Final image size: 3.06GB.

Note: End-to-end `docker compose up` + healthcheck not performed (would download BGE-M3 ~2.3GB on first `/jobs/process` call, which is expected lazy-load behavior).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this plan creates infrastructure files only, no application logic or UI rendering.

## Threat Flags

No new threat surface introduced beyond what is documented in the plan's threat model (T-docker-01 through T-docker-04). All mitigations applied:
- T-docker-01: `.env` excluded from build context via `.dockerignore`, no ARG/ENV with credentials in Dockerfile.
- T-docker-02: `env_file` directive in compose, no keys baked in compose, explicit RAPIDAPI_KEY comment.
- T-docker-04: `start_period: 60s` in healthcheck, `/health` responds without loading BGE-M3.

## Self-Check: PASSED

Files exist:
- FOUND: /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/Dockerfile
- FOUND: /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/.dockerignore
- FOUND: /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/docker-compose.yml
- FOUND: README.md contains "Despliegue (Docker)" section

Commits exist:
- FOUND: fb15fb5 — feat(quick-260523-u5d): add Dockerfile and .dockerignore
- FOUND: 038ad39 — feat(quick-260523-u5d): add docker-compose.yml with persistence volumes
- FOUND: aa08eb1 — docs(quick-260523-u5d): add Docker deployment section to README
