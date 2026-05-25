# Phase 10: Streamlit UI - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md.

**Date:** 2026-05-25
**Phase:** 10-streamlit-ui
**Mode:** --auto (Claude auto-selected the recommended option for each gray area)
**Areas discussed:** App structure/navigation, Run-now execution model, Settings↔scorer integration, Re-score path, Results display, Model lifecycle

---

## App structure & navigation

| Option | Description | Selected |
|--------|-------------|----------|
| `st.navigation` + `st.Page` (programmatic) | Modern multipage API (Streamlit ≥1.36; we're on 1.57) | ✓ |
| Legacy `pages/` magic-dir | Auto-discovered pages | |
| Single page + tabs | One file, st.tabs | |

**Auto-selection:** st.navigation/st.Page with thin page modules in ui/pages/, shared helpers in a ui/ support module. Pages: CV, Search Config, Results, Settings, Status.

---

## "Run now" execution model

| Option | Description | Selected |
|--------|-------------|----------|
| Background threading.Thread + poll | Non-blocking; UI shows status, reruns on completion | ✓ |
| Inline blocking call | Simplest but freezes the session (violates SC4) | |
| Subprocess | Heavier; loses the in-process cached embedder | |

**Auto-selection:** Background thread calling run_pipeline, passing the @st.cache_resource embedder so no 2nd BGE-M3 loads (RAM). Guard against concurrent UI runs.

---

## Settings ↔ scorer integration (central decision)

| Option | Description | Selected |
|--------|-------------|----------|
| Effective-profile overlay (settings over profile.yaml) | One shared helper merges settings weights/deal-breakers/search onto UserProfile; used by worker + Run now + Re-score | ✓ |
| Make scorer read settings directly | Spreads settings-coupling into scoring internals | |
| Keep weights only in profile.yaml | UI edits wouldn't drive scoring (fails UI-05/06) | |

**Auto-selection:** Overlay helper. profile.yaml = identity; settings table = operational knobs (weights, deal-breakers, search). Add a `deal_breakers` setting to init_db defaults.

---

## Re-score stored jobs (UI-08)

| Option | Description | Selected |
|--------|-------------|----------|
| rescore_stored() in pipeline.py reusing score_job | No re-fetch; effective profile + cached embedder; cost warning | ✓ |
| Re-run full pipeline | Would re-fetch from JSearch (wrong) | |

**Auto-selection:** Dedicated re-score path, import-clean, with a pre-run cost/count warning.

---

## Results display

| Option | Description | Selected |
|--------|-------------|----------|
| st.dataframe + filters + expander detail | Sortable/filterable list; full breakdown on expand | ✓ |
| Custom HTML cards | More work, no real gain | |

**Auto-selection:** st.dataframe with score/recommendation filters; detail view shows desglose + reasons + skills + URL.

---

## Model lifecycle (locked)

| Option | Description | Selected |
|--------|-------------|----------|
| @st.cache_resource embedder (once/process) | Required by UI-10/SC7 | ✓ |

**Auto-selection:** Locked from prior architecture decision.

---

## Claude's Discretion

- Widget specifics, page order, sidebar vs top filters, default theme.
- Overlay/rescore module location (pipeline.py vs new module) — must keep core import-clean.
- Thread status-signalling mechanism.

## Deferred Ideas

- num_pages in UI (UI-11, v2.x), salary filter (SCORE-16, v2.x), UI auth (out of scope), custom
  theming (out of scope), websocket progress push (polling suffices).
