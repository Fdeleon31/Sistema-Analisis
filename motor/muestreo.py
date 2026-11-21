"""Ficha 05 · Muestreo por unidad monetaria (MUS) y aleatorio simple.

Fuentes públicas: AICPA Audit Sampling Guide, apéndice C (factores de confianza
basados en Poisson para cero errores: 3.00 con 95 % y 2.31 con 90 %).
Tamaño: n = VL × FC / (ET − EE × FE). Intervalo: J = VL / n.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pandas as pd

FACTOR_CONFIANZA_CERO_ERRORES = {95: 3.00, 90: 2.31}


class ErrorMuestreo(ValueError):
    pass


@dataclass
class PlanMUS:
    valor_libros: float
    nivel_confianza: int
    error_tolerable: float
    error_esperado: float
    factor_expansion: float | None
    factor_confianza: float
    tamano: int
    intervalo: float
    inicio: float = 0.0
    excluidos: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def tamano_mus(
    valor_libros: float,
    error_tolerable: float,
    nivel_confianza: int = 95,
    error_esperado: float = 0.0,
    factor_expansion: float | None = None,
) -> tuple[int, float]:
    """Devuelve (tamaño, factor de confianza)."""
    if nivel_confianza not in FACTOR_CONFIANZA_CERO_ERRORES:
        raise ErrorMuestreo(f"Nivel de confianza {nivel_confianza} no soportado. Usa 90 o 95.")
    if valor_libros <= 0 or error_tolerable <= 0:
        raise ErrorMuestreo("El valor en libros y el error tolerable deben ser mayores que cero.")
    if error_esperado > 0 and factor_expansion is None:
        raise ErrorMuestreo(
            "Con error esperado mayor que cero hay que indicar el factor de expansión "
            "(tabla de la guía de muestreo para tu nivel de confianza)."
        )
    factor = FACTOR_CONFIANZA_CERO_ERRORES[nivel_confianza]
    denominador = error_tolerable - error_esperado * (factor_expansion or 0)
    if denominador <= 0:
        raise ErrorMuestreo("El error esperado es demasiado alto frente al error tolerable: no hay muestra posible.")
    n = math.ceil(round(valor_libros * factor / denominador, 9))
    return n, factor


def seleccionar_mus(
    poblacion: pd.DataFrame,
    columna_id: str,
    columna_valor: str,
    error_tolerable: float,
    nivel_confianza: int = 95,
    error_esperado: float = 0.0,
    factor_expansion: float | None = None,
    inicio: float | None = None,
    semilla: int | None = None,
) -> tuple[pd.DataFrame, PlanMUS]:
    """Selección sistemática con inicio aleatorio sobre los valores acumulados.

    El punto p selecciona la partida i cuando acumulado_anterior < p <= acumulado_i.
    """
    datos = poblacion[[columna_id, columna_valor]].copy()
    datos[columna_valor] = pd.to_numeric(datos[columna_valor])
    positivos = datos[datos[columna_valor] > 0].sort_values(columna_id, kind="stable").reset_index(drop=True)
    excluidos = datos[datos[columna_valor] <= 0]

    valor_libros = float(positivos[columna_valor].sum())
    n, factor = tamano_mus(valor_libros, error_tolerable, nivel_confianza, error_esperado, factor_expansion)
    intervalo = valor_libros / n
    if inicio is None:
        inicio = random.Random(semilla).uniform(0, intervalo)
    if not 0 <= inicio < intervalo:
        raise ErrorMuestreo(f"El inicio debe estar entre 0 y el intervalo ({intervalo:,.2f}).")

    acumulado = positivos[columna_valor].cumsum()
    anterior = acumulado.shift(fill_value=0)
    puntos = [inicio + k * intervalo for k in range(n)]
    filas = []
    i = 0
    for p in puntos:
        while not (anterior.iloc[i] < p <= acumulado.iloc[i]):
            i += 1
        filas.append((i, p))

    seleccion = (
        pd.DataFrame(filas, columns=["_fila", "punto"])
        .groupby("_fila")
        .agg(puntos=("punto", "count"), primer_punto=("punto", "min"))
        .reset_index()
    )
    resultado = positivos.iloc[seleccion["_fila"]].reset_index(drop=True)
    resultado["acumulado"] = acumulado.iloc[seleccion["_fila"]].values
    resultado["puntos"] = seleccion["puntos"].values
    resultado["primer_punto"] = seleccion["primer_punto"].round(2).values
    resultado["supera_intervalo"] = resultado[columna_valor] >= intervalo

    plan = PlanMUS(
        valor_libros=round(valor_libros, 2),
        nivel_confianza=nivel_confianza,
        error_tolerable=error_tolerable,
        error_esperado=error_esperado,
        factor_expansion=factor_expansion,
        factor_confianza=factor,
        tamano=n,
        intervalo=round(intervalo, 2),
        inicio=round(inicio, 2),
        excluidos={"partidas": int(len(excluidos)), "valor": round(float(excluidos[columna_valor].sum()), 2)},
    )
    return resultado, plan


def muestra_aleatoria(poblacion: pd.DataFrame, columna_id: str, tamano: int, semilla: int) -> pd.DataFrame:
    """n partidas al azar, repetible: la población se ordena por su identificador antes de elegir."""
    ordenada = poblacion.sort_values(columna_id, kind="stable").reset_index(drop=True)
    if tamano > len(ordenada):
        raise ErrorMuestreo(f"La muestra ({tamano}) es mayor que la población ({len(ordenada)}).")
    indices = sorted(random.Random(semilla).sample(range(len(ordenada)), tamano))
    return ordenada.iloc[indices].reset_index(drop=True)
