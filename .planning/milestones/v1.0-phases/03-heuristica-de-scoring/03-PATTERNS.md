# Phase 3: Heurística de Scoring (núcleo) - Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 12 new/modified files
**Analogs found:** 11 / 12

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/config/__init__.py` | config | request-response | `app/cv/__init__.py` | exact |
| `app/config/loader.py` | config | request-response | `app/cv/cache.py` (yaml→model pattern from RESEARCH) | role-match |
| `app/models/schemas.py` (add `LLMJobAssessment`) | model | — | existing `app/models/schemas.py` (JobScore, CVProfile) | exact |
| `app/scoring/__init__.py` | config | request-response | `app/cv/__init__.py` | exact |
| `app/scoring/ranking.py` | utility | transform | `app/dedup/normalize.py` (pure-function module) | role-match |
| `app/scoring/location.py` | utility | transform | `app/dedup/normalize.py` (NFD normalize) | role-match |
| `app/scoring/llm.py` | service | request-response | `app/cv/llm_client.py` | exact |
| `app/scoring/scorer.py` | service | request-response | `app/cv/parser.py` (orchestrator) | exact |
| `tests/scoring/__init__.py` | test | — | `tests/cv/__init__.py` | exact |
| `tests/scoring/test_loader.py` | test | — | `tests/cv/test_cache.py` | role-match |
| `tests/scoring/test_ranking.py` | test | — | `tests/dedup/test_normalize.py` | role-match |
| `tests/scoring/test_location.py` | test | — | `tests/dedup/test_normalize.py` | role-match |
| `tests/scoring/test_llm.py` | test | — | `tests/cv/test_llm_client.py` | exact |
| `tests/scoring/test_scorer.py` | test | — | `tests/cv/test_parser.py` (integration with mock) | exact |

---

## Pattern Assignments

### `app/config/__init__.py` (config, public facade)

**Analog:** `app/cv/__init__.py`

**Public facade pattern** (lines 1-9 of `app/cv/__init__.py`):
```python
"""Módulo de parseo de CV (FASE 1).

Interfaz pública:
    parse_cv(pdf_bytes: bytes) -> CVProfile
"""

from app.cv.parser import parse_cv

__all__ = ["parse_cv"]
```

**Apply to `app/config/__init__.py`:**
```python
"""Módulo de configuración — carga de UserProfile desde profile.yaml.

Interfaz pública:
    load_user_profile(path) -> UserProfile
"""

from app.config.loader import load_user_profile

__all__ = ["load_user_profile"]
```

---

### `app/config/loader.py` (config, request-response)

**No exact codebase analog** — closest pattern is `app/cv/cache.py` (file I/O + error handling) combined with RESEARCH.md Pattern 1. The RESEARCH.md pattern is authoritative here.

**Imports pattern** (from `app/cv/cache.py` lines 1-10 and RESEARCH.md):
```python
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.models.schemas import UserProfile

logger = logging.getLogger(__name__)
```

**Core function pattern** (RESEARCH.md Pattern 1 — verified against pydantic.dev docs):
```python
def load_user_profile(path: str = "data/profile.yaml") -> UserProfile:
    """Carga y valida el UserProfile desde YAML. Lanza ValueError con mensaje claro si falla."""
    try:
        with open(Path(path)) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"No se encontró profile.yaml en: {path}")
    try:
        return UserProfile.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"profile.yaml inválido:\n{e}") from e
```

**Error handling pattern** (from `app/cv/cache.py` lines — propagate with context, not bare re-raise):
- Wrap `FileNotFoundError` with path in message.
- Wrap `ValidationError` as `ValueError` with `from e` chain.
- No bare `except Exception` — let other errors propagate raw.

**Pesos sum=1.0 validator** (must be added to `PesosScoring` in `app/models/schemas.py` — RESEARCH.md Pattern with float tolerance):
```python
# In PesosScoring (app/models/schemas.py)
from pydantic import model_validator
from typing_extensions import Self

