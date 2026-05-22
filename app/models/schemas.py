"""
Schemas Pydantic v2 del Agregador de ofertas.
FASE 1 del proyecto: SOLO la forma de los datos (sin lógica todavía).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ====================== Enums ======================
class ModalidadRemoto(str, Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    indiferente = "indiferente"


class RemoteJob(str, Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unknown = "unknown"


class Recommendation(str, Enum):
    strong_fit = "strong_fit"
    good_fit = "good_fit"
    maybe = "maybe"
    skip = "skip"


# ============== UserProfile (profile.yaml) ==============
class Idioma(BaseModel):
    idioma: str
    nivel: str


class DatosPersonales(BaseModel):
    nombre: str
    email: str
    telefono: Optional[str] = None
    ubicacion_actual: str
    derecho_a_trabajar_en: list[str] = Field(default_factory=list)  # ej. ["UE", "España"]
    idiomas: list[Idioma] = Field(default_factory=list)


class PreferenciasUbicacion(BaseModel):
    ciudades_preferidas: list[str] = Field(default_factory=list)
    pais: str
    dispuesto_a_reubicarse: bool = False


class PreferenciaRemoto(BaseModel):
    modalidad_ideal: ModalidadRemoto = ModalidadRemoto.indiferente
    acepta_onsite_solo_en: list[str] = Field(default_factory=list)


class PuestoRanking(BaseModel):
    titulo: str
    sinonimos: list[str] = Field(default_factory=list)


class Expectativas(BaseModel):
    salario_minimo: Optional[int] = None
    tipo_contrato_preferido: Optional[str] = None


class PesosScoring(BaseModel):
    """Pesos del score_total. Deben sumar 1.0 (se valida al cargar)."""
    puesto: float = 0.35
    skills: float = 0.30
    ubicacion: float = 0.20
    seniority: float = 0.15

    @model_validator(mode="after")
    def check_sum(self) -> "PesosScoring":
        total = self.puesto + self.skills + self.ubicacion + self.seniority
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Los pesos deben sumar 1.0, suman {total:.6f}")
        return self


class UserProfile(BaseModel):
    datos_personales: DatosPersonales
    preferencias_ubicacion: PreferenciasUbicacion
    preferencia_remoto: PreferenciaRemoto
    # ORDENADO: índice 0 = máxima prioridad (puesto nº1 del ranking)
    ranking_puestos: list[PuestoRanking]
    expectativas: Optional[Expectativas] = None
    deal_breakers: list[str] = Field(default_factory=list)
    pesos: PesosScoring = Field(default_factory=PesosScoring)
    dedup_umbral: float = 0.85  # similitud coseno para considerar duplicado semántico


# ============== CVProfile (parseado del PDF) ==============
class Experiencia(BaseModel):
    empresa: str
    rol: str
    duracion: Optional[str] = None
    tecnologias: list[str] = Field(default_factory=list)
    logros: list[str] = Field(default_factory=list)


class Formacion(BaseModel):
    titulo: str
    institucion: Optional[str] = None
    anio: Optional[int] = None


class CVProfile(BaseModel):
    experiencia: list[Experiencia] = Field(default_factory=list)
    skills_tecnicas: list[str] = Field(default_factory=list)
    formacion: list[Formacion] = Field(default_factory=list)
    anios_experiencia_total: Optional[float] = None  # estimado
    dominios: list[str] = Field(default_factory=list)  # ej. ["finanzas", "regulación"]


# ============== Job (oferta normalizada) ==============
class Salary(BaseModel):
    min: Optional[int] = None
    max: Optional[int] = None
    moneda: Optional[str] = None
    periodo: Optional[str] = None  # ej. "anual", "mensual"


class Job(BaseModel):
    id: str  # hash estable: empresa + título normalizado + ubicación
    title: str
    company: str
    location: Optional[str] = None
    remote: RemoteJob = RemoteJob.unknown
    description: str = ""
    salary: Optional[Salary] = None
    url: Optional[str] = None
    source: str
    posted_at: Optional[str] = None  # ISO 8601
    raw: dict = Field(default_factory=dict)  # payload original de la fuente
    urls_alternativas: list[str] = Field(default_factory=list)  # de duplicados fusionados


# ============== JobScore (salida del scoring) ==============
class Desglose(BaseModel):
    encaje_puesto: int = Field(ge=0, le=100)
    encaje_skills: int = Field(ge=0, le=100)
    encaje_ubicacion: int = Field(ge=0, le=100)
    encaje_seniority: int = Field(ge=0, le=100)


class JobScore(BaseModel):
    score_total: int = Field(ge=0, le=100)  # combinación ponderada (determinista)
    recommendation: Recommendation
    desglose: Desglose
    puesto_detectado: str  # entrada del ranking, o "fuera de ranking"
    rango_puesto: Optional[int] = None  # 1 = top del ranking; None si no encaja ninguno
    reasons_for: list[str] = Field(default_factory=list)
    reasons_against: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    deal_breaker_hit: bool = False
    deal_breaker_cual: Optional[str] = None


class LLMJobAssessment(BaseModel):
    """Lo que el LLM evalúa. Solo campos que requieren comprensión de texto libre."""

    # razonamiento va PRIMERO para forzar chain-of-thought antes de los scores (SCORE-07)
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
        ge=1,
        description="Posición en el ranking (1=top, 1-based). None si 'fuera de ranking'.",
    )
    encaje_skills: int = Field(
        ge=0,
        le=100,
        description="0-100: % de requisitos de la oferta que cumple el CVProfile real.",
    )
    encaje_seniority: int = Field(
        ge=0,
        le=100,
        description=(
            "0-100: nivel pedido vs experiencia real. "
            "Pedir mucho más → bajo (pero no 0 si es razonable)."
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
        description="Razones concretas de encaje. Máx 3-4.",
    )
    reasons_against: list[str] = Field(
        default_factory=list,
        description="Razones concretas de NO encaje. HONESTO. Máx 3-4.",
    )
    deal_breaker_hit_texto: bool = Field(
        default=False,
        description="True si el texto de la oferta activa algún deal-breaker del perfil.",
    )
    deal_breaker_cual_texto: Optional[str] = Field(
        default=None,
        description=(
            "Cuál deal-breaker se activó. None si deal_breaker_hit_texto=False."
        ),
    )

    @model_validator(mode="after")
    def check_deal_breaker_consistency(self) -> "LLMJobAssessment":
        """WR-01: coerce deal_breaker_cual_texto a None cuando deal_breaker_hit_texto=False.

        Evita el estado contradictorio deal_breaker_hit_texto=False + deal_breaker_cual_texto
        no-None, que puede confundir a consumidores downstream (scorer.py, n8n).
        """
        if not self.deal_breaker_hit_texto:
            self.deal_breaker_cual_texto = None
        return self


class ScoredJob(BaseModel):
    """Lo que devuelve /jobs/process: la oferta + su puntuación."""
    job: Job
    score: JobScore
