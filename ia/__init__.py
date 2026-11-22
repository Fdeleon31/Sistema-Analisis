"""Módulo de copiloto offline y redacción de borradores NIA (Ficha 14)."""

from .copiloto import (
    CONSULTAS_SUGERIDAS,
    PropuestaCopiloto,
    ResultadoCopiloto,
    ejecutar_propuesta_aprobada,
    preparar_conexion_copiloto,
    proponer_consulta_sql,
    redactar_borrador_hallazgo,
)

__all__ = [
    "CONSULTAS_SUGERIDAS",
    "PropuestaCopiloto",
    "ResultadoCopiloto",
    "ejecutar_propuesta_aprobada",
    "preparar_conexion_copiloto",
    "proponer_consulta_sql",
    "redactar_borrador_hallazgo",
]
