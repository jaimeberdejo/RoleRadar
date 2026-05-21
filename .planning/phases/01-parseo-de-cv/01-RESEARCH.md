# Phase 1: Parseo de CV - Research

**Researched:** 2026-05-22
**Domain:** PDF text extraction + LLM structured extraction (Instructor + Anthropic) + file-based caching
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **PDF extraction library:** pymupdf (fitz) — fijado por CLAUDE.md
- **PDFs multi-página:** concatenar el texto de todas las páginas en orden de lectura
- **Input de la función núcleo:** acepta `bytes` (y/o ruta de fichero); el wrapper HTTP de la Fase 4 traducirá `UploadFile` → bytes
- **PDFs escaneados sin capa de texto:** fuera de scope v1 — si pymupdf no extrae texto, lanzar un error claro (no intentar OCR)
- **Salida estructurada:** Pydantic v2 + Instructor sobre la API de Anthropic (Claude) — fijado por CLAUDE.md. Usar `instructor.from_anthropic(...)` con `response_model=CVProfile`
- **Modelo:** configurable vía variable de entorno (p.ej. `ANTHROPIC_MODEL_CV`), con un default Claude cost-effective y capaz para extracción estructurada
- **Prompt:** instruir extracción FIEL — no inventar datos; dejar campos vacíos/None si no aparecen en el CV; estimar `anios_experiencia_total` a partir de las fechas de la experiencia
- **Idioma del CV:** soportar ES y EN indistintamente
- **Clave API:** desde `ANTHROPIC_API_KEY` (.env), nunca hardcodeada
- **Clave de caché:** sha256 del contenido del PDF (bytes)
- **Almacenamiento de caché:** fichero JSON en disco en `data/.cache/`
- **Invalidación de caché:** si el hash del PDF actual difiere del hash cacheado → re-parsear y reescribir caché
- **Fixture de tests:** un PDF de ejemplo pequeño en `tests/fixtures/` con texto conocido (generado reproduciblemente o incluido versionado)
- **Mock del LLM:** mockear la llamada a Instructor/Anthropic para devolver un `CVProfile` determinista
- **Test de caché:** una segunda llamada con el mismo PDF NO invoca el LLM (assert sobre el mock)

### Claude's Discretion
- Nombre exacto del modelo default y de la env var
- Estructura interna de `app/cv/` (módulos: extracción de texto, cliente LLM, caché)
- Formato exacto del fichero de caché
- Cómo se genera/incluye el PDF fixture

### Deferred Ideas (OUT OF SCOPE)
- OCR para PDFs escaneados (si algún día el CV no tiene capa de texto)
- Persistencia del CVProfile en DB (Fase 4)
- Endpoint HTTP `/cv/parse` (Fase 4)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CV-01 | El servicio acepta un CV en PDF y extrae un `CVProfile` estructurado vía Pydantic + Instructor (LLM) | `instructor.from_anthropic` + `response_model=CVProfile` verified as the correct API pattern |
| CV-02 | El `CVProfile` incluye experiencia, skills técnicas, formación, años de experiencia total (estimado) y dominios | `CVProfile` schema already defined in `app/models/schemas.py`; LLM prompt must instruct estimation of `anios_experiencia_total` from dates |
| CV-03 | El `CVProfile` se cachea y solo se re-parsea si el CV cambia (no re-parsear en cada run) | sha256 keyed JSON file cache in `data/.cache/`; cache-hit path bypasses LLM entirely |
| QA-01 | Test que parsea un PDF fixture con LLM mockeado y verifica campos clave | `unittest.mock.patch` on the instructor client `.messages.create`; fixture PDF generated via pymupdf or included as binary |
</phase_requirements>

---

## Summary

Esta fase convierte el CV en PDF de Jaime en un `CVProfile` Pydantic v2 estructurado usando pymupdf para extracción de texto y Instructor + Anthropic para extracción semántica. El resultado se cachea por sha256 del PDF en `data/.cache/` como JSON, de modo que los runs diarios no re-invocan el LLM si el CV no ha cambiado. El código vive completamente en `app/cv/` y expone una función pública `parse_cv(pdf_bytes: bytes) -> CVProfile`; el endpoint HTTP `/cv/parse` se añadirá en la Fase 4.

