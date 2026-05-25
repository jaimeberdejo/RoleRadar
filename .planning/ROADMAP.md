# Roadmap: BuscadorDeEmpleo

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-05-23) — [archivo](milestones/v1.0-ROADMAP.md)
- ✅ **v2.0 Standalone App (Streamlit + Scheduler)** — Phases 6-10 (shipped 2026-05-25) — [archivo](milestones/v2.0-ROADMAP.md)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-05-23</summary>

- [x] Phase 1: Parseo de CV (4/4 plans) — PDF → CVProfile cacheado (Instructor)
- [x] Phase 2: Normalización y Deduplicación (4/4 plans) — Jobs únicos, dedup exacto + BGE-M3
- [x] Phase 3: Heurística de Scoring — núcleo (4/4 plans) — JobScore honesto, determinista + LLM
- [x] Phase 4: API y Persistencia (4/4 plans) — endpoints FastAPI + SQLite + ya-vistas
- [x] Phase 5: Observabilidad, Robustez y Docs n8n (3/3 plans) — logging, stub Langfuse, README + n8n

Detalle completo en `milestones/v1.0-ROADMAP.md`. 38 requisitos, 179 tests.

</details>

<details>
<summary>✅ v2.0 Standalone App (Streamlit + Scheduler) (Phases 6-10) — SHIPPED 2026-05-25</summary>

- [x] Phase 6: Architecture Cleanup & Storage Foundation (5/5 plans) — FastAPI/n8n removed, settings table, SQLite WAL
- [x] Phase 7: Embeddings-First Scoring Refactor (6/6 plans) — all numeric sub-scores deterministic; OpenAI optional enrichment
- [x] Phase 8: JSearch Client & Worker Pipeline (4/4 plans) — app-owned fetch + APScheduler worker + shared run_pipeline + runs table
- [x] Phase 9: Notifications & Digest (5/5 plans) — Telegram/email digest; seen=0 source; mark-seen-after-delivery
- [x] Phase 10: Streamlit UI (7/7 plans) — 5-page app: CV, search config, results, settings, scheduler status

Detalle completo en `milestones/v2.0-ROADMAP.md`. 39 requisitos, 27 planes, 374 tests.

</details>

## Next

No active milestone. Run `/gsd-new-milestone` to start the next version.
