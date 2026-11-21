"""Importación con hash, normalización y totales de control (Ficha 00).

Principio: nada se corrige en silencio. Todo lo que se transforma o se excluye
queda en el control de importación y en la bitácora.
"""
from __future__ import annotations

import codecs
import hashlib
import re
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from .bitacora import Bitacora

IDENTIFICADOR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FORMATOS_FECHA = ["%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y"]
SIMBOLOS_MONEDA = r"(B/\.|USD|US\$|\$|€|\s)"


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


def detectar_codificacion(ruta: Path) -> str:
    """UTF-8 si todo el archivo decodifica como UTF-8; si no, Windows-1252."""
    decodificador = codecs.getincrementaldecoder("utf-8")()
    try:
        with ruta.open("rb") as f:
            for bloque in iter(lambda: f.read(1024 * 1024), b""):
                decodificador.decode(bloque)
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
) -> dict:
    """Carga un CSV o Excel en DuckDB sin tocar el original, normaliza y devuelve el control."""
    ruta = Path(ruta)
    tabla = validar_identificador(tabla)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo: {ruta}")
    if ruta.stat().st_size == 0:
        raise ErrorImportacion(f"El archivo está vacío: {ruta.name}")

    huella = sha256_archivo(ruta)
    extension = ruta.suffix.lower()
    control: dict = {"archivo": ruta.name, "tabla": tabla, "sha256": huella, "transformaciones": []}

    if extension in (".csv", ".txt"):
        codificacion = codificacion or detectar_codificacion(ruta)
        control["codificacion"] = codificacion
        _leer_csv(con, ruta, tabla, codificacion, saltar_filas)
    elif extension in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(ruta, sheet_name=hoja if hoja is not None else 0, skiprows=saltar_filas, dtype=str)
        control["hoja"] = hoja if hoja is not None else "primera"
        con.register("_importacion", df)
        con.execute(f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM _importacion')
        con.unregister("_importacion")
    else:
        raise ErrorImportacion(f"Formato no soportado todavía: {extension}. Usa CSV o Excel.")

    _limpiar_nombres(con, tabla)
    for origen, destino in (mapeo or {}).items():
        validar_identificador(destino)
        if origen not in _columnas(con, tabla):
            raise ErrorImportacion(
                f"El mapeo menciona la columna {origen!r}, que no está en {ruta.name}. "
                f"Columnas encontradas: {', '.join(_columnas(con, tabla))}"
            )
        con.execute(f'ALTER TABLE "{tabla}" RENAME COLUMN "{origen}" TO "{destino}"')

    if debito_credito:
        _crear_monto_desde_debito_credito(con, tabla, *debito_credito, separador_decimal, control)

    faltantes = [c for c in (columnas_requeridas or []) if c not in _columnas(con, tabla)]
    if faltantes:
        raise ErrorImportacion(
            f"Faltan columnas en {ruta.name}: {', '.join(faltantes)}. "
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
            con.execute(f'UPDATE "{tabla}" SET "{col}" = TRIM(CAST("{col}" AS VARCHAR))')

    _excluir_filas_de_total(con, tabla, control, claves)
    control.update(_totales_control(con, tabla))
    control["columnas"] = _columnas(con, tabla)
    if bitacora:
        bitacora.registrar("importacion", **control)
    return control


# --- lectura ---------------------------------------------------------------

def _leer_csv(con, ruta: Path, tabla: str, codificacion: str, saltar_filas: int | None) -> None:
    origen = ruta
    temporal = None
    if codificacion.lower() not in ("utf-8", "utf8"):
        temporal = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
        with ruta.open(encoding=codificacion, newline="") as f:
            for linea in f:
                temporal.write(linea)
        temporal.close()
        origen = Path(temporal.name)
    try:
        opciones = "header = true, all_varchar = true"
        if saltar_filas is not None:
            opciones += f", skip = {int(saltar_filas)}"
        con.execute(f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM read_csv(?, {opciones})', [str(origen)])
    finally:
        if temporal:
            Path(temporal.name).unlink(missing_ok=True)


def _columnas(con, tabla: str) -> list[str]:
    return [c[0] for c in con.execute(f'DESCRIBE "{tabla}"').fetchall()]


def _limpiar_nombres(con, tabla: str) -> None:
    """Quita BOM y espacios sobrantes en los encabezados."""
    for nombre in _columnas(con, tabla):
        limpio = nombre.replace("﻿", "").strip()
        if limpio != nombre:
            con.execute(f'ALTER TABLE "{tabla}" RENAME COLUMN "{nombre}" TO "{limpio}"')


# --- montos ----------------------------------------------------------------

def _expresion_monto(columna: str, separador_decimal: str) -> str:
    texto = f"TRIM(CAST(\"{columna}\" AS VARCHAR))"
    negativo = f"(regexp_matches({texto}, '^\\(.*\\)$') OR {texto} LIKE '-%' OR {texto} LIKE '%-')"
    limpio = f"regexp_replace({texto}, '[()\\-]|{SIMBOLOS_MONEDA}', '', 'g')"
    if separador_decimal == ",":
        limpio = f"replace(replace({limpio}, '.', ''), ',', '.')"
    else:
        limpio = f"replace({limpio}, ',', '')"
    valor = f"TRY_CAST(NULLIF({limpio}, '') AS DECIMAL(18, 2))"
    return f"CASE WHEN {negativo} THEN -{valor} ELSE {valor} END"


def _normalizar_monto(con, tabla: str, columna: str, separador_decimal: str, control: dict) -> None:
    expresion = _expresion_monto(columna, separador_decimal)
    malos = con.execute(
        f'SELECT "{columna}" FROM "{tabla}" WHERE "{columna}" IS NOT NULL '
        f"AND TRIM(CAST(\"{columna}\" AS VARCHAR)) <> '' AND ({expresion}) IS NULL LIMIT 5"
    ).fetchall()
    if malos:
        ejemplos = ", ".join(repr(m[0]) for m in malos)
        raise ErrorImportacion(
            f"No se pudieron leer algunos montos de la columna {columna!r} (ejemplos: {ejemplos}). "
            "Revisa el separador decimal (--decimal) o el formato del archivo."
        )
    con.execute(f'ALTER TABLE "{tabla}" ALTER "{columna}" TYPE DECIMAL(18, 2) USING {expresion}')
    control["transformaciones"].append(f"{columna}: texto a número (separador decimal {separador_decimal!r})")


def _crear_monto_desde_debito_credito(con, tabla: str, debito: str, credito: str, separador_decimal: str, control: dict) -> None:
    columnas = _columnas(con, tabla)
    for col in (debito, credito):
        if col not in columnas:
            raise ErrorImportacion(f"No encuentro la columna {col!r}. Columnas: {', '.join(columnas)}")
    if "monto" in columnas:
        raise ErrorImportacion("El archivo ya tiene una columna 'monto'; no uses --debito-credito.")
    exp_d = _expresion_monto(debito, separador_decimal)
    exp_c = _expresion_monto(credito, separador_decimal)
    con.execute(f'ALTER TABLE "{tabla}" ADD COLUMN monto DECIMAL(18, 2)')
    con.execute(f'UPDATE "{tabla}" SET monto = COALESCE({exp_d}, 0) - COALESCE({exp_c}, 0)')
    control["transformaciones"].append(f"monto = {debito} - {credito}")


# --- fechas ----------------------------------------------------------------

def _normalizar_fecha(con, tabla: str, formato_fecha: str | None, control: dict, columna: str = "fecha") -> None:
    texto = f'TRIM(CAST("{columna}" AS VARCHAR))'
    total = con.execute(f'SELECT COUNT(*) FROM "{tabla}" WHERE "{columna}" IS NOT NULL AND {texto} <> \'\'').fetchone()[0]

    def fallan(expresion: str) -> int:
        return con.execute(
            f'SELECT COUNT(*) FROM "{tabla}" WHERE "{columna}" IS NOT NULL AND {texto} <> \'\' AND ({expresion}) IS NULL'
        ).fetchone()[0]

    iso = f"COALESCE(TRY_CAST({texto} AS DATE), CAST(TRY_CAST({texto} AS TIMESTAMP) AS DATE))"
    candidatos = [(formato_fecha, f"CAST(TRY_STRPTIME({texto}, '{formato_fecha}') AS DATE)")] if formato_fecha else []
    if not formato_fecha:
        candidatos.append(("ISO aaaa-mm-dd", iso))
        candidatos += [(f, f"CAST(TRY_STRPTIME({texto}, '{f}') AS DATE)") for f in FORMATOS_FECHA]

    validos = [(nombre, exp) for nombre, exp in candidatos if fallan(exp) == 0]
    # Filas que no son fechas en absoluto (títulos, totales) se toleran si son muy pocas.
    if not validos:
        tolerancia = max(5, total // 1000)
        validos = [(n, e) for n, e in candidatos if fallan(e) <= tolerancia]

    if not validos:
        ejemplos = con.execute(f'SELECT DISTINCT "{columna}" FROM "{tabla}" WHERE "{columna}" IS NOT NULL LIMIT 5').fetchall()
        raise ErrorImportacion(
            f"No reconozco el formato de fecha (ejemplos: {', '.join(repr(e[0]) for e in ejemplos)}). "
            'Indícalo con --formato-fecha, por ejemplo "%d/%m/%Y".'
        )

    dia_mes = [n for n, _ in validos if n in ("%d/%m/%Y", "%d/%m/%y")]
    mes_dia = [n for n, _ in validos if n == "%m/%d/%Y"]
    if not formato_fecha and dia_mes and mes_dia:
        raise ErrorImportacion(
            "Las fechas son ambiguas: todas sirven como día/mes y como mes/día (ningún día pasa de 12). "
            'Indica el formato con --formato-fecha "%d/%m/%Y" o "%m/%d/%Y".'
        )

    nombre, expresion = validos[0]
    con.execute(f'ALTER TABLE "{tabla}" ALTER "{columna}" TYPE DATE USING {expresion}')
    control["formato_fecha"] = nombre
    control["transformaciones"].append(f"{columna}: formato {nombre}")


# --- otros -----------------------------------------------------------------

def _normalizar_entero_si_aplica(con, tabla: str, columna: str, control: dict) -> None:
    """Convierte a entero solo si todos los valores son números; si no, queda como texto."""
    texto = f'TRIM(CAST("{columna}" AS VARCHAR))'
    no_numericos = con.execute(
        f'SELECT COUNT(*) FROM "{tabla}" WHERE "{columna}" IS NOT NULL AND {texto} <> \'\' '
        f"AND TRY_CAST({texto} AS BIGINT) IS NULL"
    ).fetchone()[0]
    if no_numericos == 0:
        con.execute(f'ALTER TABLE "{tabla}" ALTER "{columna}" TYPE BIGINT USING TRY_CAST({texto} AS BIGINT)')
    else:
        con.execute(f'UPDATE "{tabla}" SET "{columna}" = {texto}')
        control["transformaciones"].append(f"{columna}: se mantiene como texto (valores alfanuméricos)")


def _excluir_filas_de_total(con, tabla: str, control: dict, claves: list[str] | None = None) -> None:
    """Excluye filas con todas las columnas clave vacías (totales, subtotales, líneas en blanco) y lo reporta.

    Por defecto las claves son fecha y asiento (mayor). Para una balanza, la clave es la cuenta.
    """
    columnas = _columnas(con, tabla)
    claves = [c for c in (claves if claves is not None else ["fecha", "asiento"]) if c in columnas]
    condiciones = [f"(\"{c}\" IS NULL OR TRIM(CAST(\"{c}\" AS VARCHAR)) = '')" for c in claves]
    if not condiciones:
        control["filas_excluidas"] = 0
        return
    donde = " AND ".join(condiciones)
    resumen = "COUNT(*)" + (', COALESCE(SUM("monto"), 0)' if "monto" in columnas else ", 0")
    if "monto" not in columnas and "saldo_final" in columnas:
        resumen = 'COUNT(*), COALESCE(SUM("saldo_final"), 0)'
    excluidas, monto = con.execute(f'SELECT {resumen} FROM "{tabla}" WHERE {donde}').fetchone()
    if excluidas:
        muestra = con.execute(f'SELECT * FROM "{tabla}" WHERE {donde} LIMIT 3').fetchall()
        con.execute(f'DELETE FROM "{tabla}" WHERE {donde}')
        control["detalle_excluidas"] = [str(m) for m in muestra]
    control["filas_excluidas"] = int(excluidas)
    control["monto_filas_excluidas"] = float(monto or 0)
    con.execute(f'SELECT COUNT(*) FROM "{tabla}"')


def _totales_control(con, tabla: str) -> dict:
    filas = con.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]
    totales = {}
    for nombre, tipo, *_ in con.execute(f'DESCRIBE "{tabla}"').fetchall():
        if nombre in ("asiento", "linea"):
            continue
        if any(t in tipo.upper() for t in ("INT", "DOUBLE", "DECIMAL", "FLOAT", "REAL")):
            valor = con.execute(f'SELECT SUM("{nombre}") FROM "{tabla}"').fetchone()[0]
            totales[nombre] = round(float(valor), 2) if valor is not None else None
    return {"filas": filas, "totales": totales}