El stack está totalmente definido por decisiones bloqueadas: pymupdf 1.26+ para extracción, instructor 1.15+ con `from_anthropic` para extracción estructurada, y pytest + `unittest.mock` para tests con LLM mockeado. El único grado de libertad de Claude es la estructura interna de módulos dentro de `app/cv/` y el modelo LLM default.

**Primary recommendation:** Separar `app/cv/` en tres módulos — `extractor.py` (pymupdf, sin dependencias de LLM), `llm_client.py` (instructor + anthropic, inyectable para mock), `cache.py` (sha256 + JSON en disco) — con `parser.py` como orquestador. Esta separación hace que los tests mockeen únicamente `llm_client.py` sin tocar pymupdf ni el sistema de caché.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Extracción de texto del PDF | app/cv/extractor.py (Python library) | — | pymupdf opera sobre bytes en memoria; sin I/O de red |
| Extracción estructurada LLM | app/cv/llm_client.py (API externa) | — | instructor + anthropic hacen la llamada; aislado para mockeo |
| Caché por hash de contenido | app/cv/cache.py (disco local) | — | JSON en `data/.cache/`; sin DB hasta Fase 4 |
| Orquestación parse_cv | app/cv/parser.py | — | Une los tres módulos; interfaz pública de la fase |
| Schemas de salida | app/models/schemas.py | — | Ya definido; `CVProfile` es la única salida de esta fase |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pymupdf | 1.26.7 | Extracción de texto de PDF en memoria | Alta performance, soporte completo de PDFs con capa de texto, API estable. Fijado por CLAUDE.md. [VERIFIED: pip registry] |
| instructor | 1.15.1 | Structured outputs de LLM con Pydantic v2 | Wrapper sobre la API Anthropic que convierte `response_model=CVProfile` en tool-calling nativo; maneja retries de validación automáticamente. Fijado por CLAUDE.md. [VERIFIED: pip registry] |
| anthropic | 0.104.0 | SDK Python para la API de Anthropic | Requisito de instructor para el backend Anthropic. [VERIFIED: pip registry] |
| pydantic | >=2.13.4 | Validación y serialización de `CVProfile` | Ya en pyproject.toml. Instructor requiere v2. [VERIFIED: pyproject.toml] |
| python-dotenv | 1.2.2 | Carga de `ANTHROPIC_API_KEY` desde `.env` | Patrón establecido en el proyecto (.env.example ya existe). [VERIFIED: pip registry] |

### Supporting (Tests)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 | Framework de tests | Siempre para tests de esta fase [VERIFIED: pip registry] |
| reportlab | 4.5.1 | Generar el PDF fixture programáticamente | Alternativa a incluir un binario PDF en git. Solo en tests. [VERIFIED: pip registry] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pymupdf (fitz) | pdfplumber, pypdf | pymupdf es más rápido y tiene mejor fidelidad de extracción; las otras alternativas son más lentas o requieren dependencias extra. Decisión bloqueada. |
| instructor + anthropic | openai con structured outputs | Decisión bloqueada por CLAUDE.md: usar Anthropic. |
| JSON en disco para caché | Redis, SQLite | Sin dependencias externas; el objetivo de persistencia real (DB) es Fase 4. Caché de un solo fichero es suficiente para un CV personal. |
| reportlab para fixture PDF | fpdf2, incluir PDF binario en git | reportlab genera PDFs reproducibles con texto conocido; evita tener binarios pesados en git. fpdf2 es alternativa más ligera. |

**Installation:**
```bash
uv add pymupdf instructor anthropic python-dotenv
uv add --dev pytest reportlab
```

**Version verification:** [VERIFIED: pip registry 2026-05-22]
- pymupdf: 1.26.7
- instructor: 1.15.1
- anthropic: 0.104.0
- python-dotenv: 1.2.2
- pytest: 9.0.3
- reportlab: 4.5.1

---

## Architecture Patterns

### System Architecture Diagram

