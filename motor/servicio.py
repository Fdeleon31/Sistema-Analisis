"""Punto único para correr un encargo: lo usan la línea de comandos y la interfaz."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd

from conectores.catalogo import detectar_perfil, obtener_perfil, proponer_opciones_perfil
from conectores.estado_cuenta_pdf import leer_estado_cuenta
from conectores.sql_fuente import es_uri_sql, leer_archivo_sql, leer_conexion_sql
from . import __version__
from .bitacora import Bitacora
from .diagnostico import evaluar_confiabilidad_datos
from .ejecutor import ResultadoPrueba, cargar_manifiesto, correr_paquete
from .exportador import exportar_excel
from .factura_electronica import leer_facturas
from .importador import (
    EXTENSIONES_EXCEL,
    EXTENSIONES_SQL,
    EXTENSIONES_TEXTO,
    ErrorImportacion,
    _es_linea_borde_alv,
    _parece_sap_alv,
    detectar_codificacion,
    importar,
    validar_identificador,
)
from .rutas import raiz_recursos, raiz_salidas, raiz_trabajo
from .sugerencias import detectar_fila_encabezado

RAIZ = raiz_trabajo()
CARPETA_PAQUETES = raiz_recursos() / "paquetes"


def _carpeta_paquetes() -> Path:
    return raiz_recursos() / "paquetes"


@dataclass
class Corrida:
    manifiesto: dict
    controles: list[dict]
    resultados: list[ResultadoPrueba]
    cedula: Path
    bitacora: Bitacora
    carpeta: Path
    encargo: dict = field(default_factory=dict)
    diagnostico: dict = field(default_factory=dict)


def actualizar_cedula_corrida(corrida: Corrida) -> Path:
    """Regenera cedula.xlsx incorporando el último estado de revisiones, firmas y bitácora."""
    return exportar_excel(
        corrida.resultados,
        corrida.controles,
        corrida.bitacora,
        corrida.cedula,
        encargo=corrida.encargo,
        diagnostico=corrida.diagnostico or None,
    )


def paquetes_disponibles() -> dict[str, dict]:
    """{id: manifiesto} de cada carpeta de paquetes con manifiesto."""
    salida = {}
    for carpeta in sorted(_carpeta_paquetes().iterdir()):
        if (carpeta / "manifiesto.yaml").exists():
            m = cargar_manifiesto(carpeta)
            salida[m["id"]] = m
    return salida


def filas_crudas(ruta: Path, hoja: str | None = None) -> list[list[str]]:
    """Primeras filas sin interpretar encabezados, para detectar dónde empieza la tabla."""
    ext = ruta.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        try:
            ws = wb[hoja] if isinstance(hoja, str) and hoja in wb.sheetnames else wb.active
            return [["" if v is None else str(v) for v in fila] for fila in ws.iter_rows(max_row=20, values_only=True)]
        finally:
            wb.close()
    if ext in EXTENSIONES_EXCEL:
        return pd.read_excel(ruta, sheet_name=hoja or 0, header=None, nrows=20, dtype=str).values.tolist()
    if ext not in EXTENSIONES_TEXTO:
        return []
    cod = detectar_codificacion(ruta, max_bytes=262144)
    with ruta.open(encoding=cod, errors="replace", newline="") as f:
        lineas = [f.readline() for _ in range(20)]
    lineas = [ln for ln in lineas if ln]
    if any(ln.strip().startswith("|") and ln.strip().endswith("|") for ln in lineas):
        return [[ln.strip()] for ln in lineas]
    try:
        dialecto = csv.Sniffer().sniff("\n".join(lineas[-5:]), delimiters=",;\t|")
    except csv.Error:
        dialecto = csv.excel
    return list(csv.reader(lineas, dialecto))


def _columnas_origen(ruta: str | Path, extra: dict) -> list[str]:
    """Obtiene los encabezados de un archivo o fuente SQL sin importar la tabla completa."""
    tabla_origen = extra.get("tabla_origen")
    consulta_sql = extra.get("consulta_sql")
    hoja = extra.get("hoja")
    saltar = extra.get("saltar_filas")

    if es_uri_sql(ruta):
        df, _ = leer_conexion_sql(str(ruta), tabla_origen=tabla_origen, consulta_sql=consulta_sql, limite=5)
        return [str(c) for c in df.columns]

    ruta_path = Path(ruta)
    ext = ruta_path.suffix.lower()
    if ext in EXTENSIONES_SQL:
        df, _ = leer_archivo_sql(ruta_path, tabla_origen=tabla_origen, consulta_sql=consulta_sql, limite=5)
        return [str(c) for c in df.columns]
    if ext == ".parquet":
        con = duckdb.connect()
        try:
            return [c[0] for c in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(ruta_path)]).fetchall()]
        finally:
            con.close()
    if ext in (".json", ".jsonl", ".ndjson"):
        con = duckdb.connect()
        try:
            return [
                c[0]
                for c in con.execute("DESCRIBE SELECT * FROM read_json_auto(?, format = 'auto')", [str(ruta_path)]).fetchall()
            ]
        finally:
            con.close()
    if ext in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(ruta_path, read_only=True, data_only=True)
        try:
            ws = wb[hoja] if isinstance(hoja, str) else (wb.worksheets[hoja] if isinstance(hoja, int) else wb.active)
            salto = int(saltar or 0)
            for idx, fila in enumerate(ws.iter_rows(max_row=salto + 1, values_only=True)):
                if idx == salto:
                    return [str(v).strip() if v is not None else f"Unnamed: {i}" for i, v in enumerate(fila)]
            return []
        finally:
            wb.close()
    if ext in EXTENSIONES_EXCEL:
        df = pd.read_excel(ruta_path, sheet_name=hoja if hoja is not None else 0, skiprows=saltar, nrows=1, dtype=str)
        return [str(c).strip() for c in df.columns]
    if ext in EXTENSIONES_TEXTO:
        cod = extra.get("codificacion") or detectar_codificacion(ruta_path, max_bytes=262144)
        if _parece_sap_alv(ruta_path, cod, saltar):
            salto = int(saltar or 0)
            with ruta_path.open(encoding=cod, errors="replace") as f:
                for i, linea in enumerate(f):
                    if i < salto or _es_linea_borde_alv(linea):
                        continue
                    return [c.strip() for c in linea.strip().strip("|").split("|")]
        salto = int(saltar or 0)
        lineas: list[str] = []
        with ruta_path.open(encoding=cod, errors="replace", newline="") as f:
            for _ in range(salto + 10):
                ln = f.readline()
                if not ln:
                    break
                lineas.append(ln)
        kwargs = {"skiprows": saltar, "nrows": 1, "dtype": str}
        if ext in (".tsv", ".tab"):
            kwargs["sep"] = "\t"
        else:
            kwargs.update({"sep": None, "engine": "python"})
        df = pd.read_csv(io.StringIO("".join(lineas)), **kwargs)
        return [str(c).lstrip("\ufeff").strip() for c in df.columns]
    return []


def _aplicar_perfil_si_corresponde(
    ruta: str | Path,
    definicion: dict,
    extra: dict,
) -> dict:
    confirmado_ui = bool(extra.pop("_confirmado_ui", False))
    perfil_req = extra.get("perfil_erp")
    if not perfil_req or confirmado_ui:
        return extra

    if extra.get("saltar_filas") is None and not es_uri_sql(ruta):
        # Reportes con filas de título (empresa, nombre del reporte, periodo) antes del encabezado.
        ruta_p = Path(ruta)
        if ruta_p.suffix.lower() in EXTENSIONES_TEXTO | EXTENSIONES_EXCEL:
            filas = filas_crudas(ruta_p, extra.get("hoja"))
            if filas and not (len(filas[0]) == 1 and str(filas[0][0]).strip().startswith("|")):
                fila_enc = detectar_fila_encabezado(filas, list(definicion["columnas_requeridas"]))
                if fila_enc > 0:
                    extra["saltar_filas"] = fila_enc

    columnas = _columnas_origen(ruta, extra)
    if perfil_req == "auto":
        perfil, _ = detectar_perfil(columnas)
    else:
        perfil = obtener_perfil(perfil_req)

    if not perfil:
        extra.pop("perfil_erp", None)
        return extra

    extra["perfil_erp"] = perfil["id"]
    prop = proponer_opciones_perfil(perfil, columnas, list(definicion["columnas_requeridas"]))

    mapeo_manual = bool(extra.get("mapeo"))
    if not mapeo_manual:
        mapeo = {col: std for std, col in prop["mapeo_std_a_col"].items() if col and col != std}
        if mapeo:
            extra["mapeo"] = mapeo
    if not extra.get("debito_credito") and not extra.get("indicador_dc") and not (
        mapeo_manual and "monto" in (extra.get("mapeo") or {}).values()
    ):
        if prop["debito_credito"]:
            extra["debito_credito"] = prop["debito_credito"]
        elif prop["indicador_dc"]:
            extra["indicador_dc"] = prop["indicador_dc"]
    if extra.get("rellenar_hacia_abajo") is None and prop.get("rellenar_hacia_abajo"):
        extra["rellenar_hacia_abajo"] = True
    if "generar_linea" not in extra and prop["generar_linea"]:
        extra["generar_linea"] = True
    if "usuario_por_defecto" not in extra and prop["usuario_por_defecto"]:
        extra["usuario_por_defecto"] = prop["usuario_por_defecto"]
    if not extra.get("formato_fecha") and prop["formato_fecha"]:
        extra["formato_fecha"] = prop["formato_fecha"]
    if not extra.get("separador_decimal") and prop["separador_decimal"]:
        extra["separador_decimal"] = prop["separador_decimal"]
    return extra


def ejecutar_encargo(
    paquete: str,
    archivos: dict[str, Path | str],
    encargo: dict | None = None,
    salida: Path | None = None,
    opciones: dict[str, dict] | None = None,
    separador_decimal: str = ".",
) -> Corrida:
    """Importa los archivos del paquete, corre sus pruebas y exporta la cédula.

    opciones: {tabla: {mapeo, formato_fecha, saltar_filas, hoja, debito_credito,
               indicador_dc, generar_linea, usuario_por_defecto, separador_decimal,
               tabla_origen, consulta_sql, perfil_erp}}.
    """
    manifiesto = cargar_manifiesto(_carpeta_paquetes() / paquete)
    encargo = encargo or {}
    opciones = opciones or {}
    carpeta = Path(salida) if salida else raiz_salidas() / datetime.now().strftime("%Y%m%d-%H%M%S")
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
        if definicion.get("tipo") == "estado_cuenta_bancario":
            controles.append(_cargar_extracto_bancario(con, Path(archivos[tabla]), tabla, bitacora))
            continue
        extra = {k: v for k, v in (opciones.get(tabla) or {}).items() if v not in (None, "", {})}
        extra = _aplicar_perfil_si_corresponde(archivos[tabla], definicion, extra)
        sep_tabla = extra.pop("separador_decimal", separador_decimal)
        controles.append(importar(
            con, archivos[tabla], tabla,
            columnas_requeridas=definicion["columnas_requeridas"],
            columnas_monto=definicion.get("columnas_monto"),
            columnas_fecha=definicion.get("columnas_fecha"),
            claves=definicion.get("claves"),
            separador_decimal=sep_tabla,
            bitacora=bitacora,
            **extra,
        ))

    diagnostico = evaluar_confiabilidad_datos(con, controles, encargo)
    bitacora.registrar(
        "diagnostico",
        estado_general=diagnostico["estado_general"],
        resumen=diagnostico["resumen"],
        conteos=diagnostico["conteos"],
        hallazgos=diagnostico["hallazgos"],
    )
    resultados = correr_paquete(con, manifiesto, bitacora, encargo)
    cedula = exportar_excel(
        resultados,
        controles,
        bitacora,
        carpeta / "cedula.xlsx",
        encargo=encargo,
        diagnostico=diagnostico,
    )
    con.close()
    return Corrida(manifiesto, controles, resultados, cedula, bitacora, carpeta, dict(encargo), diagnostico)


def _registrar_dataframe_en_duckdb(
    con: duckdb.DuckDBPyConnection,
    tabla: str,
    df: pd.DataFrame,
    bitacora: Bitacora,
    evento: str,
    control: dict,
) -> dict:
    tabla_seg = validar_identificador(tabla)
    con.register("_tmp_carga", df)
    con.execute(f'CREATE OR REPLACE TABLE "{tabla_seg}" AS SELECT * FROM _tmp_carga')
    con.unregister("_tmp_carga")
    bitacora.registrar(evento, **control)
    return control


def _cargar_facturas(con, ruta: Path, tabla: str, bitacora: Bitacora) -> dict:
    """Lee los XML de factura electrónica y los registra como tabla; los ilegibles quedan en el control."""
    lectura = leer_facturas(ruta)
    if lectura.facturas.empty:
        raise ErrorImportacion(f"No encontré facturas electrónicas legibles en {ruta.name}.")
    control = {
        "archivo": ruta.name, "tabla": tabla, "sha256": lectura.sha256, "filas": len(lectura.facturas),
        "archivos_xml": lectura.archivos, "filas_excluidas": len(lectura.errores),
        "detalle_excluidas": [f"{e['archivo']}: {e['error']}" for e in lectura.errores],
        "codificacion": "XML", "transformaciones": [f"{lectura.archivos} XML leídos; {len(lectura.errores)} ilegibles"],
    }
    return _registrar_dataframe_en_duckdb(con, tabla, lectura.facturas, bitacora, "importacion_fe", control)


def _cargar_extracto_bancario(con, ruta: Path, tabla: str, bitacora: Bitacora) -> dict:
    """Lee estados de cuenta bancarios PDF o tabulares y registra líneas omitidas en bitácora."""
    lectura = leer_estado_cuenta(ruta)
    if lectura.movimientos.empty:
        raise ErrorImportacion(f"No encontré movimientos bancarios legibles en {ruta.name}.")
    bancos = ", ".join(sorted({str(b) for b in lectura.movimientos["banco"].dropna() if str(b)}))
    transformaciones = [
        f"{lectura.archivos} archivo(s) ({lectura.metodo.upper()}); "
        f"{len(lectura.movimientos)} movimientos ({bancos}); "
        f"{lectura.lineas_omitidas} líneas no transaccionales omitidas"
    ]
    for rs in lectura.resumen_saldos:
        if rs.get("cuadra") is True:
            transformaciones.append(
                f"{rs['archivo']}: cuadre de saldos OK (calc={rs['saldo_calculado']:,.2f})"
            )
        elif rs.get("cuadra") is False:
            transformaciones.append(
                f"{rs['archivo']}: descuadre de saldo calc={rs['saldo_calculado']:,.2f} vs "
                f"reportado={rs['saldo_final_objetivo']:,.2f} (dif={rs['diferencia']:,.2f})"
            )
    control = {
        "archivo": ruta.name,
        "tabla": tabla,
        "sha256": lectura.sha256,
        "filas": len(lectura.movimientos),
        "archivos_pdf": lectura.archivos,
        "filas_excluidas": lectura.lineas_omitidas,
        "detalle_excluidas": [f"{e['archivo']} L{e.get('linea', '?')}: {e['error']}" for e in lectura.errores],
        "resumen_saldos": lectura.resumen_saldos,
        "codificacion": lectura.metodo.upper(),
        "transformaciones": transformaciones,
    }
    return _registrar_dataframe_en_duckdb(con, tabla, lectura.movimientos, bitacora, "importacion_extracto", control)
