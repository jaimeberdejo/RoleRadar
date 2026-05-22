"""
Abstracciones de embedder para el pipeline de deduplicación semántica.

Expone:
- Embedder: Protocol que deben satisfacer todos los embedders.
- BgeM3Embedder: embedder real con BAAI/bge-m3 (lazy import de sentence-transformers).
- FakeEmbedder: embedder determinista para tests (sin red, sin torch).

INVARIANTE CRÍTICA (T-02-07 / Pitfall 1 de RESEARCH.md):
  Importar este módulo NO debe importar torch ni sentence_transformers.
  El import de sentence_transformers está ÚNICAMENTE dentro de _ensure_loaded(),
  marcado con ``# noqa: PLC0415``.

Patrón análogo a app/cv/llm_client.py: seam inyectable para tests.
La diferencia es que aquí la dependencia pesada (sentence-transformers/torch)
va DENTRO del método, no a nivel de módulo.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Interfaz que deben satisfacer todos los embedders.

    Contratos:
    - embed(texts) devuelve un array float32 de shape (len(texts), dim).
    - Los vectores son L2-normalizados: dot(v, v) == 1.0.
    - Mismo texto → mismo vector (determinismo).
    """

    def embed(self, texts: list[str]) -> np.ndarray:
        """Genera embeddings L2-normalizados para una lista de textos.

        Args:
            texts: Lista de cadenas a embeber.

        Returns:
            np.ndarray float32 de shape (len(texts), dim), L2-normalizado.
            dot(E[i], E[j]) == similitud coseno entre textos i y j.
        """
        ...


class BgeM3Embedder:
    """Embedder real: BAAI/bge-m3 via sentence-transformers (lazy-loaded).

    El modelo se carga SOLO en la primera llamada a embed() (lazy loading).
    Esto evita que importar este módulo arrastre torch al proceso, lo cual
    causaría ~2-4 segundos de inicialización y fallos en CI sin torch.

    Primera llamada real a embed() descarga ~2.3 GB del modelo si no está
    en caché (HF_HOME o ~/.cache/huggingface/hub/). En tests, usar FakeEmbedder.

    Attributes:
        _model: SentenceTransformer cargado bajo demanda. None hasta la primera llamada.
    """

    def __init__(self) -> None:
        """Inicializa el embedder SIN cargar el modelo."""
        self._model = None  # carga perezosa — no descargar en __init__

    def _ensure_loaded(self) -> None:
        """Carga el modelo BAAI/bge-m3 si no está cargado todavía.

        El import de sentence_transformers ocurre aquí y solo aquí.
        El ``# noqa: PLC0415`` suprime la advertencia de linter por
        import no-top-level (patrón de lazy import establecido en el proyecto).
        """
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            logger.info("Cargando modelo BAAI/bge-m3 (primera llamada)...")
            self._model = SentenceTransformer("BAAI/bge-m3")
            logger.info("Modelo BAAI/bge-m3 cargado.")

    def embed(self, texts: list[str]) -> np.ndarray:
        """Genera embeddings L2-normalizados con BAAI/bge-m3.

        Args:
            texts: Lista de cadenas a embeber.

        Returns:
            np.ndarray float32 de shape (len(texts), 1024), L2-normalizado.
            BGE-M3 produce embeddings de dimensión 1024.
        """
        self._ensure_loaded()
        return self._model.encode(
            texts,
            normalize_embeddings=True,  # L2-normalize → dot product == cosine (Pattern 5)
            batch_size=32,               # seguro para CPU-only (Pitfall: batch grande OOM)
            show_progress_bar=False,     # silenciar tqdm en contexto de servicio
        )


class FakeEmbedder:
    """Embedder determinista para tests: sin red, sin torch.

    Estrategia de resolución de vectores (por orden de prioridad):
    1. Si el texto está en el dict ``vectors``, usa ese vector.
    2. Si se proporcionó ``default_vector``, lo usa para cualquier texto desconocido.
    3. Fallback: genera vector determinista desde hash SHA-256 del texto.

    Todos los vectores devueltos son L2-normalizados.

    Attributes:
        _vectors: Mapa opcional texto → vector pre-especificado.
        _default_vector: Vector usado cuando el texto no está en _vectors.
        _dim: Dimensión de los vectores del fallback por hash.
    """

    def __init__(
        self,
        vectors: dict[str, np.ndarray] | None = None,
        default_vector: np.ndarray | None = None,
        dim: int = 4,
    ) -> None:
        """Inicializa el FakeEmbedder.

        Args:
            vectors: Mapa texto → vector numpy. Prioridad máxima.
            default_vector: Vector devuelto para cualquier texto no mapeado.
                Si es None, se usa el fallback por hash.
            dim: Dimensión de los vectores del fallback por hash (por defecto 4).
        """
        self._vectors: dict[str, np.ndarray] = vectors or {}
        self._default_vector: np.ndarray | None = default_vector
        self._dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        """Genera embeddings deterministas para los textos dados.

        Args:
            texts: Lista de cadenas a embeber.

        Returns:
            np.ndarray float32 de shape (len(texts), dim), L2-normalizado.
            Si texts es vacío, devuelve array vacío de shape (0,).
        """
        if not texts:
            return np.array([], dtype=np.float32)

        resultado: list[np.ndarray] = []
        for texto in texts:
            if texto in self._vectors:
                # Prioridad 1: vector pre-especificado en el dict
                v = np.array(self._vectors[texto], dtype=np.float32)
            elif self._default_vector is not None:
                # Prioridad 2: vector por defecto para todos los textos desconocidos
                v = np.array(self._default_vector, dtype=np.float32)
            else:
                # Prioridad 3: fallback determinista por hash SHA-256
                h = int(hashlib.sha256(texto.encode("utf-8")).hexdigest(), 16)
                rng = np.random.default_rng(h % (2**32))
                v = rng.standard_normal(self._dim).astype(np.float32)
                norma = np.linalg.norm(v)
                v = v / (norma + 1e-9)  # L2-normalizar evitando división por cero

            resultado.append(v)

        return np.array(resultado, dtype=np.float32)