```
PDF bytes (input)
       │
       ▼
┌─────────────────┐
│  cache.py       │◄─── sha256(bytes) ──► data/.cache/{hash}.json
│  lookup_cache() │                              │
└────────┬────────┘                        (hit) │ (miss)
         │ cache miss                             │
         ▼                                        │
┌─────────────────┐                               │
│  extractor.py   │                               │
│  extract_text() │  pymupdf.open(stream=bytes)   │
│  → raw_text:str │                               │
└────────┬────────┘                               │
         │                                        │
         ▼                                        │
┌─────────────────┐                               │
│  llm_client.py  │  instructor.from_anthropic()  │
│  extract_cv()   │  response_model=CVProfile     │
│  → CVProfile    │  (mockeable en tests)         │
└────────┬────────┘                               │
         │                                        │
         ▼                                        │
┌─────────────────┐                               │
│  cache.py       │                               │
│  write_cache()  │──► data/.cache/{hash}.json    │
└────────┬────────┘                               │
         │                                        │
         └──────────────┬─────────────────────────┘
                        ▼
                   CVProfile (salida)
```

### Recommended Project Structure

```
app/
└── cv/
    ├── __init__.py          # exporta parse_cv() como interfaz pública
    ├── parser.py            # orquestador: llama extractor → llm_client → cache
    ├── extractor.py         # pymupdf: PDF bytes → raw text str
    ├── llm_client.py        # instructor + anthropic: text → CVProfile
    └── cache.py             # sha256 hash + JSON en data/.cache/
tests/
├── fixtures/
│   ├── sample_cv.pdf        # generado por conftest.py con reportlab (o incluido)
│   └── generate_fixture.py  # script para regenerar el PDF fixture
└── cv/
    ├── __init__.py
    ├── test_extractor.py    # tests de extracción de texto (sin LLM)
    ├── test_cache.py        # tests de caché (sin LLM)
    └── test_parser.py       # tests end-to-end con LLM mockeado (QA-01)
data/
└── .cache/                  # ignorado en .gitignore (no versionar CVProfile extraído)
```

### Pattern 1: Extracción de texto multi-página con pymupdf

**What:** Abrir un PDF desde bytes en memoria e iterar todas las páginas para concatenar el texto.
**When to use:** Siempre que se reciban bytes de PDF (la función núcleo acepta bytes).

```python
# Source: https://github.com/pymupdf/pymupdf/blob/main/docs/recipes-text.md
# [VERIFIED: Context7 / pymupdf docs]
import pymupdf

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extrae todo el texto de un PDF multi-página, en orden de lectura."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages_text = [page.get_text() for page in doc]
    text = "\n\n".join(pages_text).strip()
    if not text:
        raise ValueError(
            "El PDF no contiene capa de texto extraíble. "
            "PDFs escaneados (solo imagen) no están soportados en v1."
        )
    return text
```

**Import name pitfall:** El paquete se instala como `pymupdf` y se importa como `pymupdf` (desde la versión 1.24+). El alias `import fitz` sigue funcionando pero es el nombre legado — usar `import pymupdf` en código nuevo para claridad. [VERIFIED: pymupdf docs]

### Pattern 2: Extracción estructurada con Instructor + Anthropic

**What:** Crear un cliente instructor sobre el SDK de Anthropic y pasar `response_model=CVProfile` para obtener un objeto Pydantic directamente.
**When to use:** Una vez extraído el texto del PDF, para obtener el `CVProfile` estructurado.

```python
# Source: https://python.useinstructor.com/integrations/anthropic
# [VERIFIED: Context7 / instructor docs]
import os
import instructor
from anthropic import Anthropic
from app.models.schemas import CVProfile

def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())

def extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile:
    """Llama al LLM para extraer un CVProfile estructurado del texto del CV."""
    model = os.getenv("ANTHROPIC_MODEL_CV", "claude-haiku-4-5-20251001")
    return client.messages.create(
        model=model,
        max_tokens=4096,
        system=(
            "Eres un extractor de CVs preciso. "
            "Extrae ÚNICAMENTE lo que aparece explícitamente en el texto. "
            "No inventes datos. Si un campo no aparece, déjalo vacío o None. "
            "Para anios_experiencia_total, estima sumando la duración de los empleos "
            "a partir de las fechas indicadas."
        ),
        messages=[
            {
                "role": "user",
                "content": f"Extrae el CVProfile del siguiente CV:\n\n{raw_text}"
            }
        ],
        response_model=CVProfile,
        max_retries=2,
    )
```

**Instructor mode:** El modo por defecto de `instructor.from_anthropic()` es `ANTHROPIC_TOOLS` (o su alias `TOOLS` en versiones recientes). Este modo usa el tool-calling nativo de Anthropic para enforcement del schema — es el modo recomendado para Anthropic y NO requiere especificar `mode=` explícitamente. [VERIFIED: Context7 instructor docs]

