"""Cache-first CV resolution logic — NO Streamlit dependency.

This module contains the pure-Python helper resolve_cv_profile() that implements
the D-12 / SC1 cache-first contract:

  1. Compute sha256 hash of PDF bytes.
  2. Check the on-disk cache (load_cached_profile).
  3. Cache HIT  → return (profile, True)  — parse_cv is NOT called.
  4. Cache MISS → call parse_cv once, persist via save_cached_profile,
                  return (profile, False).

Keeping this logic separate from ui/pages/cv.py makes SC1 (no re-parse on cache
hit) unit-testable without a Streamlit runtime.
"""
from __future__ import annotations

from app.cv.cache import load_cached_profile, pdf_hash, save_cached_profile
from app.cv.parser import parse_cv
from app.models.schemas import CVProfile


def resolve_cv_profile(pdf_bytes: bytes, *, client=None) -> tuple[CVProfile, bool]:
    """Cache-first CV resolution.

    Returns (profile, was_cached):
      - was_cached=True  → loaded from disk cache (no LLM call).
      - was_cached=False → freshly parsed via parse_cv + saved to cache.

    Satisfies SC1: uploading the same PDF a second time returns the cached
    profile without calling parse_cv (same bytes → same sha256 hash → cache hit).

    Args:
        pdf_bytes: Raw bytes of the uploaded PDF.
        client:    Optional instructor client override (passed through to parse_cv).

    Returns:
        Tuple of (CVProfile, was_cached: bool).
    """
    h = pdf_hash(pdf_bytes)
    cached = load_cached_profile(h)
    if cached is not None:
        return cached, True
    profile = parse_cv(pdf_bytes, client=client)
    save_cached_profile(h, profile)
    return profile, False
