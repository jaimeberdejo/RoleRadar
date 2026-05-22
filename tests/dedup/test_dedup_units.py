"""
Tests unitarios de los módulos hoja de deduplicación (Plan 02-03).

Cubre:
- Invariante lazy-import: importar app.dedup.embedder NO introduce torch en sys.modules.
- FakeEmbedder: shape, vector constante, vector mapeado, determinismo por hash.
- Estructura de BgeM3Embedder: tiene método embed (sin instanciar el modelo real).
- exact_group: agrupación por hash exacto (empresa + título normalizados).
- build_embed_text: construcción del texto de embedding.
- semantic_cluster: clustering greedy coseno con FakeEmbedder.
- merge_group: canónica = descripción más larga; urls_alternativas acumuladas; no-mutación.

NOTA: Este fichero usa FakeEmbedder y fake_embedder_identico / fake_embedder_ortogonal
de conftest.py. NUNCA instancia BgeM3Embedder ni descarga el modelo BAAI/bge-m3.
"""
from __future__ import annotations

import sys

import numpy as np
import pytest

from app.models.schemas import Job


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_job(
    title: str,
    company: str,
    description: str = "",
    url: str | None = None,
    job_id: str | None = None,
) -> Job:
    """Crea un Job mínimo para tests de dedup."""
    return Job(
        id=job_id or f"id-{title[:4].lower()}-{company[:4].lower()}",
        title=title,
        company=company,
        description=description,
        source="test",
        url=url,
    )


# ──────────────────────────────────────────────────────────────────────────────
# SECCIÓN 1: Invariante lazy-import (anti-torch)
# ──────────────────────────────────────────────────────────────────────────────

def test_importar_embedder_no_introduce_torch() -> None:
    """Importar app.dedup.embedder NO debe introducir torch ni sentence_transformers en sys.modules.

    Este test es la red de seguridad anti-torch (T-02-07 / Pitfall 1 de RESEARCH.md).
    Si falla, significa que hay un import de sentence_transformers a nivel de módulo en embedder.py.
    """
    # Capturar state ANTES — puede que torch ya estuviera cargado por otro módulo
    torch_antes = "torch" in sys.modules
    st_antes = "sentence_transformers" in sys.modules

    # Importar el módulo (si ya está importado, reimportarlo no re-ejecuta el módulo,
    # pero el invariante es: el propio módulo embedder.py no debe arrastrar torch)
    import importlib
    import app.dedup.embedder
    importlib.reload(app.dedup.embedder)

    torch_despues = "torch" in sys.modules
    st_despues = "sentence_transformers" in sys.modules

    # Solo fallar si el import de embedder INTRODUJO los módulos (no estaban antes)
    if not torch_antes:
        assert not torch_despues, (
            "¡Invariante rota! Importar app.dedup.embedder introdujo 'torch' en sys.modules. "
            "Revisar que sentence_transformers solo se importa dentro de _ensure_loaded()."
        )
    if not st_antes:
        assert not st_despues, (
            "¡Invariante rota! Importar app.dedup.embedder introdujo 'sentence_transformers' en sys.modules. "
            "El import debe estar DENTRO de _ensure_loaded(), no a nivel de módulo."
        )


def test_importar_semantic_no_introduce_torch() -> None:
    """Importar app.dedup.semantic NO debe introducir torch en sys.modules.

    semantic.py importa Embedder (Protocol) de embedder.py — solo numpy, no torch.
    """
    torch_antes = "torch" in sys.modules

    import importlib
    import app.dedup.semantic
    importlib.reload(app.dedup.semantic)

    torch_despues = "torch" in sys.modules

    if not torch_antes:
        assert not torch_despues, (
            "¡Invariante rota! Importar app.dedup.semantic introdujo 'torch' en sys.modules."
        )


# ──────────────────────────────────────────────────────────────────────────────
# SECCIÓN 2: FakeEmbedder
# ──────────────────────────────────────────────────────────────────────────────

