"""Utilidades compartidas sin dependencias de UI para las interfaces Web y Escritorio."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import openpyxl
import pandas as pd

from conectores.sql_fuente import leer_archivo_sql
from motor.importador import (
    EXTENSIONES_EXCEL,
    EXTENSIONES_SQL,
    EXTENSIONES_TEXTO,
    _es_linea_borde_alv,
    _parece_sap_alv,
    detectar_codificacion,
)

NOMBRE_MARCA = "FOLIO AUDITOR"
LEMA_MARCA = "Mesa de Auditoría Determinista · Analítica NIA"

FORMATOS_FECHA: dict[str, str | None] = {
    "Detectar automáticamente": None,
    "día/mes/año (31/12/2025)": "%d/%m/%Y",
    "mes/día/año (12/31/2025)": "%m/%d/%Y",
    "año-mes-día (2025-12-31)": "%Y-%m-%d",
    "SAP aaaammdd (20251231)": "%Y%m%d",
}

SEPARADORES_DECIMALES: dict[str, str] = {
    "Punto (1,234.56)": ".",
    "Coma (1.234,56)": ",",
}

EXTENSIONES_SOPORTADAS = [
    "csv", "tsv", "tab", "txt", "dat",
    "xlsx", "xlsm", "xls",
    "parquet", "json", "jsonl", "ndjson",
    "sqlite", "sqlite3", "db", "duckdb", "sql",
]

HERRAMIENTAS = [
    (
        "asientos-nia240",
        "Asientos NIA 240",
        "Pruebas de asientos de diario, mayor contra balanza, estratificación, puntaje de riesgo explicable y selección de muestra.",
        ["NIA 240", "NIA 315", "NIA 330", "NIA 500", "NIA 530"],
    ),
    (
        "excepciones-basicas",
        "Excepciones básicas",
        "Analítica del mayor general: Ley de Benford (1 y 2 dígitos), duplicados exactos, mismo-mismo-distinto y gaps de secuencia o fechas.",
        ["NIA 240", "NIA 500", "NIA 520"],
    ),
    (
        "ventas-fe",
        "Factura DGI",
        "Validación de XML de factura electrónica de Panamá (SFEP/DGI), consistencia de totales, CUFE repetidos, huecos y conciliación de ventas.",
        ["NIA 500", "NIA 240", "DGI SFEP"],
    ),
    (
        "bancos-conciliacion",
        "Bancos PDF",
        "Lectura sin internet de estados de cuenta bancarios en PDF (bancos de Panamá), continuidad aritmética de saldos y conciliación contra el mayor.",
        ["NIA 500", "NIA 330", "BANCOS PA"],
    ),
    (
        "muestreo-mus",
        "Muestreo MUS",
        "Determinación de tamaño, selección sistemática por unidad monetaria (MUS) y evaluación estadística del límite superior de error.",
        ["NIA 530", "AICPA MUS"],
    ),
    (
        "conectores",
        "Conectores ERP / SQL",
        "Catálogo de los 10 sistemas contables de Panamá, mapeo automático de encabezados y consultas SQL de extracción en solo lectura.",
        ["SAP / ERP", "SQL SOLO LECTURA"],
    ),
    (
        "copiloto",
        "Copiloto SQL",
        "Asistente sin internet: propone SQL SELECT visible desde español natural, ejecuta en DuckDB tras tu aprobación y redacta el borrador NIA.",
        ["NIA 230", "NIA 500", "SQL VISIBLE"],
    ),
    (
        "bitacora",
        "Bitácora y Cédula",
        "Evidencia encadenada SHA-256, trazabilidad de importaciones y transformaciones, y descarga de la cédula de trabajo en Excel.",
        ["NIA 230", "SHA-256"],
    ),
    (
        "encargos",
        "Encargos y Firmas",
        "Portafolio de encargos (.yaml), historial de corridas y flujo de revisión por roles (Preparador, Revisor, Socio) bajo NIA 220/230.",
        ["NIA 220", "NIA 230", "ROLES"],
    ),
]


def formatear_tamano(bytes_totales: int) -> str:
    """Devuelve un tamaño legible (B, KB, MB, GB) sin alterar el valor real."""
    valor = float(bytes_totales)
    for unidad in ("B", "KB", "MB", "GB"):
        if valor < 1024.0 or unidad == "GB":
            return f"{valor:,.1f} {unidad}" if unidad != "B" else f"{int(valor)} B"
        valor /= 1024.0
    return f"{bytes_totales} B"


def _celda_previa(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def _vista_previa_alv(ruta: Path, codificacion: str, saltar: int) -> pd.DataFrame:
    filas: list[list[str]] = []
    salto = int(saltar or 0)
    with ruta.open(encoding=codificacion, errors="replace") as f:
        for i, linea in enumerate(f):
            if i < salto or _es_linea_borde_alv(linea):
                continue
            filas.append([c.strip() for c in linea.strip().strip("|").split("|")])
            if len(filas) >= 21:
                break
    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas[1:], columns=filas[0])


def vista_previa(
    ruta: Path,
    hoja: str | None = None,
    saltar: int = 0,
    tabla_sql: str | None = None,
    consulta_sql: str | None = None,
) -> pd.DataFrame:
    """Lee únicamente las primeras 20 filas para vista previa rápida, sin importar el tamaño del archivo."""
    ext = ruta.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        try:
            ws = wb[hoja] if isinstance(hoja, str) and hoja in wb.sheetnames else wb.active
            salto = int(saltar or 0)
            filas: list[list[str | None]] = []
            for idx, fila in enumerate(ws.iter_rows(max_row=salto + 21, values_only=True)):
                if idx < salto:
                    continue
                filas.append([_celda_previa(v) for v in fila])
            if not filas:
                return pd.DataFrame()
            encabezados = [v if v else f"Unnamed: {i}" for i, v in enumerate(filas[0])]
            ancho = len(encabezados)
            datos = [(f + [None] * ancho)[:ancho] for f in filas[1:]]
            return pd.DataFrame(datos, columns=encabezados)
        finally:
            wb.close()
    if ext in EXTENSIONES_EXCEL:
        return pd.read_excel(ruta, sheet_name=hoja or 0, skiprows=saltar or None, nrows=20, dtype=str)
    if ext == ".parquet":
        con = duckdb.connect()
        try:
            return con.execute("SELECT * FROM read_parquet(?) LIMIT 20", [str(ruta)]).df()
        finally:
            con.close()
    if ext in (".json", ".jsonl", ".ndjson"):
        con = duckdb.connect()
        try:
            return con.execute("SELECT * FROM read_json_auto(?, format = 'auto') LIMIT 20", [str(ruta)]).df()
        finally:
            con.close()
    if ext in EXTENSIONES_SQL:
        df, _ = leer_archivo_sql(ruta, tabla_origen=tabla_sql, consulta_sql=consulta_sql, limite=20)
        return df
    cod = detectar_codificacion(ruta, max_bytes=262144)
    if _parece_sap_alv(ruta, cod, saltar):
        return _vista_previa_alv(ruta, cod, saltar)
    salto = int(saltar or 0)
    lineas: list[str] = []
    with ruta.open(encoding=cod, errors="replace", newline="") as f:
        for _ in range(salto + 25):
            ln = f.readline()
            if not ln:
                break
            lineas.append(ln)
    muestra = io.StringIO("".join(lineas))
    if ext in (".tsv", ".tab"):
        return pd.read_csv(muestra, sep="\t", skiprows=saltar or None, nrows=20, dtype=str)
    return pd.read_csv(muestra, sep=None, engine="python", skiprows=saltar or None, nrows=20, dtype=str)


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


def hojas_excel(ruta: Path) -> list[str]:
    ext = ruta.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        wb = openpyxl.load_workbook(ruta, read_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()
    if ext in EXTENSIONES_EXCEL:
        return pd.ExcelFile(ruta).sheet_names
    return []


def formatear_fechas_df(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte columnas de fecha/timestamp a YYYY-MM-DD limpio para lectura contable."""
    salida = df.copy()
    for col in salida.columns:
        if pd.api.types.is_datetime64_any_dtype(salida[col]):
            salida[col] = salida[col].dt.strftime("%Y-%m-%d").fillna("")
        elif col in ("fecha", "dia") and len(salida) > 0:
            conv = pd.to_datetime(salida[col], errors="coerce")
            if conv.notna().all():
                salida[col] = conv.dt.strftime("%Y-%m-%d")
    return salida