@model_validator(mode='after')
def check_sum(self) -> Self:
    total = self.puesto + self.skills + self.ubicacion + self.seniority
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Los pesos deben sumar 1.0, suman {total:.6f}")
    return self
```

---

### `app/models/schemas.py` — add `LLMJobAssessment` (model)

**Analog:** `app/models/schemas.py` existing `JobScore` and `CVProfile` classes (lines 138-162, 106-112)

**Imports pattern** (lines 1-11 of `app/models/schemas.py`):
```python
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
```

**Existing Desglose pattern** (lines 138-143 of `app/models/schemas.py`) — note `Field(ge=0, le=100)` for range enforcement:
```python
class Desglose(BaseModel):
    encaje_puesto: int = Field(ge=0, le=100)
    encaje_skills: int = Field(ge=0, le=100)
    encaje_ubicacion: int = Field(ge=0, le=100)
    encaje_seniority: int = Field(ge=0, le=100)
```

**New `LLMJobAssessment` schema** (RESEARCH.md Pattern 2 — replicate naming + Field descriptions):
```python
class LLMJobAssessment(BaseModel):
    """Lo que el LLM evalúa. Solo campos que requieren comprensión de texto libre."""

    razonamiento: str = Field(
        description=(
            "Razonamiento paso a paso: qué puesto detectas, qué skills coinciden, "
            "qué skills faltan, nivel de seniority pedido vs experiencia del candidato, "
            "si hay deal-breakers en el texto. Sé HONESTO, no infles."
        )
    )
    puesto_detectado: str = Field(
        description=(
            "Nombre del puesto del ranking al que corresponde la oferta, "
            "usando los sinónimos proporcionados. O 'fuera de ranking' si ninguno encaja."
        )
    )
    rango_puesto: Optional[int] = Field(
        default=None,
        description="Posición en el ranking (1=top). None si puesto_detectado='fuera de ranking'.",
    )
    encaje_skills: int = Field(ge=0, le=100, description="0-100: % de requisitos que cumple el CVProfile.")
    encaje_seniority: int = Field(ge=0, le=100, description="0-100: nivel pedido vs experiencia real.")
    matched_skills: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    reasons_for: list[str] = Field(default_factory=list)
    reasons_against: list[str] = Field(default_factory=list)
    deal_breaker_hit_texto: bool = Field(default=False)
    deal_breaker_cual_texto: Optional[str] = Field(default=None)