**Nota sobre `from_provider` vs `from_anthropic`:** Instructor 1.x tiene `instructor.from_provider("anthropic/model")` como API unificada y `instructor.from_anthropic(Anthropic())` como API directa. Ambas son válidas. Para este proyecto usar `from_anthropic(Anthropic())` es más explícito y facilita la inyección de dependencias para tests. [VERIFIED: Context7 instructor docs]

### Pattern 3: Caché por sha256 en disco

**What:** Antes de llamar al LLM, calcular el sha256 de los bytes del PDF y comprobar si existe un JSON cacheado. Si existe, deserializar y devolver sin llamar al LLM.
**When to use:** En cada invocación de `parse_cv()`.

```python
# [CITED: decisiones bloqueadas CONTEXT.md]
import hashlib
import json
from pathlib import Path
from app.models.schemas import CVProfile

CACHE_DIR = Path("data/.cache")

def pdf_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()

def load_cached_profile(content_hash: str) -> CVProfile | None:
    cache_file = CACHE_DIR / f"{content_hash}.json"
    if cache_file.exists():
        return CVProfile.model_validate_json(cache_file.read_text())
    return None

def save_cached_profile(content_hash: str, profile: CVProfile) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{content_hash}.json"
    cache_file.write_text(profile.model_dump_json(indent=2))
```

**Formato del fichero de caché:** `data/.cache/{sha256_hex}.json` con el contenido de `CVProfile.model_dump_json()`. No se almacena el hash dentro del fichero (está en el nombre); esto simplifica la deserialización.

### Pattern 4: Orquestación en parser.py

```python
# [ASSUMED] — patrón de diseño sugerido, no sacado de docs externos
from app.cv.extractor import extract_text_from_pdf
from app.cv.llm_client import build_instructor_client, extract_cv_profile
from app.cv.cache import pdf_hash, load_cached_profile, save_cached_profile
from app.models.schemas import CVProfile

def parse_cv(pdf_bytes: bytes) -> CVProfile:
    """
    Interfaz pública de la fase.
    1. Comprueba caché por sha256.
    2. Si no hay caché: extrae texto con pymupdf → LLM → cachea.
    """
    h = pdf_hash(pdf_bytes)
    cached = load_cached_profile(h)
    if cached is not None:
        return cached

    raw_text = extract_text_from_pdf(pdf_bytes)
    client = build_instructor_client()
    profile = extract_cv_profile(raw_text, client)
    save_cached_profile(h, profile)
    return profile
```

### Pattern 5: Test con LLM mockeado (QA-01)

**What:** Parchear `app.cv.llm_client.build_instructor_client` para devolver un mock que retorna un `CVProfile` determinista. Verificar que: (a) el CVProfile tiene los campos correctos, (b) una segunda llamada con el mismo PDF no llama al LLM.

```python
# [CITED: unittest.mock estándar Python]
from unittest.mock import MagicMock, patch
import pytest
from app.cv.parser import parse_cv
from app.models.schemas import CVProfile, Experiencia

EXPECTED_PROFILE = CVProfile(
    experiencia=[Experiencia(empresa="Acme Corp", rol="AI Engineer", duracion="2 años")],
    skills_tecnicas=["Python", "LLMs"],
    anios_experiencia_total=2.0,
    dominios=["IA"],
)

@pytest.fixture
def mock_llm_client():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = EXPECTED_PROFILE
    return mock_client

def test_parse_cv_calls_llm_once(sample_pdf_bytes, mock_llm_client, tmp_path, monkeypatch):
    """Primera llamada invoca el LLM; segunda reutiliza la caché."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Redirigir caché a tmp_path para no contaminar data/.cache/
    monkeypatch.chdir(tmp_path)

    with patch("app.cv.llm_client.build_instructor_client", return_value=mock_llm_client):
        result1 = parse_cv(sample_pdf_bytes)
        result2 = parse_cv(sample_pdf_bytes)  # segunda llamada

    assert mock_llm_client.messages.create.call_count == 1  # LLM llamado UNA VEZ
    assert result1.skills_tecnicas == ["Python", "LLMs"]
    assert result2.anios_experiencia_total == 2.0
```

