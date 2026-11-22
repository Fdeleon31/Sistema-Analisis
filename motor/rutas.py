"""Resolución portátil de rutas para ejecución desde código fuente o paquete PyInstaller (.exe)."""
from __future__ import annotations

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
