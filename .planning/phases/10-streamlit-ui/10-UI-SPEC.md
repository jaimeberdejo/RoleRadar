---
phase: 10
slug: streamlit-ui
status: approved
shadcn_initialized: false
preset: none
created: 2026-05-25
---

# Phase 10 — UI Design Contract (Streamlit)

> Interaction/layout contract for the Streamlit standalone app. This is a **Streamlit-native**
> UI (no web design system / shadcn / custom CSS). The design value here is page structure,
> interaction states, and the success-criteria→behavior mapping — not a color/token system.
> Authored directly from 10-CONTEXT.md (default-theme personal tool; a full design-system spec
> would be overkill). See 10-CONTEXT.md for the locked implementation decisions (D-01..D-13).

---

## Design System

| Property | Value |
|----------|-------|
| Tool | Streamlit native (no shadcn) |
| Preset | not applicable |
| Component library | Streamlit built-in widgets (st.dataframe, st.file_uploader, st.status, st.navigation/st.Page, st.expander, st.metric) |
| Icon library | Streamlit/emoji shortcodes only |
| Font | Streamlit default theme |

**Theming:** Streamlit default theme. No custom CSS, no color tokens, no spacing scale to
declare — Streamlit owns layout/spacing/typography. The Color/Spacing/Typography/Registry
sections below are intentionally "not applicable" for this native-widget app.

---

## Navigation & Page Structure

Multipage app via `st.navigation` + `st.Page` (entry: `ui/app.py`; page bodies: `ui/pages/*.py`).
Page order in the nav:

| Page | Module | Purpose | Requirements |
|------|--------|---------|--------------|
| CV | `ui/pages/cv.py` | Upload PDF → parse/cache → show CVProfile | UI-01 |
| Search Config | `ui/pages/search.py` | Edit search params, persist to settings | UI-02 |
| Results | `ui/pages/results.py` | List + filter scored offers, detail breakdown, Run now, Re-score | UI-03, UI-04, UI-07, UI-08 |
| Settings | `ui/pages/settings.py` | Scoring weights + deal-breakers + threshold, persist | UI-05, UI-06 |
| Status | `ui/pages/status.py` | Scheduler dashboard from runs table | UI-09 |

Shared helpers (`ui/services.py` or similar): cached embedder (`@st.cache_resource`), storage
accessor, settings read/write, effective-profile builder, run-status state. Never import streamlit
into `app/` core.

---

## Per-Page Interaction Contract (states: idle / loading / empty / error / success)

### CV (UI-01, SC1)
- **idle:** `st.file_uploader` (accept `.pdf`). Helper text: "Sube tu CV en PDF — se cachea y no se
  vuelve a parsear si no cambia."
- **on upload:** compute `pdf_hash` → `load_cached_profile`. **cache hit** → show CVProfile WITHOUT
  re-parsing (note "perfil cargado de caché"). **cache miss** → `st.status("Parseando CV…")` while
  `parse_cv(pdf_bytes)` runs, then `save_cached_profile`.
- **success:** render CVProfile — experiencia (empresa/rol/tecnologías), skills_técnicas, formación,
  años_experiencia_total, dominios.
- **error:** parse failure → `st.error("No se pudo parsear el CV: {motivo}")`, keep the uploader.
- **empty:** no CV yet → info "Aún no has subido un CV. El scoring de skills usará un perfil vacío."

### Search Config (UI-02, SC2)
- Widgets bound to settings: `search_country`, language, `search_query`/positions, `date_posted`
  (select: month/3days/today), `employment_types`, remote-only (toggle).
- **success on save:** `st.success("Guardado — el próximo run del worker usará estos parámetros.")`.
  Persisted via `set_setting`; no Docker restart (SC2).
- Show current persisted values on load (read from `get_settings`).

### Results (UI-03, UI-04, UI-07, UI-08)
- **list:** `st.dataframe` of all scored offers (cols: title, company, score_total, recommendation),
  sortable. Filters: score-min slider + recommendation multiselect (strong_fit/good_fit/maybe/skip).
- **empty:** "No hay ofertas puntuadas todavía. Pulsa «Run now» o espera al worker."
- **detail:** select/expand a row → full breakdown: 4 sub-scores (encaje_puesto/skills/ubicación/
  seniority via st.metric or a table), reasons_for, reasons_against, matched_skills,
  missing_requirements, deal_breaker info, and the apply URL (link).
