"""
Módulo LLM para extracción estructurada de CVs.

Expone:
- build_instructor_client(): fábrica del cliente instructor (seam de inyección para tests).
- extract_cv_profile(raw_text, client): llama al LLM con response_model=CVProfile y devuelve
  un CVProfile tipado.

Mitigaciones de seguridad (T-01-06, T-01-07, T-01-08, WR-03):
- El texto del CV va SOLO en el mensaje de usuario; el system prompt es una cadena fija
  sin interpolación de f-string con contenido del CV (anti prompt-injection).
- El texto del CV se escapa con html.escape y se delimita con etiquetas <cv>...</cv>
  para evitar que secuencias tipo '</cv><system>...' alteren la estructura del prompt
  (WR-03: consistente con la estrategia de _escape_for_prompt en scoring/llm.py).
- La clave de API la lee el SDK de Anthropic del entorno; nunca se referencia en este fichero.
- El modelo se configura via ANTHROPIC_MODEL_CV con default verificado claude-haiku-4-5-20251001.
"""
from __future__ import annotations

import html
import os

import instructor
from anthropic import Anthropic

from app.models.schemas import CVProfile
from app.obs.tracing import trace_llm


def _escape_cv_text(text: str) -> str:
    """Escapa caracteres XML significativos en el texto del CV para evitar prompt injection.

    Aplica la misma estrategia que _escape_for_prompt en scoring/llm.py (WR-03):
    escapa < > & para que texto del CV que contenga '</cv>' no pueda alterar
    la separación estructural del prompt. El LLM recibe &lt; &gt; &amp; como dato,
    no como etiquetas de estructura.
    """
    return html.escape(text, quote=False)


def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())


def extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile:
    """Llama al LLM para extraer un CVProfile estructurado del texto del CV.

    Args:
        raw_text: Texto plano extraído del PDF del CV.
        client:   Cliente instructor inyectado (real o mock). Debe exponer
                  .messages.create(model, max_tokens, system, messages,
                  response_model, max_retries).

    Returns:
        CVProfile validado por Pydantic con los datos del CV.
    """
    model = os.getenv("ANTHROPIC_MODEL_CV", "claude-haiku-4-5-20251001")
    with trace_llm("extract_cv_profile", model=model):
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
                    "content": (
                        "Extrae el CVProfile del siguiente CV:\n\n"
                        f"<cv>\n{_escape_cv_text(raw_text)}\n</cv>"
                    ),
                }
            ],
            response_model=CVProfile,
            max_retries=2,
        )
