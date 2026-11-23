"""Resolución portátil de rutas para ejecución desde código fuente o paquete PyInstaller (.exe)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def raiz_recursos() -> Path:
    """Carpeta de recursos de solo lectura (paquetes/, conectores/perfiles/, estilos)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[1]


def raiz_trabajo() -> Path:
    """Carpeta persistente de trabajo junto al ejecutable o en la raíz del proyecto."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def raiz_salidas() -> Path:
    """Carpeta donde se guardan las corridas (cédulas, bitácoras, muestras).

    FOLIO_SALIDAS permite redirigirla (las pruebas automáticas la apuntan a una carpeta temporal para no
    mezclar corridas de prueba con el portafolio real del auditor).
    """
    otra = os.environ.get("FOLIO_SALIDAS")
    return Path(otra) if otra else raiz_trabajo() / "salidas"
