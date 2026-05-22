# Phase 3: Heurística de Scoring (núcleo) - Research

**Researched:** 2026-05-22
**Domain:** Hybrid deterministic scoring + LLM judgment (Instructor + Anthropic)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Capa DETERMINISTA (Python puro, unit-testeable sin LLM):**
- `encaje_puesto` = función de DECAIMIENTO del `rango_puesto`: rango 1 → 100 (máximo), cada posición más abajo reduce de forma graduada (default lineal con `paso` configurable, p.ej. 100, 85, 70, 55…), con un `suelo` para ofertas fuera de ranking (rango_puesto=None → encaje bajo, p.ej. 20, NO 0 — fuera de ranking no se descarta sola). Parámetros configurables. El LLM decide QUÉ rango encaja; el SCORE de encaje_puesto lo calcula Python desde el decay.
- `encaje_ubicacion` = reglas deterministas desde `Job.remote` + `Job.location` vs `UserProfile`: remote y modalidad_ideal lo permite → alto (~100); onsite/hybrid en ciudad de `ciudades_preferidas` o `acepta_onsite_solo_en` → alto; onsite/hybrid fuera de esas ciudades y `dispuesto_a_reubicarse=false` → muy bajo (~10) y marcar candidato a deal-breaker de ubicación; `unknown` → neutro (~50).
- `score_total` = suma PONDERADA de los 4 sub-encajes con pesos de `UserProfile.pesos` (deben sumar 1.0 — validar al cargar). Fórmula determinista, redondeo a int 0-100.
- `recommendation` = bandas deterministas de `score_total` (defaults: ≥80 strong_fit, ≥60 good_fit, ≥40 maybe, <40 skip), configurables. PERO un deal-breaker fuerza skip (override duro).
- **Deal-breaker = filtro DURO**: detección determinista de los basados en ubicación + los detectados por el LLM en el texto → `deal_breaker_hit=true`, `deal_breaker_cual` explica cuál, y `recommendation=skip`.

**Capa LLM (Instructor + Anthropic, response_model = LLMJobAssessment):**
- `puesto_detectado` (str) + `rango_puesto` (int|null): el LLM empareja la oferta con la entrada del ranking usando los sinónimos; null si ninguna encaja.
- `encaje_skills` (0-100): requisitos de la oferta vs skills REALES del CVProfile.
- `encaje_seniority` (0-100): nivel/años pedidos vs experiencia real del CVProfile; pedir mucho más baja el encaje y aparece en `missing_requirements`, pero NO descarta solo.
- `matched_skills` [str], `missing_requirements` [str], `reasons_for` [str], `reasons_against` [str] (honesto, sin inflar).
- `deal_breaker_hit_texto` (bool) + `cual` (str|null): deal-breakers detectables en el texto.
- El LLM NO calcula `score_total`, `encaje_puesto` ni `encaje_ubicacion`.

**Estructura de módulos:**
- `app/config/loader.py`: `load_user_profile(path="data/profile.yaml") -> UserProfile`
- `app/scoring/ranking.py`: `encaje_puesto_desde_rango(rango: int|None, ...) -> int`
- `app/scoring/location.py`: `evaluar_ubicacion(job, profile) -> (encaje:int, deal_breaker:str|None)`
- `app/scoring/llm.py`: `build_instructor_client()` + `assess_job(job, cv, profile, client) -> LLMJobAssessment`
- `app/scoring/scorer.py`: `score_job(job, cv_profile, user_profile, client=None, ...) -> JobScore`
- Nuevo schema `LLMJobAssessment` en `app/models/schemas.py`

**Modelo LLM:** Configurable vía env `ANTHROPIC_MODEL_SCORING`; default `claude-sonnet-4-6` (por su mayor capacidad de juicio que haiku). Clave desde `ANTHROPIC_API_KEY` (env); nunca hardcodeada. Estructurar la llamada en una sola función para que Fase 5 pueda envolverla con Langfuse.

**Tests (QA-04):** Exhaustivos, LLM siempre mockeado, cero red.

### Claude's Discretion
- Nombre exacto del modelo default y decay (lineal vs por tramos) — lineal con paso/suelo configurable
- Si los parámetros de decay/bandas viven en profile.yaml o en código con defaults
- Estructura interna exacta y nombres de campos de `LLMJobAssessment`
- Cómo se redondean/clampan los scores

