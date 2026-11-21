"""Punto único para correr un encargo: lo usan la línea de comandos y la interfaz."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb

from . import __version__
from .bitacora import Bitacora
from .ejecutor import ResultadoPrueba, cargar_manifiesto, correr_paquete
from .exportador import exportar_excel
from .factura_electronica import leer_facturas
from .importador import ErrorImportacion, importar, validar_identificador

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_PAQUETES = RAIZ / "paquetes"


@dataclass
class Corrida:
    manifiesto: dict
    controles: list[dict]
    resultados: list[ResultadoPrueba]
    cedula: Path
    bitacora: Bitacora
    carpeta: Path


def paquetes_disponibles() -> dict[str, dict]:
    """{id: manifiesto} de cada carpeta de paquetes con manifiesto."""
    salida = {}
    for carpeta in sorted(CARPETA_PAQUETES.iterdir()):
        if (carpeta / "manifiesto.yaml").exists():
            m = cargar_manifiesto(carpeta)
            salida[m["id"]] = m
    return salida


def ejecutar_encargo(
    paquete: str,
    archivos: dict[str, Path],
    encargo: dict | None = None,
    salida: Path | None = None,
    opciones: dict[str, dict] | None = None,
    separador_decimal: str = ".",
) -> Corrida:
    """Importa los archivos del paquete, corre sus pruebas y exporta la cédula.

    opciones: {tabla: {mapeo, formato_fecha, saltar_filas, hoja, debito_credito}}.
    """
    manifiesto = cargar_manifiesto(CARPETA_PAQUETES / paquete)
    encargo = encargo or {}
    opciones = opciones or {}
    carpeta = Path(salida) if salida else RAIZ / "salidas" / datetime.now().strftime("%Y%m%d-%H%M%S")
    carpeta.mkdir(parents=True, exist_ok=True)
    bitacora = Bitacora(carpeta / "bitacora.jsonl")
    bitacora.registrar("inicio", version_motor=__version__, paquete=manifiesto["id"],
                       version_paquete=manifiesto["version"], cliente=encargo.get("cliente"))

    con = duckdb.connect()
    controles = []
    for definicion in manifiesto["archivos"]:
        tabla = definicion["tabla"]
        if tabla not in archivos or archivos[tabla] is None:
            if definicion.get("opcional"):
                continue
            raise ErrorImportacion(f"El paquete necesita el archivo '{tabla}' ({definicion.get('descripcion', '')}).")
        if definicion.get("tipo") == "factura_electronica":
            controles.append(_cargar_facturas(con, Path(archivos[tabla]), tabla, bitacora))
            continue
        extra = {k: v for k, v in (opciones.get(tabla) or {}).items() if v not in (None, "", {})}
        controles.append(importar(
            con, archivos[tabla], tabla,
            columnas_requeridas=definicion["columnas_requeridas"],
            columnas_monto=definicion.get("columnas_monto"),
            columnas_fecha=definicion.get("columnas_fecha"),
            claves=definicion.get("claves"),
            separador_decimal=separador_decimal,
            bitacora=bitacora,
            **extra,
        ))

    resultados = correr_paquete(con, manifiesto, bitacora, encargo)
    cedula = exportar_excel(resultados, controles, bitacora, carpeta / "cedula.xlsx", encargo=encargo)
    con.close()
    return Corrida(manifiesto, controles, resultados, cedula, bitacora, carpeta)


def _cargar_facturas(con, ruta: Path, tabla: str, bitacora: Bitacora) -> dict:
    """Lee los XML de factura electrónica y los registra como tabla; los ilegibles quedan en el control."""
    tabla = validar_identificador(tabla)
    lectura = leer_facturas(ruta)
    if lectura.facturas.empty:
        raise ErrorImportacion(f"No encontré facturas electrónicas legibles en {ruta.name}.")
    con.register("_facturas", lectura.facturas)
    con.execute(f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM _facturas')
    con.unregister("_facturas")
    control = {
        "archivo": ruta.name, "tabla": tabla, "sha256": lectura.sha256, "filas": len(lectura.facturas),
        "archivos_xml": lectura.archivos, "filas_excluidas": len(lectura.errores),
        "detalle_excluidas": [f"{e['archivo']}: {e['error']}" for e in lectura.errores],
        "codificacion": "XML", "transformaciones": [f"{lectura.archivos} XML leídos; {len(lectura.errores)} ilegibles"],
    }
    bitacora.registrar("importacion_fe", **control)
    return control
