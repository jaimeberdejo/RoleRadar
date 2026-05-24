# Feature Research — v2.0 (Streamlit + Scheduler)

**Domain:** Personal job-aggregator standalone app — single user, self-hosted, local SQLite
**Researched:** 2026-05-24
**Confidence:** HIGH (Streamlit and APScheduler verified via Context7/official docs; scoring
repositioning based on existing codebase analysis; digest delivery via standard library patterns)

---

## Scope

Only **new** v2.0 features are catalogued here. The following are already shipped and
excluded: CV parse, normalization, semantic dedup (BGE-M3), scoring heuristic, SQLite
persistence with history and seen-tracking.

---

## Feature Landscape

### 1. Streamlit UI

#### Table Stakes (these must work or the app feels broken)

| Feature | Why Expected | Complexity | Existing Module Dependency |
|---------|--------------|------------|---------------------------|
| Upload CV (PDF) from the UI | Only way Jaime can feed his CV without touching files manually | LOW | `app/cv/parser.py`, `app/cv/cache.py` — wrap `parse_cv_from_bytes()` |
| Display CV parse status and cached CVProfile | User needs to know whether the CV was parsed and what was extracted | LOW | `app/cv/cache.py` — read cache; render `CVProfile` fields |
| Configure search conditions: query/job-position, country, language | Core configuration — without this the JSearch client has nothing to call | LOW | New `app/sources/jsearch.py` (no existing dep) |
| Configure search conditions: num_pages, date_posted filter | Expected parameters of any job-search tool; JSearch supports `num_pages`, `date_posted`, `employment_types` | LOW | New JSearch client |
| View scored jobs list (title, company, score, recommendation) | Primary consumer surface — the reason the app exists | MEDIUM | `app/storage/sqlite.py` `get_history()` — extend or reuse directly |
| Sort/filter jobs by score_total and recommendation | Standard table behavior; `st.dataframe` provides sorting out of the box | LOW | `app/storage/sqlite.py` — pass filter params to query |
| Show job detail (full score breakdown, reasons_for, reasons_against, matched/missing skills) | Score breakdown is the differentiator; hiding it defeats the purpose | MEDIUM | `app/models/schemas.py` `JobScore` — deserialize `score_json` from DB |
| Mark a job as "seen/notified" toggle | Prevents digest from re-delivering old jobs; basic UX hygiene | LOW | `app/storage/sqlite.py` — `seen` column already exists; needs a `mark_seen(id)` method |

#### Differentiators (not expected, but high value for this specific app)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Fine-tune scoring weights from the UI (sliders for puesto/skills/ubicacion/seniority percentages) | Jaime can experiment with ranking priorities without touching `profile.yaml`; portfolio demo of the heuristic | MEDIUM | In-memory override of `PesosScoring`; persisting back to `profile.yaml` would be nice but is not strictly required for v2.0 |
| Configure deal-breakers as editable list in the UI | Makes the filter-hard logic tangible and easy to adjust during active search | MEDIUM | Mutates `UserProfile.deal_breakers` in session; no existing dep — needs profile write-back mechanism |
| Live "re-score all" button (apply new weights to existing DB records without re-fetching) | Lets Jaime recalibrate without waiting for the next scheduled run | HIGH | Requires iterating stored `Job` records + `score_job()` + upsert; expensive BGE-M3 + optional LLM pass |
| Show scheduler status ("last run: 08:00, next run: 08:00 tomorrow, 3 new jobs found") | Makes the autonomous worker visible and trustworthy | LOW | `app/storage/sqlite.py` — add a `runs` or `scheduler_state` table; alternatively write a JSON state file |
| Search history per run (when runs happened, how many jobs in/duped/scored/new) | Portfolio-grade observability; satisfies the deferred STORE-04 req | MEDIUM | Requires a `runs` table in SQLite — new schema migration |

#### Anti-Features (deliberately out of scope)

