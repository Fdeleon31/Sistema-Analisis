"""Ficha 14 · Copiloto en lenguaje natural 100 % sin internet y redactor de hallazgos NIA.

Principio: la IA/copiloto propone SQL visible y redacta estructura de papel de trabajo;
el motor DuckDB calcula de forma determinista; el auditor aprueba explícitamente.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from conectores.estado_cuenta_pdf import leer_estado_cuenta
from conectores.sql_fuente import validar_consulta_solo_lectura
from motor.bitacora import Bitacora
from motor.factura_electronica import leer_facturas
from motor.importador import importar, validar_identificador
from motor.seguridad import bloquear_duckdb_externo

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

CONSULTAS_SUGERIDAS = [
    ("Asientos > 25,000", "Muéstrame los asientos con monto mayor a 25,000 ordenados de mayor a menor"),
    ("Registrados en fin de semana", "Asientos registrados en fin de semana (sábado o domingo)"),
    ("Por usuario (resumen)", "Resumen de asientos y monto total por usuario"),
    ("Cerca o posterior al cierre", "Asientos contabilizados cerca o posterior al cierre contable"),
    ("Montos redondos", "Movimientos con montos redondos superiores a 5,000"),
    ("Asientos descuadrados", "Asientos descuadrados donde el débito no coincide con el crédito"),
]


@dataclass
class PropuestaCopiloto:
    pregunta: str
    titulo: str
    explicacion: str
    sql: str
    nia: list[str] = field(default_factory=list)
    tabla_objetivo: str = "mayor"


@dataclass
class ResultadoCopiloto:
    pregunta: str
    titulo: str
    sql_ejecutado: str
    sql_sha256: str
    tabla: pd.DataFrame
    borrador: str
    nia: list[str] = field(default_factory=list)


def _norm(texto: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


def _numero_de_texto(texto_num: str) -> float:
    limpio = texto_num.strip().replace(",", "")
    return float(limpio)


def _extraer_umbral_mayor(q_norm: str) -> float | None:
    m = re.search(
        r"(?:mayor(?:es)?\s+(?:a|que)|superior(?:es)?\s+a|encima\s+de|sobre|desde|>=?)\s*(?:b/\.?|\$|usd)?\s*(\d[\d,]*(?:\.\d+)?)(?:\s*(mil))?",
        q_norm,
    )
    if not m:
        return None
    val = _numero_de_texto(m.group(1))
    return val * 1000.0 if m.group(2) else val


def _extraer_umbral_menor(q_norm: str) -> float | None:
    m = re.search(
        r"(?:menor(?:es)?\s+(?:a|que)|inferior(?:es)?\s+a|debajo\s+de|bajo|hasta|<=?)\s*(?:b/\.?|\$|usd)?\s*(\d[\d,]*(?:\.\d+)?)(?:\s*(mil))?",
        q_norm,
    )
    if not m:
        return None
    val = _numero_de_texto(m.group(1))
    return val * 1000.0 if m.group(2) else val


def _extraer_rango(q_norm: str) -> tuple[float, float] | None:
    m = re.search(
        r"\bentre\s*(?:b/\.?|\$|usd)?\s*(\d[\d,]*(?:\.\d+)?)\s*y\s*(?:b/\.?|\$|usd)?\s*(\d[\d,]*(?:\.\d+)?)",
        q_norm,
    )
    if not m:
        return None
    a, b = _numero_de_texto(m.group(1)), _numero_de_texto(m.group(2))
    return (min(a, b), max(a, b))


def _fecha_cierre_encargo(encargo: dict | None) -> date:
    raw = (encargo or {}).get("fecha_cierre")
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
    return date(2025, 12, 31)


def _elegir_tabla_objetivo(q_norm: str, tablas_disponibles: dict[str, list[str]] | None) -> str:
    disponibles = list((tablas_disponibles or {}).keys())
    if any(k in q_norm for k in ("factura", "cufe", "itbms", "dgi", "nota de credito")) and (
        not disponibles or "facturas" in disponibles
    ):
        return "facturas"
    if any(k in q_norm for k in ("extracto", "bancari", "banco", "conciliacion", "saldo corrido")) and (
        "extracto" in disponibles or (not disponibles and "cuenta" not in q_norm)
    ):
        return "extracto"
    if any(k in q_norm for k in ("balanza", "saldo inicial", "saldo final")) and (
        not disponibles or "balanza" in disponibles
    ):
        return "balanza"
    if disponibles and "mayor" not in disponibles:
        return disponibles[0]
    return "mayor"


def _sql_facturas(q_norm: str, limite: int) -> tuple[str, str, str, list[str]]:
    if "resumen" in q_norm or "por mes" in q_norm:
        return (
            "Resumen mensual de facturación electrónica DGI",
            "Agrupa documentos electrónicos válidos (sin ambiente de pruebas) por mes calendario.",
            "SELECT strftime(fecha_emision, '%Y-%m') AS mes,\n"
            "       COUNT(*) AS documentos,\n"
            "       ROUND(SUM(total_neto), 2) AS neto,\n"
            "       ROUND(SUM(total_itbms), 2) AS itbms,\n"
            "       ROUND(SUM(total), 2) AS total\n"
            "FROM facturas\n"
            "WHERE COALESCE(ambiente, '1') <> '2'\n"
            "GROUP BY 1\n"
            "ORDER BY 1",
            ["NIA 500", "DGI SFEP"],
        )
    if "nota" in q_norm and "credito" in q_norm:
        return (
            "Notas de crédito emitidas en SFEP",
            "Filtra documentos electrónicos tipo 04 y 06.",
            "SELECT archivo, cufe, tipo_documento, punto_facturacion, numero, fecha_emision, nombre_receptor, total_neto, total\n"
            "FROM facturas\n"
            "WHERE tipo_documento IN ('04', '06')\n"
            f"ORDER BY fecha_emision, numero\nLIMIT {limite}",
            ["NIA 500", "NIA 240"],
        )
    conds = ["COALESCE(ambiente, '1') <> '2'"]
    mayor = _extraer_umbral_mayor(q_norm)
    if mayor is not None:
        conds.append(f"total >= {mayor:.2f}")
    where = " AND ".join(conds)
    return (
        "Consulta analítica de facturas electrónicas DGI",
        "Lista facturas electrónicas ordenadas por importe total descendente.",
        "SELECT archivo, cufe, tipo_documento_nombre, punto_facturacion, numero, fecha_emision, nombre_receptor, total_neto, total_itbms, total\n"
        "FROM facturas\n"
        f"WHERE {where}\n"
        f"ORDER BY total DESC, fecha_emision\nLIMIT {limite}",
        ["NIA 500", "DGI SFEP"],
    )


def _sql_extracto(q_norm: str, limite: int) -> tuple[str, str, str, list[str]]:
    conds = ["1=1"]
    razones: list[str] = []
    if "debito" in q_norm or "cargo" in q_norm or "retiro" in q_norm:
        conds.append("debito > 0")
        razones.append("solo cargos/débitos bancarios")
    elif "credito" in q_norm or "deposito" in q_norm or "abono" in q_norm:
        conds.append("credito > 0")
        razones.append("solo créditos/abonos bancarios")
    mayor = _extraer_umbral_mayor(q_norm)
    if mayor is not None:
        conds.append(f"ABS(monto) >= {mayor:.2f}")
        razones.append(f"importe absoluto ≥ {mayor:,.2f}")
    where = " AND ".join(conds)
    expl = "Consulta movimientos importados del extracto bancario PDF" + (
        f" ({', '.join(razones)})." if razones else "."
    )
    return (
        "Movimientos del extracto bancario",
        expl,
        "SELECT archivo, banco, cuenta_bancaria, linea, fecha, referencia, descripcion, debito, credito, monto, saldo\n"
        "FROM extracto\n"
        f"WHERE {where}\n"
        f"ORDER BY ABS(monto) DESC, fecha, linea\nLIMIT {limite}",
        ["NIA 500", "NIA 330"],
    )


def _sql_balanza(q_norm: str, limite: int) -> tuple[str, str, str, list[str]]:
    mayor = _extraer_umbral_mayor(q_norm)
    filtro = f"WHERE ABS(saldo_final) >= {mayor:.2f}\n" if mayor is not None else ""
    return (
        "Análisis de balanza de comprobación",
        "Presenta cuentas de la balanza ordenadas por valor absoluto del saldo final.",
        "SELECT cuenta, descripcion, saldo_inicial, saldo_final,\n"
        "       ROUND(saldo_final - saldo_inicial, 2) AS variacion_neta\n"
        "FROM balanza\n"
        f"{filtro}"
        f"ORDER BY ABS(saldo_final) DESC, cuenta\nLIMIT {limite}",
        ["NIA 520", "NIA 500"],
    )


def proponer_consulta_sql(
    pregunta: str,
    tablas_disponibles: dict[str, list[str]] | None = None,
    encargo: dict | None = None,
) -> PropuestaCopiloto:
    """Traduce una solicitud en español a una consulta SQL SELECT/WITH visible y segura (sin red)."""
    if not isinstance(pregunta, str) or not pregunta.strip():
        raise ValueError("Escribe una pregunta o instrucción de auditoría para proponer la consulta SQL.")

    q = pregunta.strip()
    q_norm = _norm(q)
    cierre = _fecha_cierre_encargo(encargo)

    m_top = re.search(r"\b(?:top|primeros?|primeras?)\s+(\d+)\b", q_norm)
    limite = max(1, min(int(m_top.group(1)), 5000)) if m_top else 500

    tabla = _elegir_tabla_objetivo(q_norm, tablas_disponibles)
    if tabla == "facturas":
        titulo, expl, sql, nia = _sql_facturas(q_norm, limite)
        validar_consulta_solo_lectura(sql)
        return PropuestaCopiloto(q, titulo, expl, sql, nia, tabla)
    if tabla == "extracto":
        titulo, expl, sql, nia = _sql_extracto(q_norm, limite)
        validar_consulta_solo_lectura(sql)
        return PropuestaCopiloto(q, titulo, expl, sql, nia, tabla)
    if tabla == "balanza":
        titulo, expl, sql, nia = _sql_balanza(q_norm, limite)
        validar_consulta_solo_lectura(sql)
        return PropuestaCopiloto(q, titulo, expl, sql, nia, tabla)

    # Consultas sobre el Mayor General / Diario Contable (`mayor`)
    if "descuadrad" in q_norm or ("debito" in q_norm and "credito" in q_norm and "no coincide" in q_norm):
        sql = (
            "SELECT asiento, MIN(fecha) AS fecha, ANY_VALUE(usuario) AS usuario,\n"
            "       COUNT(*) AS lineas,\n"
            "       ROUND(SUM(CASE WHEN monto > 0 THEN monto ELSE 0 END), 2) AS total_debito,\n"
            "       ROUND(SUM(CASE WHEN monto < 0 THEN -monto ELSE 0 END), 2) AS total_credito,\n"
            "       ROUND(SUM(monto), 2) AS descuadre_neto\n"
            "FROM mayor\n"
            "GROUP BY asiento\n"
            "HAVING ABS(SUM(monto)) > 0.01\n"
            f"ORDER BY ABS(SUM(monto)) DESC, asiento\nLIMIT {limite}"
        )
        validar_consulta_solo_lectura(sql)
        return PropuestaCopiloto(
            q,
            "Asientos contables descuadrados",
            "Agrupa por número de asiento y filtra aquellos cuya suma neta difiere de cero (> 0.01).",
            sql,
            ["NIA 240", "NIA 500"],
            "mayor",
        )

    if "duplicad" in q_norm or "repetid" in q_norm:
        sql = (
            "SELECT fecha, cuenta, CAST(monto AS DECIMAL(18, 2)) AS monto,\n"
            "       COUNT(*) AS repeticiones,\n"
            "       STRING_AGG(DISTINCT CAST(asiento AS VARCHAR), ', ' ORDER BY CAST(asiento AS VARCHAR)) AS asientos\n"
            "FROM mayor\n"
            "GROUP BY fecha, cuenta, CAST(monto AS DECIMAL(18, 2))\n"
            "HAVING COUNT(*) > 1\n"
            f"ORDER BY repeticiones DESC, ABS(monto) DESC\nLIMIT {limite}"
        )
        validar_consulta_solo_lectura(sql)
        return PropuestaCopiloto(
            q,
            "Posibles líneas duplicadas en el mayor",
            "Agrupa movimientos por fecha, cuenta y monto exacto para identificar repeticiones.",
            sql,
            ["NIA 240", "NIA 500"],
            "mayor",
        )

    if any(k in q_norm for k in ("por usuario", "cada usuario", "resumen de usuarios", "usuarios")):
        if "poco frecuente" in q_norm or "pocos asientos" in q_norm:
            sql = (
                "SELECT usuario, COUNT(DISTINCT asiento) AS asientos, COUNT(*) AS lineas,\n"
                "       ROUND(SUM(CASE WHEN monto > 0 THEN monto ELSE 0 END), 2) AS total_debito,\n"
                "       ROUND(MAX(ABS(monto)), 2) AS monto_maximo\n"
                "FROM mayor\n"
                "GROUP BY usuario\n"
                "HAVING COUNT(DISTINCT asiento) < 5\n"
                "ORDER BY asientos ASC, total_debito DESC"
            )
            validar_consulta_solo_lectura(sql)
            return PropuestaCopiloto(
                q,
                "Usuarios poco frecuentes (< 5 asientos)",
                "Detecta usuarios con menos de 5 asientos distintos en el periodo auditado.",
                sql,
                ["NIA 240"],
                "mayor",
            )
        sql = (
            "SELECT usuario, COUNT(DISTINCT asiento) AS asientos, COUNT(*) AS lineas,\n"
            "       ROUND(SUM(CASE WHEN monto > 0 THEN monto ELSE 0 END), 2) AS total_debito,\n"
            "       ROUND(MAX(ABS(monto)), 2) AS mayor_partida\n"
            "FROM mayor\n"
            "GROUP BY usuario\n"
            f"ORDER BY total_debito DESC\nLIMIT {limite}"
        )
        validar_consulta_solo_lectura(sql)
        return PropuestaCopiloto(
            q,
            "Actividad agregada por usuario",
            "Resume cantidad de asientos, líneas, débitos acumulados y mayor partida por usuario.",
            sql,
            ["NIA 240", "NIA 520"],
            "mayor",
        )

    if any(k in q_norm for k in ("por cuenta", "cada cuenta", "resumen de cuentas")):
        sql = (
            "SELECT cuenta, COUNT(DISTINCT asiento) AS asientos, COUNT(*) AS lineas,\n"
            "       ROUND(SUM(CASE WHEN monto > 0 THEN monto ELSE 0 END), 2) AS debitos,\n"
            "       ROUND(SUM(CASE WHEN monto < 0 THEN -monto ELSE 0 END), 2) AS creditos,\n"
            "       ROUND(SUM(monto), 2) AS saldo_neto\n"
            "FROM mayor\n"
            "GROUP BY cuenta\n"
            f"ORDER BY ABS(SUM(monto)) DESC, cuenta\nLIMIT {limite}"
        )
        validar_consulta_solo_lectura(sql)
        return PropuestaCopiloto(
            q,
            "Sumarización por cuenta contable",
            "Consolida débitos, créditos y movimiento neto por cuenta del mayor general.",
            sql,
            ["NIA 520", "NIA 315"],
            "mayor",
        )

    if "por mes" in q_norm or "mensual" in q_norm:
        sql = (
            "SELECT strftime(fecha, '%Y-%m') AS mes, COUNT(DISTINCT asiento) AS asientos,\n"
            "       ROUND(SUM(CASE WHEN monto > 0 THEN monto ELSE 0 END), 2) AS total_debito,\n"
            "       ROUND(SUM(monto), 2) AS movimiento_neto\n"
            "FROM mayor\n"
            "GROUP BY 1\n"
            "ORDER BY 1"
        )
        validar_consulta_solo_lectura(sql)
        return PropuestaCopiloto(
            q,
            "Tendencia mensual del diario contable",
            "Agrupa el volumen de asientos e importes débito por mes del ejercicio.",
            sql,
            ["NIA 520"],
            "mayor",
        )

    # Construcción dinámica de filtros combinables sobre `mayor`
    conds: list[str] = []
    razones: list[str] = []
    nias = ["NIA 500"]

    rango = _extraer_rango(q_norm)
    if rango:
        conds.append(f"ABS(monto) BETWEEN {rango[0]:.2f} AND {rango[1]:.2f}")
        razones.append(f"monto entre {rango[0]:,.2f} y {rango[1]:,.2f}")
    else:
        mayor = _extraer_umbral_mayor(q_norm)
        menor = _extraer_umbral_menor(q_norm)
        if mayor is not None:
            conds.append(f"ABS(monto) >= {mayor:.2f}")
            razones.append(f"monto absoluto ≥ {mayor:,.2f}")
        if menor is not None:
            conds.append(f"ABS(monto) <= {menor:.2f}")
            razones.append(f"monto absoluto ≤ {menor:,.2f}")

    if "fin de semana" in q_norm or "sabado" in q_norm or "domingo" in q_norm:
        conds.append("EXTRACT('dow' FROM fecha) IN (0, 6)")
        razones.append("registrados en sábado o domingo")
        nias.append("NIA 240")

    if "posterior al cierre" in q_norm or "despues del cierre" in q_norm:
        conds.append(f"fecha > DATE '{cierre.isoformat()}'")
        razones.append(f"posteriores al cierre ({cierre.isoformat()})")
        nias.append("NIA 240")
    elif "cerca" in q_norm and "cierre" in q_norm:
        ini_cerca = cierre - timedelta(days=7)
        conds.append(f"fecha >= DATE '{ini_cerca.isoformat()}'")
        razones.append(f"cercanos o posteriores al cierre (desde {ini_cerca.isoformat()})")
        nias.append("NIA 240")

    for mes_txt, mes_num in MESES_ES.items():
        if re.search(rf"\b{mes_txt}\b", q_norm):
            conds.append(f"EXTRACT('month' FROM fecha) = {mes_num}")
            razones.append(f"mes de {mes_txt}")
            break

    if "redond" in q_norm:
        conds.append("ABS(monto) >= 100 AND CAST(ROUND(ABS(monto) * 100) AS BIGINT) % 10000 = 0")
        razones.append("montos redondos (múltiplos exactos de 100)")
        nias.append("NIA 240")

    if "vacia" in q_norm or "sin descripcion" in q_norm or "generica" in q_norm:
        conds.append(
            "(TRIM(COALESCE(descripcion, '')) = '' OR LOWER(TRIM(descripcion)) IN ('ajuste', 'ajuste varios', 'reclasificacion', 'reclasificación', 'varios', 'n/a'))"
        )
        razones.append("descripción vacía o genérica")
        nias.append("NIA 240")

    m_cta = re.search(r"\bcuenta(?:s)?\s+([0-9][0-9a-zA-Z_-]*)", q_norm)
    if m_cta:
        cod_cta = m_cta.group(1)
        conds.append(f"starts_with(CAST(cuenta AS VARCHAR), '{cod_cta}')")
        razones.append(f"cuenta con prefijo '{cod_cta}'")
    elif "ingreso" in q_norm:
        pref = str((encargo or {}).get("prefijo_ingresos") or "4").replace("'", "")
        conds.append(f"starts_with(CAST(cuenta AS VARCHAR), '{pref}')")
        razones.append(f"cuentas de ingresos (prefijo '{pref}')")

    m_usr = re.search(r"\busuario\s+([a-zA-Z0-9_.-]+)", q_norm)
    if m_usr and m_usr.group(1) not in ("poco", "por", "con", "sin", "y", "de"):
        usr = m_usr.group(1)
        conds.append(f"LOWER(CAST(usuario AS VARCHAR)) LIKE '%{usr}%'")
        razones.append(f"usuario contiene '{usr}'")

    if "materialidad" in q_norm:
        mat_ej = float((encargo or {}).get("materialidad_ejecucion") or (encargo or {}).get("materialidad") or 100000.0)
        conds.append(f"ABS(monto) >= {mat_ej:.2f}")
        razones.append(f"importe ≥ materialidad ({mat_ej:,.2f})")
        nias.append("NIA 320")

    where_sql = f"WHERE {' AND '.join(conds)}\n" if conds else ""
    sql = (
        "SELECT asiento, linea, fecha, cuenta, descripcion, CAST(monto AS DECIMAL(18, 2)) AS monto, usuario\n"
        "FROM mayor\n"
        f"{where_sql}"
        f"ORDER BY ABS(monto) DESC, fecha, asiento, linea\nLIMIT {limite}"
    )
    validar_consulta_solo_lectura(sql)
    expl = "Consulta de líneas del mayor filtrando por: " + ("; ".join(razones) if razones else "mayores importes absolutos.")
    return PropuestaCopiloto(
        q,
        "Consulta analítica del mayor general",
        expl,
        sql,
        list(dict.fromkeys(nias)),
        "mayor",
    )


def redactar_borrador_hallazgo(
    titulo: str,
    nia: list[str],
    tabla: pd.DataFrame,
    explicacion_consulta: str = "",
    encargo: dict | None = None,
) -> str:
    """Redacta borrador estructurado NIA usando únicamente cifras calculadas por DuckDB."""
    cliente = (encargo or {}).get("cliente") or "Cliente auditado"
    cierre = _fecha_cierre_encargo(encargo).isoformat()
    normas = ", ".join(nia) if nia else "NIA 500"
    n_filas = len(tabla)

    col_monto = next(
        (c for c in ("total_debito", "monto", "total", "descuadre_neto", "saldo_final", "total_absoluto") if c in tabla.columns),
        None,
    )
    monto_txt = ""
    if n_filas > 0 and col_monto is not None:
        serie = pd.to_numeric(tabla[col_monto], errors="coerce").dropna()
        if not serie.empty:
            monto_txt = (
                f" Suma de `{col_monto}` = {float(serie.sum()):,.2f} "
                f"(valor absoluto acumulado = {float(serie.abs().sum()):,.2f}; "
                f"máximo observado = {float(serie.abs().max()):,.2f})."
            )

    rango_txt = ""
    col_fecha = next((c for c in ("fecha", "fecha_emision") if c in tabla.columns), None)
    if n_filas > 0 and col_fecha is not None:
        fechas = pd.to_datetime(tabla[col_fecha], errors="coerce").dropna()
        if not fechas.empty:
            rango_txt = f" Rango temporal observado: {fechas.min():%Y-%m-%d} a {fechas.max():%Y-%m-%d}."

    if n_filas == 0:
        condicion = (
            f"Al aplicar la consulta sobre `{cliente}` (cierre {cierre}) no se identificaron "
            "partidas que cumplan la condición de riesgo o excepción evaluada (0 registros)."
        )
        recomendacion = "Dejar evidencia del procedimiento ejecutado con resultado satisfactorio en el papel de trabajo."
    else:
        condicion = (
            f"Durante la revisión analítica de `{cliente}` (cierre {cierre}), el motor determinista "
            f"identificó **{n_filas:,} registro(s)** bajo el criterio evaluado"
            + (f" ({explicacion_consulta.rstrip('.')})" if explicacion_consulta else "")
            + "."
        )
        recomendacion = (
            "Solicitar documentación soporte original (comprobantes, autorizaciones y evidencia de revisión), "
            "validar el tratamiento contable y documentar la conclusión del encargado/gerente en la cédula."
        )

    return (
        f"PAPEL DE TRABAJO · BORRADOR DE HALLAZGO ({normas})\n"
        f"Título: {titulo}\n\n"
        f"1. Condición:\n{condicion}\n\n"
        f"2. Criterio:\nConforme a {normas}, los registros inusuales, fuera de horario/periodo o de cuantía relevante "
        "requieren verificación de soporte, autorización e integridad contable.\n\n"
        f"3. Efecto cuantificado (Motor Determinista):\n"
        f"{n_filas:,} fila(s) extraída(s) directamente por DuckDB.{monto_txt}{rango_txt}\n\n"
        f"4. Recomendación / Seguimiento:\n{recomendacion}\n"
    )


def ejecutar_propuesta_aprobada(
    con: duckdb.DuckDBPyConnection,
    sql_aprobado: str,
    pregunta: str = "",
    titulo: str = "Consulta ad-hoc aprobada",
    nia: list[str] | None = None,
    explicacion: str = "",
    bitacora: Bitacora | None = None,
    encargo: dict | None = None,
    limite: int = 5000,
) -> ResultadoCopiloto:
    """Ejecuta en DuckDB únicamente SQL validado en solo lectura y registra la aprobación en bitácora."""
    bloquear_duckdb_externo(con)
    sql_limpia = validar_consulta_solo_lectura(sql_aprobado)
    sha = hashlib.sha256(sql_limpia.encode("utf-8")).hexdigest()
    limite_seg = max(1, min(int(limite), 100_000))
    envuelta = f"SELECT * FROM ({sql_limpia}) AS _sub LIMIT {limite_seg}"
    df = con.execute(envuelta).df()

    nia_lista = list(nia or ["NIA 500", "NIA 230"])
    borrador = redactar_borrador_hallazgo(titulo, nia_lista, df, explicacion_consulta=explicacion, encargo=encargo)

    if bitacora is not None:
        bitacora.registrar(
            "consulta_copiloto_aprobada",
            pregunta=pregunta,
            titulo=titulo,
            sql_sha256=sha,
            filas_resultado=len(df),
            sql=sql_limpia,
        )

    return ResultadoCopiloto(
        pregunta=pregunta,
        titulo=titulo,
        sql_ejecutado=sql_limpia,
        sql_sha256=sha,
        tabla=df,
        borrador=borrador,
        nia=nia_lista,
    )


def preparar_conexion_copiloto(
    fuentes: dict[str, Path | str],
    opciones: dict[str, dict] | None = None,
) -> tuple[duckdb.DuckDBPyConnection, dict[str, list[str]]]:
    """Abre conexión DuckDB en memoria e ingesta archivos CSV/Excel/Parquet/SQLite/FE/PDF para el copiloto."""
    con = duckdb.connect()
    opciones = opciones or {}
    tablas_cols: dict[str, list[str]] = {}
    for tabla, origen in fuentes.items():
        if origen is None:
            continue
        tabla_seg = validar_identificador(tabla)
        ruta = Path(origen) if not isinstance(origen, Path) else origen
        ext = ruta.suffix.lower() if isinstance(origen, Path) or not str(origen).startswith(("sqlite:", "postgresql:", "mssql:", "mysql:")) else ""
        if tabla_seg == "facturas" or ext == ".xml":
            df_fe = leer_facturas(ruta).facturas
            con.register("_tmp_cop_fe", df_fe)
            con.execute(f'CREATE OR REPLACE TABLE "{tabla_seg}" AS SELECT * FROM _tmp_cop_fe')
            con.unregister("_tmp_cop_fe")
        elif tabla_seg == "extracto" or ext == ".pdf":
            df_ext = leer_estado_cuenta(ruta).movimientos
            con.register("_tmp_cop_ext", df_ext)
            con.execute(f'CREATE OR REPLACE TABLE "{tabla_seg}" AS SELECT * FROM _tmp_cop_ext')
            con.unregister("_tmp_cop_ext")
        else:
            extra = {k: v for k, v in (opciones.get(tabla) or {}).items() if not k.startswith("_") and v not in (None, "", {})}
            sep = extra.pop("separador_decimal", ".")
            importar(con, origen, tabla_seg, separador_decimal=sep, **extra)
        tablas_cols[tabla_seg] = [c[0] for c in con.execute(f'DESCRIBE "{tabla_seg}"').fetchall()]
    bloquear_duckdb_externo(con)
    return con, tablas_cols