def pesos_defecto_puntaje(manifiesto: dict) -> tuple[dict[str, int], int, int]:
    """Obtiene los pesos y umbrales por defecto del puntaje de riesgo desde el manifiesto."""
    for pr in manifiesto.get("pruebas", []):
        if pr.get("id") == "asientos-puntaje":
            params = pr.get("parametros", {})
            pesos = {k: int(v) for k, v in (params.get("pesos") or {}).items()}
            return pesos, 25, 15
    return {}, 25, 15


def _normalizar_fecha(valor: Any) -> date | None:
    """Convierte date, datetime o cadena ISO a date; devuelve None si es inválido."""
    if valor is None or valor is pd.NaT:
        return None
    if isinstance(valor, datetime):
        return date(valor.year, valor.month, valor.day)
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        txt = valor.strip()
        if not txt:
            return None
        try:
            return date.fromisoformat(txt)
        except ValueError:
            try:
                return datetime.fromisoformat(txt).date()
            except ValueError:
                return None
    return None


def calcular_periodo_inicio(fecha_cierre: Any) -> date:
    """Calcula el inicio de período anual a partir de fecha_cierre con respaldo seguro."""
    fc = _normalizar_fecha(fecha_cierre)
    if fc is None:
        return date(2025, 1, 1)
    if fc.month == 12:
        return date(fc.year, 1, 1)
    if fc.year <= 1:
        return date(2025, 1, 1)
    return date(fc.year - 1, fc.month + 1, 1)