```

**Critical:** `LLMJobAssessment` must NOT contain `encaje_ubicacion`, `score_total`, or `recommendation` — those are deterministic (Pitfall 5 in RESEARCH.md).

---

### `app/scoring/ranking.py` (utility, transform)

**Analog:** `app/dedup/normalize.py` (pure function module, stdlib only, no external deps)

**Module header pattern** (lines 1-22 of `app/dedup/normalize.py`):
```python
"""
Funciones de normalización de texto para el pipeline de deduplicación.

Responsabilidades:
  - normalize_field: ...
  - stable_job_id: ...

Estas funciones son puras (stdlib only) y no tienen dependencias externas.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
```

**Core pure-function pattern** (RESEARCH.md Pattern 3 — verified arithmetically):
```python
def encaje_puesto_desde_rango(
    rango: int | None,
    *,
    paso: int = 15,
    suelo: int = 20,
    maximo: int = 100,
) -> int:
    """Score de encaje_puesto a partir del rango del puesto (1-based).

    - rango=1 → maximo (100 por defecto)
    - rango=N → max(suelo, maximo - (N-1)*paso)
    - rango=None (fuera de ranking) → suelo (no 0 — no se descarta solo)
    """
    if rango is None:
        return suelo
    score = maximo - (rango - 1) * paso
    return max(suelo, score)
```

**Table of values** (rango 1→100, 2→85, 3→70, 4→55, None→20 with defaults paso=15, suelo=20):
- Monotonicity: `encaje_puesto(N) >= encaje_puesto(N+1)` for all N — test this property.
- `suelo > 0` is a hard requirement: fuera de ranking no descarta sola.

---

### `app/scoring/location.py` (utility, transform)

**Analog:** `app/dedup/normalize.py` — NFD city normalization pattern (lines 25-55)

**NFD normalize pattern** (lines 51-55 of `app/dedup/normalize.py`) — the exact approach to replicate for city matching:
```python
# Paso 1: NFD — descompone caracteres acentuados
s = unicodedata.normalize("NFD", s)
# Paso 2: quitar combining marks (acentos, tildes, cedillas, etc.)
s = "".join(c for c in s if unicodedata.category(c) != "Mn")
# Paso 3+4: casefold, strip y colapso de espacios
return re.sub(r"\s+", " ", s.casefold().strip())
```

**Imports for location.py:**
```python
from __future__ import annotations

import logging
import unicodedata

from app.models.schemas import Job, ModalidadRemoto, RemoteJob, UserProfile

logger = logging.getLogger(__name__)
```

**Public function signature** (RESEARCH.md Pattern 4):
```python
def evaluar_ubicacion(
    job: Job,
    profile: UserProfile,
) -> tuple[int, str | None]:
    """Devuelve (encaje_ubicacion, deal_breaker_descripcion|None).

    encaje_ubicacion: 0-100 determinista según Job.remote + location vs preferencias.
    deal_breaker_descripcion: str si la ubicación activa un deal-breaker, None si no.
    """
```

**City matching helper** (RESEARCH.md Code Examples — use substring match not equality, Pitfall 6):
```python
def _normalize_city(name: str) -> str:
    """NFD lowercase sin acentos. Mismo algoritmo que dedup/normalize.py."""
    nfd = unicodedata.normalize("NFD", name.lower().strip())
    return "".join(c for c in nfd if not unicodedata.combining(c))

def _ciudad_aceptada(location: str | None, ciudades: list[str]) -> bool:
    """True si location normalizada contiene alguna ciudad aceptada (substring match)."""
    if not location:
        return False
    loc_norm = _normalize_city(location)
    return any(_normalize_city(c) in loc_norm for c in ciudades)
```

**Decision matrix** (RESEARCH.md Pattern 4 — 8 cases):

| `job.remote` | `_ciudad_aceptada` | `dispuesto_a_reubicarse` | `encaje` | `deal_breaker` |
|---|---|---|---|---|
| `remote` + modal permite (remote/hybrid/indiferente) | any | any | 100 | None |
| `remote` + modal=onsite | any | any | 60 | None |
| `hybrid` | True | any | 80 | None |
| `hybrid` | False | False | 10 | "Trabajo híbrido fuera de ciudades aceptadas: {city}" |
| `hybrid` | False | True | 50 | None |
| `onsite` | True | any | 90 | None |
| `onsite` | False | False | 10 | "Presencial fuera de ciudades aceptadas: {city}" |
| `onsite` | False | True | 40 | None |
| `unknown` | any | any | 50 | None |

**"Ciudades aceptadas"** = `profile.preferencias_ubicacion.ciudades_preferidas` + `profile.preferencia_remoto.acepta_onsite_solo_en` (concatenate both lists before passing to `_ciudad_aceptada`).

---

### `app/scoring/llm.py` (service, request-response)

**Analog:** `app/cv/llm_client.py` — EXACT pattern (lines 1-62)

**Module docstring pattern** (lines 1-14 of `app/cv/llm_client.py`) — replicate structure including security mitigations note:
```python
"""
Módulo LLM para evaluación de ofertas de empleo.

Expone:
- build_instructor_client(): fábrica del cliente instructor (seam de inyección para tests).
- assess_job(job, cv_profile, user_profile, client): llama al LLM con
  response_model=LLMJobAssessment y devuelve una evaluación tipada.

Mitigaciones de seguridad:
- El texto de la oferta va SOLO en el mensaje de usuario en XML tags; el system prompt
  es una cadena fija sin interpolación de contenido externo (anti prompt-injection).
