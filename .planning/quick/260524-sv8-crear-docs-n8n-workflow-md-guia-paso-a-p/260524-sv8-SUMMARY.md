---
phase: quick
plan: 260524-sv8
subsystem: docs
tags: [documentation, n8n, workflow, integration]
dependency_graph:
  requires: []
  provides: [docs/N8N-WORKFLOW.md, README n8n link]
  affects: [README.md]
tech_stack:
  added: []
  patterns: [Markdown documentation, n8n node-by-node guide]
key_files:
  created:
    - docs/N8N-WORKFLOW.md
  modified:
    - README.md
decisions:
  - "Link inserted before ### Flujo completo (after intro paragraph) to preserve existing README contract content"
  - "source values in Code node snippet use exact MAPPER_REGISTRY strings: arbeitnow, jsearch"
  - "Security section uses explicit ADVERTENCIA block to highlight RapidAPI key handling"
metrics:
  duration: "~5 min"
  completed: "2026-05-24T18:53:33Z"
---

# Phase quick Plan 260524-sv8: Crear docs/N8N-WORKFLOW.md — Guía paso a paso Summary

**One-liner:** Step-by-step n8n workflow guide (8 sections, 500 lines) covering all 8 nodes with copy-paste JavaScript snippets, security warnings, and source→mapper table matching the real MAPPER_REGISTRY.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Crear docs/N8N-WORKFLOW.md | 68219d0 | docs/N8N-WORKFLOW.md (created, 500 lines) |
| 2 | Añadir enlace en el README | b17770c | README.md (+4 lines) |

## What Was Built

- **docs/N8N-WORKFLOW.md** (new file, 500 lines): Complete n8n workflow guide in Spanish with 8 required sections:
  1. Título y diagrama ASCII — full ASCII flow diagram
  2. Prerrequisitos — service up, CV uploaded, n8n installed, credentials ready
  3. Paso a paso nodo a nodo — 8 nodes (Schedule Trigger, Arbeitnow HTTP, JSearch HTTP, Code/ProcessRequest builder, HTTP POST /jobs/process, Split Out, Filter, Code/digest formatter, Telegram + email variant)
  4. Seguridad — explicit ADVERTENCIA block; RapidAPI key stays ONLY in n8n; API_KEY as n8n credential
  5. Mapeo de datos: source → mapper — table with arbeitnow, jsearch, generic
  6. Programación y costes — cron, timeout rationale, OpenAI cost estimate, ya_visto idempotence
  7. Troubleshooting — 8-row table covering 404/401/connection/timeout/empty results/Telegram/JSearch/Markdown errors
  8. Enlace al contrato JSON completo

- **README.md** modification: 4-line paragraph with relative Markdown link `[docs/N8N-WORKFLOW.md](docs/N8N-WORKFLOW.md)` inserted in the "Integración con n8n" section, between the intro paragraph and `### Flujo completo`. No existing content removed.

## Verification

All checks from plan `<verification>` block passed:

```
docs/N8N-WORKFLOW.md: 500 lines (>= 200 required)
grep -c "^##" docs/N8N-WORKFLOW.md → 23 (section headers)
source values "arbeitnow", "jsearch", "generic" all present
Security section includes: Seguridad, RapidAPI, X-API-Key
grep "docs/N8N-WORKFLOW.md" README.md → 1 match
```

- JavaScript snippets are inside fenced code blocks with ` ```javascript ` tags.
- Bash/shell snippet uses ` ```bash ` tag.
- JSON snippets use ` ```json ` tag.
- `source` values in the Code node snippet match MAPPER_REGISTRY exactly: `'arbeitnow'`, `'jsearch'`.
- README section "Integración con n8n" content unchanged except for the 4-line addition.
- Internal links use relative paths from repo root: `docs/N8N-WORKFLOW.md` and `../README.md#...`.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `docs/N8N-WORKFLOW.md` exists: FOUND
- Commit 68219d0 exists: FOUND
- Commit b17770c exists: FOUND
- README contains "docs/N8N-WORKFLOW.md": FOUND (1 match)
- Line count >= 200: FOUND (500 lines)
