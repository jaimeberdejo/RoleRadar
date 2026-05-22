"""
Tests unitarios para app/cv/extractor.py.

Verifica que:
- extract_text_from_pdf devuelve una cadena no vacía para un PDF válido
- el texto extraído contiene contenido conocido del fixture
- se lanza ValueError con "capa de texto" en PDFs sin capa de texto
"""
from __future__ import annotations

import pymupdf
import pytest

from app.cv.extractor import extract_text_from_pdf


def test_extract_text_returns_string(sample_pdf_bytes: bytes) -> None:
    """extract_text_from_pdf devuelve una cadena no vacía para un PDF con texto."""
    text = extract_text_from_pdf(sample_pdf_bytes)
    assert isinstance(text, str)
    assert len(text) > 0


def test_extract_text_contains_known_content(sample_pdf_bytes: bytes) -> None:
    """El texto extraído contiene literales conocidos del fixture del CV."""
    text = extract_text_from_pdf(sample_pdf_bytes)
    assert "AI Engineer" in text


def test_extract_text_raises_on_empty_pdf() -> None:
    """Un PDF sin capa de texto lanza ValueError con mensaje 'capa de texto'."""
    doc = pymupdf.open()
    doc.new_page()  # página en blanco, sin capa de texto
    empty_pdf = doc.tobytes()
    with pytest.raises(ValueError, match="capa de texto"):
        extract_text_from_pdf(empty_pdf)