- La clave de API la lee el SDK de Anthropic del entorno; nunca se referencia aquí.
- El modelo se configura via ANTHROPIC_MODEL_SCORING con default claude-sonnet-4-6.
"""
```

**Factory pattern** (lines 25-27 of `app/cv/llm_client.py`) — replicate verbatim:
```python
def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())
```

**Core LLM call pattern** (lines 30-61 of `app/cv/llm_client.py`) — replicate structure, adapt for scoring:
```python
def assess_job(
    job: Job,
    cv_profile: CVProfile,
    user_profile: UserProfile,
    client: instructor.Instructor,
) -> LLMJobAssessment:
    """Llama al LLM para evaluar el encaje job↔candidato.

    NOTA: Esta función es el único punto de entrada LLM para scoring.
    Fase 5 la envolverá con Langfuse para observabilidad.
    """
    model = os.getenv("ANTHROPIC_MODEL_SCORING", "claude-sonnet-4-6")
    return client.messages.create(
        model=model,
        max_tokens=2048,
        system=(
            "Eres un evaluador HONESTO de ofertas de empleo. "
            "Tu objetivo es dar una evaluación realista y calibrada de si la oferta encaja "
            "con el candidato. NO infles los reasons_for ni ocultes los reasons_against. "
            "Si hay requisitos que el candidato claramente no cumple, ponlos en missing_requirements. "
            "El valor de este sistema está en filtrar bien, no en parecer optimista."
        ),
        messages=[{"role": "user", "content": _build_prompt(job, cv_profile, user_profile)}],
        response_model=LLMJobAssessment,
        max_retries=2,
    )
```

**Key differences from `cv/llm_client.py`:**
- `response_model=LLMJobAssessment` (not `CVProfile`)
- `model` from `ANTHROPIC_MODEL_SCORING` (not `ANTHROPIC_MODEL_CV`)
- `max_tokens=2048` (scoring needs less than CV extraction's 4096)
- System prompt instructs JUDGMENT + HONESTY (not extraction)
- User content uses XML tags for structured multi-part context (see RESEARCH.md Pattern 5)
- Helper `_build_prompt(job, cv_profile, user_profile)` separates prompt construction (easier to test prompt content)

**Prompt helper pattern** (from RESEARCH.md Pattern 5 — XML tags, text format over JSON):
```python
def _build_prompt(job: Job, cv_profile: CVProfile, user_profile: UserProfile) -> str:
    """Construye el mensaje de usuario con XML tags. Texto legible, no JSON crudo."""
    ranking_text = _format_ranking(user_profile.ranking_puestos)
    cv_text = _format_cv(cv_profile)
    deal_breakers_text = "\n".join(f"- {db}" for db in user_profile.deal_breakers)
    return (
        "<candidato>\n"
        f"<cv>{cv_text}</cv>\n"
        f"<ranking_puestos>{ranking_text}</ranking_puestos>\n"
        "<preferencias_ubicacion>"
        f"modalidad_ideal={user_profile.preferencia_remoto.modalidad_ideal.value}, "
        f"acepta_onsite_en={user_profile.preferencia_remoto.acepta_onsite_solo_en}"
        "</preferencias_ubicacion>\n"
        f"<deal_breakers>\n{deal_breakers_text}\n</deal_breakers>\n"
        "</candidato>\n"
        f"<oferta>\n{_format_job(job)}\n</oferta>\n"
        "Evalúa el encaje de esta oferta con el candidato."
    )
```

---

### `app/scoring/scorer.py` (service, request-response)

**Analog:** `app/cv/parser.py` — orchestrator pattern (lines 1-47)

**Module docstring pattern** (lines 1-13 of `app/cv/parser.py`) — replicate structure:
```python
"""
Orquestador de scoring de ofertas.

