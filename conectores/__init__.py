"""Conectores para sistemas contables de Panamá y fuentes SQL/multiformato (Ficha 12)."""

from .catalogo import detectar_perfil, obtener_perfil, perfiles_disponibles, proponer_opciones_perfil
from .sql_fuente import (
    enmascarar_uri,
    es_uri_sql,
    leer_archivo_sql,
    leer_conexion_sql,
    listar_tablas_archivo_sql,
    resolver_uri_sql,
    validar_consulta_solo_lectura,
)

__all__ = [
    "detectar_perfil",
    "enmascarar_uri",
    "es_uri_sql",
    "leer_archivo_sql",
    "leer_conexion_sql",
    "listar_tablas_archivo_sql",
    "obtener_perfil",
    "perfiles_disponibles",
    "proponer_opciones_perfil",
    "resolver_uri_sql",
    "validar_consulta_solo_lectura",
]