class TestFakeEmbedder:
    """Tests del embedder determinista para tests."""

    def test_shape_correcta_con_default_vector(self) -> None:
        """embed(['a','b','c']) con default_vector devuelve shape (3, dim)."""
        from app.dedup.embedder import FakeEmbedder

        v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        emb = FakeEmbedder(default_vector=v)
        resultado = emb.embed(["texto1", "texto2", "texto3"])

        assert isinstance(resultado, np.ndarray), "Debe devolver np.ndarray"
        assert resultado.shape == (3, 4), f"Shape esperada (3, 4), obtenida {resultado.shape}"
        assert resultado.dtype == np.float32, f"dtype esperado float32, obtenido {resultado.dtype}"

    def test_vector_constante_con_default_vector(self) -> None:
        """Todas las filas son iguales cuando se usa default_vector → similitud coseno 1.0."""
        from app.dedup.embedder import FakeEmbedder

        v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        emb = FakeEmbedder(default_vector=v)
        resultado = emb.embed(["x", "y"])

        np.testing.assert_array_almost_equal(
            resultado[0], resultado[1],
            err_msg="Con default_vector, todas las filas deben ser iguales."
        )

    def test_similitud_coseno_1_con_default_vector(self) -> None:
        """dot(v, v) == 1.0 para vectores idénticos L2-normalizados."""
        from app.dedup.embedder import FakeEmbedder

        v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        emb = FakeEmbedder(default_vector=v)
        E = emb.embed(["a", "b"])
        sim = E @ E.T
        assert sim[0, 1] >= 0.999, f"Similitud coseno esperada ≥ 0.999, obtenida {sim[0, 1]}"

    def test_vector_mapeado_por_dict(self) -> None:
        """embed([texto_conocido]) devuelve el vector pre-especificado del dict."""
        from app.dedup.embedder import FakeEmbedder

        v_conocido = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
        emb = FakeEmbedder(vectors={"texto_conocido": v_conocido})
        resultado = emb.embed(["texto_conocido"])

        np.testing.assert_array_almost_equal(
            resultado[0], v_conocido,
            err_msg="El vector para texto_conocido debe coincidir con el del dict."
        )

    def test_fallback_hash_es_deterministico(self) -> None:
        """Texto desconocido sin default → mismo vector en llamadas sucesivas."""
        from app.dedup.embedder import FakeEmbedder

        emb = FakeEmbedder()  # sin vectors ni default_vector
        r1 = emb.embed(["texto_sin_mapear"])
        r2 = emb.embed(["texto_sin_mapear"])

        np.testing.assert_array_almost_equal(
            r1[0], r2[0],
            err_msg="El fallback hash debe producir el mismo vector para el mismo texto."
        )

    def test_fallback_diferentes_textos_dan_diferentes_vectores(self) -> None:
        """Textos distintos sin mapear deben dar vectores distintos (con alta probabilidad)."""
        from app.dedup.embedder import FakeEmbedder

        emb = FakeEmbedder()
        r = emb.embed(["texto_A_muy_largo", "texto_B_distinto"])

        # Es extremadamente improbable que dos hashes SHA-256 distintos produzcan el
        # mismo vector de dimensión 4 después de normalización L2.
        assert not np.allclose(r[0], r[1]), (
            "Textos distintos deben producir vectores distintos (fallback por hash)."
        )

    def test_embed_lista_vacia_devuelve_array_vacio(self) -> None:
        """embed([]) debe devolver un array vacío sin error."""
        from app.dedup.embedder import FakeEmbedder

        emb = FakeEmbedder()
        resultado = emb.embed([])
        assert isinstance(resultado, np.ndarray)
        assert len(resultado) == 0

    def test_bge_m3_tiene_metodo_embed_sin_instanciar_modelo(self) -> None:
        """BgeM3Embedder expone método embed (verificación estructural, sin descargar el modelo)."""
        from app.dedup.embedder import BgeM3Embedder

        emb = BgeM3Embedder()
        assert hasattr(emb, "embed"), "BgeM3Embedder debe tener método 'embed'"
        assert callable(emb.embed), "BgeM3Embedder.embed debe ser callable"
        # NO llamamos a emb.embed() — eso descargaría el modelo BAAI/bge-m3 (~2.3 GB)

    def test_tres_clases_exportadas(self) -> None:
        """embedder.py debe exportar exactamente Embedder, BgeM3Embedder y FakeEmbedder."""
        from app.dedup import embedder as emb_module

        assert hasattr(emb_module, "Embedder"), "Debe existir clase Embedder"
        assert hasattr(emb_module, "BgeM3Embedder"), "Debe existir clase BgeM3Embedder"
        assert hasattr(emb_module, "FakeEmbedder"), "Debe existir clase FakeEmbedder"


