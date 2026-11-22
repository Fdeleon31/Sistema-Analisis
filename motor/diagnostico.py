"""Diagnóstico previo de integridad contable y confiabilidad de los datos fuente.

Evalúa determinísticamente en DuckDB (NIA 500 / NIA 320) si los archivos
importados son íntegros, cuadran en partida doble, cubren el período del encargo
y carecen de claves duplicadas o errores de lectura antes de emitir conclusiones.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import duckdb
import pandas as pd


ORDEN_ESTADO = {"ALERTA": 0, "ADVERTENCIA": 1, "OK": 2}


def _tablas_cargadas(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in con.execute("SHOW TABLES").fetchall()}


def _columnas_tabla(con: duckdb.DuckDBPyConnection, tabla: str) -> set[str]:
    return {r[0] for r in con.execute(f'DESCRIBE "{tabla}"').fetchall()}


def _fecha_iso(val: Any) -> date | None:
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _item(
    codigo: str,
    nombre: str,
    tabla: str,
    estado: str,
    valor: str,
    detalle: str,
    accion_sugerida: str = "",
) -> dict:
    return {
        "codigo": codigo,
        "nombre": nombre,
        "tabla": tabla,
        "estado": estado,
        "valor": valor,
        "detalle": detalle,
        "accion_sugerida": accion_sugerida,
    }


def _revisar_cuadre_diario(con: duckdb.DuckDBPyConnection, tablas: set[str]) -> dict | None:
    if "mayor" not in tablas:
        return None
    cols = _columnas_tabla(con, "mayor")
    if not {"asiento", "monto"}.issubset(cols):
        return None
    neto = con.execute("SELECT COALESCE(SUM(monto), 0) FROM mayor").fetchone()[0]
    neto_f = round(float(neto or 0.0), 2)
    descuadrados = con.execute(
        "SELECT COUNT(*) FROM (SELECT asiento FROM mayor GROUP BY asiento HAVING ABS(SUM(monto)) > 0.01)"
    ).fetchone()[0]
    if abs(neto_f) <= 0.01 and descuadrados == 0:
        return _item(
            "cuadre_diario",
            "Cuadre contable del libro diario",
            "mayor",
            "OK",
            "Diferencia 0.00 (0 descuadres)",
            "Suma de débitos y créditos igual a cero a nivel global y por asiento.",
        )
    return _item(
        "cuadre_diario",
        "Cuadre contable del libro diario",
        "mayor",
        "ALERTA",
        f"Dif. global {neto_f:,.2f} · {descuadrados} asiento(s) descuadrados",
        "El mayor importado no suma cero en partida doble; puede haber un corte incompleto, filtro activo en el ERP o error de signo.",
        "Verificar si el archivo excluye asientos de apertura/cierre o revisar mapeo Debe/Haber antes de concluir.",
    )


def _revisar_cuadre_balanza(con: duckdb.DuckDBPyConnection, tablas: set[str]) -> dict | None:
    if "balanza" not in tablas:
        return None
    cols = _columnas_tabla(con, "balanza")
    if "saldo_final" not in cols:
        return None
    neto = round(float(con.execute("SELECT COALESCE(SUM(saldo_final), 0) FROM balanza").fetchone()[0] or 0.0), 2)
    if abs(neto) <= 0.05:
        return _item(
            "cuadre_balanza",
            "Cuadre neto de balanza de comprobación",
            "balanza",
            "OK",
            "Suma neta 0.00",
            "Los saldos finales de la balanza cuadrada suman cero.",
        )
    return _item(
        "cuadre_balanza",
        "Cuadre neto de balanza de comprobación",
        "balanza",
        "ADVERTENCIA",
        f"Suma neta {neto:,.2f}",
        "La balanza presenta un saldo neto distinto de cero (habitual si solo incluye cuentas de balance o resultados sin cierre, o si falta un rubro).",
        "Confirmar con el contador que la balanza incluye cuentas de activo, pasivo, patrimonio y resultado.",
    )


def _revisar_extractos(controles: list[dict]) -> list[dict]:
    salida: list[dict] = []
    for ctrl in controles:
        if ctrl.get("tabla") != "extracto":
            continue
        detalles_err = ctrl.get("detalle_excluidas") or []
        resumenes = ctrl.get("resumen_saldos") or []
        descuadres = [r for r in resumenes if r.get("cuadra") is False]
        if detalles_err or descuadres:
            partes = []
            if detalles_err:
                partes.append(f"{len(detalles_err)} línea(s) con error de lectura")
            for d in descuadres:
                partes.append(f"{d['archivo']}: dif. saldo {d['diferencia']:,.2f}")
            salida.append(
                _item(
                    "integridad_extracto",
                    "Integridad y cuadre de extracto bancario",
                    "extracto",
                    "ALERTA",
                    " · ".join(partes),
                    "El extracto PDF reportó líneas ilegibles o diferencias entre Saldo Inicial + Créditos - Débitos y Saldo Final.",
                    "Revisar los renglones en 'Control de archivos' y la prueba 'bancos-continuidad'.",
                )
            )
        elif any(r.get("cuadra") is True for r in resumenes):
            salida.append(
                _item(
                    "integridad_extracto",
                    "Integridad y cuadre de extracto bancario",
                    "extracto",
                    "OK",
                    f"{len(resumenes)} PDF(s) conciliados al centavo",
                    "Saldo inicial + créditos - débitos coincide exactamente con el saldo final del extracto.",
                )
            )
    return salida


def _revisar_campos_y_claves(con: duckdb.DuckDBPyConnection, tablas: set[str], controles: list[dict]) -> list[dict]:
    items: list[dict] = []
    if "mayor" in tablas:
        cols = _columnas_tabla(con, "mayor")
        nulos_cuenta = (
            con.execute("SELECT COUNT(*) FROM mayor WHERE cuenta IS NULL OR TRIM(CAST(cuenta AS VARCHAR)) = ''").fetchone()[0]
            if "cuenta" in cols else 0
        )
        nulos_monto = (
            con.execute("SELECT COUNT(*) FROM mayor WHERE monto IS NULL").fetchone()[0]
            if "monto" in cols else 0
        )
        dup_claves = (
            con.execute("SELECT COUNT(*) FROM (SELECT asiento, linea FROM mayor GROUP BY asiento, linea HAVING COUNT(*) > 1)").fetchone()[0]
            if {"asiento", "linea"}.issubset(cols) else 0
        )
        if nulos_cuenta or nulos_monto or dup_claves:
            items.append(
                _item(
                    "claves_mayor",
                    "Integridad de campos y claves en mayor",
                    "mayor",
                    "ALERTA",
                    f"Cuenta vacía: {nulos_cuenta} · Monto nulo: {nulos_monto} · Claves duplicadas: {dup_claves}",
                    "Se detectaron filas sin cuenta o monto, o pares (asiento, linea) duplicados en el mayor.",
                    "Corregir el origen antes de ejecutar pruebas de duplicados o reconciliaciones.",
                )
            )
        else:
            items.append(
                _item(
                    "claves_mayor",
                    "Integridad de campos y claves en mayor",
                    "mayor",
                    "OK",
                    "0 nulos críticos · 0 claves duplicadas",
                    "Todas las líneas del mayor cuentan con asiento, línea única, cuenta y monto válido.",
                )
            )

    notas_sinteticas: list[str] = []
    for ctrl in controles:
        transf = " | ".join(ctrl.get("transformaciones") or [])
        if ctrl.get("fechas_invalidas"):
            notas_sinteticas.append(f"{ctrl.get('tabla')}: {ctrl['fechas_invalidas']} fecha(s) ilegibles convertidas a NULL")
        if "linea: generada" in transf:
            notas_sinteticas.append(f"{ctrl.get('tabla')}: columna 'linea' numerada sintéticamente")
        if "usuario: valor por defecto" in transf:
            notas_sinteticas.append(f"{ctrl.get('tabla')}: columna 'usuario' completada con valor por defecto")
    if notas_sinteticas:
        items.append(
            _item(
                "transformaciones_origen",
                "Ajustes aplicados durante la importación",
                ", ".join(sorted({c.get("tabla", "") for c in controles if c.get("tabla")})),
                "ADVERTENCIA",
                f"{len(notas_sinteticas)} ajuste(s)",
                "; ".join(notas_sinteticas),
                "Las pruebas de autor/usuario o secuencia por línea dependen de columnas reales del ERP.",
            )
        )
    return items


def _revisar_cobertura_fechas(con: duckdb.DuckDBPyConnection, tablas: set[str], encargo: dict) -> list[dict]:
    inicio = _fecha_iso(encargo.get("periodo_inicio"))
    cierre = _fecha_iso(encargo.get("fecha_cierre"))
    items: list[dict] = []
    for tabla in sorted(tablas):
        cols = _columnas_tabla(con, tabla)
        if "fecha" not in cols:
            continue
        fila = con.execute(
            f'SELECT COUNT(*), COUNT(*) FILTER (WHERE "fecha" IS NULL), MIN("fecha"), MAX("fecha") FROM "{tabla}"'
        ).fetchone()
        total, nulas, fmin, fmax = fila
        if not total:
            continue
        fuera = 0
        if inicio and cierre:
            lim_inf = inicio - timedelta(days=31)
            lim_sup = cierre + timedelta(days=45)
            fuera = con.execute(
                f'SELECT COUNT(*) FROM "{tabla}" WHERE "fecha" IS NOT NULL AND ("fecha" < ? OR "fecha" > ?)',
                [lim_inf, lim_sup],
            ).fetchone()[0]
        rango = f"{fmin} a {fmax}" if fmin and fmax else "Sin fechas válidas"
        if nulas > 0:
            items.append(
                _item(
                    f"fechas_{tabla}",
                    f"Validez y cobertura de fechas ({tabla})",
                    tabla,
                    "ALERTA",
                    f"{nulas} fecha(s) nulas · rango {rango}",
                    f"La tabla '{tabla}' contiene registros sin fecha válida ({nulas} de {total}).",
                    "Revisar filas excluidas o formato de fecha en origen.",
                )
            )
        elif fuera > 0:
            items.append(
                _item(
                    f"fechas_{tabla}",
                    f"Validez y cobertura de fechas ({tabla})",
                    tabla,
                    "ADVERTENCIA",
                    f"{fuera} registro(s) fuera de ventana · rango {rango}",
                    f"Existen movimientos fuera del período esperado ({inicio} a {cierre}, con margen de corte).",
                    "Verificar si corresponden a ajustes históricos o a un ejercicio equivocado.",
                )
            )
        else:
            items.append(
                _item(
                    f"fechas_{tabla}",
                    f"Validez y cobertura de fechas ({tabla})",
                    tabla,
                    "OK",
                    f"Rango {rango} ({total} filas)",
                    f"Fechas completas y consistentes dentro del período auditado en '{tabla}'.",
                )
            )
    return items


def _revisar_parametros_encargo(encargo: dict) -> dict:
    cliente = str(encargo.get("cliente") or "").strip()
    cierre = str(encargo.get("fecha_cierre") or "").strip()
    mat = float(encargo.get("materialidad") or 0.0)
    if cliente and cierre and mat > 0:
        return _item(
            "parametros_encargo",
            "Parámetros de encargo y materialidad (NIA 320)",
            "encargo",
            "OK",
            f"Materialidad B/. {mat:,.2f} · Cierre {cierre}",
            f"Encargo configurado para '{cliente}' con umbral de materialidad y fecha de cierre definidos.",
        )
    return _item(
        "parametros_encargo",
        "Parámetros de encargo y materialidad (NIA 320)",
        "encargo",
        "ADVERTENCIA",
        f"Materialidad B/. {mat:,.2f}" if mat > 0 else "Sin materialidad > 0",
        "Falta definir cliente, fecha de cierre o materialidad positiva en el encargo.",
        "Completar los datos del encargo antes de emitir o firmar el papel de trabajo.",
    )


def evaluar_confiabilidad_datos(
    con: duckdb.DuckDBPyConnection,
    controles: list[dict],
    encargo: dict | None = None,
) -> dict:
    """Ejecuta controles determinísticos de confiabilidad y devuelve semáforo + hallazgos."""
    encargo = encargo or {}
    tablas = _tablas_cargadas(con)
    hallazgos: list[dict] = []

    for posible in (_revisar_cuadre_diario(con, tablas), _revisar_cuadre_balanza(con, tablas)):
        if posible:
            hallazgos.append(posible)
    hallazgos.extend(_revisar_extractos(controles))
    hallazgos.extend(_revisar_campos_y_claves(con, tablas, controles))
    hallazgos.extend(_revisar_cobertura_fechas(con, tablas, encargo))
    hallazgos.append(_revisar_parametros_encargo(encargo))

    conteos = {"OK": 0, "ADVERTENCIA": 0, "ALERTA": 0}
    for h in hallazgos:
        est = h["estado"]
        conteos[est] = conteos.get(est, 0) + 1

    if conteos["ALERTA"] > 0:
        estado_general = "ALERTA"
    elif conteos["ADVERTENCIA"] > 0:
        estado_general = "ADVERTENCIA"
    else:
        estado_general = "OK"

    resumen = (
        f"{conteos['OK']} OK · {conteos['ADVERTENCIA']} advertencia(s) · {conteos['ALERTA']} alerta(s)"
    )
    hallazgos_ord = sorted(hallazgos, key=lambda h: (ORDEN_ESTADO.get(h["estado"], 9), h["nombre"]))
    return {
        "estado_general": estado_general,
        "resumen": resumen,
        "conteos": conteos,
        "hallazgos": hallazgos_ord,
    }


def diagnostico_a_dataframe(diagnostico: dict | None) -> pd.DataFrame:
    """Convierte el resultado de diagnóstico en DataFrame listo para exportar a Excel."""
    cols = ["estado", "codigo", "nombre", "tabla", "valor", "detalle", "accion_sugerida"]
    hallazgos = (diagnostico or {}).get("hallazgos") or []
    return pd.DataFrame(hallazgos, columns=cols)