| Feature | Why Requested | Why Wrong for This Tool | Alternative |
|---------|---------------|-------------------------|-------------|
| Authentication / login screen | Multi-user SaaS instinct | Single-user local app — auth adds friction with zero security benefit; Streamlit runs on localhost or behind VPN | Run behind Tailscale/VPN if exposed; no in-app auth |
| Multiple user profiles / multi-tenancy | Generic platform thinking | Scope is one person, one CV, one ranking. Multi-user would require per-session DB isolation, auth, storage partitioning | One `profile.yaml`, one `jobs.db` |
| Dark/light theme toggle, custom CSS theming | Visual polish temptation | Streamlit provides a built-in theme system in `.streamlit/config.toml`; custom CSS is maintenance overhead | Use Streamlit native theme config |
| Real-time push notifications inside the browser | "Push feels modern" | Not how Streamlit works — Streamlit re-renders on interaction, not push; digest delivery belongs to the scheduler (Telegram/email), not the UI | Scheduler-driven digest delivery |
| Pagination through the raw JSearch results before scoring | "I want to see everything" | The scoring pipeline IS the filter — browsing unscored results defeats the purpose | Browse scored results; lower the threshold if too few pass |
| Export to Excel/PDF | Data portability instinct | SQLite DB + `st.dataframe` copy-to-clipboard covers 95% of the need; adding export libraries is dep bloat | `st.dataframe` built-in clipboard copy is sufficient |

---

### 2. Recurring Scheduled Search (APScheduler Worker)

#### Table Stakes

| Feature | Why Expected | Complexity | Existing Module Dependency |
|---------|--------------|------------|---------------------------|
| Worker runs automatically at configurable interval (e.g., daily at 08:00) even when the Streamlit browser tab is closed | Core promise of "always-on" — useless if it only runs when the app is open | MEDIUM | New `worker/scheduler.py`; imports `app/sources/jsearch.py`, `app/dedup/`, `app/scoring/scorer.py`, `app/storage/sqlite.py` |
| Worker persists scored jobs to the same SQLite DB the UI reads from | Shared persistence is the glue between background worker and UI | LOW | `app/storage/sqlite.py` — SQLite supports multiple readers + one writer; connection-per-call pattern already in place (`check_same_thread=False`) |
| Worker deduplicates new jobs against jobs already in the DB (not just within a run) | Prevents re-notifying about jobs already scored in a previous run | LOW | `app/storage/sqlite.py` `was_seen(id)` — already implemented; call before scoring |
| Configurable schedule (interval in hours, or cron expression) via `.env` or `profile.yaml` | Different users have different polling needs; hardcoded daily is fragile | LOW | New `config/` loader extension; APScheduler `CronTrigger` or `IntervalTrigger` |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Worker runs as a **separate process** (not a background thread inside Streamlit) | Streamlit does not officially support background threads; a separate process (second Docker service) decouples the worker from UI restarts and avoids SQLite cross-thread issues | MEDIUM | Two services in `docker-compose.yml`: `streamlit` and `worker`; share the `data` volume; APScheduler v3 `BackgroundScheduler` or a simple `python worker/run.py` with `schedule` loop |
| Manual "run now" button in the UI that triggers an immediate search | Allows Jaime to kick off a search outside the schedule (e.g., right after updating deal-breakers) | MEDIUM | HTTP call from UI to worker, OR shared flag file/SQLite `commands` table that the worker polls; avoid direct IPC for simplicity |
| Worker logs each run result (jobs fetched, duped, scored, new) to a `runs` table | Auditability; shows whether the tool is actually finding new jobs | MEDIUM | Extend `app/storage/sqlite.py` with `log_run()` and `get_runs()` |

#### Anti-Features

| Feature | Why Requested | Why Wrong for This Tool | Alternative |
|---------|---------------|-------------------------|-------------|
| Background thread spawned inside Streamlit process | Simpler single-process deployment | Streamlit explicitly warns against it (no `ScriptRunContext`; SQLite cross-thread `ProgrammingError`; dies when browser tab is idle for too long) | Separate Docker service (two lightweight Python processes sharing a volume) |
| GitHub Actions / cloud cron | "Serverless, no infra" | BGE-M3 is ~2.3 GB; downloading it on every GH Actions run is impractical; SQLite file is local | Docker worker on the same machine |
| Multiple concurrent search jobs | "Run AI Engineer AND Data Engineer separately" | Single search job is simpler; JSearch query can include multiple position terms | Combine positions in one JSearch query string |

---

### 3. Digest Delivery (Telegram or Email)

#### Table Stakes