# ──────────────────────────────────────────────────────────────────────────────
# SECCIÓN 3: exact_group
# ──────────────────────────────────────────────────────────────────────────────

class TestExactGroup:
    """Tests del nivel-1 de dedup: agrupación por hash exacto empresa+título."""

    def test_tres_jobs_dos_duplicados_exactos(self) -> None:
        """3 jobs donde 2 tienen misma empresa+título normalizados → 2 grupos."""
        from app.dedup.exact import exact_group

        job1 = _make_job("AI Engineer", "Acme Corp", job_id="id-1")
        job2 = _make_job("ai engineer", "acme corp", job_id="id-2")  # mismo normalizado
        job3 = _make_job("Data Analyst", "FinanceFirm", job_id="id-3")

        grupos = exact_group([job1, job2, job3])

        assert len(grupos) == 2, f"Esperados 2 grupos, obtenidos {len(grupos)}"
        # El grupo con 2 elementos contiene job1 y job2
        tamanios = sorted([len(g) for g in grupos])
        assert tamanios == [1, 2], f"Tamaños de grupos esperados [1, 2], obtenidos {tamanios}"

    def test_jobs_sin_duplicados(self) -> None:
        """3 jobs todos distintos → 3 grupos individuales."""
        from app.dedup.exact import exact_group

        jobs = [
            _make_job("AI Engineer", "Acme", job_id="id-1"),
            _make_job("ML Engineer", "BetaCorp", job_id="id-2"),
            _make_job("Data Analyst", "Gamma", job_id="id-3"),
        ]
        grupos = exact_group(jobs)
        assert len(grupos) == 3, f"Esperados 3 grupos, obtenidos {len(grupos)}"
        for g in grupos:
            assert len(g) == 1

    def test_lista_vacia(self) -> None:
        """exact_group([]) → lista vacía."""
        from app.dedup.exact import exact_group

        assert exact_group([]) == []

    def test_normalizacion_de_acentos(self) -> None:
        """empresa 'Índitex' y 'Inditex' deben ser consideradas duplicadas."""
        from app.dedup.exact import exact_group

        job1 = _make_job("AI Engineer", "Índitex", job_id="id-1")
        job2 = _make_job("ai engineer", "Inditex", job_id="id-2")

        grupos = exact_group([job1, job2])
        assert len(grupos) == 1, "Acentos no deben diferenciar grupos"
        assert len(grupos[0]) == 2

    def test_un_solo_job(self) -> None:
        """exact_group con un solo job → lista con un grupo de un elemento."""
        from app.dedup.exact import exact_group

        job = _make_job("AI Engineer", "Acme", job_id="id-1")
        grupos = exact_group([job])
        assert len(grupos) == 1
        assert grupos[0][0] is job


# ──────────────────────────────────────────────────────────────────────────────
# SECCIÓN 4: build_embed_text y semantic_cluster
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildEmbedText:
    """Tests de la función que construye el texto para embedding."""

    def test_texto_completo(self) -> None:
        """Título + empresa + primeras 50 palabras de descripción."""
        from app.dedup.semantic import build_embed_text

        desc_50_palabras = " ".join([f"palabra{i}" for i in range(50)])
        job = _make_job("AI Engineer", "Acme", description=desc_50_palabras + " extra")

        resultado = build_embed_text(job, desc_words=50)
        assert resultado.startswith("AI Engineer Acme")
        # Las 50 primeras palabras están; "extra" NO debería estar
        assert "extra" not in resultado
        assert "palabra49" in resultado

    def test_descripcion_vacia_no_falla(self) -> None:
        """Con descripción vacía el texto degenera a 'title company' sin error."""
        from app.dedup.semantic import build_embed_text

        job = _make_job("Senior Dev", "StartupXYZ", description="")
        resultado = build_embed_text(job)

        assert resultado == "Senior Dev StartupXYZ", f"Resultado inesperado: '{resultado}'"

    def test_descripcion_corta_incluida_completa(self) -> None:
        """Si la descripción tiene menos de desc_words, se incluye completa."""
        from app.dedup.semantic import build_embed_text

        job = _make_job("Dev", "Corp", description="solo tres palabras aqui")
        resultado = build_embed_text(job, desc_words=50)

        assert "solo tres palabras aqui" in resultado


