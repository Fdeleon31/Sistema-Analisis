"""Cálculos estadísticos de la Ficha 01 (Ley de Benford).

Fuente pública: Nigrini, M. J. (2012). Benford's Law: Applications for
Forensic Accounting, Auditing, and Fraud Detection. Wiley. Tabla 7.1
(umbrales de MAD) y estadístico Z con corrección por continuidad.
"""
from __future__ import annotations

import math

import pandas as pd

# Umbrales de MAD de Nigrini (2012): cercana, aceptable, marginal; encima = no conforme.
UMBRALES_MAD = {
    1: (0.006, 0.012, 0.015),
    2: (0.0012, 0.0018, 0.0022),
}
Z_CRITICO = 1.96  # 5 % de significancia, dos colas


def proporcion_esperada(digito: int) -> float:
    return math.log10(1 + 1 / digito)


def rango_digitos(digitos: int) -> range:
    if digitos == 1:
        return range(1, 10)
    if digitos == 2:
        return range(10, 100)
    raise ValueError("Solo se soportan 1 o 2 dígitos")


def z_estadistico(real: float, esperada: float, n: int) -> float:
    if n <= 0 or not (0.0 < esperada < 1.0):
        return 0.0
    diferencia = abs(real - esperada)
    correccion = 1 / (2 * n)
    if correccion < diferencia:
        diferencia -= correccion
    varianza = esperada * (1 - esperada) / n
    if varianza <= 0.0:
        return 0.0
    return diferencia / math.sqrt(varianza)


def conformidad(mad: float, digitos: int) -> str:
    cercana, aceptable, marginal = UMBRALES_MAD[digitos]
    if mad <= cercana:
        return "Conformidad cercana"
    if mad <= aceptable:
        return "Conformidad aceptable"
    if mad <= marginal:
        return "Conformidad marginal"
    return "No conforme"


def analizar_benford(conteos: pd.DataFrame, digitos: int) -> tuple[pd.DataFrame, dict]:
    """Recibe columnas `digito` y `conteo`; devuelve la tabla por dígito y el resumen."""
    por_digito = dict(zip(conteos["digito"].astype(int), conteos["conteo"].astype(int)))
    n = sum(por_digito.values())
    if n == 0:
        raise ValueError("No hay montos que cumplan el mínimo para analizar Benford")

    filas = []
    for d in rango_digitos(digitos):
        conteo = por_digito.get(d, 0)
        real = conteo / n
        esperada = proporcion_esperada(d)
        z = z_estadistico(real, esperada, n)
        filas.append(
            {
                "digito": d,
                "conteo": conteo,
                "proporcion_real": round(real, 6),
                "proporcion_esperada": round(esperada, 6),
                "diferencia": round(real - esperada, 6),
                "z": round(z, 3),
                "significativo_5pct": z > Z_CRITICO,
            }
        )
    tabla = pd.DataFrame(filas)
    mad = float((tabla["proporcion_real"] - tabla["proporcion_esperada"]).abs().mean())
    resumen = {
        "n": n,
        "mad": round(mad, 6),
        "conformidad": conformidad(mad, digitos),
        "digitos_significativos": tabla.loc[tabla["significativo_5pct"], "digito"].tolist(),
    }
    return tabla, resumen