| Feature | Why Expected | Complexity | Existing Module Dependency |
|---------|--------------|------------|---------------------------|
| Send a digest of new `strong_fit` and `good_fit` jobs after each scheduled run | Core delivery mechanism — without this the tool requires Jaime to open the app after every run | LOW | New `app/notifications/telegram.py` and/or `app/notifications/email.py`; no existing dep |
| Digest includes: job title, company, score_total, recommendation, top reasons_for, and a URL | Enough info to decide whether to click through without opening the app | LOW | Read from `ScoredJob` / `JobScore`; format as Markdown (Telegram supports it) or HTML email |
| Configurable minimum score threshold for digest (e.g., only score >= 70) | Prevents digest spam on low-quality days | LOW | Add `DIGEST_MIN_SCORE` env var; filter `ScoredJob` list before sending |
| Choose delivery channel (Telegram or email) via `.env` — if neither is configured, skip silently | Not everyone uses Telegram; email is the fallback; if both are unconfigured the worker should not crash | LOW | Check `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` vs `SMTP_*` env vars; skip gracefully |
| "No new jobs matching your criteria" message when the run yields nothing above threshold | Assures the user the worker ran successfully even on quiet days | LOW | Send a brief "ran OK, 0 new matches" message; configurable via `DIGEST_NOTIFY_EMPTY=true/false` |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Telegram digest uses Markdown formatting (bold title, score as `[85/100]`, URL as inline link) | Readable at a glance on mobile without opening the app | LOW | Telegram Bot API supports `parse_mode=Markdown`; `httpx` (already a dep) for the HTTP call |
| Email digest renders as simple HTML table | More scannable than plain text for multiple jobs | MEDIUM | `email.mime` stdlib + `smtplib`; no new deps; supports Gmail app passwords and generic SMTP |
| Digest is only sent if there are **new** (not previously seen) jobs above threshold | Avoids re-notifying on jobs already delivered — the `seen` flag in SQLite handles this | LOW | `app/storage/sqlite.py` `was_seen()` + mark seen after sending; already partially in place |
| Digest delivery status tracked in the `runs` table (sent to which channel, N jobs included) | Auditability; portfolio completeness | LOW | Extend `log_run()` with delivery metadata |

#### Anti-Features

| Feature | Why Requested | Why Wrong for This Tool | Alternative |
|---------|---------------|-------------------------|-------------|
| Both Telegram AND email simultaneously as default | "Redundancy is good" | Double-notification is annoying for a single-user personal tool; choose one | User picks one channel via `.env` |
| Rich HTML email with CSS styling, logo | Professional-looking output | Maintenance burden; HTML email rendering is notoriously fragile across clients; plain-text or minimal HTML table is more reliable | Simple `<table>` or even plain text with newlines |
| Telegram bot that accepts commands (e.g., `/search now`) | Interactive bot feels powerful | Requires a polling/webhook loop which complicates the worker process significantly; out of scope for v2.0 | "Run now" button in the Streamlit UI |
| Push notifications via browser (Web Push API) | "Native feel" | Requires service workers, VAPID keys, browser permission grants — entirely different infrastructure; Streamlit has no native support | Telegram/email digest is sufficient |
| WhatsApp integration | Wide adoption | Requires WhatsApp Business API (paid) or unofficial Baileys; disproportionate to value | Telegram is free, has a proper bot API, and already verified end-to-end in v1.1 |

---

### 4. Embeddings-First Scoring (OpenAI Optional Enrichment)

#### Table Stakes