### Deferred Ideas (OUT OF SCOPE)
- Observabilidad Langfuse real alrededor de la llamada de scoring (Fase 5, OBS-02)
- Endpoints /jobs/score y /jobs/process (Fase 4)
- Persistencia de los scores (Fase 4)
- Calibración fina de los pesos/decay contra resultados reales (post-uso real)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCORE-01 | Para cada oferta única, devolver un `JobScore` con `score_total`, `recommendation` y desglose de 4 sub-encajes | `score_job()` orquesta todas las capas; `LLMJobAssessment` aporta skills/seniority; Python calcula puesto/ubicacion/total |
| SCORE-02 | Ranking de puestos como PESO graduado (decay configurable), no filtro binario; fuera de ranking no se descarta | Decay lineal `max(suelo, maximo - (rango-1)*paso)` verificado aritméticamente |
| SCORE-03 | Ubicación y remoto evaluados con reglas deterministas según preferencias | Mapa de 4 casos: remote-permitido / onsite-ciudad-aceptada / onsite-fuera-sin-reubicacion / unknown |
| SCORE-04 | Seniority comparado contra CVProfile; pedir mucho baja encaje y aparece en missing_requirements, pero no descarta | LLM devuelve `encaje_seniority` + `missing_requirements`; scorer lo incluye sin forzar skip |
| SCORE-05 | Deal-breaker → `recommendation=skip`, `deal_breaker_hit=true`, explicar cuál (filtro duro) | Override post-score: cualquier deal-breaker (ubicación O texto) fuerza skip antes de asignar recommendation |
| SCORE-06 | `score_total` ponderado con pesos configurables desde profile.yaml (defaults puesto 35/skills 30/ubicacion 20/seniority 15) | Fórmula `round(encaje_puesto*p.puesto + ... )`, clamped 0-100; pesos validan sum=1.0 |
| SCORE-07 | Honestidad: `reasons_for`, `reasons_against`, `matched_skills`, `missing_requirements` sin inflar | System prompt con instrucción explícita de honestidad + campo `razonamiento` (chain-of-thought) en LLMJobAssessment |
| SCORE-08 | Prompt al LLM incluye CVProfile real, ranking con sinónimos, preferencias ubicación/remoto, deal_breakers y la oferta | `assess_job()` serializa todo en el mensaje de usuario con XML tags |
| QA-04 | Tests exhaustivos de la heurística (decay, deal-breaker, ubicación, score_total, bandas); LLM mockeado | `tests/scoring/` con 5 módulos de test; `MagicMock` retorna `LLMJobAssessment` controlado |
</phase_requirements>

---

## Summary

Esta fase construye el núcleo del proyecto: la heurística híbrida que puntúa cada oferta de empleo contra el perfil real de Jaime. La arquitectura separa claramente responsabilidades: Python determinista (ranking decay, ubicación, score ponderado, bandas, deal-breaker override) e Instructor+Anthropic (detección de puesto, evaluación de skills/seniority, honestidad de reasons). Esta separación es la clave del diseño: hace la heurística testeable con mocks y auditables en producción.

La investigación confirma que todos los patrones necesarios ya están implementados en las fases anteriores del proyecto y pueden reutilizarse directamente: el patrón `build_instructor_client()` + `client.messages.create(response_model=...)` de `app/cv/llm_client.py`, el patrón de mock `MagicMock().messages.create.return_value = X` de `tests/conftest.py`, y el patrón de injectable dependency de `app/dedup/__init__.py`. No se necesitan dependencias nuevas: `instructor`, `anthropic`, `pyyaml`, y `pydantic` ya están instalados con versiones correctas.

Los dos puntos técnicos que requieren más cuidado son: (1) el sistema prompt del LLM para asegurar honestidad en `reasons_against` y `missing_requirements` sin inflar (la clave es un campo `razonamiento` explícito de chain-of-thought + instrucción explícita de severidad honesta), y (2) el deal-breaker override que debe aplicarse DESPUÉS del cálculo del score_total, no antes, para que el score refleje la calidad real de la oferta aunque sea descartada.

**Primary recommendation:** Construir de menor a mayor acoplamiento: `config/loader.py` primero (sin deps de scoring) → `schemas.LLMJobAssessment` → `scoring/ranking.py` + `scoring/location.py` (deterministas, testeable sin LLM) → `scoring/llm.py` (LLM layer) → `scoring/scorer.py` (orquestador) → tests exhaustivos.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ranking decay (encaje_puesto) | Python determinista | — | Función matemática pura; el LLM decide el rango, Python calcula el score |
| Evaluación ubicación (encaje_ubicacion) | Python determinista | — | Reglas booleanas sobre campos estructurados de Job + UserProfile |
| Score total ponderado | Python determinista | — | Suma con pesos; completamente auditado |
| Bandas de recommendation | Python determinista | — | Thresholds configurables sobre score_total |
| Deal-breaker override | Python determinista | LLM (detección textual) | Python aplica el override; LLM detecta deal-breakers en texto libre |
| Detección de puesto (rango) | LLM (Instructor) | — | Requiere matching semántico de títulos+sinónimos en texto libre |
| Evaluación skills (encaje_skills) | LLM (Instructor) | — | Requiere comprensión de CVProfile real vs requisitos de la oferta |
| Evaluación seniority (encaje_seniority) | LLM (Instructor) | — | Requiere inferencia de años/nivel pedido desde descripción |
| matched_skills / missing_requirements | LLM (Instructor) | — | Extracción de evidencia textual del LLM |
| reasons_for / reasons_against | LLM (Instructor) | — | Requiere juicio sobre fit holístico |
| Carga de UserProfile (profile.yaml) | Config layer | — | pyyaml → Pydantic v2 model_validate; validación de pesos |

---

## Standard Stack

### Core (ya instalado — sin nuevas deps necesarias)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| instructor | 1.15.1 | Structured output del LLM con Pydantic v2 | Patrón establecido en Fase 1 (cv/llm_client.py); evita parsing manual de JSON |
| anthropic | 0.104.0 | SDK para Claude (scoring LLM) | Única API LLM del proyecto; ANTHROPIC_API_KEY ya gestionada |
| pydantic | 2.13.4 | Validación de schemas + model_validator | Ya en uso en todos los módulos; pesos sum=1.0 via model_validator |
| pyyaml | 6.0.3 | Parseo de profile.yaml | Ya instalado; yaml.safe_load() + UserProfile.model_validate() |

[VERIFIED: pyproject.toml del repo + `uv.lock`]

### Verification

```bash
# Verificar versiones actuales (ya instaladas)
.venv/bin/python -c "import instructor; print(instructor.__version__)"  # 1.15.1
.venv/bin/python -c "import anthropic; print(anthropic.__version__)"    # 0.104.0
.venv/bin/python -c "import pydantic; print(pydantic.__version__)"      # 2.13.4
```

