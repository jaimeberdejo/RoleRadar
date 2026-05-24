---
phase: quick
plan: 260524-tgs
subsystem: docs
tags: [n8n, backfill, documentation]
dependency_graph:
  requires: []
  provides: [docs/N8N-WORKFLOW.md updated with backfill strategy]
  affects: []
tech_stack:
  added: []
  patterns: [backfill via first-run detection using /jobs/history]
key_files:
  modified:
    - docs/N8N-WORKFLOW.md
decisions:
  - "Nodo 1.5 inserted as the canonical place for both first-run detection and query-list emission — no duplicate Code nodes"
  - "Always Output Data ON is the linchpin: without it n8n silently drops the [] response and cuts the flow"
  - "60-day corte filter is a no-op in daily mode (date_posted=3days already bounds it) — safe to always apply"
metrics:
  duration: "~5 min"
  completed: "2026-05-24"
---

# Quick Task 260524-tgs: Ampliar docs/N8N-WORKFLOW.md con backfill

**One-liner:** Added Nodo 1.5 (Historial HTTP + Modo de búsqueda Code) for automatic first-run backfill detection, reconciled Nodo 2b multi-query to remove duplicate Code node, updated Nodo 3 with 60-day timestamp filter, and added Troubleshooting row for Always Output Data.

## What Changed and Why

### A. Flow diagram updated

The ASCII diagram now shows the two new nodes (`HTTP GET /jobs/history?limit=1` and `Code "Modo de búsqueda"`) between the Schedule Trigger and the source HTTP Requests. Previously the diagram showed the Schedule connecting directly to Arbeitnow/JSearch.

### B. New section: Nodo 1.5

Inserted between the Nodo 1 (Schedule) `---` separator and `### Nodo 2a`. Contains:

- **HTTP Request "Historial"** table: method GET, `/jobs/history?limit=1`, `Always Output Data ON` with a callout explaining exactly why this option is critical (n8n drops the flow on empty `[]` without it).
- **Code "Modo de búsqueda"** table + snippet: detects `primerRun` by filtering `$('Historial').all()` for items with a real `id` field (avoids the phantom empty-json item that Always Output Data injects). Sets `date_posted = 'all'` + `num_pages = '10'` for first run, `'3days'` + `'1'` for daily runs. Emits one item per query so JSearch iterates.

### C. Nodo 2b reconciled

- Query params table: replaced fixed example values with n8n expressions (`={{ $json.query }}`, `={{ $json.num_pages }}`, `={{ $json.date_posted }}`).
- Multi-query subsection: replaced the old standalone Code snippet (which would have been a second duplicate query-list emitter) with a prose explanation pointing to Nodo 1.5 as the single source of truth. The old snippet with `return [{ json: { query: 'AI Engineer in Barcelona' } }, ...]` is gone.

### D. Nodo 3 snippet updated

Changed `const jsearch` to `let jsearch` and added:

```javascript
const corte = Math.floor(Date.now() / 1000) - 60 * 24 * 60 * 60;
jsearch = jsearch.filter(o => !o.job_posted_at_timestamp || o.job_posted_at_timestamp >= corte);
```

Also updated the comment to reference Nodo 1.5 instead of the old multi-query note. Added a `>` blockquote below the snippet explaining the filter behavior and its no-op nature in daily mode.

### E. Troubleshooting row added

New row at the end of the table:

> El flujo no hace nada el primer día / no llegan ofertas → `Always Output Data` not ON → activate `Options → Always Output Data` in the `Historial` node.

## Verification Executed

```
grep -n "Nodo 1.5"                     → 5 matches (section header + 4 internal refs)
grep -n "primerRun"                    → 3 matches (assignment + 2 uses in snippet + prose)
grep -n "corte"                        → 2 matches (declaration + filter line)
grep -c "AI Engineer in Barcelona"     → 1  (only in Nodo 1.5; NOT duplicated in Nodo 2b)
grep -n 'date_posted.*\$json'          → 1 match (expression in Nodo 2b table)
grep -n "Always Output Data"           → 3 matches (table row, callout prose, Troubleshooting)
```

All checks passed. No broken fences, no duplicate query-list Code nodes, no orphaned headers.

## Commit

`ef4a9b5` — `docs(260524-tgs): add backfill strategy and Nodo 1.5 to N8N-WORKFLOW.md`

## Self-Check: PASSED

- `docs/N8N-WORKFLOW.md` exists and was committed at ef4a9b5.
- All five changes (A-E) applied and verified.
- Single Code node emitting the query list (Nodo 1.5 only).