| Feature | Why Expected | Complexity | Existing Module Dependency |
|---------|--------------|------------|---------------------------|
| All numeric sub-scores (encaje_puesto, encaje_skills, encaje_ubicacion, encaje_seniority) produced without any OpenAI call | App must be fully functional when `OPENAI_API_KEY` is absent | HIGH | Major refactor of `app/scoring/scorer.py` and `app/scoring/llm.py`; `app/dedup/embedder.py` BGE-M3 already available |
| encaje_skills computed as cosine similarity between CV embedding and job description embedding (BGE-M3) | Local, free, fast, consistent | MEDIUM | `app/dedup/embedder.py` `BgeM3Embedder` — already builds L2-normalized embeddings; cosine = dot product of L2-norm vecs; reuse directly |
| encaje_puesto computed via decay from ranking match (deterministic, no LLM) | Already implemented in `app/scoring/ranking.py`; ranking match now must be determined without LLM | MEDIUM | `app/scoring/ranking.py` `encaje_puesto_desde_rango()` — already deterministic; but `rango_puesto` currently comes from the LLM `LLMJobAssessment`; must replace with an embeddings-based title→ranking match |
| encaje_ubicacion computed deterministically from job's `remote` field + `location` text match | Already implemented in `app/scoring/location.py` | NONE | `app/scoring/location.py` — unchanged; already fully deterministic |
| encaje_seniority computed deterministically from years/seniority keywords in description vs `CVProfile.anios_experiencia_total` | Regex + keyword match on description for seniority signals (junior/senior/lead + N years) | MEDIUM | New helper in `app/scoring/`; replaces the LLM seniority assessment |
| deal_breaker_hit computed without LLM (keyword/substring match of `UserProfile.deal_breakers` against description) | Deterministic filter; does not need LLM judgment for literal text matches | LOW | Existing `evaluar_ubicacion` pattern; extend for text deal-breakers |

#### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| When `OPENAI_API_KEY` is set: LLM adds `reasons_for`, `reasons_against`, `matched_skills`, `missing_requirements` as honest prose | The "LLM as enrichment, not scorer" model — numbers are deterministic and testable, prose is the added value | MEDIUM | `app/scoring/llm.py` `assess_job()` refactored to a narrower schema: only prose fields + optional skills itemization; `encaje_skills`/`encaje_seniority`/`rango_puesto` removed from LLM schema |
| When `OPENAI_API_KEY` is absent: `reasons_for`/`reasons_against` populated from rule-based templates (e.g., "CV embedding similarity: 78 — strong match") | App is not a degraded experience without OpenAI — it's complete | MEDIUM | New `app/scoring/fallback_reasons.py`; generates human-readable explanations from deterministic scores |
| Ranking title match uses BGE-M3 embedding similarity between job title and each ranking entry's title + synonyms | More robust than LLM-based classification; handles typos, multilingual titles ("Ingeniero de IA" matches "AI Engineer") | MEDIUM | `app/scoring/ranking_embed.py`; embed each ranking entry once at startup (cache); compare against job title embedding |
| Seniority detection via regex + year patterns as a configurable mapping (e.g., "lead/principal" → 5+ years) | Transparent and adjustable without LLM; covers the common patterns in JSearch job descriptions | LOW | Simple mapping in `profile.yaml` or hardcoded `SENIORITY_MAP`; configurable |

#### Anti-Features

| Feature | Why Requested | Why Wrong for This Tool | Alternative |
|---------|---------------|-------------------------|-------------|
| Multiple LLM providers (Anthropic, Gemini, etc.) | Flexibility is good in theory | Introduces an abstraction layer (LiteLLM or custom) that adds complexity with no user benefit — Jaime only has one key | Keep OpenAI as the single optional provider; the interface is narrow (Instructor + `gpt-4o-mini`) |
| Embeddings via OpenAI API (text-embedding-3-small) instead of BGE-M3 | Lower local compute burden | Contradicts the "free, private, offline-capable" decision already made; requires internet connectivity for every scoring run | BGE-M3 is already installed and cached; keep it |
| Fine-tuned threshold for "exact skill match" in embeddings scoring | "More accuracy" | BGE-M3 is multilingual and generalist; fine-tuning thresholds is premature until real data validates the scoring | Use cosine > 0.75 as default (configurable in `profile.yaml`), revisit after first real runs |
| Streaming LLM responses displayed in the UI | Impressive demo | LLM call is in the worker/scorer, not in the UI render path; streaming adds complexity with no UX value in this context | Return completed `JobScore`; display as static text |

---

## Feature Dependencies