**No se necesita `uv add` en esta fase.** Todas las dependencias ya están en `pyproject.toml`.

[VERIFIED: verificado ejecutando los comandos en entorno local]

---

## Architecture Patterns

### System Architecture Diagram

```
[profile.yaml] ──────────────────────────────────────────────┐
                                                             ↓
[Job (deduplicado)] ──→  scoring/scorer.py::score_job()
[CVProfile (cacheado)] ──→   │
[UserProfile] ───────────────│
                             │
                             ├─── 1. location.py::evaluar_ubicacion(job, profile)
                             │         → (encaje_ubicacion: int, deal_breaker_loc: str|None)
                             │
                             ├─── 2. llm.py::assess_job(job, cv, profile, client)
                             │         → LLMJobAssessment
                             │              (rango_puesto, puesto_detectado,
                             │               encaje_skills, encaje_seniority,
                             │               matched_skills, missing_requirements,
                             │               reasons_for, reasons_against,
                             │               deal_breaker_hit_texto, deal_breaker_cual_texto)
                             │
                             ├─── 3. ranking.py::encaje_puesto_desde_rango(rango, ...)
                             │         → encaje_puesto: int
                             │
                             ├─── 4. score_total = weighted_sum(desglose, pesos)
                             │         = round(clamp(encaje_puesto*p.puesto + ...))
                             │
                             ├─── 5. recommendation = banda(score_total)
                             │         (≥80 strong_fit, ≥60 good_fit, ≥40 maybe, <40 skip)
                             │
                             └─── 6. deal_breaker_override()
                                       cualquier deal_breaker → recommendation = skip

                             → JobScore (schema completo)
```

### Recommended Project Structure

```
app/
├── config/
│   ├── __init__.py
│   └── loader.py          # load_user_profile(path) -> UserProfile
├── scoring/
│   ├── __init__.py        # public facade: score_job()
│   ├── ranking.py         # encaje_puesto_desde_rango() — decay lineal
│   ├── location.py        # evaluar_ubicacion() — reglas deterministas
│   ├── llm.py             # build_instructor_client() + assess_job()
│   └── scorer.py          # score_job() — orquesta todo
└── models/
    └── schemas.py         # + LLMJobAssessment (nuevo)

tests/
└── scoring/
    ├── __init__.py
    ├── test_loader.py      # config/loader.py
    ├── test_ranking.py     # decay, monotonía, suelo
    ├── test_location.py    # reglas ubicación, deal-breaker loc
    ├── test_llm.py         # assess_job con mock (verifica prompt, response_model)
    └── test_scorer.py      # score_job integración (LLM mockeado)
```

---

## Pattern 1: Profile Loader (pyyaml → Pydantic v2)

**What:** Cargar `data/profile.yaml` con `yaml.safe_load()` y validar con `UserProfile.model_validate()`.

**When to use:** Al arrancar el servicio o al cargar el perfil para scoring. Validar que pesos sumen 1.0 aquí — no en scorer.

**Example:**
```python
# app/config/loader.py
# Source: Pydantic docs + verificado localmente
from __future__ import annotations
import yaml
from pathlib import Path
from pydantic import ValidationError
from app.models.schemas import UserProfile

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

**Importante:** La validación de que `pesos` sumen 1.0 ya está en el schema `PesosScoring` (debe añadirse como `model_validator`). La suma `0.35 + 0.30 + 0.20 + 0.15` en floats da `0.9999999999999999` (no exactamente 1.0), por lo que se debe usar tolerancia: `abs(total - 1.0) < 1e-6`. [VERIFIED: probado localmente]

---

## Pattern 2: LLMJobAssessment Schema (nuevo en schemas.py)

**What:** El schema que el LLM devuelve. Solo campos que el LLM puede evaluar a partir de texto.

**When to use:** `response_model=LLMJobAssessment` en la llamada de instructor.

**Design decisions:**
- Incluir un campo `razonamiento` (str) PRIMERO para forzar chain-of-thought antes de los scores. [CITED: python.useinstructor.com/prompting — "models perform better when prompted to explain logic step-by-step"] `[VERIFIED: python.useinstructor.com/prompting]`
- `rango_puesto: Optional[int]` — None si la oferta no encaja en ningún puesto del ranking.
- `encaje_skills` y `encaje_seniority` con `Field(ge=0, le=100)` — Instructor reintentará si el LLM devuelve fuera de rango (max_retries=2). [VERIFIED: python.useinstructor.com/blog/2024/08/20/should-i-be-using-structured-outputs]
- Los campos booleanos/opcionales de deal-breaker son separados: `deal_breaker_hit_texto: bool` + `deal_breaker_cual_texto: Optional[str]`.

```python
# En app/models/schemas.py — añadir:
# Source: verificado con patrones de instructor docs
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
    encaje_skills: int = Field(
        ge=0, le=100,
        description="0-100: qué % de los requisitos de la oferta cumple el CVProfile real.",
    )
    encaje_seniority: int = Field(
        ge=0, le=100,
        description=(
            "0-100: qué tan bien encaja el nivel pedido con la experiencia real. "
            "Pedir bastante más de lo que tiene el candidato → score bajo (pero no 0 si es razonable)."
        ),
    )
    matched_skills: list[str] = Field(
        default_factory=list,
        description="Skills del CVProfile que la oferta pide explícitamente.",
    )
    missing_requirements: list[str] = Field(
        default_factory=list,
        description="Requisitos de la oferta que el candidato podría no cumplir. Sin inflar.",
    )
    reasons_for: list[str] = Field(
        default_factory=list,
        description="Razones concretas por las que la oferta encaja. Máx 3-4 puntos.",
    )
    reasons_against: list[str] = Field(
        default_factory=list,
        description="Razones concretas por las que NO encaja. HONESTO. Máx 3-4 puntos.",
    )
    deal_breaker_hit_texto: bool = Field(
        default=False,
        description="True si el texto de la oferta activa algún deal-breaker del perfil.",
    )
    deal_breaker_cual_texto: Optional[str] = Field(
        default=None,
        description="Cuál deal-breaker se activó (texto exacto o descripción). None si deal_breaker_hit_texto=False.",
    )