class TestSemanticCluster:
    """Tests del clustering semántico greedy por coseno."""

    def test_todos_identicos_un_solo_cluster(self, fake_embedder_identico) -> None:
        """Con vectores idénticos (similitud 1.0), todos los jobs van al mismo cluster."""
        from app.dedup.semantic import semantic_cluster

        jobs = [
            _make_job("AI Engineer", "TechCorp", "We build AI.", job_id="id-1"),
            _make_job("AI Engineer", "TechCorp", "We build AI.", job_id="id-2"),
            _make_job("AI Engineer", "TechCorp", "We build AI.", job_id="id-3"),
        ]
        clusters = semantic_cluster(jobs, fake_embedder_identico, umbral=0.85)

        assert len(clusters) == 1, f"Esperado 1 cluster, obtenidos {len(clusters)}"
        assert len(clusters[0]) == 3, f"El cluster debe tener 3 jobs, tiene {len(clusters[0])}"

    def test_ortogonales_cada_job_en_su_cluster(self, fake_embedder_ortogonal) -> None:
        """Con vectores ortogonales (similitud 0.0) y umbral 0.85, cada job va a su cluster."""
        from app.dedup.semantic import semantic_cluster

        jobs = [
            _make_job("AI Engineer", "TechCorp", "We build AI.", job_id="id-1"),
            _make_job("Data Analyst", "FinanceFirm", "We analyze data.", job_id="id-2"),
            _make_job("Backend Developer", "StartupXYZ", "We write code.", job_id="id-3"),
        ]
        clusters = semantic_cluster(jobs, fake_embedder_ortogonal, umbral=0.85)

        assert len(clusters) == 3, f"Esperados 3 clusters, obtenidos {len(clusters)}"
        for c in clusters:
            assert len(c) == 1, f"Cada cluster debe tener 1 job, tiene {len(c)}"

    def test_lista_vacia_devuelve_vacia(self) -> None:
        """semantic_cluster([]) → []."""
        from app.dedup.semantic import semantic_cluster
        from app.dedup.embedder import FakeEmbedder

        emb = FakeEmbedder()
        resultado = semantic_cluster([], emb)
        assert resultado == []

    def test_un_solo_job_devuelve_un_cluster(self, fake_embedder_identico) -> None:
        """semantic_cluster con un solo job → [[0]]."""
        from app.dedup.semantic import semantic_cluster

        jobs = [_make_job("Dev", "Corp", "Descripción.", job_id="id-1")]
        clusters = semantic_cluster(jobs, fake_embedder_identico)

        assert len(clusters) == 1
        assert clusters[0] == [0]

    def test_indices_cubren_todos_los_jobs(self, fake_embedder_ortogonal) -> None:
        """Los índices en todos los clusters cubren exactamente {0, 1, 2}."""
        from app.dedup.semantic import semantic_cluster

        jobs = [
            _make_job("AI Engineer", "TechCorp", "We build AI.", job_id="id-1"),
            _make_job("Data Analyst", "FinanceFirm", "We analyze data.", job_id="id-2"),
            _make_job("Backend Developer", "StartupXYZ", "We write code.", job_id="id-3"),
        ]
        clusters = semantic_cluster(jobs, fake_embedder_ortogonal, umbral=0.85)

        todos_indices = {idx for cluster in clusters for idx in cluster}
        assert todos_indices == {0, 1, 2}, f"Índices esperados {{0,1,2}}, obtenidos {todos_indices}"


# ──────────────────────────────────────────────────────────────────────────────
# SECCIÓN 5: merge_group
# ──────────────────────────────────────────────────────────────────────────────