```
[Streamlit UI — Browse jobs]
    └──reads──> [SQLiteStorage.get_history()]  (already exists)

[Streamlit UI — Upload CV]
    └──calls──> [app/cv/parser.py + cache.py]  (already exists)

[Streamlit UI — Fine-tune weights]
    └──overrides──> [UserProfile.pesos in session state]
    └──feeds──> [score_job() if re-score triggered]

[Scheduler Worker — daily run]
    └──calls──> [JSearch client]  (new)
    └──calls──> [normalization → dedup → scoring pipeline]  (already exists; wire up)
    └──writes──> [SQLiteStorage.upsert_scored_jobs()]  (already exists)
    └──triggers──> [Digest delivery]  (new)

[Digest delivery]
    └──reads──> [SQLiteStorage — new jobs above threshold]
    └──sends──> [Telegram bot API or SMTP]  (new)
    └──marks──> [SQLiteStorage.mark_seen()]  (extends existing seen column)

[Embeddings-first scoring]
    └──requires──> [BgeM3Embedder]  (already exists in app/dedup/embedder.py)
    └──replaces──> [LLM encaje_skills, encaje_seniority, rango_puesto fields]
    └──optionally enhances with──> [OpenAI prose enrichment]

[Ranking title match via embeddings]
    └──requires──> [BgeM3Embedder]  (reuse)
    └──replaces──> [LLM rango_puesto detection]

[Scheduler Worker separate process]
    ├──shares──> [data/ Docker volume with Streamlit process]
    └──conflict-avoids──> [Streamlit background thread anti-pattern]
```

### Dependency Notes

- **Browse jobs requires `get_history()`:** The method exists but returns dicts; the UI needs `score_json` deserialized to `JobScore`. Consider extending `get_history()` to return `ScoredJob` objects directly, or deserialize in the UI layer.
- **Fine-tune weights → re-score:** Re-scoring all historical jobs requires loading each stored `Job` + `CVProfile`, running `score_job()` with new weights, and upserting. This triggers BGE-M3 load (slow first time) and optionally N OpenAI calls. Gate behind an explicit "Re-score" button with a cost warning.
- **Embeddings-first scoring refactors `scorer.py`:** The current `score_job()` calls `assess_job()` (LLM) to get `rango_puesto`, `encaje_skills`, `encaje_seniority`. In v2.0 these come from deterministic/embedding computations. `LLMJobAssessment` schema shrinks to prose-only fields. This is the highest-complexity change in v2.0.
- **Scheduler worker and Streamlit must not share SQLite connections across threads:** SQLite objects must not cross thread boundaries. Both processes open their own connections per call — the existing `connection-per-call` pattern in `SQLiteStorage._connect()` already handles this correctly for a two-process setup (WAL mode recommended for concurrent write/read).
- **JSearch client depends on RAPIDAPI_KEY:** The existing `docker-compose.yml` has this key hardcoded (the known security issue). v2.0 must move it to `.env` before wiring the client.

---

## MVP Definition (v2.0 Launch)

### Launch With

These features together deliver the core v2.0 promise: autonomous daily search, no n8n, no FastAPI.

- [ ] **Streamlit UI — 3 pages:** (1) CV Upload + profile status, (2) Search configuration (query, country, language, schedule interval), (3) Results browser with score breakdown
- [ ] **JSearch client** — `app/sources/jsearch.py` calling RapidAPI JSearch with configurable query params
- [ ] **Scheduler worker as separate process** — `worker/run.py` with APScheduler `BackgroundScheduler` (or `CronTrigger`), running independent of Streamlit, sharing `data/` volume
- [ ] **Embeddings-first scoring** — `encaje_skills` and `rango_puesto` computed via BGE-M3 cosine similarity; `encaje_seniority` via keyword rules; LLM optional enrichment when key present
- [ ] **Digest delivery — one channel** — Telegram if `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` present; otherwise email if `SMTP_*` present; silent skip if neither
- [ ] **Docker Compose update** — retire `n8n` service; add `worker` service; move `RAPIDAPI_KEY` to `.env`; retain `buscadordeempleo` → rename to `streamlit`

### Add After Validation (v2.x)

- [ ] **Fine-tune weights in UI** — requires UX validation that sliders are actually useful vs just editing `profile.yaml`
- [ ] **"Run now" button** — trigger immediately; requires simple IPC between UI and worker (flag file or SQLite `commands` table)
- [ ] **Scheduler status display in UI** — `runs` table showing last run time, jobs found, digest sent
- [ ] **Re-score all button** — expensive; gate with confirmation and cost estimate (N × LLM calls if OpenAI enabled)
- [ ] **Edit deal-breakers in UI** — needs profile write-back mechanism; `profile.yaml` as single source of truth
- [ ] **STORE-04: run history and analytics** — after first week of real usage to know what metrics matter