```

---

## Pattern 3: Decay Function (ranking.py)

**What:** Función lineal con paso y suelo configurables, monotónica, para `encaje_puesto`.

**Formula verificada aritméticamente:** `max(suelo, maximo - (rango - 1) * paso)`

| rango | resultado (paso=15, suelo=20, maximo=100) |
|-------|------------------------------------------|
| 1 | 100 |
| 2 | 85 |
| 3 | 70 |
| 4 | 55 |
| 5 | 40 |
| None (fuera de ranking) | 20 (suelo) |

[VERIFIED: probado localmente con Python]

```python
# app/scoring/ranking.py
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

    Todos los parámetros configurables; defaults cubren ranking de 4 puestos de Jaime
    con step 15: 100, 85, 70, 55 → nunca cae por debajo de suelo=20.
    """
    if rango is None:
        return suelo
    score = maximo - (rango - 1) * paso
    return max(suelo, score)
```

**Propiedad de monotonía:** `encaje_puesto(rango=N) >= encaje_puesto(rango=N+1)` para todo N. Esto debe verificarse en los tests: rango 1 > rango 2 > rango 3 > rango 4 > suelo.

---

## Pattern 4: Location Evaluator (location.py)

**What:** Reglas deterministas que mapean `(Job.remote, Job.location)` × `UserProfile` a `(encaje_ubicacion: int, deal_breaker_loc: str | None)`.

**City matching:** `unicodedata.normalize('NFD', city.lower().strip())` + strip combining chars (NFD strips accents). [VERIFIED: probado localmente — 'Barcelona'→'barcelona', 'Málaga'→'malaga', 'München'→'munchen']

**Mapa de casos:**

| Job.remote | location | perfil | encaje_ubicacion | deal_breaker_loc |
|------------|----------|--------|-----------------|-----------------|
| `remote` | any | `modalidad_ideal in (remote, hybrid, indiferente)` | 100 | None |
| `remote` | any | `modalidad_ideal = onsite` | 60 | None (flexible) |
| `hybrid` | ciudad aceptada | any | 80 | None |
| `hybrid` | ciudad NO aceptada + `dispuesto_a_reubicarse=False` | any | 10 | "Trabajo híbrido fuera de ciudades aceptadas: {city}" |
| `hybrid` | ciudad NO aceptada + `dispuesto_a_reubicarse=True` | any | 50 | None |
| `onsite` | ciudad aceptada | any | 90 | None |
| `onsite` | ciudad NO aceptada + `dispuesto_a_reubicarse=False` | any | 10 | "Presencial fuera de ciudades aceptadas: {city}" |
| `onsite` | ciudad NO aceptada + `dispuesto_a_reubicarse=True` | any | 40 | None |
| `unknown` | any | any | 50 | None |

**"Ciudad aceptada"** = normalización NFD de `Job.location` contiene cualquier ciudad de `ciudades_preferidas` + `acepta_onsite_solo_en` (usando `in` sobre substring normalizado, no igualdad exacta — para manejar "Barcelona, España" vs "Barcelona").

```python
# app/scoring/location.py  — ejemplo de la función pública
def evaluar_ubicacion(
    job: Job,
    profile: UserProfile,
) -> tuple[int, str | None]:
    """Devuelve (encaje_ubicacion, deal_breaker_descripcion|None).

    encaje_ubicacion: 0-100 determinista según Job.remote + location vs preferencias.
    deal_breaker_descripcion: str si la ubicación activa un deal-breaker, None si no.
    """
    ...
```

---

## Pattern 5: LLM Assessment (llm.py)

**What:** Factory injectable + llamada única que el LLM hace. Replica exactamente el patrón de `app/cv/llm_client.py`.

**System prompt design para tarea de JUICIO (vs extracción):** El sistema debe instruir explícitamente honestidad, no inflar `reasons_against`, y usar el chain-of-thought del campo `razonamiento`. La estructura del mensaje de usuario usa XML tags para separar el contexto.

**max_retries=2:** Suficiente para que Instructor reintente si el LLM devuelve un score fuera del rango ge=0, le=100 o un rango_puesto inválido. [VERIFIED: instructor.from_anthropic() respeta max_retries]

```python
# app/scoring/llm.py
import os
import instructor
from anthropic import Anthropic
from app.models.schemas import CVProfile, Job, LLMJobAssessment, UserProfile

def build_instructor_client() -> instructor.Instructor:
    """Factory del cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())

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
    ranking_text = _format_ranking(user_profile.ranking_puestos)
    cv_text = _format_cv(cv_profile)
    job_text = _format_job(job)
    deal_breakers_text = "\n".join(f"- {db}" for db in user_profile.deal_breakers)

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
        messages=[
            {
                "role": "user",
                "content": (
                    "<candidato>\n"
                    f"<cv>{cv_text}</cv>\n"
                    f"<ranking_puestos>{ranking_text}</ranking_puestos>\n"
                    "<preferencias_ubicacion>"
                    f"modalidad_ideal={user_profile.preferencia_remoto.modalidad_ideal.value}, "
                    f"acepta_onsite_en={user_profile.preferencia_remoto.acepta_onsite_solo_en}"
                    "</preferencias_ubicacion>\n"
                    f"<deal_breakers>\n{deal_breakers_text}\n</deal_breakers>\n"
                    "</candidato>\n"
                    f"<oferta>\n{job_text}\n</oferta>\n"
                    "Evalúa el encaje de esta oferta con el candidato."
                ),
            }
        ],
        response_model=LLMJobAssessment,
        max_retries=2,
    )
