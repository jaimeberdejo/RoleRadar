"""Tests de limpieza de imports — MIG-01.

Verifica que eliminar app/api/ no deja rastros de fastapi/uvicorn
en el grafo de imports del paquete app.storage.
"""
from __future__ import annotations

import sys


def test_fastapi_not_importable_after_removal() -> None:
    """Importar app.storage no arrastra fastapi ni uvicorn. (MIG-01)

    Si algún módulo de app.storage importara fastapi transitivamente,
    este test fallaría — señalando un import olvidado al borrar app/api/.
    """
    import app.storage  # noqa: F401

    assert "fastapi" not in sys.modules, (
        "fastapi está en sys.modules tras importar app.storage — "
        "comprobar imports en app/storage/ o app/__init__.py"
    )
    assert "uvicorn" not in sys.modules, (
        "uvicorn está en sys.modules tras importar app.storage"
    )
