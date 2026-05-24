# Stack Research

**Domain:** Personal job-search aggregator — Streamlit standalone app with background scheduler
**Researched:** 2026-05-24
**Confidence:** HIGH (all versions confirmed via pip/PyPI; library patterns verified via Context7)

---

## v2.0 Stack Delta

This document covers ONLY the net additions and removals for v2.0.
The existing core stack (Pydantic v2, Instructor, OpenAI, pymupdf, sentence-transformers/BGE-M3, httpx, SQLite stdlib, pytest, Docker) is validated and reused as-is.

---

## ADD: New Dependencies

### Core Technologies

| Technology | Version (pin `>=`) | Purpose | Why Recommended |
|------------|-------------------|---------|-----------------|
| `streamlit` | `>=1.57.0` | UI framework — all user-facing pages | Latest stable (2026-04-28); explicitly supports Python 3.10–3.14 (confirmed PyPI). Used industry-wide for ML/AI dashboards. No separate web server needed — `streamlit run` replaces uvicorn for the UI process. |
| `APScheduler` | `>=3.11.2` | Background scheduler worker — recurring job searches | Latest stable 3.x (2025-12-22, confirmed PyPI). Production/Stable classifier. v3 is the battle-tested branch; v4.x is still pre-release alpha and explicitly not for production use (confirmed Context7 version history). `BlockingScheduler` in a separate Docker service is the clean pattern for a standalone daemon. |
| `python-telegram-bot` | `>=22.7` | Telegram digest delivery | Latest stable (confirmed pip). Async-native (asyncio since v20). Uses httpx internally — no second HTTP client. `bot.send_message()` is a 3-line integration for push-only delivery (no polling needed). Lighter than building raw Bot API calls: no error-handling boilerplate, automatic retry on 429. |

### Supporting Libraries

| Library | Version (pin `>=`) | Purpose | When to Use |
|---------|-------------------|---------|-------------|
| `pandas` | `>=2.2` | DataFrame display in Streamlit (`st.dataframe`) | Already a transitive dep of sentence-transformers; explicit pin ensures `st.dataframe` renders properly. Only needed for tabular job display — do not use for core data logic (Pydantic models own that). |

---

## EXISTING DEPS — Reuse Confirmed (no changes needed)

| Existing Dep | v2.0 Role | Notes |
|---|---|---|
| `httpx>=0.28.1` | JSearch HTTP client (new `app/sources/jsearch.py` module) | Already on the stack. JSearch (RapidAPI) uses standard REST: `GET https://jsearch.p.rapidapi.com/search` with headers `X-RapidAPI-Key` and `X-RapidAPI-Host: jsearch.p.rapidapi.com`. No new HTTP dep needed. Use `httpx.AsyncClient` with `params={"query": ..., "page": 1, "num_pages": 1}`. Key from `RAPIDAPI_KEY` env var. |
| `sentence-transformers>=5.5.1` + BGE-M3 | Embeddings-first scoring: skills similarity + puesto similarity | The existing `BgeM3Embedder` (lazy import, `_ensure_loaded()` pattern) is reused unchanged. In v2.0, the scorer calls `embedder.embed([skill_text])` and `embedder.embed([job_description])` to compute cosine similarity for `encaje_skills` and `encaje_puesto` — replacing the LLM as the numeric scorer. The lazy-import invariant means importing the module does NOT pull torch until `embed()` is first called. |
| `python-dotenv>=1.2.2` | Loading `RAPIDAPI_KEY`, `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, SMTP vars from `.env` | No change. |
| `pyyaml>=6.0.3` | `profile.yaml` config loading | No change. |
| `openai>=2.38.0` + `instructor>=1.15.1` | Optional LLM enrichment layer (honest reasons + matched/missing skills prose) | Still on the stack; activates only when `OPENAI_API_KEY` is present. App must work without it. |

---

## REMOVE: Dropped Dependencies

| Remove | Reason |
|--------|--------|
| `fastapi>=0.128.0` | Its only consumer (n8n) is being retired. The core logic modules (cv/, dedup/, scoring/, storage/) are imported in-process by Streamlit and the scheduler worker. No HTTP server needed. |
| `uvicorn[standard]>=0.31.1` | Serves FastAPI; retired with it. Streamlit uses its own server (`streamlit run`). |
| `python-multipart>=0.0.22` | Only needed for FastAPI file-upload (`multipart/form-data` in `/cv/parse`). Streamlit's `st.file_uploader` handles file upload natively without this dep. |

**uv commands to remove:**
```bash
uv remove fastapi uvicorn python-multipart
```

---

## Architecture Integration Points

### Streamlit + BGE-M3/torch in the same process

Streamlit runs as a single Python process (multi-threaded for concurrent users, but this is a single-user app so that is not a concern). The BGE-M3 lazy-import pattern already used in `app/dedup/embedder.py` is the correct approach:

- Importing `app/dedup/embedder` or `app/scoring/scorer` at module level does NOT import torch.
- Torch is loaded only on the first call to `BgeM3Embedder.embed()`.
- In Streamlit, wrap the embedder instantiation with `@st.cache_resource` so the model is loaded once per process lifetime and reused across reruns:

```python
@st.cache_resource
def get_embedder():
    from app.dedup.embedder import BgeM3Embedder
    return BgeM3Embedder()