### Pattern 6: Generación del PDF fixture con pymupdf

**What:** Generar un PDF mínimo programáticamente en conftest.py para que el fixture no sea un binario opaco en git.

```python
# Source: https://github.com/pymupdf/pymupdf
# [VERIFIED: Context7 / pymupdf docs]
import pymupdf
import pytest

@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """PDF mínimo con texto de CV conocido, generado en memoria."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Jaime Berdejo - AI Engineer\n"
        "Empresa: Acme Corp | Rol: AI Engineer | 2022-2024\n"
        "Skills: Python, LLMs, FastAPI\n"
        "Formación: Grado Informática, UPC, 2020\n",
        fontsize=12,
    )
    return doc.tobytes()
```

### Anti-Patterns to Avoid

- **Importar `fitz` en código nuevo:** usar `import pymupdf` — `fitz` es el nombre legado y puede causar confusión. [VERIFIED: pymupdf docs]
- **Parchear el SDK de Anthropic directamente (`anthropic.Anthropic`):** mockear a nivel de `build_instructor_client()` es más robusto y no depende de los internos del SDK.
- **Hardcodear el nombre del modelo:** siempre leer de `os.getenv("ANTHROPIC_MODEL_CV", "claude-haiku-4-5-20251001")`. Si el modelo cambia, solo cambia el default en el código, no hay que modificar la lógica.
- **Pasar rutas de fichero al LLM:** nunca mandar el path al LLM, solo el texto extraído — el LLM no tiene acceso al sistema de ficheros.
- **Cache contaminación en tests:** usar `tmp_path` o `monkeypatch.chdir(tmp_path)` para que los tests no escriban en `data/.cache/` real.
- **Llamar `client.create()` en lugar de `client.messages.create()`:** con `instructor.from_anthropic()`, el método correcto es `client.messages.create(...)` (no `client.create()`). Con `instructor.from_provider()` se usa `client.create()`. Estas APIs son distintas. [VERIFIED: Context7 instructor docs]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM structured output + Pydantic validation | Parser propio de JSON del LLM | instructor | Maneja tool-calling, retries en fallos de validación, deserialización a Pydantic automáticamente |
| PDF text extraction | Parser de bytes PDF propio | pymupdf | Encoding, fonts, multi-página, texto con formatos complejos — decenas de edge cases |
| LLM retries en fallos de validación | Loop de retry manual | instructor `max_retries=2` | Instructor reenvía el error de Pydantic al LLM para auto-corrección |
| Serialización del CVProfile para caché | JSON manual con `json.dumps` | `profile.model_dump_json()` + `CVProfile.model_validate_json()` | Garantiza la roundtrip del schema Pydantic v2 incluyendo Optionals y listas |

**Key insight:** El valor de instructor es que el LLM devuelve un objeto Python tipado directamente. Sin instructor, hay que parsear JSON del LLM manualmente, manejar fallos de schema, escribir el retry loop, etc.

---

## Common Pitfalls

### Pitfall 1: Nombre de modelo desactualizado
**What goes wrong:** `claude-3-5-haiku-20241022` (modelo viejo) está deprecado desde febrero 2026. `claude-haiku-3-5` nunca fue un ID válido.
**Why it happens:** Knowledge de entrenamiento obsoleta sobre nombres de modelos Anthropic.
**How to avoid:** El modelo actual es `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`). Verificado contra la página oficial de modelos. [VERIFIED: platform.claude.com/docs/en/about-claude/models/overview]
**Warning signs:** Error 404 o `invalid_model_id` de la API de Anthropic.

### Pitfall 2: `import fitz` vs `import pymupdf`
**What goes wrong:** `import fitz` sigue funcionando (es un alias de compatibilidad), pero mezclarlo con `import pymupdf` en el mismo codebase genera confusión.
**Why it happens:** pymupdf históricamente se llamaba `fitz`.
**How to avoid:** Usar consistentemente `import pymupdf` en todo el código nuevo del proyecto. [VERIFIED: pymupdf docs]
**Warning signs:** Linters que reportan que `fitz` no está en el namespace del paquete instalado.