- **Run now (SC4):** primary button "▶ Run now". On click → background thread runs `run_pipeline`
  with the cached embedder. **loading:** `st.status("Buscando y puntuando ofertas…")` + button
  disabled (no double-run). On finish → `st.rerun()`; Results refreshes with new offers.
  **error:** run errors surfaced from PipelineResult.errors as `st.warning` (per-query/per-job),
  the run still completes.
- **Re-score (UI-08):** button "↻ Re-score stored". **confirmation/cost warning first:** "Esto
  re-puntúa N ofertas con los pesos actuales (sin re-buscar). Si hay OPENAI_API_KEY, hará N llamadas
  LLM. ¿Continuar?" → on confirm, re-score via the shared path + cached embedder; show progress.

### Settings (UI-05, UI-06)
- **weights:** four number inputs / sliders for puesto/skills/ubicación/seniority. **validation:**
  must sum to 1.0 (PesosScoring validator) — normalize or block save with
  `st.error("Los pesos deben sumar 1.0 (suman X).")`. Persist to `score_weight_*` settings.
- **deal-breakers:** editable list (st.data_editor or text-area, one per line) → persist as a
  `deal_breakers` JSON setting.
- **threshold:** `notification_min_score` number input.
- **success:** `st.success("Guardado — afecta al worker y a «Re-score».")`
- **secrets:** NEVER display TELEGRAM_BOT_TOKEN/SMTP_PASSWORD/OPENAI_API_KEY — only show booleans
  ("Telegram configurado: ✓/✗", "Email configurado: ✓/✗", "OpenAI: ✓/✗").

### Status (UI-09, SC6)
- Read `get_recent_runs()`. Show: last run timestamp, next run (last + `schedule_interval_hours`),
  new-offers/notified counts. `st.metric` for headline numbers + a table of recent runs
  (fetched/deduped/scored/new_seen/channel/notified/errors).
- **empty:** "El worker aún no ha ejecutado ningún run."

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA (Results) | "▶ Run now" |
| Re-score CTA | "↻ Re-score stored" |
| Empty state (Results) | "No hay ofertas puntuadas todavía. Pulsa «Run now» o espera al worker." |
| Empty state (CV) | "Aún no has subido un CV. El scoring de skills usará un perfil vacío." |
| Error state (CV parse) | "No se pudo parsear el CV: {motivo}. Revisa que sea un PDF válido." |
| Run-now loading | "Buscando y puntuando ofertas…" |
| Re-score confirmation | "Esto re-puntúa N ofertas con los pesos actuales (sin re-buscar). ¿Continuar?" |
| Save success | "Guardado — el próximo run del worker lo usará." |
| Weights error | "Los pesos deben sumar 1.0 (suman {X})." |

Language: Spanish (the user's language, consistent with the rest of the app).

---

## Spacing Scale

Not applicable — Streamlit default layout/spacing. No custom spacing tokens.

## Typography

Not applicable — Streamlit default theme typography.

## Color

Not applicable — Streamlit default theme. (Recommendation badges may use Streamlit's built-in
semantic colors via st.success/st.warning/st.error or emoji, not a custom palette.)

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| Streamlit built-ins | st.navigation/Page, file_uploader, dataframe, status, expander, metric, data_editor, button, slider, multiselect, number_input, toggle | not required (first-party, no external registry) |

---

## Success-Criteria → UI-Behavior Map (the acceptance gates)

| SC | UI behavior that satisfies it |
|----|-------------------------------|
| SC1 | CV page: cache-hit path renders CVProfile without re-parse; reload of same file = no re-parse |
| SC2 | Search Config save → `set_setting`; worker reads settings at run start (no restart) |
| SC3 | Results: sortable st.dataframe + filters; row expand shows all 4 sub-scores + reasons + skills |
| SC4 | Run now: background thread + st.status + disabled button; st.rerun on finish; no freeze |
| SC5 | Settings: weights/deal-breakers → settings table; Re-score applies via effective-profile overlay, no fetch |
| SC6 | Status: last/next run + new-offers count from get_recent_runs |
| SC7 | Embedder via `@st.cache_resource` — one instance/process; Run now & Re-score reuse it (no reload) |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS (Spanish copy table above; every state has copy)
- [x] Dimension 2 Visuals: PASS (Streamlit-native widgets specified per page)
- [x] Dimension 3 Color: PASS (n/a — default theme; semantic st.success/warning/error only)
- [x] Dimension 4 Typography: PASS (n/a — default theme)
- [x] Dimension 5 Spacing: PASS (n/a — Streamlit layout)
- [x] Dimension 6 Registry Safety: PASS (first-party widgets only)

**Approval:** approved 2026-05-25 (Streamlit-native contract; authored from 10-CONTEXT.md in --auto mode)
