import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Las corridas de prueba van a una carpeta temporal, no al portafolio real (salidas/) del auditor.
import os as _os  # noqa: E402
import tempfile as _tempfile  # noqa: E402

_os.environ.setdefault("FOLIO_SALIDAS", _tempfile.mkdtemp(prefix="folio_pruebas_salidas_"))

import pytest


@pytest.fixture(autouse=True)
def _scrypt_rapido_en_pruebas(request, monkeypatch):
    """Usa el costo scrypt mínimo permitido (2^14) para que la suite sea rápida.

    Las pruebas marcadas con @pytest.mark.scrypt_real usan el costo vigente de producción.
    """
    if request.node.get_closest_marker("scrypt_real"):
        return
    from motor import cripto

    monkeypatch.setattr(cripto, "SCRYPT_N", cripto.SCRYPT_N_MINIMO)


def pytest_configure(config):
    config.addinivalue_line("markers", "scrypt_real: usa el costo scrypt de producción (2^17)")
