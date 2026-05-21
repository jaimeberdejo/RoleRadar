# Phase 1: Parseo de CV - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, defaults auto-accepted — user hands-off)

<domain>
## Phase Boundary

Convertir el CV en PDF de Jaime en un `CVProfile` estructurado (Pydantic, ya definido en
`app/models/schemas.py`) y fiable, cacheado para no re-parsear en cada run. Cubre extracción
de texto del PDF, extracción estructurada vía LLM (Instructor + Anthropic), caché por hash de
contenido, y tests con un PDF fixture y el LLM mockeado.

Fuera de boundary: el endpoint HTTP `/cv/parse` (eso es Fase 4 / API), persistencia en
DB (Fase 4), scoring (Fase 3). Esta fase entrega una función/módulo `app/cv/` reutilizable.
</domain>

<decisions>
## Implementation Decisions

### Extracción de PDF
- Librería: **pymupdf (fitz)** — fijado por CLAUDE.md
- PDFs multi-página: concatenar el texto de todas las páginas en orden de lectura
- Input de la función núcleo: acepta `bytes` (y/o ruta de fichero); el wrapper HTTP de la Fase 4 traducirá `UploadFile` → bytes
- PDFs escaneados / sin capa de texto (OCR): fuera de scope v1 — si pymupdf no extrae texto, lanzar un error claro (no intentar OCR)

### Extracción estructurada con LLM
- Salida estructurada: **Pydantic v2 + Instructor** sobre la API de Anthropic (Claude) — fijado por CLAUDE.md. Usar `instructor.from_anthropic(...)` con `response_model=CVProfile`
- Modelo: configurable vía variable de entorno (p.ej. `ANTHROPIC_MODEL_CV`), con un default Claude cost-effective y capaz para extracción estructurada (recomendado `claude-haiku-4-5`, ya que el parseo es extracción no razonamiento profundo y además se cachea). Claude's discretion sobre el nombre exacto del default.
- Prompt: instruir extracción FIEL — no inventar datos; dejar campos vacíos/None si no aparecen en el CV; estimar `anios_experiencia_total` a partir de las fechas de la experiencia
- Idioma del CV: soportar ES y EN indistintamente (el LLM extrae independientemente del idioma del documento)
- Clave API desde `ANTHROPIC_API_KEY` (.env), nunca hardcodeada

### Caché del CVProfile
- Clave de caché: **sha256 del contenido del PDF** (bytes) → re-parsea solo si el contenido cambia
- Almacenamiento: fichero JSON en disco en esta fase (sin DB todavía; la persistencia real es Fase 4). Guardar el `CVProfile` serializado + el hash de origen
- Ubicación: `data/.cache/` (añadir a `.gitignore` si procede)
- Invalidación: si el hash del PDF actual difiere del hash cacheado → re-parsear y reescribir caché

### Tests
- Fixture: un PDF de ejemplo pequeño en `tests/fixtures/` con texto conocido (generarlo de forma reproducible, p.ej. con pymupdf/reportlab, o incluir un PDF mínimo versionado)
- Mock del LLM: mockear la llamada a Instructor/Anthropic para devolver un `CVProfile` determinista — el test verifica el wiring (extracción de texto + parseo + caché), NO la calidad del LLM
- Test de caché: una segunda llamada con el mismo PDF NO invoca el LLM (assert sobre el mock)

### Claude's Discretion
- Nombre exacto del modelo default y de la env var
- Estructura interna de `app/cv/` (módulos: extracción de texto, cliente LLM, caché)
- Formato exacto del fichero de caché
- Cómo se genera/incluye el PDF fixture
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/models/schemas.py` ya define `CVProfile`, `Experiencia`, `Formacion` (Pydantic v2). Usar tal cual como `response_model`.
- `data/profile.yaml` existe (UserProfile) pero NO se usa en esta fase (es para scoring). El CV se parsea aparte y se combinará después.
- Estructura `app/cv/` existe (carpeta vacía) — destino del código de esta fase.

### Established Patterns
- Pydantic v2, type hints en todo (ver schemas.py). Python >=3.13.
- Gestión de deps con `uv add`. Esta fase añade: `pymupdf`, `instructor`, `anthropic`, `python-dotenv` (y `pytest` para tests).

### Integration Points
- La salida `CVProfile` la consumirá el scoring (Fase 3) y el endpoint `/cv/parse` (Fase 4).
</code_context>

<specifics>
## Specific Ideas

- El CV real de Jaime está en PDF (probablemente con capa de texto). El parseo debe usar SU experiencia verdadera, no skills escritas a mano.
- `.env` ya lista `ANTHROPIC_API_KEY`. `OPENAI_API_KEY` no se usa en esta fase.
</specifics>

<deferred>
## Deferred Ideas

- OCR para PDFs escaneados (si algún día el CV no tiene capa de texto)
- Persistencia del CVProfile en DB (Fase 4)
- Endpoint HTTP `/cv/parse` (Fase 4)
</deferred>