Implementa la interfaz pública `score_job(job, cv_profile, user_profile, client) -> JobScore` que:
  1. Evalúa ubicación de forma determinista (location.py).
  2. Llama al LLM para evaluar skills/seniority/puesto (llm.py).
  3. Calcula encaje_puesto desde decay (ranking.py).
  4. Calcula score_total ponderado con pesos de UserProfile.pesos.
  5. Asigna recommendation por bandas.
  6. Aplica deal-breaker override (filtro duro — último paso).

Este módulo es el único punto de entrada para consumidores externos.
"""
```

**Imports pattern** (replicating `app/cv/parser.py` lines 14-19 — import only leaf modules):
```python
from __future__ import annotations

import logging

import instructor

from app.models.schemas import (
    CVProfile, Desglose, Job, JobScore, Recommendation, UserProfile,
)
from app.scoring.location import evaluar_ubicacion
from app.scoring.llm import assess_job, build_instructor_client
from app.scoring.ranking import encaje_puesto_desde_rango

logger = logging.getLogger(__name__)
```

**Orchestrator pattern** (from `app/cv/parser.py` lines 22-47 — single public function, lazy client creation, linear steps):
```python
def score_job(
    job: Job,
    cv_profile: CVProfile,
    user_profile: UserProfile,
    client: instructor.Instructor | None = None,
) -> JobScore:
    """Puntúa una oferta contra el perfil del usuario.

    Args:
        job:          Oferta normalizada (Job de Fase 2).
        cv_profile:   CV estructurado (CVProfile de Fase 1).
        user_profile: Perfil del usuario (UserProfile del config loader).
        client:       Cliente instructor inyectado. Si None, se construye uno real.
                      Inyectable para tests (cero red).

    Returns:
        JobScore completo con score_total, recommendation y desglose.
    """
    if client is None:
        client = build_instructor_client()

    # Paso 1: ubicación determinista
    encaje_ubicacion, deal_breaker_loc = evaluar_ubicacion(job, user_profile)

    # Paso 2: evaluación LLM (skills, seniority, puesto, deal-breaker textual)
    assessment = assess_job(job, cv_profile, user_profile, client)

    # Paso 3: decay del ranking (determinista sobre rango del LLM)
    encaje_puesto = encaje_puesto_desde_rango(assessment.rango_puesto)

    # Paso 4: score_total ponderado (determinista)
    pesos = user_profile.pesos
    raw = (
        encaje_puesto * pesos.puesto
        + assessment.encaje_skills * pesos.skills
        + encaje_ubicacion * pesos.ubicacion
        + assessment.encaje_seniority * pesos.seniority
    )
    score_total = max(0, min(100, round(raw)))

    # Paso 5: recomendación por bandas
    recommendation = _banda(score_total)

    # Paso 6: deal-breaker override — ÚLTIMO (score_total conserva valor real)
    deal_breaker_hit = bool(deal_breaker_loc or assessment.deal_breaker_hit_texto)
    deal_breaker_cual: str | None = deal_breaker_loc or assessment.deal_breaker_cual_texto
    if deal_breaker_hit:
        recommendation = Recommendation.skip

    return JobScore(
        score_total=score_total,
        recommendation=recommendation,
        desglose=Desglose(
            encaje_puesto=encaje_puesto,
            encaje_skills=assessment.encaje_skills,
            encaje_ubicacion=encaje_ubicacion,
            encaje_seniority=assessment.encaje_seniority,
        ),
        puesto_detectado=assessment.puesto_detectado,
        rango_puesto=assessment.rango_puesto,
        reasons_for=assessment.reasons_for,
        reasons_against=assessment.reasons_against,
        matched_skills=assessment.matched_skills,
        missing_requirements=assessment.missing_requirements,
        deal_breaker_hit=deal_breaker_hit,
        deal_breaker_cual=deal_breaker_cual,
    )


def _banda(score: int) -> Recommendation:
    if score >= 80:
        return Recommendation.strong_fit
    if score >= 60:
        return Recommendation.good_fit
    if score >= 40:
        return Recommendation.maybe
    return Recommendation.skip
```

**Critical ordering:** Deal-breaker override is step 6 (LAST). The `score_total` reflects true offer quality even for deal-broken offers — only `recommendation` is overridden to `skip`.

---

### `app/scoring/__init__.py` (config, public facade)

**Analog:** `app/cv/__init__.py` (lines 1-9) — exact pattern

```python
"""Módulo de scoring de ofertas (FASE 3).

