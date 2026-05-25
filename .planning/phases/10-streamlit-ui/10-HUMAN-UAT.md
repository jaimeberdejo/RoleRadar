---
status: partial
phase: 10-streamlit-ui
source: [10-VERIFICATION.md]
started: 2026-05-25
updated: 2026-05-25
---

## Current Test

[awaiting human testing — run `docker compose up` or `streamlit run ui/app.py` and check the items below]

## Tests

### 1. CV page cache-hit flow (UI-01 / SC1)
expected: Upload a PDF on the CV page → it parses and shows the extracted profile (experiencia, skills, formación). Upload the SAME PDF again → it loads from cache ("Perfil cargado de caché" caption) WITHOUT re-parsing.
result: [pending]

### 2. "Run now" non-blocking feel (UI-07 / SC4)
expected: Click "▶ Run now" on Results → button disables, a live status/spinner shows, the UI stays interactive (not frozen), and when the run finishes the results refresh with a "N nuevas ofertas" headline.
result: [pending]

### 3. Full breakdown detail view (UI-03 / UI-04 / SC3)
expected: Results list is sortable + filterable by score and recommendation; selecting a row expands a detail view showing all 4 sub-scores (puesto/skills/ubicación/seniority), reasons_for/against, matched/missing skills, deal-breaker info, and the apply URL link.
result: [pending]

### 4. Settings weight validation (UI-05 / SC5)
expected: On Settings, entering scoring weights that do NOT sum to 1.0 blocks the save with a Spanish error ("Los pesos deben sumar 1.0 (suman X)."); valid weights save and the next run / Re-score reflect them.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps

(none — automated layer fully green: 363 tests pass, all 7 success criteria code-verified, code review resolved. These 4 items are visual/runtime confirmations only.)
