"""Importación con hash, normalización y totales de control (Ficha 00 y Ficha 12).

Principio: nada se corrige en silencio. Todo lo que se transforma o se excluye
queda en el control de importación y en la bitácora.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import re
import tempfile
import unicodedata
from datetime import date, datetime
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd

from conectores.sql_fuente import es_uri_sql, leer_archivo_sql, leer_conexion_sql
from .bitacora import Bitacora
from .seguridad import citar_identificador_sql, validar_formato_fecha_sql

IDENTIFICADOR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FORMATOS_FECHA = [
    "%d/%m/%Y", "%m/%d/%Y",
    "%d-%m-%Y", "%m-%d-%Y",
    "%d.%m.%Y", "%Y/%m/%d", "%Y.%m.%d",
    "%Y%m%d",
    "%d/%m/%y", "%m/%d/%y",
]
SIMBOLOS_MONEDA = r"(B/\.|USD|US\$|\$|€|\s)"
TIPOS_NUMERICOS = ("INT", "BIGINT", "SMALLINT", "TINYINT", "HUGEINT", "DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL")
DEBITOS_IND = {"S", "D", "DR", "DEBE", "DEBITO", "DEBIT", "+"}
CREDITOS_IND_DEFECTO = ("H", "C", "CR", "HABER", "CREDITO", "CREDIT", "-")
EXTENSIONES_TEXTO = {".csv", ".txt", ".tsv", ".tab", ".dat"}
EXTENSIONES_EXCEL = {".xlsx", ".xlsm", ".xls"}
EXTENSIONES_SQL = {".sqlite", ".sqlite3", ".db", ".duckdb", ".sql"}


class ErrorImportacion(ValueError):
    """Error con un mensaje pensado para el auditor, no para el programador."""


def validar_identificador(nombre: str) -> str:
    if not isinstance(nombre, str) or not IDENTIFICADOR.match(nombre):
        raise ValueError(f"Nombre no válido para tabla o columna: {nombre!r}")
    return nombre


def sha256_archivo(ruta: str | Path) -> str:
    h = hashlib.sha256()
    with Path(ruta).open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def detectar_codificacion(ruta: Path, max_bytes: int | None = 8 * 1024 * 1024) -> str:
    """Detecta UTF-16 (con BOM), UTF-8 o Windows-1252 leyendo hasta max_bytes (por defecto 8 MB)."""
    with ruta.open("rb") as f:
        inicio = f.read(4)
    if inicio.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    decodificador = codecs.getincrementaldecoder("utf-8")()
    leidos = 0
    tamano = ruta.stat().st_size
    try:
        with ruta.open("rb") as f:
            while True:
                por_leer = 1024 * 1024 if max_bytes is None else min(1024 * 1024, max_bytes - leidos)
                if por_leer <= 0:
                    break
                bloque = f.read(por_leer)
                if not bloque:
                    break
                leidos += len(bloque)
                decodificador.decode(bloque, final=False)
            if leidos >= tamano:
                decodificador.decode(b"", final=True)
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def importar(
    con: duckdb.DuckDBPyConnection,
    ruta: str | Path,
    tabla: str,
    mapeo: dict[str, str] | None = None,
    columnas_requeridas: list[str] | None = None,
    separador_decimal: str = ".",
    formato_fecha: str | None = None,
    saltar_filas: int | None = None,
    hoja: str | int | None = None,
    debito_credito: tuple[str, str] | None = None,
    codificacion: str | None = None,
    columnas_monto: list[str] | None = None,
    columnas_fecha: list[str] | None = None,
    claves: list[str] | None = None,
    bitacora: Bitacora | None = None,
    indicador_dc: str | tuple[str, tuple[str, ...]] | None = None,
    generar_linea: bool = False,
    usuario_por_defecto: str | None = None,
    tabla_origen: str | None = None,
    consulta_sql: str | None = None,
    perfil_erp: str | None = None,
    rellenar_hacia_abajo: bool = False,
) -> dict:
    """Carga un archivo o fuente SQL en DuckDB sin tocar el original, normaliza y devuelve el control.

    `rellenar_hacia_abajo`: en reportes agrupados (QuickBooks "Journal", Sage "General Journal") la fecha y
    el número de asiento solo aparecen en la primera línea; las demás líneas del asiento los heredan de la
    anterior. Solo se rellenan filas que tienen cuenta (los subtotales sin cuenta se siguen excluyendo) y
    cada relleno queda contado en el control de importación.
    """
    tabla = validar_identificador(tabla)
    if debito_credito and indicador_dc:
        raise ErrorImportacion("No uses --debito-credito e --indicador-dc al mismo tiempo.")

    control: dict = {"tabla": tabla, "transformaciones": []}
    if perfil_erp:
        control["perfil_erp"] = perfil_erp

    if es_uri_sql(ruta):
        try:
            df, meta = leer_conexion_sql(str(ruta), tabla_origen=tabla_origen, consulta_sql=consulta_sql)
        except ValueError as e:
            raise ErrorImportacion(str(e)) from e
        control.update(meta)
        control["transformaciones"].append(f"consulta SQL solo lectura: {meta['origen_sql']}")
        _registrar_dataframe(con, df, tabla)
    else:
        ruta_path = Path(ruta)
        if not ruta_path.exists():
            raise FileNotFoundError(f"No existe el archivo: {ruta_path}")
        if ruta_path.stat().st_size == 0:
            raise ErrorImportacion(f"El archivo está vacío: {ruta_path.name}")

        control["archivo"] = ruta_path.name
        control["sha256"] = sha256_archivo(ruta_path)
        extension = ruta_path.suffix.lower()
        if saltar_filas:
            control["transformaciones"].append(
                f"se omitieron {int(saltar_filas)} fila(s) de título antes del encabezado"
            )

        if extension in EXTENSIONES_TEXTO:
            codificacion = codificacion or detectar_codificacion(ruta_path)
            control["codificacion"] = codificacion
            _leer_texto_tabular(con, ruta_path, tabla, codificacion, saltar_filas, extension, control)
        elif extension in EXTENSIONES_EXCEL:
            if extension in (".xlsx", ".xlsm") and ruta_path.stat().st_size > 10 * 1024 * 1024:
                _leer_excel_grande_a_duckdb(con, ruta_path, tabla, hoja, saltar_filas, control)
            else:
                df = pd.read_excel(
                    ruta_path,
                    sheet_name=hoja if hoja is not None else 0,
                    skiprows=saltar_filas,
                    dtype=str,
                )
                control["hoja"] = hoja if hoja is not None else "primera"
                _registrar_dataframe(con, df, tabla)
        elif extension == ".parquet":
            control["codificacion"] = "Parquet"
            con.execute(f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM read_parquet(?)', [str(ruta_path)])
        elif extension in (".json", ".jsonl", ".ndjson"):
            control["codificacion"] = "JSON"
            con.execute(
                f"CREATE OR REPLACE TABLE \"{tabla}\" AS SELECT * FROM read_json_auto(?, format = 'auto')",
                [str(ruta_path)],
            )
        elif extension in EXTENSIONES_SQL:
            try:
                df, meta = leer_archivo_sql(ruta_path, tabla_origen=tabla_origen, consulta_sql=consulta_sql)
            except ValueError as e:
                raise ErrorImportacion(str(e)) from e
            control["codificacion"] = meta["codificacion"]
            control["origen_sql"] = meta["origen_sql"]
            control["transformaciones"].append(f"consulta SQL ({meta['codificacion']}): {meta['origen_sql']}")
            _registrar_dataframe(con, df, tabla)
        else:
            raise ErrorImportacion(
                f"Formato no soportado todavía: {extension}. "
                "Usa CSV, TSV, TXT (incluido SAP ALV), Excel, Parquet, JSON/JSONL, SQLite, DuckDB o .sql."
            )

    _limpiar_nombres(con, tabla)
    _aplicar_mapeo(con, tabla, mapeo, control.get("archivo", str(ruta)), control)

    if debito_credito:
        _crear_monto_desde_debito_credito(con, tabla, *debito_credito, separador_decimal, control)
    elif indicador_dc:
        _aplicar_indicador_dc(con, tabla, indicador_dc, separador_decimal, control)

    if rellenar_hacia_abajo:
        _rellenar_hacia_abajo(con, tabla, control)

    columnas_actuales = _columnas(con, tabla)
    if generar_linea and "linea" not in columnas_actuales and "asiento" in columnas_actuales:
        con.execute(
            f'CREATE OR REPLACE TABLE "{tabla}" AS '
            f'SELECT *, ROW_NUMBER() OVER (PARTITION BY "asiento") AS linea FROM "{tabla}"'
        )
        control["transformaciones"].append("linea: generada secuencialmente por asiento (no venía en el origen)")
        columnas_actuales = _columnas(con, tabla)

    if usuario_por_defecto is not None and "usuario" not in columnas_actuales:
        con.execute(f'ALTER TABLE "{tabla}" ADD COLUMN usuario VARCHAR')
        con.execute(f'UPDATE "{tabla}" SET usuario = ?', [str(usuario_por_defecto)])
        control["transformaciones"].append(
            f"usuario: asignado valor por defecto {usuario_por_defecto!r} (no venía en el origen)"
        )

    faltantes = [c for c in (columnas_requeridas or []) if c not in _columnas(con, tabla)]
    if faltantes:
        raise ErrorImportacion(
            f"Faltan columnas en {control['archivo']}: {', '.join(faltantes)}. "
            f"Columnas encontradas: {', '.join(_columnas(con, tabla))}. "
            "Usa --mapeo para renombrarlas o --debito-credito si el monto viene en dos columnas."
        )

    columnas = _columnas(con, tabla)
    for col in columnas_monto if columnas_monto is not None else ["monto"]:
        if col in columnas:
            _normalizar_monto(con, tabla, col, separador_decimal, control)
    for col in columnas_fecha if columnas_fecha is not None else ["fecha"]:
        if col in columnas:
            _normalizar_fecha(con, tabla, formato_fecha, control, col)
    for col in ("asiento", "linea"):
        if col in columnas:
            _normalizar_entero_si_aplica(con, tabla, col, control)
    for col in ("cuenta", "descripcion", "usuario"):
        if col in columnas:
            con.execute(f'ALTER TABLE "{tabla}" ALTER "{col}" TYPE VARCHAR USING TRIM(CAST("{col}" AS VARCHAR))')

    _excluir_filas_de_total(con, tabla, control, claves)
    control.update(_totales_control(con, tabla))
    control["columnas"] = _columnas(con, tabla)
    if bitacora:
        bitacora.registrar("importacion", **control)
    return control


# --- lectura ---------------------------------------------------------------

def _registrar_dataframe(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, tabla: str) -> None:
    con.register("_importacion", df)
    con.execute(f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM _importacion')
    con.unregister("_importacion")


def _celda_excel_a_texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def _leer_excel_grande_a_duckdb(
    con: duckdb.DuckDBPyConnection,
    ruta: Path,
    tabla: str,
    hoja: str | int | None,
    saltar_filas: int | None,
    control: dict,
) -> None:
    """Lee un archivo Excel pesado (> 10 MB) en modo streaming para mantener bajo el uso de RAM."""
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    temporal = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
    try:
        if isinstance(hoja, str):
            ws = wb[hoja]
            control["hoja"] = hoja
        elif isinstance(hoja, int):
            ws = wb.worksheets[hoja]
            control["hoja"] = hoja
        else:
            ws = wb.active
            control["hoja"] = "primera"

        salto = int(saltar_filas or 0)
        escritor = csv.writer(temporal)
        encabezado_escrito = False
        for idx, fila in enumerate(ws.iter_rows(values_only=True)):
            if idx < salto:
                continue
            valores = [_celda_excel_a_texto(v) for v in fila]
            if not encabezado_escrito:
                valores = [v if v else f"Unnamed: {i}" for i, v in enumerate(valores)]
                encabezado_escrito = True
            escritor.writerow(valores)
        temporal.close()
        control["transformaciones"].append("lectura Excel en streaming (archivo pesado)")
        con.execute(
            f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM read_csv(?, header = true, all_varchar = true)',
            [temporal.name],
        )
    finally:
        wb.close()
        temporal.close()
        Path(temporal.name).unlink(missing_ok=True)


def _es_linea_borde_alv(linea: str) -> bool:
    limpia = linea.strip()
    return not limpia or bool(re.match(r"^[\|\-\+\=\s]+$", limpia))


def _parece_sap_alv(ruta: Path, codificacion: str, saltar_filas: int | None) -> bool:
    salto = int(saltar_filas or 0)
    revisadas = 0
    con_pipe = 0
    with ruta.open(encoding=codificacion, errors="replace") as f:
        for i, linea in enumerate(f):
            if i < salto:
                continue
            limpia = linea.strip()
            if _es_linea_borde_alv(limpia):
                continue
            revisadas += 1
            if limpia.startswith("|") and limpia.endswith("|") and limpia.count("|") >= 3:
                con_pipe += 1
            if revisadas >= 5:
                break
    return revisadas > 0 and con_pipe == revisadas


def _leer_texto_tabular(
    con: duckdb.DuckDBPyConnection,
    ruta: Path,
    tabla: str,
    codificacion: str,
    saltar_filas: int | None,
    extension: str,
    control: dict,
) -> None:
    if _parece_sap_alv(ruta, codificacion, saltar_filas):
        temporal = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
        omitidas = 0
        salto = int(saltar_filas or 0)
        try:
            with ruta.open(encoding=codificacion, newline="") as f:
                escritor = csv.writer(temporal)
                for i, linea in enumerate(f):
                    if i < salto:
                        continue
                    limpia = linea.strip()
                    if _es_linea_borde_alv(limpia):
                        omitidas += 1
                        continue
                    celdas = [c.strip() for c in limpia.strip("|").split("|")]
                    escritor.writerow(celdas)
            temporal.close()
            control["transformaciones"].append(
                f"formato SAP ALV (|): limpio a columnas estándar ({omitidas} líneas separadoras/en blanco omitidas)"
            )
            con.execute(
                f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM read_csv(?, header = true, all_varchar = true)',
                [temporal.name],
            )
        finally:
            Path(temporal.name).unlink(missing_ok=True)
        return

    origen = ruta
    temporal = None
    if codificacion.lower() not in ("utf-8", "utf8"):
        temporal = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
        with ruta.open("r", encoding=codificacion, newline="") as f:
            while bloque := f.read(8 * 1024 * 1024):
                temporal.write(bloque)
        temporal.close()
        origen = Path(temporal.name)
    try:
        opciones = "header = true, all_varchar = true"
        if extension in (".tsv", ".tab"):
            opciones += ", delim = '\t'"
        if saltar_filas is not None:
            opciones += f", skip = {int(saltar_filas)}"
        con.execute(f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM read_csv(?, {opciones})', [str(origen)])
    finally:
        if temporal:
            Path(temporal.name).unlink(missing_ok=True)


def _columnas(con, tabla: str) -> list[str]:
    return [c[0] for c in con.execute(f"DESCRIBE {citar_identificador_sql(tabla)}").fetchall()]


def _tipos_columnas(con, tabla: str) -> dict[str, str]:
    return {c[0]: c[1].upper() for c in con.execute(f"DESCRIBE {citar_identificador_sql(tabla)}").fetchall()}


def _limpiar_nombres(con, tabla: str) -> None:
    """Quita BOM y espacios sobrantes en los encabezados."""
    tabla_q = citar_identificador_sql(tabla)
    for nombre in _columnas(con, tabla):
        limpio = nombre.replace("\ufeff", "").strip()
        if limpio != nombre:
            con.execute(
                f"ALTER TABLE {tabla_q} RENAME COLUMN {citar_identificador_sql(nombre)} "
                f"TO {citar_identificador_sql(limpio)}"
            )


def _aplicar_mapeo(
    con: duckdb.DuckDBPyConnection,
    tabla: str,
    mapeo: dict[str, str] | None,
    nombre_archivo: str,
    control: dict,
) -> None:
    if not mapeo:
        return
    tabla_q = citar_identificador_sql(tabla)
    cols = _columnas(con, tabla)
    for origen, destino in mapeo.items():
        validar_identificador(destino)
        if origen not in cols:
            raise ErrorImportacion(
                f"El mapeo menciona la columna {origen!r}, que no está en {nombre_archivo}. "
                f"Columnas encontradas: {', '.join(cols)}"
            )

    # Evita colisiones si el nombre destino ya existía en la tabla de origen.
    temporales: dict[str, str] = {}
    for idx, (origen, destino) in enumerate(mapeo.items()):
        if origen == destino:
            continue
        cols_ahora = _columnas(con, tabla)
        if destino in cols_ahora and destino not in mapeo:
            respaldo = f"_orig_{destino}"
            while respaldo in cols_ahora:
                respaldo += "_"
            con.execute(
                f"ALTER TABLE {tabla_q} RENAME COLUMN {citar_identificador_sql(destino)} "
                f"TO {citar_identificador_sql(respaldo)}"
            )
            control["transformaciones"].append(f"{destino}: columna original renombrada a {respaldo} por colisión de mapeo")
        tmp = f"__cuadra_map_{idx}__"
        con.execute(
            f"ALTER TABLE {tabla_q} RENAME COLUMN {citar_identificador_sql(origen)} "
            f"TO {citar_identificador_sql(tmp)}"
        )
        temporales[tmp] = destino

    for tmp, destino in temporales.items():
        con.execute(
            f"ALTER TABLE {tabla_q} RENAME COLUMN {citar_identificador_sql(tmp)} "
            f"TO {citar_identificador_sql(destino)}"
        )


# --- montos ----------------------------------------------------------------

def _expresion_monto(columna: str, separador_decimal: str) -> str:
    col_q = citar_identificador_sql(columna)
    texto = f"TRIM(CAST({col_q} AS VARCHAR))"
    negativo = f"(regexp_matches({texto}, '^\\(.*\\)$') OR {texto} LIKE '-%' OR {texto} LIKE '%-')"
    limpio = f"regexp_replace({texto}, '[()\\-]|{SIMBOLOS_MONEDA}', '', 'g')"
    if separador_decimal == ",":
        limpio = f"replace(replace({limpio}, '.', ''), ',', '.')"
    else:
        limpio = f"replace({limpio}, ',', '')"
    valor = f"TRY_CAST(NULLIF({limpio}, '') AS DECIMAL(18, 2))"
    return f"CASE WHEN {negativo} THEN -{valor} ELSE {valor} END"


def _es_tipo_numerico(tipo_sql: str) -> bool:
    return any(t in tipo_sql.upper() for t in TIPOS_NUMERICOS)


def _validar_textos_numericos(con, tabla: str, columna: str, expresion: str, separador_decimal: str) -> None:
    """Rechaza cadenas no vacías que no se puedan parsear como número antes de convertir/coercionar."""
    tabla_q = citar_identificador_sql(tabla)
    col_q = citar_identificador_sql(columna)
    malos = con.execute(
        f"SELECT {col_q} FROM {tabla_q} WHERE {col_q} IS NOT NULL "
        f"AND TRIM(CAST({col_q} AS VARCHAR)) <> '' AND ({expresion}) IS NULL LIMIT 5"
    ).fetchall()
    if malos:
        ejemplos = ", ".join(repr(m[0]) for m in malos)
        raise ErrorImportacion(
            f"No se pudieron leer algunos montos de la columna {columna!r} (ejemplos: {ejemplos}). "
            "Revisa el separador decimal (--decimal) o el formato del archivo."
        )


def _normalizar_monto(con, tabla: str, columna: str, separador_decimal: str, control: dict) -> None:
    tabla_q = citar_identificador_sql(tabla)
    col_q = citar_identificador_sql(columna)
    tipo_actual = _tipos_columnas(con, tabla).get(columna, "VARCHAR")
    if tipo_actual == "DECIMAL(18,2)":
        return
    if _es_tipo_numerico(tipo_actual):
        con.execute(f"ALTER TABLE {tabla_q} ALTER {col_q} TYPE DECIMAL(18, 2) USING CAST({col_q} AS DECIMAL(18, 2))")
        control["transformaciones"].append(f"{columna}: numérico ({tipo_actual}) a DECIMAL(18, 2)")
        return

    expresion = _expresion_monto(columna, separador_decimal)
    _validar_textos_numericos(con, tabla, columna, expresion, separador_decimal)
    con.execute(f"ALTER TABLE {tabla_q} ALTER {col_q} TYPE DECIMAL(18, 2) USING {expresion}")
    control["transformaciones"].append(f"{columna}: texto a número (separador decimal {separador_decimal!r})")


def _crear_monto_desde_debito_credito(con, tabla: str, debito: str, credito: str, separador_decimal: str, control: dict) -> None:
    tabla_q = citar_identificador_sql(tabla)
    deb_q = citar_identificador_sql(debito)
    cred_q = citar_identificador_sql(credito)
    columnas = _columnas(con, tabla)
    for col in (debito, credito):
        if col not in columnas:
            raise ErrorImportacion(f"No encuentro la columna {col!r}. Columnas: {', '.join(columnas)}")
    if "monto" in columnas:
        raise ErrorImportacion("El archivo ya tiene una columna 'monto'; no uses --debito-credito.")
    tipos = _tipos_columnas(con, tabla)
    es_num_d = _es_tipo_numerico(tipos.get(debito, "VARCHAR"))
    es_num_c = _es_tipo_numerico(tipos.get(credito, "VARCHAR"))
    exp_d = f"CAST({deb_q} AS DECIMAL(18, 2))" if es_num_d else _expresion_monto(debito, separador_decimal)
    exp_c = f"CAST({cred_q} AS DECIMAL(18, 2))" if es_num_c else _expresion_monto(credito, separador_decimal)
    if not es_num_d:
        _validar_textos_numericos(con, tabla, debito, exp_d, separador_decimal)
    if not es_num_c:
        _validar_textos_numericos(con, tabla, credito, exp_c, separador_decimal)
    con.execute(f"ALTER TABLE {tabla_q} ADD COLUMN monto DECIMAL(18, 2)")
    con.execute(f"UPDATE {tabla_q} SET monto = COALESCE({exp_d}, 0) - COALESCE({exp_c}, 0)")
    control["transformaciones"].append(f"monto = {debito} - {credito}")


def _norm_ind(valor: str) -> str:
    limpio = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode()
    return limpio.strip().upper()


def _aplicar_indicador_dc(
    con: duckdb.DuckDBPyConnection,
    tabla: str,
    indicador_dc: str | tuple[str, tuple[str, ...]],
    separador_decimal: str,
    control: dict,
) -> None:
    if isinstance(indicador_dc, (tuple, list)):
        col_ind, vals_cred = indicador_dc[0], indicador_dc[1]
    else:
        col_ind, vals_cred = indicador_dc, CREDITOS_IND_DEFECTO

    tabla_q = citar_identificador_sql(tabla)
    col_ind_q = citar_identificador_sql(col_ind)
    columnas = _columnas(con, tabla)
    if col_ind not in columnas:
        raise ErrorImportacion(f"No encuentro la columna indicadora D/H {col_ind!r}. Columnas: {', '.join(columnas)}")
    if "monto" not in columnas:
        raise ErrorImportacion("Para usar indicador Debe/Haber, primero debe existir o mapearse la columna 'monto'.")

    _normalizar_monto(con, tabla, "monto", separador_decimal, control)
    creditos = {_norm_ind(v) for v in vals_cred}
    validos = DEBITOS_IND | creditos

    distintos = [
        r[0] for r in con.execute(
            f"SELECT DISTINCT CAST({col_ind_q} AS VARCHAR) FROM {tabla_q} "
            f"WHERE {col_ind_q} IS NOT NULL AND TRIM(CAST({col_ind_q} AS VARCHAR)) <> ''"
        ).fetchall()
    ]
    desconocidos = [v for v in distintos if _norm_ind(v) not in validos]
    if desconocidos:
        raise ErrorImportacion(
            f"Indicador Debe/Haber desconocido en {col_ind!r}: {', '.join(repr(x) for x in desconocidos[:5])}. "
            f"Valores reconocidos: {', '.join(sorted(validos))}."
        )

    crudos_credito = [v for v in distintos if _norm_ind(v) in creditos]
    if crudos_credito:
        placeholders = ", ".join("?" for _ in crudos_credito)
        con.execute(
            f"UPDATE {tabla_q} SET monto = CASE "
            f"WHEN CAST({col_ind_q} AS VARCHAR) IN ({placeholders}) THEN -ABS(monto) "
            f"ELSE ABS(monto) END "
            f"WHERE monto IS NOT NULL",
            crudos_credito,
        )
    else:
        con.execute(f"UPDATE {tabla_q} SET monto = ABS(monto) WHERE monto IS NOT NULL")
    control["transformaciones"].append(f"monto: signo aplicado con indicador Debe/Haber {col_ind!r}")


# --- fechas ----------------------------------------------------------------

def _normalizar_fecha(con, tabla: str, formato_fecha: str | None, control: dict, columna: str = "fecha") -> None:
    tabla_q = citar_identificador_sql(tabla)
    col_q = citar_identificador_sql(columna)
    tipo_actual = _tipos_columnas(con, tabla).get(columna, "VARCHAR")
    if tipo_actual == "DATE":
        control["formato_fecha"] = "DATE nativo"
        return
    if "TIMESTAMP" in tipo_actual:
        con.execute(f"ALTER TABLE {tabla_q} ALTER {col_q} TYPE DATE USING CAST({col_q} AS DATE)")
        control["formato_fecha"] = "TIMESTAMP"
        control["transformaciones"].append(f"{columna}: TIMESTAMP a DATE")
        return

    if formato_fecha is not None:
        formato_fecha = validar_formato_fecha_sql(formato_fecha)

    texto = f"TRIM(CAST({col_q} AS VARCHAR))"
    total = con.execute(f"SELECT COUNT(*) FROM {tabla_q} WHERE {col_q} IS NOT NULL AND {texto} <> ''").fetchone()[0]

    def fallan(expresion: str) -> int:
        return con.execute(
            f"SELECT COUNT(*) FROM {tabla_q} WHERE {col_q} IS NOT NULL AND {texto} <> '' AND ({expresion}) IS NULL"
        ).fetchone()[0]

    def _exigir_siglo_actual(exp: str) -> str:
        return f"CASE WHEN EXTRACT(YEAR FROM ({exp})) >= 1900 THEN ({exp}) END"

    iso = f"COALESCE(TRY_CAST({texto} AS DATE), CAST(TRY_CAST({texto} AS TIMESTAMP) AS DATE))"
    candidatos = [(formato_fecha, f"CAST(TRY_STRPTIME({texto}, '{formato_fecha}') AS DATE)")] if formato_fecha else []
    if not formato_fecha:
        candidatos.append(("ISO aaaa-mm-dd", _exigir_siglo_actual(iso)))
        for f in FORMATOS_FECHA:
            exp = f"CAST(TRY_STRPTIME({texto}, '{f}') AS DATE)"
            if "%Y" in f:
                exp = _exigir_siglo_actual(exp)
            candidatos.append((f, exp))

    fallas = {nombre: fallan(exp) for nombre, exp in candidatos}
    validos = [(nombre, exp) for nombre, exp in candidatos if fallas[nombre] == 0]
    # Filas que no son fechas en absoluto (títulos, totales) se toleran si son muy pocas, pero solo
    # para el formato con MENOS fallas: un formato que además falla con fechas reales (p. ej. dd/mm ante
    # 01/15/2025) no compite y no vuelve "ambiguo" un archivo que no lo es.
    if not validos and candidatos:
        tolerancia = min(max(5, total // 1000), max(1, total // 20))
        minimo = min(fallas.values())
        validos = [(n, e) for n, e in candidatos if fallas[n] == minimo and minimo <= tolerancia]

    if not validos:
        ejemplos = con.execute(f"SELECT DISTINCT {col_q} FROM {tabla_q} WHERE {col_q} IS NOT NULL LIMIT 5").fetchall()
        raise ErrorImportacion(
            f"No reconozco el formato de fecha (ejemplos: {', '.join(repr(e[0]) for e in ejemplos)}). "
            'Indícalo con --formato-fecha, por ejemplo "%d/%m/%Y".'
        )

    nombres_validos = {n for n, _ in validos}
    pares_ambiguos = [
        ("%d/%m/%Y", "%m/%d/%Y"),
        ("%d/%m/%y", "%m/%d/%y"),
        ("%d-%m-%Y", "%m-%d-%Y"),
    ]
    if not formato_fecha and any(d in nombres_validos and m in nombres_validos for d, m in pares_ambiguos):
        raise ErrorImportacion(
            "Las fechas son ambiguas: todas sirven como día/mes y como mes/día (ningún día pasa de 12). "
            'Indica el formato con --formato-fecha "%d/%m/%Y" o "%m/%d/%Y".'
        )

    nombre, expresion = validos[0]
    fechas_fallidas = fallas[nombre]
    con.execute(f"ALTER TABLE {tabla_q} ALTER {col_q} TYPE DATE USING {expresion}")
    control["formato_fecha"] = nombre
    control["transformaciones"].append(f"{columna}: formato {nombre}")
    if fechas_fallidas:
        control["fechas_invalidas"] = int(fechas_fallidas)
        control["transformaciones"].append(
            f"{columna}: {fechas_fallidas} valor(es) no reconocibles convertidos a NULL (dentro de tolerancia)"
        )


# --- otros -----------------------------------------------------------------

def _rellenar_hacia_abajo(con, tabla: str, control: dict, columnas: tuple[str, ...] = ("fecha", "asiento")) -> None:
    """Copia fecha y asiento de la fila anterior a las líneas de detalle que los traen vacíos."""
    actuales = _columnas(con, tabla)
    cols = [c for c in columnas if c in actuales]
    if not cols or "cuenta" not in actuales:
        return
    tabla_q = citar_identificador_sql(tabla)

    def vacio(c: str) -> str:
        cq = citar_identificador_sql(c)
        return f"({cq} IS NULL OR TRIM(CAST({cq} AS VARCHAR)) = '')"

    cuenta_ok = f"NOT {vacio('cuenta')}"
    hijas = f"{cuenta_ok} AND " + " AND ".join(vacio(c) for c in cols)
    n = con.execute(f"SELECT COUNT(*) FROM {tabla_q} WHERE {hijas}").fetchone()[0]
    if not n:
        return
    reemplazos = []
    for c in cols:
        cq = citar_identificador_sql(c)
        reemplazos.append(
            f"CASE WHEN {hijas} THEN LAST_VALUE(NULLIF(TRIM(CAST({cq} AS VARCHAR)), '') IGNORE NULLS) "
            f"OVER (ORDER BY rowid ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) "
            f"ELSE CAST({cq} AS VARCHAR) END AS {cq}"
        )
    con.execute(
        f"CREATE OR REPLACE TABLE {tabla_q} AS SELECT * REPLACE ({', '.join(reemplazos)}) FROM {tabla_q} ORDER BY rowid"
    )
    control["filas_rellenadas"] = int(n)
    control["transformaciones"].append(
        f"{' y '.join(cols)}: copiados de la línea anterior en {n} línea(s) de detalle (reporte agrupado)"
    )


def _normalizar_entero_si_aplica(con, tabla: str, columna: str, control: dict) -> None:
    """Convierte a entero solo si todos los valores son números; si no, queda como texto."""
    tabla_q = citar_identificador_sql(tabla)
    col_q = citar_identificador_sql(columna)
    tipo_actual = _tipos_columnas(con, tabla).get(columna, "VARCHAR")
    if "INT" in tipo_actual and "BIGINT" == tipo_actual:
        return
    texto = f"TRIM(CAST({col_q} AS VARCHAR))"
    no_numericos = con.execute(
        f"SELECT COUNT(*) FROM {tabla_q} WHERE {col_q} IS NOT NULL AND {texto} <> '' "
        f"AND TRY_CAST({texto} AS BIGINT) IS NULL"
    ).fetchone()[0]
    if no_numericos == 0:
        con.execute(f"ALTER TABLE {tabla_q} ALTER {col_q} TYPE BIGINT USING TRY_CAST({texto} AS BIGINT)")
    else:
        con.execute(f"ALTER TABLE {tabla_q} ALTER {col_q} TYPE VARCHAR USING {texto}")
        control["transformaciones"].append(f"{columna}: se mantiene como texto (valores alfanuméricos)")


def _excluir_filas_de_total(con, tabla: str, control: dict, claves: list[str] | None = None) -> None:
    """Excluye filas con todas las columnas clave vacías (totales, subtotales, líneas en blanco) y lo reporta.

    Por defecto las claves son fecha y asiento (mayor). Para una balanza, la clave es la cuenta.
    """
    tabla_q = citar_identificador_sql(tabla)
    columnas = _columnas(con, tabla)
    claves = [c for c in (claves if claves is not None else ["fecha", "asiento"]) if c in columnas]
    condiciones = [
        f"({citar_identificador_sql(c)} IS NULL OR TRIM(CAST({citar_identificador_sql(c)} AS VARCHAR)) = '')"
        for c in claves
    ]
    if not condiciones:
        control["filas_excluidas"] = 0
        return
    donde = " AND ".join(condiciones)
    resumen = "COUNT(*)" + (', COALESCE(SUM("monto"), 0)' if "monto" in columnas else ", 0")
    if "monto" not in columnas and "saldo_final" in columnas:
        resumen = 'COUNT(*), COALESCE(SUM("saldo_final"), 0)'
    excluidas, monto = con.execute(f"SELECT {resumen} FROM {tabla_q} WHERE {donde}").fetchone()
    if excluidas:
        muestra = con.execute(f"SELECT * FROM {tabla_q} WHERE {donde} LIMIT 3").fetchall()
        con.execute(f"DELETE FROM {tabla_q} WHERE {donde}")
        control["detalle_excluidas"] = [str(m) for m in muestra]
    control["filas_excluidas"] = int(excluidas)
    control["monto_filas_excluidas"] = float(monto or 0)
    con.execute(f"SELECT COUNT(*) FROM {tabla_q}")


def _totales_control(con, tabla: str) -> dict:
    tabla_q = citar_identificador_sql(tabla)
    filas = con.execute(f"SELECT COUNT(*) FROM {tabla_q}").fetchone()[0]
    totales = {}
    for nombre, tipo, *_ in con.execute(f"DESCRIBE {tabla_q}").fetchall():
        if nombre in ("asiento", "linea"):
            continue
        if _es_tipo_numerico(tipo):
            valor = con.execute(f"SELECT SUM({citar_identificador_sql(nombre)}) FROM {tabla_q}").fetchone()[0]
            totales[nombre] = round(float(valor), 2) if valor is not None else None
    return {"filas": filas, "totales": totales}