### Future Consideration (v3+)

- [ ] **Additional job sources** (Arbeitnow, LinkedIn scrape, etc.) — the source mapper is isolated; add when JSearch coverage proves insufficient
- [ ] **Langfuse full wiring** (OBS-04) — deferred from v1.0; only valuable once LLM enrichment is in steady-state use
- [ ] **Salary extraction and filtering** — JSearch returns structured salary data; surface it in scoring and digest

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Streamlit — CV upload + results browser | HIGH | LOW (reuses existing modules) | P1 |
| JSearch client | HIGH | LOW | P1 |
| Scheduler worker (separate process) | HIGH | MEDIUM | P1 |
| Embeddings-first scoring (encaje_skills + rango_puesto) | HIGH | HIGH (core refactor) | P1 |
| Digest delivery (Telegram or email) | HIGH | LOW | P1 |
| Docker Compose cleanup (retire n8n, RAPIDAPI_KEY to .env) | HIGH (security) | LOW | P1 |
| Scheduler status in UI | MEDIUM | LOW | P2 |
| Fine-tune weights in UI | MEDIUM | MEDIUM | P2 |
| "Run now" button | MEDIUM | MEDIUM | P2 |
| Run history / analytics | LOW | MEDIUM | P3 |
| Re-score all button | LOW | HIGH | P3 |

---

## Notes on Scoring Reposition (Highest-Complexity Item)

The v2.0 scoring change is the most technically involved feature because `scorer.py` currently treats the LLM as the primary source of three sub-scores (`encaje_skills`, `encaje_seniority`, `rango_puesto`). The refactor must:

1. **Replace LLM rango_puesto detection** with embedding cosine similarity between job title and each ranked position's title + synonyms (embed ranking entries once at startup with BGE-M3; cache in memory).
2. **Replace LLM encaje_skills** with cosine similarity between the CV profile text (skills + experience concatenated) and the job description embedding.
3. **Replace LLM encaje_seniority** with a keyword/regex detector scanning the job description for seniority signals (years required, level titles) compared against `CVProfile.anios_experiencia_total`.
4. **Narrow the LLM schema** (`LLMJobAssessment`) to only produce prose: `razonamiento`, `reasons_for`, `reasons_against`, `matched_skills`, `missing_requirements`, `deal_breaker_hit_texto`, `deal_breaker_cual_texto` — removing `rango_puesto`, `encaje_skills`, `encaje_seniority`.
5. **Add fallback reason generation** when no LLM key is present, using rule templates.

The existing 179 tests will require updates for the scoring tests that mock `LLMJobAssessment` with numeric fields. This is expected and appropriate — the interface is changing.

---

## Sources

- Streamlit multipage app documentation: https://docs.streamlit.io/develop/concepts/multipage-apps
- Streamlit threading guidance: https://docs.streamlit.io/develop/concepts/design/multithreading
- Streamlit `st.file_uploader` docs (Context7 / `/streamlit/docs`)
- Streamlit `st.dataframe` docs (Context7 / `/streamlit/docs`)
- APScheduler CronTrigger and BackgroundScheduler docs (Context7 / `/agronholm/apscheduler`)
- APScheduler BackgroundScheduler for WSGI/web apps: https://apscheduler.readthedocs.io/en/3.x/userguide.html
- SQLite cross-thread pitfalls in Streamlit: https://discuss.streamlit.io/t/programmingerror-sqlite-objects-created-in-a-thread
- Streamlit + APScheduler ReportContext warning: https://discuss.streamlit.io/t/missing-reportcontext-warning-when-using-apschedulers-backgroundscheduler
- BGE-M3 dense embeddings + cosine similarity: https://bge-model.com/bge/bge_m3.html
- JSearch RapidAPI parameters: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
- Telegram Bot API Python patterns: https://andrewkushnerov.medium.com/send-notifications-to-telegram-with-python

---

*Feature research for: BuscadorDeEmpleo v2.0 Standalone App (Streamlit + Scheduler)*
*Researched: 2026-05-24*
