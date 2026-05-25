"""
Tests for app/scoring/puesto_match.py — TDD RED phase.

Tests cover:
- Matching via identical vectors (best match returns rango=1)
- Below-threshold returns ("fuera de ranking", None)
- embedder=None raises ValueError with "embedder" in message
- Empty ranking returns ("fuera de ranking", None)
- Multiple entries: returns the highest cosine match
- UMBRAL_PUESTO_DEFAULT constant is exported
- Module import does NOT load torch
"""
from __future__ import annotations

import importlib
import sys

import numpy as np
import pytest

from app.dedup.embedder import FakeEmbedder
from app.models.schemas import PuestoRanking
from app.scoring.puesto_match import UMBRAL_PUESTO_DEFAULT, match_puesto_por_coseno


class TestPuestoMatchBasic:
    """Core behavior of match_puesto_por_coseno."""

    def test_identical_vectors_returns_rango_1(self) -> None:
        """When all texts get the same vector, best match is the first entry (rango=1)."""
        ranking = [
            PuestoRanking(titulo="AI Engineer", sinonimos=["LLM Engineer"]),
            PuestoRanking(titulo="Data Engineer", sinonimos=[]),
        ]
        vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        embedder = FakeEmbedder(default_vector=vec)

        puesto, rango = match_puesto_por_coseno("AI Engineer", ranking, embedder)

        assert rango == 1
        assert puesto == "AI Engineer"

    def test_below_threshold_returns_fuera_de_ranking(self) -> None:
        """When best cosine is below umbral, returns ('fuera de ranking', None).

        The query title gets [1,0,0,0] and all corpus texts get [0,1,0,0] (orthogonal).
        cosine = dot([1,0,0,0], [0,1,0,0]) = 0.0, which is below any positive umbral.
        """
        ranking = [
            PuestoRanking(titulo="AI Engineer", sinonimos=["LLM Engineer"]),
            PuestoRanking(titulo="Data Engineer", sinonimos=[]),
        ]
        query_title = "Completely Different Title"
        # corpus texts: "AI Engineer LLM Engineer" and "Data Engineer "
        corpus_text_1 = "AI Engineer LLM Engineer"
        corpus_text_2 = "Data Engineer "
        vecs = {
            query_title: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
            corpus_text_1: np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
            corpus_text_2: np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32),
        }
        embedder = FakeEmbedder(vectors=vecs)

        puesto, rango = match_puesto_por_coseno(query_title, ranking, embedder)

        assert rango is None
        assert puesto == "fuera de ranking"

    def test_embedder_none_raises_value_error(self) -> None:
        """embedder=None raises ValueError with 'embedder' in the message."""
        ranking = [PuestoRanking(titulo="AI Engineer", sinonimos=[])]

        with pytest.raises(ValueError, match="embedder"):
            match_puesto_por_coseno("title", ranking, None)

    def test_empty_ranking_returns_fuera_de_ranking(self) -> None:
        """Empty ranking list returns ('fuera de ranking', None)."""
        embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))

        puesto, rango = match_puesto_por_coseno("AI Engineer", [], embedder)

        assert rango is None
        assert puesto == "fuera de ranking"

    def test_multiple_entries_returns_best_match(self) -> None:
        """When multiple entries exceed threshold, returns the one with highest cosine."""
        ranking = [
            PuestoRanking(titulo="Data Engineer", sinonimos=[]),
            PuestoRanking(titulo="AI Engineer", sinonimos=["LLM Engineer"]),
        ]
        # Title vector: [1, 0, 0, 0]
        # "Data Engineer " corpus text → [0.5, 0.5, 0, 0] (normalized): cosine = 0.5 * 1 = 0.5
        # "AI Engineer LLM Engineer" corpus text → [1, 0, 0, 0]: cosine = 1.0
        # Use FakeEmbedder with explicit mappings for the corpus texts
        q_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        # Corpus text 1 (Data Engineer, no synonyms): "Data Engineer "
        # Corpus text 2 (AI Engineer, LLM Engineer sinonimos): "AI Engineer LLM Engineer"
        data_eng_vec = np.array([0.3, 0.7, 0.0, 0.0], dtype=np.float32)  # low cosine
        ai_eng_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)    # cosine=1.0

        # Build exact keys for the corpus texts as produced by the implementation
        vecs = {
            "Senior AI Position": q_vec,
            "Data Engineer ": data_eng_vec,
            "AI Engineer LLM Engineer": ai_eng_vec,
        }
        embedder = FakeEmbedder(vectors=vecs, default_vector=q_vec)

        puesto, rango = match_puesto_por_coseno("Senior AI Position", ranking, embedder)

        # AI Engineer has highest cosine → rango=2 (second in list)
        assert rango == 2
        assert puesto == "AI Engineer"


class TestPuestoMatchConstants:
    """Module-level constants are correct and exported."""

    def test_umbral_puesto_default_value(self) -> None:
        """UMBRAL_PUESTO_DEFAULT is 0.55."""
        assert UMBRAL_PUESTO_DEFAULT == 0.55

    def test_umbral_used_by_default(self) -> None:
        """Default umbral argument equals UMBRAL_PUESTO_DEFAULT."""
        import inspect
        sig = inspect.signature(match_puesto_por_coseno)
        default = sig.parameters["umbral"].default
        assert default == UMBRAL_PUESTO_DEFAULT


class TestPuestoMatchImportSafety:
    """Importing puesto_match must not trigger torch or sentence_transformers."""

    def test_import_does_not_load_torch(self) -> None:
        """After importing puesto_match, 'torch' must not be in sys.modules."""
        # Force a fresh module check (the module is already imported above,
        # but if torch were loaded it would show up)
        assert "torch" not in sys.modules, (
            "torch was loaded — puesto_match.py has a runtime import of app.dedup or "
            "sentence_transformers. Use TYPE_CHECKING guard (Pitfall 7)."
        )

    def test_import_does_not_load_sentence_transformers(self) -> None:
        """After importing puesto_match, 'sentence_transformers' must not be in sys.modules."""
        assert "sentence_transformers" not in sys.modules, (
            "sentence_transformers was loaded — check runtime imports in puesto_match.py."
        )