### Pitfall 3: `client.create()` vs `client.messages.create()`
**What goes wrong:** Con `instructor.from_anthropic(Anthropic())`, la API es `client.messages.create(...)`. Llamar a `client.create(...)` devolverá un error de atributo. Con `instructor.from_provider("anthropic/...")` se usa `client.create(...)`. Las dos variantes de API no son intercambiables.
**Why it happens:** instructor ofrece dos formas de inicialización para Anthropic con APIs ligeramente distintas.
**How to avoid:** Elegir una variante y ser consistente. Este proyecto usa `from_anthropic` → usar siempre `client.messages.create()`. [VERIFIED: Context7 instructor docs]
**Warning signs:** `AttributeError: 'Instructor' object has no attribute 'messages'` o similar.

### Pitfall 4: Token limit en CVs muy largos
**What goes wrong:** Un CV con muchas páginas puede exceder el context window de haiku (200k tokens en claude-haiku-4-5) si se pasan todos los metadatos del PDF, pero en la práctica un CV estándar tiene < 2000 palabras (< 3000 tokens). El riesgo real es pasar accidentalmente texto OCR o páginas en blanco que inflaman el input.
**Why it happens:** pymupdf extrae todo el texto, incluyendo encabezados de página, números de página, etc.
**How to avoid:** Truncar `raw_text` a los primeros N caracteres (p.ej. 20.000 chars ≈ 5.000 tokens) si supera un umbral configurable. Agregar warning en logs si se trunca. [ASSUMED — umbral por defecto; ajustar según el CV real]
**Warning signs:** Latencia inusualmente alta o error `max_tokens` de la API.

### Pitfall 5: Caché contaminada en tests
**What goes wrong:** Los tests escriben en `data/.cache/` real, lo que puede contaminar runs futuros o hacer que los tests sean flaky (si el caché de un test previo afecta a otro).
**Why it happens:** `CACHE_DIR` hardcodeado como path relativo.
**How to avoid:** En tests, usar `monkeypatch.chdir(tmp_path)` o sobreescribir `CACHE_DIR` via monkeypatch. La ubicación del caché debe ser configurable (p.ej. desde una variable de entorno `CV_CACHE_DIR` con default `data/.cache/`). [ASSUMED — patrón de diseño recomendado]
**Warning signs:** Tests que pasan en primera ejecución pero fallan en la segunda por caché inesperado.

### Pitfall 6: CVProfile no serializable si tiene campos Enum
**What goes wrong:** `CVProfile.model_dump_json()` serializa correctamente con Pydantic v2, pero si se usa `json.dumps(profile.dict())` con `mode="python"` en lugar de `model_dump_json()`, los Enum y Optional pueden no roundtrip correctamente.
**Why it happens:** Pydantic v2 cambia el comportamiento por defecto de serialización.
**How to avoid:** Siempre usar `profile.model_dump_json()` para escribir caché y `CVProfile.model_validate_json(text)` para leer. [VERIFIED: pydantic v2 docs implícito en schemas existentes]

---

## Code Examples

### Verificación de texto extraído vacío (detección de PDF escaneado)

```python
# Source: https://github.com/pymupdf/pymupdf/blob/main/docs/faq/index.md
# [VERIFIED: Context7 / pymupdf docs]
text = page.get_text().strip()
if not text or len(text) < 10:
    # Probablemente un PDF escaneado (solo imagen); fuera de scope v1
    raise ValueError("Página sin capa de texto; PDF posiblemente escaneado.")
```

### Instructor con Anthropic — forma canónica para este proyecto

```python
# Source: https://python.useinstructor.com/blog/archive/2024/page/2
# [VERIFIED: Context7 / instructor docs]
import instructor
from anthropic import Anthropic
from app.models.schemas import CVProfile

client = instructor.from_anthropic(Anthropic())

profile = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=4096,
    messages=[{"role": "user", "content": "...texto del CV..."}],
    response_model=CVProfile,
    max_retries=2,
)
# profile es ya un CVProfile Pydantic v2 validado
```

### Apertura de PDF desde bytes en memoria

