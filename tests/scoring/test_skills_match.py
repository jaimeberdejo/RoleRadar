"""
Tests for app/scoring/skills_match.py — TDD RED phase.

Tests cover:
- Identical vectors → score = 100
- Orthogonal vectors → score = 0
- Negative cosine (clamped) → score = 0
- Partial cosine → linear mapping to 0-100
- embedder=None raises ValueError with "embedder" in message
- cv_text empty or whitespace-only raises ValueError
- job_description empty returns 0 (neutral, with WARNING log)
- CV_SKILLS_TEXT_MAX_TOKENS constant is 500 and exported
- Module import does NOT load torch

WR-04 fix: FakeEmbedder is imported DEFERRED inside each test body (Pitfall 7).
Module-level import of app.dedup.embedder would drag torch/sentence-transformers
into the process at collection time.
"""
from __future__ import annotations

import sys

import numpy as np
import pytest

from app.scoring.skills_match import CV_SKILLS_TEXT_MAX_TOKENS, encaje_skills_por_coseno


class TestSkillsMatchBasic:
    """Core behavior of encaje_skills_por_coseno."""

    def test_identical_vectors_returns_100(self) -> None:
        """Identical vectors → cosine=1.0 → score=100."""
        from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7 (WR-04)
        vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        embedder = FakeEmbedder(default_vector=vec)
        score = encaje_skills_por_coseno("Python LLMs FastAPI", "We need Python and LLMs", embedder)
        assert score == 100, f"Identical vectors should give 100, got {score}"

    def test_orthogonal_vectors_returns_0(self) -> None:
        """Orthogonal vectors → cosine=0.0 → score=0."""
        from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7 (WR-04)
        cv_text = "cv text"
        job_desc = "job desc"
        vecs = {
            cv_text: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
            job_desc: np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
        }
        embedder = FakeEmbedder(vectors=vecs)
        score = encaje_skills_por_coseno(cv_text, job_desc, embedder)
        assert score == 0, f"Orthogonal vectors should give 0, got {score}"

    def test_negative_cosine_clamped_to_0(self) -> None:
        """Negative cosine (anti-parallel) is clamped to 0, not negative."""
        from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7 (WR-04)
        cv_text = "cv text"
        job_desc = "job desc"
        vecs = {
            cv_text: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
            job_desc: np.array([-1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        }
        embedder = FakeEmbedder(vectors=vecs)
        # Note: FakeEmbedder L2-normalizes all vectors; [-1,0,0,0] becomes [-1,0,0,0] (already normalized)
        # dot([1,0,0,0], [-1,0,0,0]) = -1.0 → clamped to 0
        score = encaje_skills_por_coseno(cv_text, job_desc, embedder)
        assert score == 0, f"Negative cosine should be clamped to 0, got {score}"

    def test_partial_cosine_linear_mapping(self) -> None:
        """Cosine maps linearly: a value between 0 and 1 maps to 0-100 range."""
        from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7 (WR-04)
        # We construct vectors with a known cosine.
        # cos(60 degrees) = 0.5 → score = 50
        cv_vec = np.array([1.0, 0.0], dtype=np.float32)
        job_vec = np.array([0.5, 0.5 ** 0.5], dtype=np.float32)  # not unit but will be normalized
        # Use a 2D FakeEmbedder but actually let's compute expected:
        # FakeEmbedder normalizes: cv_vec already norm=1; job_vec: norm = sqrt(0.25+0.5) = sqrt(0.75) ≈ 0.866
        # normalized job_vec = [0.5/0.866, 0.707/0.866] ≈ [0.577, 0.816]
        # dot = 1.0 * 0.577 + 0 * 0.816 = 0.577 → score = 58
        # Easier: use vectors we know the dot of after normalization
        # Use explicit: [cos(theta), sin(theta)] for theta=60: [0.5, 0.866]
        cv_text = "cv"
        job_text = "job"
        vecs = {
            cv_text: np.array([1.0, 0.0], dtype=np.float32),
            job_text: np.array([0.5, (3 ** 0.5) / 2], dtype=np.float32),
        }
        embedder = FakeEmbedder(vectors=vecs)
        # Both are unit vectors: dot = 0.5 → score = int(round(0.5 * 100)) = 50
        score = encaje_skills_por_coseno(cv_text, job_text, embedder)
        assert score == 50, f"Cosine=0.5 should give score=50, got {score}"


class TestSkillsMatchGuards:
    """Guard conditions."""

    def test_embedder_none_raises_value_error(self) -> None:
        """embedder=None raises ValueError with 'embedder' in the message."""
        with pytest.raises(ValueError, match="embedder"):
            encaje_skills_por_coseno("cv text", "job description", None)

    def test_cv_text_empty_raises_value_error(self) -> None:
        """Empty cv_text raises ValueError."""
        from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7 (WR-04)
        embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
        with pytest.raises(ValueError):
            encaje_skills_por_coseno("", "job description", embedder)

    def test_cv_text_whitespace_only_raises_value_error(self) -> None:
        """Whitespace-only cv_text raises ValueError."""
        from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7 (WR-04)
        embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
        with pytest.raises(ValueError):
            encaje_skills_por_coseno("   \n\t  ", "job description", embedder)

    def test_job_description_empty_returns_0(self) -> None:
        """Empty job_description returns 0 (neutral, not an error)."""
        from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7 (WR-04)
        embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
        score = encaje_skills_por_coseno("Python FastAPI LLMs", "", embedder)
        assert score == 0, f"Empty job description should return 0, got {score}"

    def test_job_description_whitespace_returns_0(self) -> None:
        """Whitespace-only job_description returns 0."""
        from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7 (WR-04)
        embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
        score = encaje_skills_por_coseno("Python FastAPI", "   ", embedder)
        assert score == 0, f"Whitespace job description should return 0, got {score}"


class TestSkillsMatchConstants:
    """Module-level constants."""

    def test_cv_skills_text_max_tokens_is_500(self) -> None:
        """CV_SKILLS_TEXT_MAX_TOKENS == 500."""
        assert CV_SKILLS_TEXT_MAX_TOKENS == 500

    def test_cv_text_truncated_at_max_tokens(self) -> None:
        """cv_text longer than CV_SKILLS_TEXT_MAX_TOKENS is truncated before embedding."""
        # Build a cv_text that is very long; the truncated version should be the
        # first 500 chars.
        long_cv = "Python " * 200  # 1400 chars
        job_desc = "job description"
        truncated_cv = long_cv[:CV_SKILLS_TEXT_MAX_TOKENS]

        recorded_texts: list[list[str]] = []

        class RecordingEmbedder:
            def embed(self, texts: list[str]) -> np.ndarray:
                recorded_texts.append(texts)
                vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
                return np.array([vec, vec], dtype=np.float32)

        encaje_skills_por_coseno(long_cv, job_desc, RecordingEmbedder())

        assert len(recorded_texts) == 1, "embed should be called exactly once"
        actual_cv_text = recorded_texts[0][0]
        assert len(actual_cv_text) <= CV_SKILLS_TEXT_MAX_TOKENS, (
            f"cv_text was not truncated: len={len(actual_cv_text)}"
        )
        assert actual_cv_text == truncated_cv, "cv_text should be the first 500 chars"


class TestSkillsMatchImportSafety:
    """Importing skills_match must not trigger torch or sentence_transformers."""

    def test_import_does_not_load_torch(self) -> None:
        """After importing skills_match, 'torch' must not be in sys.modules."""
        assert "torch" not in sys.modules, (
            "torch was loaded — skills_match.py has a runtime import of app.dedup or "
            "sentence_transformers. Use TYPE_CHECKING guard (Pitfall 7)."
        )

    def test_import_does_not_load_sentence_transformers(self) -> None:
        """After importing skills_match, 'sentence_transformers' must not be in sys.modules."""
        assert "sentence_transformers" not in sys.modules