```

`st.cache_resource` is designed exactly for this: singleton heavy objects (ML models, DB connections) shared across reruns. No cross-session thread-safety issue for a single-user local app.

### APScheduler worker — separate Docker service

The scheduler must run independently of whether the Streamlit tab is open. The clean Docker pattern:

- **Two services in docker-compose:** `app` (Streamlit, `streamlit run app/ui/main.py`) and `worker` (BlockingScheduler daemon, `python -m app.worker`).
- Both services share the same `data` volume (SQLite) and `hf_cache` volume (BGE-M3 model).
- The worker imports the same core modules in-process (no HTTP round-trip to the UI).
- `BlockingScheduler` is the right scheduler class when the Python process exists solely to run the scheduler (blocks until SIGTERM). Use `CronTrigger` or `IntervalTrigger` for the daily search job.
- SQLite concurrent access: worker writes jobs; Streamlit reads jobs. SQLite's WAL mode handles this safely. Open a new connection per thread/process (do not share `sqlite3.Connection` objects across process boundaries — each service has its own connection pool).

```python
# app/worker/__main__.py (skeleton)
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BlockingScheduler()
scheduler.add_job(run_daily_search, CronTrigger(hour=8, minute=0))
scheduler.start()  # blocks; exits cleanly on SIGTERM
```

### Telegram delivery — push-only, no polling

For digest delivery (worker pushes a message; no bot commands needed):

```python
import asyncio
import telegram

async def send_digest(token: str, chat_id: int, text: str) -> None:
    async with telegram.Bot(token) as bot:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

# From sync worker context:
asyncio.run(send_digest(token, chat_id, digest_text))
```

Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (integer). No polling loop, no Application/Updater needed — just `telegram.Bot`.

### Email delivery — stdlib only

Use Python's stdlib `smtplib` + `email.message.EmailMessage`. No new dep. Sufficient for a single-user digest:

```python
import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["Subject"] = "Daily Job Digest"
msg["From"] = smtp_from
msg["To"] = smtp_to
msg.set_content(html_body, subtype="html")

with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
    smtp.login(smtp_user, smtp_password)
    smtp.send_message(msg)
```

Env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`. Works with Gmail (port 465), Proton Bridge, or any SMTP relay. No third-party dep.

### JSearch client — httpx, no new dep

```python
# app/sources/jsearch.py (skeleton)
import httpx

JSEARCH_BASE = "https://jsearch.p.rapidapi.com"
JSEARCH_HOST = "jsearch.p.rapidapi.com"

async def search_jobs(query: str, rapidapi_key: str, page: int = 1, num_pages: int = 1) -> list[dict]:
    headers = {
        "X-RapidAPI-Key": rapidapi_key,
        "X-RapidAPI-Host": JSEARCH_HOST,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{JSEARCH_BASE}/search",
            headers=headers,
            params={"query": query, "page": page, "num_pages": num_pages},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
```

The existing `jsearch` mapper in `app/dedup/mappers.py` handles normalization of the raw response to `Job`. Key: `RAPIDAPI_KEY` from env.

---

## Installation (uv commands)

