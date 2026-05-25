# BuscadorDeEmpleo — Living Retrospective

## Milestone: v2.0 — Standalone App (Streamlit + Scheduler)

**Shipped:** 2026-05-25
**Phases:** 5 (6–10) | **Plans:** 27 | **Tests:** 179 (v1.0) → 374

### What Was Built
Turned the v1.x headless FastAPI service into a self-contained app: a Streamlit multipage UI
+ an APScheduler worker sharing one in-process core (cv/dedup/scoring/storage/pipeline/
notifications), no FastAPI, no n8n. Phase 6 cleaned the architecture (settings table, SQLite WAL).
Phase 7 made all numeric scores deterministic (BGE-M3 + rules), OpenAI optional. Phase 8 added an
app-owned JSearch client + worker + shared `run_pipeline` + runs table. Phase 9 added Telegram/email
digest with mark-seen-after-delivery. Phase 10 built the 5-page Streamlit UI with a settings→profile
overlay so UI edits drive the worker.

### What Worked
- **RED-first per phase.** Each phase opened with a Wave 0 of failing guard tests that locked the
  contract before implementation. Clean RED→GREEN progression (259→374) with zero regressions.
- **Push logic into testable core helpers.** The Streamlit UI is thin; the real logic (overlay,
  rescore, next-run, filters, channel resolution) lives in pure functions with pytest coverage —
  Streamlit's hard-to-test surface didn't block validation.
- **Deep code review on the strong model caught real bugs.** Three production-grade bugs were caught
  before merge, each fixed with a regression test verified to fail without the fix:
  1. Phase 9: Telegram chunk→job-id pairing via substring match → could mark *failed* deliveries as
     seen (silent data loss).
  2. Phase 10: the Search Config page persisted 6 params the pipeline never consumed (SC2 was a no-op).
  3. Phase 10: "Re-score" overwrote good skill scores with neutral-50 (description not stored).
- **The settings table as a cross-process bus** held up: UI writes → worker/scorer/notifications read,
  verified end-to-end by the integration checker.

### What Was Inefficient
- A planner pass hit a session limit mid-run; recovered by accepting the 6 written plans and adding
  the 1 missing (DOC-04) plan rather than replanning — but it cost a recovery cycle.
- The decision-coverage gate is a literal `D-NN` token match in `must_haves.truths`; plans implemented
  every decision but didn't tag the tokens, so each phase needed a manual tagging pass. Tagging
  decisions in truths during planning would avoid it.
- `get_history` shipped without `remote`/`url`/`location` fields needed by the re-score path — caught
  in review, but storing the full job row up front would have avoided the re-score data-quality caveat.

### Patterns Established
- `streamlit.runtime.exists()` gate around every page's render body so modules import cleanly under
  pytest (no ScriptRunContext side effects).
- Background work in Streamlit: thread does pure Python → module-level dict under a lock; a
  `@st.fragment(run_every=...)` polls it. Never `st.*` from the thread; never `add_script_run_ctx`.
- `@st.cache_resource` for the heavy embedder, injected into `run_pipeline(embedder=...)` so a UI
  "Run now" reuses the one model instance instead of loading a second.
- Effective-profile overlay (`model_copy(update=...)`) as the single seam where settings override
  profile.yaml — used identically by worker, Run now, and Re-score.

### Key Lessons
- Goal-backward review (does the code achieve the *success criterion*, not just pass tests?) is what
  caught the SC2 no-op and the re-score regression — both passed their own unit tests in isolation.
- For a RED-first phase, the orchestrator must gate waves with RED-awareness: a full-suite `-x` gate
  misfires on the intentionally-failing guard tests. Track "no regression in pre-existing tests +
  this wave's guards turn green" instead.

### Cost Observations
- Model mix (per user guidance): **Opus** for planning, code review, and the gnarly fixes
  (data-loss/integration bugs); **Sonnet** for execution and test-writing. The Opus reviews paid for
  themselves — three real bugs caught pre-merge.
- Sessions: spanned a session-limit boundary (recovered cleanly from filesystem state).

---

## Cross-Milestone Trends

| Milestone | Phases | Plans | Tests | Notable |
|-----------|--------|-------|-------|---------|
| v1.0 MVP | 5 | 19 | 179 | Headless FastAPI service; the intelligent core |
| v2.0 Standalone | 5 | 27 | 374 | Streamlit + worker; local-first scoring; FastAPI/n8n removed |