```

**Importante:** Las funciones helper `_format_ranking()`, `_format_cv()`, `_format_job()` deben serializar datos de forma legible para el LLM (no `model_dump_json()` crudo — el LLM funciona mejor con texto estructurado que con JSON anidado).

---

## Pattern 6: Scorer Orquestador (scorer.py)

**What:** `score_job()` ensambla el `JobScore` final combinando las 3 capas.

**Orden de operaciones crítico:**

```
1. evaluar_ubicacion(job, profile)         → (encaje_ubicacion, deal_breaker_loc)
2. assess_job(job, cv, profile, client)    → LLMJobAssessment
3. encaje_puesto_desde_rango(assessment.rango_puesto, ...)  → encaje_puesto
4. score_total = weighted_sum(desglose, profile.pesos)
5. recommendation = banda(score_total)
6. deal_breaker_override:                 ← DESPUÉS del cálculo de score_total
   si deal_breaker_loc OR assessment.deal_breaker_hit_texto:
       recommendation = skip
       deal_breaker_hit = True
       deal_breaker_cual = deal_breaker_loc or assessment.deal_breaker_cual_texto
```

**Por qué el override va AL FINAL:** El `score_total` refleja la calidad real de la oferta incluso cuando hay deal-breaker. Esto permite futuros análisis ("esta oferta habría sido un 85 si no fuera por la ubicación") y honestidad del sistema. El `recommendation=skip` es el filtro duro, no el score.

**score_total formula:**
```python
raw = (
    desglose.encaje_puesto * pesos.puesto
    + desglose.encaje_skills * pesos.skills
    + desglose.encaje_ubicacion * pesos.ubicacion
    + desglose.encaje_seniority * pesos.seniority
)
score_total = max(0, min(100, round(raw)))
```
[VERIFIED: probado localmente — 100*0.35 + 100*0.30 + 100*0.20 + 100*0.15 = 100.0 → round(100.0) = 100]

**Bandas de recommendation (defaults):**
```python
def _band(score: int) -> Recommendation:
    if score >= 80: return Recommendation.strong_fit
    if score >= 60: return Recommendation.good_fit
    if score >= 40: return Recommendation.maybe
    return Recommendation.skip
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM structured output con validación + retry | Parser manual de JSON del LLM | `instructor.from_anthropic()` con `response_model=LLMJobAssessment` | Instructor maneja tool_use de Anthropic, reintenta automáticamente si Pydantic falla, valida `ge=0, le=100` sin código extra |
| YAML → objeto validado | Parser manual de YAML + validación manual | `yaml.safe_load()` + `UserProfile.model_validate(data)` | Pydantic v2 da mensajes de error claros con localización del campo |
| Clamp de scores a 0-100 | `if score < 0: score = 0; if score > 100: score = 100` | `max(0, min(100, round(raw)))` | One-liner idiomático; `Field(ge=0, le=100)` en Pydantic cubre el schema output |
| Accent-insensitive city matching | Regex complejo o mapping manual | `unicodedata.normalize('NFD', city.lower())` + `''.join(c for c in nfd if not unicodedata.combining(c))` | NFD descompone caracteres precompuestos y eliminar combining chars da string ASCII normalizado [VERIFIED: probado localmente] |
| Mock de instructor en tests | Crear un stub completo de la superficie instructor | `MagicMock()` con `.messages.create.return_value = LLMJobAssessment(...)` | Patrón ya establecido en tests/conftest.py para CVProfile; funciona igual para LLMJobAssessment |

**Key insight:** La separación determinista/LLM permite testear el 80% de la heurística (toda la parte determinista) sin tocar la red ni el LLM real. Solo `assess_job()` necesita mock en tests.

---

## Common Pitfalls

### Pitfall 1: LLM devuelve rango_puesto inválido (e.g., 0 o fuera del rango del ranking)
**What goes wrong:** El LLM indexa desde 0 o inventa un rango 5 cuando solo hay 4 puestos.
**Why it happens:** La instrucción en el prompt no es lo suficientemente específica sobre el rango válido.
**How to avoid:** Incluir explícitamente en el campo `description` de `rango_puesto` el rango válido: "Posición en el ranking (1-based, entre 1 y N donde N es el número de puestos del ranking)". Añadir `@field_validator('rango_puesto')` en `LLMJobAssessment` que valide `1 <= rango <= len(ranking)` cuando no es None, y dejar que Instructor reintente. [VERIFIED: instructor auto-retry on ValidationError]
**Warning signs:** `rango_puesto=0` en los logs, `encaje_puesto` calculado como más alto que el máximo.

