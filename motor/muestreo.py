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


# --- Ficha 05b · Evaluación de la muestra MUS ------------------------------------------

# AICPA Audit Sampling Guide, apéndice C, tabla C-3 (sobrestimaciones), por nivel de confianza.
FACTORES_EVALUACION = {
    95: [3.00, 4.75, 6.30, 7.76],
    90: [2.31, 3.89, 5.33, 6.69],
}


@dataclass
class EvaluacionMUS:
    intervalo: float
    nivel_confianza: int
    error_tolerable: float
    precision_basica: float
    error_proyectado: float
    margen_incremental: float
    limite_superior: float
    conclusion: str
    detalle: pd.DataFrame
    subestimaciones: pd.DataFrame

    def resumen(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not isinstance(v, pd.DataFrame)}


def evaluar_mus(
    errores: pd.DataFrame,
    intervalo: float,
    error_tolerable: float,
    nivel_confianza: int = 95,
    columna_id: str = "id",
    columna_libros: str = "valor_libros",
    columna_auditado: str = "valor_auditado",
) -> EvaluacionMUS:
    """Límite superior de error por sobrestimación (método de la tabla C-3)."""
    if nivel_confianza not in FACTORES_EVALUACION:
        raise ErrorMuestreo(f"Nivel de confianza {nivel_confianza} no soportado. Usa 90 o 95.")
    factores = FACTORES_EVALUACION[nivel_confianza]

    datos = errores[[columna_id, columna_libros, columna_auditado]].copy()
    datos.columns = ["id", "valor_libros", "valor_auditado"]
    datos["valor_libros"] = pd.to_numeric(datos["valor_libros"])
    datos["valor_auditado"] = pd.to_numeric(datos["valor_auditado"])
    datos["error"] = (datos["valor_libros"] - datos["valor_auditado"]).round(2)
    if (datos["valor_libros"] <= 0).any():
        raise ErrorMuestreo("Las partidas con error deben tener valor en libros positivo.")

    subestimaciones = datos[datos["error"] < 0].reset_index(drop=True)
    sobre = datos[datos["error"] > 0].copy()
    sobre["supera_intervalo"] = sobre["valor_libros"] >= intervalo
    sobre["contaminacion"] = (sobre["error"] / sobre["valor_libros"]).round(6)
    sobre["proyectado"] = sobre.apply(
        lambda f: f["error"] if f["supera_intervalo"] else f["contaminacion"] * intervalo, axis=1
    ).round(2) if len(sobre) else []

    menores = sobre[~sobre["supera_intervalo"]].sort_values("contaminacion", ascending=False, kind="stable")
    if len(menores) > len(factores) - 1:
        raise ErrorMuestreo(
            f"Hay {len(menores)} errores en partidas menores que el intervalo; la tabla incluida llega a "
            f"{len(factores) - 1}. Agrega los factores siguientes de la tabla C-3 antes de evaluar."
        )
    margenes = {}
    for k, (indice, fila) in enumerate(menores.iterrows(), start=1):
        margenes[indice] = round((factores[k] - factores[k - 1] - 1) * fila["proyectado"], 2)
    sobre["margen_incremental"] = [margenes.get(i, 0.0) for i in sobre.index]
    sobre["orden"] = [list(menores.index).index(i) + 1 if i in margenes else None for i in sobre.index]

    precision = round(intervalo * factores[0], 2)
    proyectado = round(float(sobre["proyectado"].sum()) if len(sobre) else 0.0, 2)
    margen = round(float(sobre["margen_incremental"].sum()) if len(sobre) else 0.0, 2)
    limite = round(precision + proyectado + margen, 2)
    if limite <= error_tolerable:
        conclusion = (f"El límite superior de error ({limite:,.2f}) no supera el error tolerable "
                      f"({error_tolerable:,.2f}): la muestra respalda que el saldo no tiene un error material.")
    else:
        conclusion = (f"El límite superior de error ({limite:,.2f}) supera el error tolerable "
                      f"({error_tolerable:,.2f}): la muestra no permite concluir; considera ampliar pruebas o ajustar el saldo.")
    detalle = sobre.sort_values(["supera_intervalo", "contaminacion"], ascending=[False, False]).reset_index(drop=True)
    return EvaluacionMUS(intervalo, nivel_confianza, error_tolerable, precision, proyectado, margen, limite,
                         conclusion, detalle, subestimaciones)
