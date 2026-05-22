# BuscadorDeEmpleo — Agregador inteligente de ofertas

Servicio **Python (FastAPI)** que recibe ofertas de empleo, las **normaliza**,
**deduplica** (semántico) y las **puntúa contra mi perfil real** (CV + ranking de
puestos + preferencias). La orquestación diaria (disparo, llamadas a APIs de
empleo, entrega por email) la hará **n8n** por fuera, llamando a este servicio.

## Estado
En construcción por fases:
- **FASE 1 ✅** — estructura, schemas Pydantic (`app/models/schemas.py`) y `data/profile.yaml`.
- FASE 2 — parseo CV (PDF → `CVProfile`).
- FASE 3 — normalización + deduplicación semántica.
- FASE 4 — la HEURÍSTICA de scoring (LLM + lógica determinista). ← núcleo.
- FASE 5 — endpoints FastAPI + persistencia (Supabase/SQLite) + sección n8n.

## Estructura
```
app/   models/ api/ config/ cv/ dedup/ scoring/ storage/
data/  profile.yaml
tests/
```

## Empezar
- Edita `data/profile.yaml` (tu perfil, **sin tocar código**).
- `cp .env.example .env` y pon tus claves (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).
- Dependencias: se añaden con `uv add ...` según la fase.

## Integración con n8n (se documentará en la fase final)
`Schedule → APIs de empleo → Merge → POST /jobs/process → Filter por score → email`.

## Stack
Python 3.11+ · uv · FastAPI · Pydantic v2 + Instructor · httpx · Anthropic (scoring) ·
BGE-M3 embeddings (dedup) · Supabase(pgvector)+fallback SQLite · pytest.