```bash
# Add new deps
uv add "streamlit>=1.57.0"
uv add "APScheduler>=3.11.2"
uv add "python-telegram-bot>=22.7"

# pandas is likely already a transitive dep; pin explicitly if st.dataframe needs it
# uv add "pandas>=2.2"  # add only if not already resolved

# Remove retired deps
uv remove fastapi uvicorn python-multipart
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| UI framework | Streamlit 1.57 | Gradio, Panel, Dash | Streamlit is the dominant choice for AI/ML apps, best Python 3.13 support, `st.cache_resource` is purpose-built for model caching. Gradio is narrower (model demos). Dash requires more boilerplate. |
| Scheduler | APScheduler 3.11.2 (BlockingScheduler in separate container) | APScheduler v4 alpha, Celery, RQ, cron | APScheduler v4 is explicitly alpha/not-production-ready. Celery/RQ require Redis (new infra dep, violates lightweight constraint). Cron requires OS-level setup outside Python. APScheduler 3.x is proven, zero extra infra. |
| Scheduler topology | Separate Docker service (worker) | BackgroundScheduler inside Streamlit process | Streamlit reruns its script on every user interaction, which causes BackgroundScheduler to be re-instantiated or to fight with Streamlit's rerun model. Separate process is the robust pattern — worker is always on regardless of UI state. |
| Telegram | python-telegram-bot 22.7 | Raw httpx to Bot API | python-telegram-bot uses httpx internally; adds retry logic, proper async context manager, and avoids writing `requests.post("https://api.telegram.org/bot{TOKEN}/sendMessage", ...)` boilerplate. Weight cost is low (it's already async/httpx-based). |
| Email | stdlib smtplib | sendgrid, mailgun SDK, resend | This is a personal single-user tool. smtplib requires zero new deps and works with any SMTP relay (Gmail, Proton, Mailtrap for testing). Third-party email APIs add cost, accounts, and deps for no benefit at this scale. |
| JSearch HTTP | Existing httpx | requests, aiohttp | httpx is already on the stack and async-native. No reason to add another HTTP dep. |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `celery` | Redis dependency, operational overhead, overkill for a single daily cron job | APScheduler BlockingScheduler |
| `rq` | Also requires Redis | APScheduler BlockingScheduler |
| `APScheduler>=4.0.0a*` | Explicitly marked pre-release/not-production in the official docs | APScheduler 3.11.2 stable |
| `requests` | Redundant — httpx already on stack and async-native | httpx |
| `aiohttp` | Redundant — same reason | httpx |
| `sendgrid`, `mailgun` | External service accounts + billing for single-user personal tool | stdlib smtplib |
| `redis` | No component in v2.0 needs it | (not needed) |
| `sqlalchemy` | APScheduler can use it as a job store but we are NOT using APScheduler's job store — we use our own SQLite storage module. Adding SQLAlchemy just for this would drag in significant ORM complexity. | stdlib sqlite3 (existing) |
| `pgvector` / Supabase | Already out of scope (decision 2026-05-23) — dedup runs in-memory per run | BGE-M3 cosine in-memory |
| Any new embedding model | BGE-M3 is already on the stack, trained for multilingual retrieval, and handles both dedup and skill matching | Existing BgeM3Embedder |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `streamlit>=1.57.0` | Python 3.10–3.14 | Python 3.13 confirmed supported. torch/sentence-transformers coexist via lazy import + `@st.cache_resource`. No known incompatibilities as of 2026-05-24. |
| `APScheduler>=3.11.2` | Python 3.8–3.13 | v3 stable. v4 alpha intentionally excluded. |
| `python-telegram-bot>=22.7` | Python 3.8+ (asyncio) | Internally uses httpx >=0.27. No conflict with project's `httpx>=0.28.1`. |
| `sentence-transformers>=5.5.1` | `torch` (transitive) | Lazy import invariant in `BgeM3Embedder._ensure_loaded()` prevents torch import at module level — tests stay torch-free with `FakeEmbedder`. |

---

## .env Additions for v2.0

```bash
# Scheduler / sources
RAPIDAPI_KEY=your_key_here        # JSearch (RapidAPI) — rotate the inline one from docker-compose

# Telegram digest (optional — leave blank to disable)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Email digest (optional — leave blank to disable)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_TO=
```

`ANTHROPIC_API_KEY` (legacy v1.0) can be removed from `.env.example` — stack is OpenAI-only now.

---

## Sources

- Streamlit 1.57.0 — `pip index versions streamlit` (confirmed 2026-05-24); Python 3.13 support confirmed via PyPI classifiers and community discussion
- APScheduler 3.11.2 — `pip index versions APScheduler` (confirmed 2026-05-24); v4 pre-release warning from Context7 `/agronholm/apscheduler` version history
- APScheduler 3.x BackgroundScheduler vs BlockingScheduler — [User guide (3.x)](https://apscheduler.readthedocs.io/en/3.x/userguide.html); BlockingScheduler recommended for standalone daemon use
- python-telegram-bot 22.7 — `pip index versions python-telegram-bot` (confirmed 2026-05-24); Bot.send_message pattern from Context7 `/python-telegram-bot/python-telegram-bot`
- JSearch RapidAPI authentication — `X-RapidAPI-Key` header pattern confirmed via [RapidAPI additional headers docs](https://docs.rapidapi.com/docs/additional-request-headers) and community examples
- Streamlit threading guidance — [Official threading docs](https://docs.streamlit.io/develop/concepts/design/multithreading); st.cache_resource for ML models from [official cache_resource docs](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource)
- smtplib for email — Python stdlib, zero new deps; confirmed viable for single-user digest in 2025 community practice

---
*Stack research for: BuscadorDeEmpleo v2.0 — Streamlit + APScheduler standalone app*
*Researched: 2026-05-24*