class TestMergeGroup:
    """Tests del merger: descripción más larga como canónica + urls_alternativas."""

    def test_un_solo_job_sin_cambios(self) -> None:
        """merge_group con 1 job devuelve ese job sin modificaciones."""
        from app.dedup.merger import merge_group

        job = _make_job("Dev", "Corp", description="Descripción corta.", url="https://corp.com/job", job_id="id-1")
        resultado = merge_group([job])

        assert resultado is job, "Con 1 job, debe devolver el mismo objeto"

    def test_descripcion_mas_larga_es_canonica(self) -> None:
        """El job con descripción más larga debe ser la canónica."""
        from app.dedup.merger import merge_group

        job_corto = _make_job("Dev", "Corp", description="Corta.", url="https://corp.com/corta", job_id="id-corto")
        job_largo = _make_job("Dev", "Corp", description="Una descripción mucho más larga y detallada.", url="https://corp.com/larga", job_id="id-largo")

        resultado = merge_group([job_corto, job_largo])

        assert resultado.description == job_largo.description, (
            "La descripción canónica debe ser la más larga."
        )

    def test_url_descartada_en_urls_alternativas(self) -> None:
        """La URL del job descartado aparece en urls_alternativas de la canónica."""
        from app.dedup.merger import merge_group

        job_corto = _make_job("Dev", "Corp", description="Corta.", url="https://corp.com/corta", job_id="id-1")
        job_largo = _make_job("Dev", "Corp", description="Una descripción mucho más larga.", url="https://corp.com/larga", job_id="id-2")

        resultado = merge_group([job_corto, job_largo])

        assert "https://corp.com/corta" in resultado.urls_alternativas, (
            "La URL del job descartado debe estar en urls_alternativas."
        )

    def test_url_canonica_no_en_urls_alternativas(self) -> None:
        """La URL de la canónica NO debe aparecer duplicada en urls_alternativas."""
        from app.dedup.merger import merge_group

        job_corto = _make_job("Dev", "Corp", description="Corta.", url="https://corp.com/corta", job_id="id-1")
        job_largo = _make_job("Dev", "Corp", description="Descripción más larga.", url="https://corp.com/larga", job_id="id-2")

        resultado = merge_group([job_corto, job_largo])

        assert resultado.url not in resultado.urls_alternativas, (
            "La URL de la canónica no debe estar en sus propias urls_alternativas."
        )

    def test_no_mutacion_del_original(self) -> None:
        """merge_group NO debe mutar el job canónico original (usa model_copy)."""
        from app.dedup.merger import merge_group

        job_corto = _make_job("Dev", "Corp", description="Corta.", url="https://corp.com/corta", job_id="id-1")
        job_largo = _make_job("Dev", "Corp", description="Descripción mucho más larga.", url="https://corp.com/larga", job_id="id-2")

        urls_antes = list(job_largo.urls_alternativas)
        resultado = merge_group([job_corto, job_largo])

        assert job_largo.urls_alternativas == urls_antes, (
            "merge_group NO debe mutar el job canónico original. "
            "Usar model_copy(update=...) en lugar de mutación directa."
        )
        # El resultado sí debe tener las URLs alternativas
        assert len(resultado.urls_alternativas) > len(urls_antes)

    def test_tres_jobs_acumula_dos_urls_alternativas(self) -> None:
        """Con 3 jobs, la canónica acumula 2 URLs alternativas."""
        from app.dedup.merger import merge_group

        job1 = _make_job("Dev", "Corp", description="Corta.", url="https://corp.com/1", job_id="id-1")
        job2 = _make_job("Dev", "Corp", description="Mediana y bastante más larga.", url="https://corp.com/2", job_id="id-2")
        job3 = _make_job("Dev", "Corp", description="La descripción más larga de todas, sin duda.", url="https://corp.com/3", job_id="id-3")

        resultado = merge_group([job1, job2, job3])

        assert resultado.description == job3.description
        assert len(resultado.urls_alternativas) == 2
        assert "https://corp.com/1" in resultado.urls_alternativas
        assert "https://corp.com/2" in resultado.urls_alternativas

    def test_job_sin_url_no_contamina_urls_alternativas(self) -> None:
        """Jobs descartados sin URL no añaden None a urls_alternativas."""
        from app.dedup.merger import merge_group

        job_sin_url = _make_job("Dev", "Corp", description="Corta.", url=None, job_id="id-1")
        job_con_url = _make_job("Dev", "Corp", description="Descripción más larga.", url="https://corp.com/ok", job_id="id-2")

        resultado = merge_group([job_sin_url, job_con_url])

        assert None not in resultado.urls_alternativas, (
            "urls_alternativas no debe contener None (jobs sin URL se ignoran)."
        )