```python
# Source: https://github.com/pymupdf/pymupdf/blob/main/docs/document.md
# [VERIFIED: Context7 / pymupdf docs]
import pymupdf

with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
    text = "\n\n".join(page.get_text() for page in doc)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `import fitz` | `import pymupdf` | pymupdf ~1.24 | Usar `import pymupdf` en código nuevo; `fitz` sigue funcionando como alias |
| `instructor.from_openai(create=anthropic...)` | `instructor.from_anthropic(Anthropic())` | instructor ~0.5 | API limpia dedicada para Anthropic; no necesita wrapping manual |
| `Mode.ANTHROPIC_TOOLS` (explícito) | `Mode.TOOLS` (o default) | instructor ~1.x | ANTHROPIC_TOOLS y TOOLS son equivalentes; el default ya es correcto para Anthropic |
| `claude-3-haiku-20240307` | `claude-haiku-4-5-20251001` | Oct 2025 | claude-3-5-haiku deprecado Feb 2026; usar alias `claude-haiku-4-5` o ID con fecha |
| `profile.dict()` (Pydantic v1) | `profile.model_dump_json()` (Pydantic v2) | Pydantic v2 | Los schemas del proyecto ya usan v2 |

**Deprecated/outdated:**
- `claude-3-5-haiku-20241022`: deprecado, retirado en febrero 2026. Reemplazar por `claude-haiku-4-5-20251001`. [VERIFIED: platform.claude.com/docs]
- `claude-3-haiku-20240307`: modelo de generación anterior, inferior a haiku 4.5. [VERIFIED: platform.claude.com/docs]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Truncar `raw_text` a 20.000 chars como protección contra CVs anómalos | Common Pitfalls #4 | Riesgo bajo — el CV real de Jaime es estándar. Si se trunca texto relevante, bajará la calidad del CVProfile extraído. Ajustable. |
| A2 | Usar `monkeypatch.chdir(tmp_path)` como estrategia para aíslar caché en tests | Common Pitfalls #5 | Si `CACHE_DIR` es absoluto, este enfoque no funciona. Alternativa: sobreescribir `cache.CACHE_DIR` via monkeypatch directamente. |
| A3 | El CV real de Jaime tiene capa de texto (no es escaneado) | Pitfalls #4 | Si el PDF es una imagen escaneada, el extractor fallará con error claro. OCR está fuera de scope v1. |

**If this table is empty:** No — hay tres asunciones que deben tenerse en cuenta en el plan.

---

## Open Questions

1. **Ubicación configurable del caché**
   - What we know: La decisión bloqueada dice `data/.cache/` como path
   - What's unclear: ¿debe ser configurable vía env var para facilitar los tests sin monkeypatch de chdir?
   - Recommendation: Añadir `CV_CACHE_DIR` env var con default `data/.cache/`. Coste mínimo, elimina un pitfall de tests.

2. **Estrategia del PDF fixture**
   - What we know: La decisión dice "generarlo de forma reproducible (p.ej. con pymupdf/reportlab) o incluir un PDF mínimo versionado"
   - What's unclear: pymupdf ya es dependencia core (no solo test); usar pymupdf en conftest.py para generar el fixture evita añadir reportlab solo para tests
   - Recommendation: Generar el fixture con pymupdf en conftest.py (ya disponible). Solo añadir reportlab si se necesita formato más rico.

3. **max_tokens para la llamada al LLM**
   - What we know: claude-haiku-4-5 soporta 64k tokens de output; un CVProfile completo no supera los 2.000 tokens de salida
   - What's unclear: ¿cuánto establecer como límite para no malgastar budget?
   - Recommendation: `max_tokens=4096` es suficiente para cualquier CVProfile razonable y cuesta poco.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13+ | Runtime del proyecto | ✓ | 3.13.5 | — |
| uv | Gestión de dependencias | ✓ | 0.9.24 | pip + venv |
| pymupdf | Extracción PDF | ✓ (system pip) | 1.26.7 | — (no fallback; decisión bloqueada) |
| instructor | Structured LLM outputs | ✗ (no en project venv aún) | 1.15.1 disponible | `uv add instructor` |
| anthropic | SDK Anthropic | ✗ (no en project venv aún) | 0.104.0 disponible | `uv add anthropic` |
| python-dotenv | Carga de .env | ✗ (no en project venv aún) | 1.2.2 disponible | `uv add python-dotenv` |
| ANTHROPIC_API_KEY | Llamada al LLM | ✓ (en .env.example; usuario debe copiar) | — | Sin fallback (requerida para llamadas reales; tests la mockean) |

**Missing dependencies with no fallback:**
- `ANTHROPIC_API_KEY`: debe estar en `.env` para llamadas reales. Tests la mockean, así que no bloquea los tests.

**Missing dependencies with fallback:**
- `instructor`, `anthropic`, `python-dotenv`: no instalados en el venv del proyecto aún, pero disponibles via `uv add`. El plan debe incluir un paso de instalación.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pytest.ini` o `pyproject.toml [tool.pytest.ini_options]` — ninguno existe aún (Wave 0 gap) |
| Quick run command | `pytest tests/cv/ -x -q` |
| Full suite command | `pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CV-01 | `parse_cv(bytes)` devuelve `CVProfile` tipado válido | unit | `pytest tests/cv/test_parser.py -x -q` | ❌ Wave 0 |
| CV-02 | `CVProfile` tiene experiencia, skills, formación, años, dominios poblados desde el texto | unit | `pytest tests/cv/test_parser.py::test_cv_fields_populated -x` | ❌ Wave 0 |
| CV-03 | Segunda llamada con el mismo PDF no invoca al LLM (mock call count == 1) | unit | `pytest tests/cv/test_parser.py::test_cache_avoids_llm_call -x` | ❌ Wave 0 |
| QA-01 | Test con fixture PDF real y LLM mockeado; verifica campos clave | unit | `pytest tests/cv/ -x -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/cv/ -x -q`
- **Per wave merge:** `pytest -x -q`
- **Phase gate:** Full suite green antes de `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/cv/__init__.py` — init del módulo de tests
- [ ] `tests/conftest.py` — fixture `sample_pdf_bytes` (generar PDF con pymupdf)
- [ ] `tests/cv/test_extractor.py` — tests de `extract_text_from_pdf` sin LLM
- [ ] `tests/cv/test_cache.py` — tests de `load_cached_profile` / `save_cached_profile`
- [ ] `tests/cv/test_parser.py` — tests end-to-end con mock de `build_instructor_client`
- [ ] `pyproject.toml [tool.pytest.ini_options]` — configuración mínima de pytest (testpaths, pythonpath)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes (parcial) | Pydantic v2 valida la salida del LLM; pymupdf aísla el procesamiento del PDF |
| V6 Cryptography | No | sha256 es para cache-keying, no criptografía de seguridad |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key expuesta en código | Information Disclosure | `ANTHROPIC_API_KEY` solo desde `.env`; `.env` en `.gitignore`; `.env.example` sin valor real [VERIFIED: .gitignore pattern en proyecto] |
| PDF malicioso (zip bomb, etc.) | Tampering | pymupdf aísla el procesamiento; no ejecuta código del PDF. Aceptable para uso personal. |
| Inyección de prompt en el texto del CV | Tampering | Pasar el texto como contenido de usuario, no como instrucción de sistema. El system prompt no debe interpolarse con contenido del CV. |

---

## Sources

### Primary (HIGH confidence)
- Context7 `/websites/python_useinstructor` — instructor `from_anthropic`, `messages.create`, `response_model`, modos TOOLS/ANTHROPIC_TOOLS, retries
- Context7 `/pymupdf/pymupdf` — `pymupdf.open(stream=bytes)`, `page.get_text()`, detección de páginas sin texto, generación de PDF desde cero
- `platform.claude.com/docs/en/about-claude/models/overview` — IDs de modelos actuales, `claude-haiku-4-5-20251001` como modelo haiku vigente
- `app/models/schemas.py` — `CVProfile`, `Experiencia`, `Formacion` ya definidos (lectura directa del repo)

### Secondary (MEDIUM confidence)
- pip registry (verificado 2026-05-22) — versiones actuales: pymupdf 1.26.7, instructor 1.15.1, anthropic 0.104.0, pytest 9.0.3
- `platform.claude.com/docs` (via WebFetch) — deprecación de claude-3-5-haiku confirmada

### Tertiary (LOW confidence)
- Ninguna — todas las afirmaciones críticas están verificadas con fuentes primarias.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versiones verificadas contra pip registry; instructor y pymupdf verificados contra Context7
- Architecture: HIGH — patrones verificados contra docs oficiales; estructura de módulos es ASSUMED (A1-A3 en Assumptions Log)
- Pitfalls: HIGH — pitfall de nombres de modelo verificado contra Anthropic docs oficiales; los demás son patrones conocidos verificados

**Research date:** 2026-05-22
**Valid until:** 2026-06-22 (estable — las versiones de librerías y modelos Anthropic cambian, pero los patrones de API son estables)