### Pitfall 2: Deal-breaker override no aplicado (recommendation != skip aunque deal_breaker_hit=True)
**What goes wrong:** El scorer calcula recommendation por bandas y luego no sobreescribe.
**Why it happens:** La condición de override se olvida o se aplica antes del cálculo de score_total.
**How to avoid:** El override es el ÚLTIMO paso del scorer, siempre. Test explícito: `assert score.recommendation == Recommendation.skip` cuando `deal_breaker_hit=True` independientemente de los sub-scores.
**Warning signs:** `deal_breaker_hit=True` con `recommendation != skip` en logs.

### Pitfall 3: Float precision en validación pesos sum=1.0
**What goes wrong:** `0.35 + 0.30 + 0.20 + 0.15 == 1.0` devuelve `False` en Python.
**Why it happens:** Aritmética de punto flotante IEEE 754: `0.35 + 0.30 + 0.20 + 0.15 = 0.9999999999999999`.
**How to avoid:** Usar `abs(total - 1.0) < 1e-6` en el `model_validator`. [VERIFIED: probado localmente]
**Warning signs:** ValidationError "pesos no suman 1.0" en profile.yaml válidos.

### Pitfall 4: LLM inflando scores (honesty drift)
**What goes wrong:** El LLM devuelve `encaje_skills=90` para una oferta donde el CVProfile no tiene las skills principales pedidas.
**Why it happens:** Los LLMs tienen sesgo hacia resultados positivos/optimistas.
**How to avoid:** (a) Campo `razonamiento` primero en `LLMJobAssessment` fuerza al LLM a articular el reasoning antes de dar scores. (b) System prompt con instrucción explícita: "NO infles los reasons_for" y "Si hay requisitos que el candidato claramente no cumple, ponlos en missing_requirements". (c) Test de smoke con una oferta que pida skills completamente distintas → mock LLM devuelve scores bajos y el test verifica que se reflejan en JobScore.
**Warning signs:** `reasons_against` siempre vacío, `missing_requirements` siempre vacío.

### Pitfall 5: Responsabilidad leakage entre capas
**What goes wrong:** El scorer llama al LLM para calcular `encaje_ubicacion` o `score_total`, o le pide que devuelva una `recommendation` directamente.
**Why it happens:** Es tentador pedirle "todo" al LLM para simplificar el scorer.
**How to avoid:** `LLMJobAssessment` NO tiene campos `encaje_ubicacion`, `score_total`, ni `recommendation` — así el planner lo tiene imposible de añadir accidentalmente. El scorer usa SIEMPRE los valores de `LLMJobAssessment` solo para los 4 campos que le corresponden al LLM.
**Warning signs:** Ver `score_total` o `encaje_ubicacion` en el schema de `LLMJobAssessment`.

### Pitfall 6: City matching por igualdad exacta falla con sufijos
**What goes wrong:** `Job.location = "Barcelona, España"` no matchea con `"Barcelona"` en `ciudades_preferidas`.
**Why it happens:** Las APIs de empleo devuelven la ciudad con país o región.
**How to avoid:** Usar substring match normalizado: `any(norm(c) in norm(job.location) for c in ciudades_aceptadas)`. [VERIFIED: verificado con casos reales de profile.yaml y formato de Arbeitnow]
**Warning signs:** `encaje_ubicacion=10` para ofertas en Barcelona con `Job.location="Barcelona, Spain"`.

### Pitfall 7: Import de scoring sin mock leaking model download
**What goes wrong:** `from app.scoring import score_job` en tests descarga BGE-M3 transitivamente.
**Why it happens:** Si `app/scoring/__init__.py` importa transitivamente `app/dedup` (que tiene BgeM3Embedder).
**How to avoid:** `app/scoring/` NO debe importar `app/dedup`. El scorer recibe `Job`s ya deduplicados; no tiene responsabilidad de deduplicar. Los imports en `scoring/scorer.py` solo importan los submódulos de scoring.
**Warning signs:** Tests de scoring tardan 30+ segundos en la primera ejecución.

---

## Code Examples

### Profile loader completo con manejo de errores

```python
# Source: pydantic.dev/docs/validation/latest/examples/files (verificado)
import yaml
from pathlib import Path
from pydantic import ValidationError
from app.models.schemas import UserProfile

def load_user_profile(path: str = "data/profile.yaml") -> UserProfile:
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

### Pesos sum=1.0 con tolerancia float

```python
# Source: verificado localmente (0.35+0.30+0.20+0.15 != 1.0 en floats Python)
from pydantic import model_validator
from typing_extensions import Self

class PesosScoring(BaseModel):
    puesto: float = 0.35
    skills: float = 0.30
    ubicacion: float = 0.20
    seniority: float = 0.15

    @model_validator(mode='after')
    def check_sum(self) -> Self:
        total = self.puesto + self.skills + self.ubicacion + self.seniority
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Los pesos deben sumar 1.0, suman {total:.6f}")
        return self
```

### Mock del LLM en tests (replicar patrón de conftest.py)

```python
# Source: patrón establecido en tests/conftest.py (mock_llm_client)
from unittest.mock import MagicMock
from app.models.schemas import LLMJobAssessment

def make_mock_scoring_client(assessment: LLMJobAssessment) -> MagicMock:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = assessment
    return mock_client

# En tests:
assessment = LLMJobAssessment(
    razonamiento="El candidato tiene Python y LLMs; la oferta pide exactamente eso.",
    puesto_detectado="Ingeniero de IA / AI Engineer",
    rango_puesto=1,
    encaje_skills=85,
    encaje_seniority=70,
    matched_skills=["Python", "LLMs"],
    missing_requirements=[],
    reasons_for=["Match en skills principales"],
    reasons_against=["Requiere experiencia en Kubernetes (no en CV)"],
    deal_breaker_hit_texto=False,
    deal_breaker_cual_texto=None,
)
client = make_mock_scoring_client(assessment)
score = score_job(job, cv_profile, user_profile, client=client)
assert score.recommendation == Recommendation.strong_fit
```

### City normalization

```python
# Source: verificado localmente con unicodedata
import unicodedata