Interfaz pública:
    score_job(job, cv_profile, user_profile, client=None) -> JobScore
"""

from app.scoring.scorer import score_job

__all__ = ["score_job"]
```

**Critical:** Do NOT import from `app.dedup` here or transitively. The scorer receives already-deduplicated `Job` objects. Importing `app.dedup` would trigger BGE-M3 model download in tests (Pitfall 7 in RESEARCH.md).

---

## Test Pattern Assignments

### `tests/scoring/test_loader.py`

**Analog:** `tests/cv/test_cache.py` (file I/O unit tests) + `tests/cv/test_extractor.py`

**Test module pattern** (from `tests/cv/test_extractor.py` — functional tests, no class):
```python
"""
Tests para app/config/loader.py.

Verifica:
1. load_user_profile carga un profile.yaml válido → UserProfile con campos correctos.
2. load_user_profile con ruta inexistente → FileNotFoundError.
3. load_user_profile con pesos que no suman 1.0 → ValueError.
4. load_user_profile con profile.yaml real de data/ → UserProfile válido.
"""
from __future__ import annotations

import pytest
from app.config.loader import load_user_profile
```

**Fixture pattern for temp YAML** (from `tests/cv/test_cache.py` tmp_path usage):
```python
def test_carga_perfil_valido(tmp_path) -> None:
    yaml_content = "..."  # minimal valid profile.yaml content
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(yaml_content)
    profile = load_user_profile(str(profile_path))
    assert isinstance(profile, UserProfile)
```

---

### `tests/scoring/test_ranking.py`

**Analog:** `tests/dedup/test_normalize.py` (pure function tests, parametrize)

**Parametrize pattern** (from `tests/dedup/test_normalize.py`):
```python
import pytest
from app.scoring.ranking import encaje_puesto_desde_rango

@pytest.mark.parametrize("rango,expected", [
    (1, 100),
    (2, 85),
    (3, 70),
    (4, 55),
    (None, 20),
])
def test_decay_values(rango, expected) -> None:
    assert encaje_puesto_desde_rango(rango) == expected

def test_monotonia() -> None:
    """rango N siempre >= rango N+1."""
    scores = [encaje_puesto_desde_rango(i) for i in range(1, 6)]
    for a, b in zip(scores, scores[1:]):
        assert a >= b

def test_suelo_mayor_que_cero() -> None:
    assert encaje_puesto_desde_rango(None) > 0
```

---

### `tests/scoring/test_location.py`

**Analog:** `tests/dedup/test_normalize.py` (parametrized pure function tests)

**Test coverage required** (8 cases from RESEARCH.md Pattern 4 decision matrix):
```python
from app.scoring.location import evaluar_ubicacion
# Test: remote + modalidad remote → encaje=100, no deal_breaker
# Test: remote + modalidad onsite → encaje=60, no deal_breaker
# Test: onsite + ciudad aceptada → encaje=90, no deal_breaker
# Test: onsite + ciudad NO aceptada + no reubicarse → encaje=10, deal_breaker str
# Test: onsite + ciudad NO aceptada + sí reubicarse → encaje=40, no deal_breaker
# Test: hybrid + ciudad aceptada → encaje=80, no deal_breaker
# Test: hybrid + ciudad NO aceptada + no reubicarse → encaje=10, deal_breaker str
# Test: unknown → encaje=50, no deal_breaker
# Test: location="Barcelona, España" matches "Barcelona" (Pitfall 6 — substring match)
```

---

### `tests/scoring/test_llm.py`

**Analog:** `tests/cv/test_llm_client.py` — EXACT pattern (lines 1-71)

**Mock construction pattern** (lines 34-38 of `tests/cv/test_llm_client.py`):
```python
def _make_mock_client() -> MagicMock:
    """Construye un MagicMock que imita la superficie instructor.from_anthropic()."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _MOCK_ASSESSMENT  # LLMJobAssessment instance
    return mock_client
