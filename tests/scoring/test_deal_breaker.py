"""
Tests for app/scoring/deal_breaker.py — deterministic keyword/substring matcher.

Covers:
- Basic hit and no-hit cases
- Case-insensitive matching
- Accent/NFD normalization (e.g., "exigé" matches "exige")
- Empty job_text → no hit
- Empty deal_breakers list → no hit
- Multiple hits → joined with "; "
- Import does NOT load torch or heavy deps (no app.dedup imports)
"""
from __future__ import annotations

import pytest

from app.scoring.deal_breaker import DealBreakerResult, detectar_deal_breaker


# ---------------------------------------------------------------------------
# Basic functionality
# ---------------------------------------------------------------------------


class TestDetectarDealBreaker:
    def test_hit_substring_present(self) -> None:
        """Deal-breaker substring found in job text → hit=True."""
        result = detectar_deal_breaker(
            "Se exige 5+ años de experiencia en Python",
            ["exige 5+ años de experiencia"],
        )
        assert result.hit is True
        assert result.cual is not None
        assert "exige 5+ años de experiencia" in result.cual

    def test_no_hit_substring_absent(self) -> None:
        """Deal-breaker not in job text → hit=False, cual=None."""
        result = detectar_deal_breaker(
            "Great remote Python job with flexible hours",
            ["exige 5+ años de experiencia"],
        )
        assert result.hit is False
        assert result.cual is None

    def test_case_insensitive_match(self) -> None:
        """Match is case-insensitive via casefold."""
        result = detectar_deal_breaker(
            "PRESENCIAL FUERA DE BARCELONA REQUERIDO",
            ["presencial fuera de Barcelona"],
        )
        assert result.hit is True
        assert result.cual is not None

    def test_case_insensitive_mixed(self) -> None:
        """Job text with mixed case, deal_breaker lowercase."""
        result = detectar_deal_breaker(
            "Presencial Fuera de Barcelona",
            ["presencial fuera de barcelona"],
        )
        assert result.hit is True

    def test_english_text_no_match_for_spanish_dealbreaker(self) -> None:
        """English 'We require 5+ years...' does NOT match Spanish 'exige 5+ años'."""
        result = detectar_deal_breaker(
            "We require 5+ years of experience presencial",
            ["exige 5+ años de experiencia"],
        )
        assert result.hit is False
        assert result.cual is None

    # ---------------------------------------------------------------------------
    # Guard cases
    # ---------------------------------------------------------------------------

    def test_empty_job_text_no_hit(self) -> None:
        """Empty job text → no hit regardless of deal_breakers."""
        result = detectar_deal_breaker("", ["exige 5+ años de experiencia"])
        assert result.hit is False
        assert result.cual is None

    def test_empty_deal_breakers_no_hit(self) -> None:
        """Empty deal_breakers list → no hit regardless of job text."""
        result = detectar_deal_breaker("any text with lots of content here", [])
        assert result.hit is False
        assert result.cual is None

    def test_whitespace_only_job_text_no_hit(self) -> None:
        """Whitespace-only job text normalizes to empty → no hit."""
        result = detectar_deal_breaker("   ", ["exige 5+ años"])
        assert result.hit is False
        assert result.cual is None

    # ---------------------------------------------------------------------------
    # Multiple hits
    # ---------------------------------------------------------------------------

    def test_multiple_hits_joined_with_semicolon(self) -> None:
        """When multiple deal_breakers fire, cual joins them with '; '."""
        result = detectar_deal_breaker(
            "se exige 5+ años de experiencia y es presencial fuera de barcelona",
            ["exige 5+ años de experiencia", "presencial fuera de barcelona"],
        )
        assert result.hit is True
        assert result.cual is not None
        assert "; " in result.cual

    def test_multiple_deal_breakers_only_one_fires(self) -> None:
        """Only the matching deal_breakers appear in cual."""
        result = detectar_deal_breaker(
            "Se exige 5+ años de experiencia en Python",
            ["exige 5+ años de experiencia", "presencial fuera de barcelona"],
        )
        assert result.hit is True
        assert "exige 5+ años de experiencia" in result.cual
        assert "presencial fuera de barcelona" not in result.cual

    # ---------------------------------------------------------------------------
    # NFD / accent normalization
    # ---------------------------------------------------------------------------

    def test_accented_char_in_job_text_matches_unaccented_dealbreaker(self) -> None:
        """NFD normalization: 'exigé' in job text matches deal_breaker 'exige'."""
        result = detectar_deal_breaker(
            "Se exigé 5+ años de experiencia",
            ["exige 5+ años de experiencia"],
        )
        assert result.hit is True

    def test_accented_char_in_dealbreaker_matches_unaccented_job_text(self) -> None:
        """NFD normalization: deal_breaker 'exigé' matches unaccented job text 'exige'."""
        result = detectar_deal_breaker(
            "Se exige 5+ años de experiencia",
            ["exigé 5+ años de experiencia"],
        )
        assert result.hit is True

    def test_tilde_normalization(self) -> None:
        """Spanish tildes normalized: 'años' matches 'anos'."""
        result = detectar_deal_breaker(
            "exige 5+ anos de experiencia",
            ["exige 5+ años de experiencia"],
        )
        assert result.hit is True

    # ---------------------------------------------------------------------------
    # Return type
    # ---------------------------------------------------------------------------

    def test_returns_deal_breaker_result_dataclass(self) -> None:
        """Function always returns a DealBreakerResult."""
        result = detectar_deal_breaker("some text", ["keyword"])
        assert isinstance(result, DealBreakerResult)

    def test_no_hit_result_has_none_cual(self) -> None:
        """When no hit, cual is explicitly None (not empty string)."""
        result = detectar_deal_breaker("irrelevant job text", ["not present"])
        assert result.cual is None

    # ---------------------------------------------------------------------------
    # No heavy dependencies
    # ---------------------------------------------------------------------------

    def test_no_app_dedup_import(self) -> None:
        """deal_breaker.py source must NOT have import statements for app.dedup.

        We check the source file directly for import lines instead of inspecting
        sys.modules, because other test modules may have already imported app.dedup
        earlier in the session, which would cause a false positive in a sys.modules
        check.

        The check only looks at import-statement lines (lines starting with 'import'
        or 'from') to avoid matching the docstring comment that mentions app.dedup.
        """
        import inspect

        import app.scoring.deal_breaker as db_module

        source = inspect.getsource(db_module)
        # Only check import-statement lines, not comments or docstrings
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        dedup_imports = [l for l in import_lines if "app.dedup" in l]
        assert not dedup_imports, (
            f"deal_breaker.py must not import from app.dedup (Pitfall 7 — "
            f"drags BGE-M3/torch into scorer tests). Found: {dedup_imports}"
        )