def _normalize_city(name: str) -> str:
    """Normaliza ciudad a ASCII lowercase para comparación. NFD + strip combining chars."""
    nfd = unicodedata.normalize('NFD', name.lower().strip())
    return ''.join(c for c in nfd if not unicodedata.combining(c))

def _ciudad_aceptada(location: str | None, ciudades: list[str]) -> bool:
    """True si location (normalizada) contiene alguna ciudad aceptada (normalizada)."""
    if not location:
        return False
    loc_norm = _normalize_city(location)
    return any(_normalize_city(c) in loc_norm for c in ciudades)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Parsear JSON del LLM manualmente | `instructor.from_anthropic()` con `response_model=` | instructor 1.0+ | Validación automática + retry; no código de parsing |
| Pydantic v1 `__validators__` | `@model_validator(mode='after')` / `@field_validator` | Pydantic v2 | API limpia, modo before/after explícito |
| `BaseModel(**data)` para validar | `BaseModel.model_validate(data)` | Pydantic v2 | Método explícito preferido para validar desde dict |

**Deprecated/outdated:**
- `instructor.patch(client)`: la API antigua de Instructor. Ahora se usa `instructor.from_anthropic(Anthropic())`. [VERIFIED: código existente en app/cv/llm_client.py ya usa el nuevo patrón]
- `@validator` de Pydantic v1: reemplazado por `@field_validator` + `@model_validator`. [VERIFIED: schemas.py ya usa Pydantic v2 Field]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | El modelo `claude-sonnet-4-6` (por nombre exacto) está disponible via Anthropic API con la clave de Jaime | Standard Stack / Pattern 5 (llm.py) | Si el nombre exacto difiere, la llamada LLM falla; mitigado porque el modelo es configurable via `ANTHROPIC_MODEL_SCORING` env var |
| A2 | Los valores de bandas de recommendation (≥80 strong_fit, ≥60 good_fit, ≥40 maybe, <40 skip) son adecuados para el perfil de Jaime | Pattern 6 (scorer) | Podría generar demasiados "strong_fit" o "skip"; calibrable post-uso sin tocar código si están como constantes configurables |
| A3 | `max_retries=2` es suficiente para que Instructor resuelva scores fuera de rango [0, 100] | Pattern 5 (llm.py) | En casos extremos el LLM podría fallar 3 veces; se propaga como excepción que el Fase 4 debe capturar por oferta |

---

## Open Questions (RESOLVED)

1. **¿Los parámetros de decay y bandas deben vivir en profile.yaml o como defaults en código?** — RESOLVED
   - Lo que sabemos: CONTEXT.md dice "Parámetros configurables (defaults en código; opcionalmente leíbles de profile.yaml)"
   - Lo que está claro: Los defaults en código son suficientes para esta fase. Profile.yaml ya tiene los pesos. Añadir paso/suelo/bandas a profile.yaml añadiría schema pero también flexibilidad real.
   - Recomendación: Defaults en código para esta fase (simplifica el schema de UserProfile). Si el usuario quiere ajustar post-uso, se añade a profile.yaml en v2.
   - **Resolution:** Defaults en código (constantes configurables por argumento) en esta fase; los pesos siguen viniendo de profile.yaml. Ajuste vía profile.yaml diferido a v2.

2. **¿Cómo serializar CVProfile al LLM?** — RESOLVED
   - Lo que sabemos: `cv_profile.model_dump_json()` produce JSON compacto pero el LLM puede leerlo.
   - Lo que está claro: Texto estructurado legible (markdown-style) produce mejores resultados de juicio que JSON anidado.
   - Recomendación: Helper `_format_cv()` que genera texto legible — más natural para evaluación.
   - **Resolution:** Helper `_format_cv()` que genera texto estructurado legible (no JSON crudo) para el prompt de juicio del LLM.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| instructor | assess_job() | ✓ | 1.15.1 | — |
| anthropic | assess_job() | ✓ | 0.104.0 | — |
| pydantic | todos los schemas | ✓ | 2.13.4 | — |
| pyyaml | load_user_profile() | ✓ | 6.0.3 | — |
| ANTHROPIC_API_KEY | assess_job() real | Verificar en .env | — | Tests: LLM siempre mockeado |
| pytest | tests/scoring/ | ✓ | 9.0.3 | — |

**Missing dependencies with no fallback:** Ninguna — todas las deps están instaladas.

**Missing dependencies with fallback:**
- `ANTHROPIC_API_KEY`: no bloquea tests (LLM mockeado). Bloquea llamadas reales a /jobs/score (Fase 4). Ya en `.env.example`.