def formatear_periodo_auditado(periodo_inicio: Any, fecha_cierre: Any) -> str:
    """Normaliza inicio y cierre de período auditado y devuelve 'YYYY-MM-DD al YYYY-MM-DD'."""
    fc = _normalizar_fecha(fecha_cierre) or date(2025, 12, 31)
    pi = _normalizar_fecha(periodo_inicio) or calcular_periodo_inicio(fc)
    return f"{pi.isoformat()} al {fc.isoformat()}"


def constancia_tiempo_real() -> tuple[str, str]:
    """Devuelve marcas de tiempo reales (local con zona corta, UTC) para constancia de auditoría."""
    loc = datetime.now().astimezone()
    utc = loc.astimezone(timezone.utc)
    nombre_tz = (loc.tzname() or "").strip()
    if nombre_tz and len(nombre_tz) <= 6 and " " not in nombre_tz:
        tz = nombre_tz
    else:
        offset = loc.strftime("%z")
        if offset in ("", "+0000", "-0000"):
            tz = "UTC"
        elif len(offset) == 5 and offset.endswith("00"):
            tz = offset[:3]
        elif len(offset) == 5:
            tz = f"{offset[:3]}:{offset[3:]}"
        else:
            tz = offset or "UTC"
    return (f"{loc:%Y-%m-%d  %H:%M:%S} ({tz})", f"{utc:%Y-%m-%d %H:%M:%S} UTC")


def formula_contextual(
    hid: str,
    cliente: str,
    fecha_cierre: Any,
    materialidad: float,
    estado_bit: str,
    periodo_inicio: Any = None,
) -> tuple[str, str]:
    """Construye el nombre de cuadro y la fórmula contextual de la barra de auditoría."""
    fc = _normalizar_fecha(fecha_cierre)
    cierre_txt = fc.isoformat() if fc is not None else str(fecha_cierre)
    periodo_txt = formatear_periodo_auditado(periodo_inicio, fecha_cierre)
    mapa = {
        "asientos-nia240": (
            "NIA-240",
            f'=AUDITAR.DIARIO(Cliente="{cliente}"; Periodo="{periodo_txt}"; Cierre="{cierre_txt}"; Materialidad={materialidad:,.2f}; Puntaje="10 criterios")',
        ),
        "excepciones-basicas": (
            "BENFORD-01",
            '=ANALIZAR.MAYOR(Pruebas="Benford 1-2, Duplicados, Mismo-Distinto, Gaps"; Feriados="Panamá")',
        ),
        "ventas-fe": (
            "DGI-SFEP",
            f'=CONCILIAR.FE(Formato="XML DGI"; Cierre="{cierre_txt}"; Control="CUFE, Totales, Secuencia")',
        ),
        "bancos-conciliacion": (
            "BANCO-01",
            f'=CONCILIAR.BANCOS(Origen="PDF / CSV"; Cierre="{cierre_txt}"; Cuenta="1101"; Ventana="±5 días")',
        ),
        "muestreo-mus": (
            "MUS-530",
            '=MUESTREAR.MUS(Confianza="95 % / 90 %"; Metodo="Sistematico"; Evaluacion="LimiteSuperiorError")',
        ),
        "conectores": (
            "ERP-SQL",
            '=CONECTAR.PANAMA(Perfiles=13; Formatos="SAP ALV, Parquet, JSON, SQLite, DuckDB, SQL RO")',
        ),
        "copiloto": (
            "IA-SQL",
            f'=COPILOTO.AUDITOR(Modo="100% Offline"; Aprobacion="Auditor"; Motor="DuckDB"; Cierre="{cierre_txt}")',
        ),
        "bitacora": (
            "BITACORA",
            f'=AUDITAR.EVIDENCIA(Cadena="SHA-256"; Estado="{estado_bit}"; Exportacion="cedula.xlsx")',
        ),
        "encargos": (
            "PORTAFOLIO",
            f'=GESTIONAR.FIRMA(Cliente="{cliente}"; Periodo="{periodo_txt}"; Roles="Preparador -> Revisor -> Socio"; Norma="NIA 220")',
        ),
    }
    return mapa[hid]


def cargar_dataframe_muestreo(ruta: Path) -> pd.DataFrame:
    """Carga tabulares CSV/TSV/Excel/Parquet para población o resultados MUS."""
    ext = ruta.suffix.lower()
    if ext == ".parquet":
        con = duckdb.connect()
        try:
            return con.execute("SELECT * FROM read_parquet(?)", [str(ruta)]).df()
        finally:
            con.close()
    if ext in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(ruta)
    cod = detectar_codificacion(ruta, max_bytes=262144)
    return pd.read_csv(ruta, sep=None, engine="python", encoding=cod)
