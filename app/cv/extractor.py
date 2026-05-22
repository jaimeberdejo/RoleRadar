"""
Extractor de texto plano desde PDFs usando pymupdf.

Módulo hoja sin dependencias de LLM: sólo I/O de fichero/bytes.
El parser (parser.py) lo usa como primer paso antes de llamar al LLM.
"""
from __future__ import annotations

import pymupdf


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extrae todo el texto de un PDF multi-página, en orden de lectura.

    Args:
        pdf_bytes: Contenido del PDF en memoria (bytes crudos).

    Returns:
        Texto completo del PDF, páginas separadas por doble salto de línea.

    Raises:
        ValueError: Si los bytes no son un PDF válido, están vacíos, o el PDF
            no contiene capa de texto extraíble (ej. PDF escaneado sólo imagen
            — OCR no está soportado en v1).
    """
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            pages_text = [page.get_text() for page in doc]
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise ValueError(
            f"No se pudo abrir el PDF: {exc}. "
            "Comprueba que el fichero es un PDF válido y no está vacío."
        ) from exc
    text = "\n\n".join(pages_text).strip()
    if not text:
        raise ValueError(
            "El PDF no contiene capa de texto extraíble. "
            "PDFs escaneados (solo imagen) no están soportados en v1."
        )
    return text