[VERIFIED: pyproject.toml + verificado ejecutando tests (87 passed)]

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/scoring/ -q` |
| Full suite command | `pytest tests/ -q` |

[VERIFIED: 87 tests pasan actualmente con `pytest tests/ -q`]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCORE-01 | `score_job()` devuelve `JobScore` completo con todos los campos | integration | `pytest tests/scoring/test_scorer.py -q` | ❌ Wave 0 |
| SCORE-02 | Decay: rango 1 → max; monotónico; rango None → suelo > 0 | unit | `pytest tests/scoring/test_ranking.py -q` | ❌ Wave 0 |
| SCORE-03 | Remote → alto; onsite ciudad aceptada → alto; onsite fuera → muy bajo + deal-breaker | unit | `pytest tests/scoring/test_location.py -q` | ❌ Wave 0 |
| SCORE-04 | encaje_seniority bajo + missing_requirements desde mock LLM → se refleja en JobScore sin skip | integration | `pytest tests/scoring/test_scorer.py::test_seniority_bajo_no_descarta -q` | ❌ Wave 0 |
| SCORE-05 | deal_breaker (loc o texto) → recommendation=skip aunque sub-scores sean altos | integration | `pytest tests/scoring/test_scorer.py::test_deal_breaker_fuerza_skip -q` | ❌ Wave 0 |
| SCORE-06 | score_total ponderado exacto dados 4 sub-scores + pesos conocidos | unit | `pytest tests/scoring/test_scorer.py::test_score_total_ponderado -q` | ❌ Wave 0 |
| SCORE-07 | reasons_against y missing_requirements del mock se propagan sin modificar | integration | `pytest tests/scoring/test_scorer.py::test_honestidad_propagada -q` | ❌ Wave 0 |
| SCORE-08 | assert_called_once + kwargs verifican CVProfile, ranking, prefs, deal_breakers, oferta en el prompt | unit | `pytest tests/scoring/test_llm.py::test_assess_job_pasa_contexto -q` | ❌ Wave 0 |
| QA-04 | Suite completa de heurística (cobertura de todos los casos del scoring) | unit+integration | `pytest tests/scoring/ -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/scoring/ -q`
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** `pytest tests/ -q` (87 tests existentes + todos los de scoring) green antes de `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/scoring/__init__.py` — paquete de tests de scoring
- [ ] `tests/scoring/test_loader.py` — load_user_profile: ruta válida, inválida, pesos inválidos
- [ ] `tests/scoring/test_ranking.py` — decay, monotonía, suelo, rango None
- [ ] `tests/scoring/test_location.py` — 6 casos de ubicación + deal-breaker location
- [ ] `tests/scoring/test_llm.py` — assess_job: verifica response_model=LLMJobAssessment, model env, max_retries, contexto en prompt
- [ ] `tests/scoring/test_scorer.py` — score_job integración con LLM mockeado: deal-breaker, bandas, score_total exacto, seniority no descarta, honestidad propagada

---

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Pydantic v2 `Field(ge=0, le=100)` en LLMJobAssessment + model_validator en PesosScoring |
| V6 Cryptography | no | — |

### Known Threat Patterns for {LLM scoring stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via job description | Tampering | El texto de la oferta va en XML tags en el mensaje de usuario (no en el system prompt). El system prompt es string fijo sin f-string interpolation de contenido externo [VERIFIED: patrón de app/cv/llm_client.py] |
| API key leakage | Information Disclosure | ANTHROPIC_API_KEY solo desde env; el SDK la lee directamente; nunca en código o logs |
| LLM-returned out-of-range scores | Tampering | `Field(ge=0, le=100)` en LLMJobAssessment + Instructor max_retries=2; post-processing clamp `max(0, min(100, ...))` |

---

## Sources

### Primary (HIGH confidence)
- `app/cv/llm_client.py` — patrón injectable factory + instructor.from_anthropic() verificado en codebase
- `app/models/schemas.py` — schemas existentes (JobScore, Desglose, UserProfile, PesosScoring, CVProfile, Job) verificados
- `data/profile.yaml` — perfil real de Jaime con ranking, pesos, deal_breakers verificados
- `tests/conftest.py` — patrón MagicMock para LLM verificado
- `pyproject.toml` — versiones de dependencias verificadas

### Secondary (MEDIUM confidence)
- [python.useinstructor.com/prompting](https://python.useinstructor.com/prompting) — chain-of-thought field mejora calidad de juicio
- [python.useinstructor.com/blog/2024/10/17/building-a-pairwise-llm-judge-with-instructor-and-pydantic](https://python.useinstructor.com/blog/2024/10/17/building-a-pairwise-llm-judge-with-instructor-and-pydantic) — LLM judge pattern con system prompt + structured Judgment
- [pydantic.dev/docs/validation/latest/examples/files](https://pydantic.dev/docs/validation/latest/examples/files) — yaml.safe_load() + model_validate()
- [python.useinstructor.com/blog/2024/08/20/should-i-be-using-structured-outputs](https://python.useinstructor.com/blog/2024/08/20/should-i-be-using-structured-outputs) — Instructor auto-retry on field_validator failure

### Tertiary (LOW confidence — verificar en uso real)
- Nombre exacto del modelo `claude-sonnet-4-6` para scoring — se asume disponible; configurable via env var [ASSUMED - A1]

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — todas las deps verificadas en pyproject.toml + entorno local
- Architecture: HIGH — basada en código existente del proyecto (Fases 1 y 2) y patrones Instructor verificados
- Decay formula: HIGH — verificada aritméticamente con Python
- City matching: HIGH — verificado con unicodedata localmente
- Score formula: HIGH — verificada aritméticamente con Python
- Float precision pitfall (pesos): HIGH — verificado localmente (0.35+0.30+0.20+0.15 != 1.0)
- LLM model name: LOW — A1 en Assumptions Log; mitigado con env var configurable
- Pitfalls: MEDIUM — basados en patrones conocidos de sistemas híbridos LLM+determinista

**Research date:** 2026-05-22
**Valid until:** 2026-06-22 (stable stack — instructor, anthropic, pydantic raramente cambian en 30 días)