```

**Verification pattern** (lines 51-70 of `tests/cv/test_llm_client.py`):
```python
def test_passes_response_model_and_model(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_MODEL_SCORING", raising=False)
    mock_client = _make_mock_client()
    assess_job(job, cv_profile, user_profile, mock_client)
    mock_client.messages.create.assert_called_once()
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["response_model"] is LLMJobAssessment
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["max_retries"] == 2
```

**Prompt content verification** (additional test not in cv/test_llm_client.py):
```python
def test_assess_job_incluye_contexto_en_prompt(monkeypatch) -> None:
    """SCORE-08: el prompt incluye CVProfile, ranking, prefs, deal_breakers, oferta."""
    mock_client = _make_mock_client()
    assess_job(job, cv_profile, user_profile, mock_client)
    kwargs = mock_client.messages.create.call_args.kwargs
    content = kwargs["messages"][0]["content"]
    assert "AI Engineer" in content          # puesto del ranking
    assert "Python" in content               # skill del CVProfile
    assert "presencial fuera de Barcelona" in content  # deal_breaker real
    assert job.title in content              # título de la oferta
```

---

### `tests/scoring/test_scorer.py`

**Analog:** `tests/cv/test_parser.py` — integration test with mock LLM (lines 1-82)

**Mock injection pattern** (lines 27-44 of `tests/cv/test_parser.py`):
```python
with patch("app.cv.parser.build_instructor_client", return_value=mock_llm_client):
    result = parse_cv(sample_pdf_bytes)
```

**For scorer tests — inject client directly** (scorer accepts `client=` param, no patch needed):
```python
def make_mock_scoring_client(assessment: LLMJobAssessment) -> MagicMock:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = assessment
    return mock_client

def test_deal_breaker_ubicacion_fuerza_skip(sample_job_onsite_madrid, ...) -> None:
    """SCORE-05: deal-breaker de ubicación → recommendation=skip aunque sub-scores sean altos."""
    assessment = LLMJobAssessment(
        razonamiento="...", puesto_detectado="AI Engineer", rango_puesto=1,
        encaje_skills=90, encaje_seniority=80, ...,
        deal_breaker_hit_texto=False, deal_breaker_cual_texto=None,
    )
    client = make_mock_scoring_client(assessment)
    score = score_job(sample_job_onsite_madrid, cv_profile, user_profile, client=client)
    assert score.recommendation == Recommendation.skip
    assert score.deal_breaker_hit is True

def test_score_total_ponderado_exacto(...) -> None:
    """SCORE-06: dados 4 sub-scores + pesos conocidos → total ponderado esperado."""
    # encaje_puesto=100 (rango=1), skills=80, ubicacion=100 (remote), seniority=70
    # pesos: puesto=0.35, skills=0.30, ubicacion=0.20, seniority=0.15
    # expected = round(100*0.35 + 80*0.30 + 100*0.20 + 70*0.15) = round(35+24+20+10.5) = 90
    assert score.score_total == 90

def test_seniority_bajo_no_descarta(...) -> None:
    """SCORE-04: encaje_seniority bajo + missing_requirements → en JobScore sin skip."""
    # LLM devuelve encaje_seniority=30, missing_requirements=["5+ años de experiencia"]
    # recommendation debe ser maybe o mejor (no skip), si score_total >= 40
    assert score.recommendation != Recommendation.skip
    assert "5+ años de experiencia" in score.missing_requirements
```

---

## Shared Patterns

### Injectable LLM client (seam for tests)
**Source:** `app/cv/llm_client.py` lines 25-27
**Apply to:** `app/scoring/llm.py` + `app/scoring/scorer.py`
```python
def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())
```
Pattern: factory function is separate from the call function. `scorer.py` accepts `client=None` and calls the factory lazily. Tests inject a `MagicMock()` directly.

### MagicMock LLM pattern
**Source:** `tests/conftest.py` lines 67-77 + `tests/cv/test_llm_client.py` lines 34-38
**Apply to:** `tests/scoring/test_llm.py` + `tests/scoring/test_scorer.py`
```python
mock_client = MagicMock()
mock_client.messages.create.return_value = <typed_response_instance>
```
All scoring tests must use this pattern. Zero real API calls in tests.

### NFD normalization
**Source:** `app/dedup/normalize.py` lines 51-55
**Apply to:** `app/scoring/location.py` city matching
```python
s = unicodedata.normalize("NFD", s)
s = "".join(c for c in s if unicodedata.category(c) != "Mn")
return re.sub(r"\s+", " ", s.casefold().strip())
```
Use `unicodedata.category(c) != "Mn"` (not `not unicodedata.combining(c)` — both work but `!= "Mn"` is the established project convention from `normalize.py`).

### from __future__ import annotations
**Source:** All existing app modules (lines 1 of `app/cv/llm_client.py`, `app/dedup/normalize.py`, `app/cv/parser.py`)
**Apply to:** All new `app/` modules
```python
from __future__ import annotations
```

### Logging pattern
**Source:** `app/dedup/__init__.py` line 23, `app/dedup/normalize.py` line 22
**Apply to:** `app/scoring/scorer.py`, `app/config/loader.py`
```python
import logging
logger = logging.getLogger(__name__)
# Usage: logger.info("score_job: job=%s score=%d recommendation=%s", job.id, score.score_total, score.recommendation.value)
```

### Pydantic v2 model_validate
**Source:** `app/models/schemas.py` (all BaseModel subclasses)
**Apply to:** `app/config/loader.py`
```python
return UserProfile.model_validate(data)  # not UserProfile(**data)
```

### Deferred imports to avoid heavy model loading
**Source:** `app/dedup/__init__.py` lines 106-109
**Apply to:** `app/scoring/__init__.py` — must NOT import from `app.dedup`
```python
# Pattern: imports deferidos dentro del cuerpo de función para evitar
# arrastrar numpy/torch al importar el paquete (T-02-11)
from app.dedup.exact import exact_group  # noqa: PLC0415
```
For scoring: `app/scoring/` never imports `app/dedup`. The scorer receives already-deduplicated `Job` objects.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `app/config/loader.py` | config | file-I/O → validate | No YAML config loader exists yet — pattern comes from RESEARCH.md verified against pydantic.dev docs |

---

## Metadata

**Analog search scope:** `app/cv/`, `app/dedup/`, `app/models/`, `tests/cv/`, `tests/dedup/`, `tests/conftest.py`, `data/profile.yaml`
**Files scanned:** 14 source files + 8 test files
**Pattern extraction date:** 2026-05-22

**Analog quality summary:**
- `app/scoring/llm.py` ← `app/cv/llm_client.py`: identical pattern, adapt response_model + model env + system prompt tone
- `app/scoring/scorer.py` ← `app/cv/parser.py`: identical orchestrator structure, adapt steps 1-6
- `app/scoring/location.py` ← `app/dedup/normalize.py`: reuse NFD algorithm, adapt for city substring matching
- `app/config/loader.py` ← RESEARCH.md Pattern 1 (yaml.safe_load + model_validate — no codebase analog)
- `app/scoring/ranking.py` ← `app/dedup/normalize.py`: reuse pure-function module style
- `tests/scoring/test_llm.py` ← `tests/cv/test_llm_client.py`: replicate almost verbatim
- `tests/scoring/test_scorer.py` ← `tests/cv/test_parser.py`: replicate integration + mock injection pattern
