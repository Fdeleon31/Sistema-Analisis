"""Ficha 10 · Lectura de facturas electrónicas de la DGI de Panamá (XML).

Lee una carpeta, un ZIP o un XML suelto y devuelve una fila por documento.
Ignora los espacios de nombres para tolerar variaciones entre PAC.
Un XML ilegible no detiene la lectura: queda en la lista de errores.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

TIPOS_DOCUMENTO = {
    "01": "Factura de operación interna",
    "02": "Factura de importación",
    "03": "Factura de exportación",
    "04": "Nota de crédito referente a una o varias FE",
    "05": "Nota de débito referente a una o varias FE",
    "06": "Nota de crédito genérica",
    "07": "Nota de débito genérica",
    "08": "Factura de zona franca",
    "09": "Reembolso",
}
NOTAS_CREDITO = {"04", "06"}
COLUMNAS = [
    "archivo", "cufe", "ambiente", "tipo_documento", "tipo_documento_nombre", "punto_facturacion", "numero",
    "fecha_emision", "ruc_emisor", "nombre_emisor", "ruc_receptor", "nombre_receptor",
    "total_neto", "total_itbms", "total", "suma_items",
]


@dataclass
class LecturaFE:
    facturas: pd.DataFrame
    errores: list[dict] = field(default_factory=list)
    archivos: int = 0
    sha256: str = ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _primero(raiz: ET.Element, *ruta: str) -> ET.Element | None:
    """Primer elemento que sigue la ruta de nombres locales, a cualquier profundidad para el primero."""
    candidatos = [e for e in raiz.iter() if _local(e.tag) == ruta[0]]
    for nombre in ruta[1:]:
        siguientes = []
        for c in candidatos:
            siguientes.extend(e for e in c.iter() if _local(e.tag) == nombre and e is not c)
        candidatos = siguientes
    return candidatos[0] if candidatos else None


def _texto(raiz: ET.Element, *ruta: str) -> str | None:
    e = _primero(raiz, *ruta)
    return e.text.strip() if e is not None and e.text else None


def _numero(valor: str | None) -> float | None:
    if valor is None:
        return None
    return round(float(valor), 2)


def leer_xml(contenido: bytes, nombre: str) -> dict:
    raiz = ET.fromstring(contenido)
    rfe = raiz if _local(raiz.tag) == "rFE" else _primero(raiz, "rFE")
    if rfe is None:
        raise ValueError("No contiene el elemento rFE de factura electrónica")
    cufe = _texto(rfe, "dId") or _texto(raiz, "dCUFE")
    fecha = _texto(rfe, "gDGen", "dFechaEm")
    items = [e for e in rfe.iter() if _local(e.tag) == "dValTotItem"]
    tipo = _texto(rfe, "gDGen", "iDoc")
    return {
        "archivo": nombre,
        "cufe": cufe,
        "ambiente": _texto(rfe, "gDGen", "iAmb"),
        "tipo_documento": tipo,
        "tipo_documento_nombre": TIPOS_DOCUMENTO.get(tipo or "", "Desconocido"),
        "punto_facturacion": _texto(rfe, "gDGen", "dPtoFacDF"),
        "numero": int(_texto(rfe, "gDGen", "dNroDF")) if _texto(rfe, "gDGen", "dNroDF") else None,
        "fecha_emision": pd.Timestamp(fecha).date() if fecha else None,
        "ruc_emisor": _texto(rfe, "gEmis", "gRucEmi", "dRuc"),
        "nombre_emisor": _texto(rfe, "gEmis", "dNombEm"),
        "ruc_receptor": _texto(rfe, "gDatRec", "gRucRec", "dRuc"),
        "nombre_receptor": _texto(rfe, "gDatRec", "dNombRec"),
        "total_neto": _numero(_texto(rfe, "gTot", "dTotNeto")),
        "total_itbms": _numero(_texto(rfe, "gTot", "dTotITBMS")),
        "total": _numero(_texto(rfe, "gTot", "dVTot")),
        "suma_items": round(sum(float(e.text) for e in items if e.text), 2) if items else None,
    }


def _fuentes(ruta: Path):
    """Produce (nombre, bytes) de cada XML en una carpeta, un ZIP o un archivo suelto."""
    if ruta.is_dir():
        for p in sorted(ruta.rglob("*")):
            if p.suffix.lower() == ".xml":
                yield str(p.relative_to(ruta)), p.read_bytes()
            elif p.suffix.lower() == ".zip":
                yield from _fuentes(p)
    elif ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as z:
            for nombre in sorted(z.namelist()):
                if nombre.lower().endswith(".xml"):
                    yield nombre, z.read(nombre)
    elif ruta.suffix.lower() == ".xml":
        yield ruta.name, ruta.read_bytes()
    else:
        raise ValueError(f"Usa una carpeta, un ZIP o un XML: {ruta.name}")


def leer_facturas(ruta: str | Path) -> LecturaFE:
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe: {ruta}")
    filas, errores, huella, n = [], [], hashlib.sha256(), 0
    for nombre, contenido in _fuentes(ruta):
        n += 1
        huella.update(hashlib.sha256(contenido).digest())
        try:
            filas.append(leer_xml(contenido, nombre))
        except (ET.ParseError, ValueError) as e:
            errores.append({"archivo": nombre, "error": str(e)})
    facturas = pd.DataFrame(filas, columns=COLUMNAS)
    return LecturaFE(facturas=facturas, errores=errores, archivos=n, sha256=huella.hexdigest())
