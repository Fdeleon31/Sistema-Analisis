"""Catálogo de perfiles de sistemas contables/ERP del mercado panameño (Ficha 12)."""
from __future__ import annotations

from pathlib import Path

import yaml

from motor.rutas import raiz_recursos
from motor.sugerencias import normalizar, sugerir_debito_credito, sugerir_indicador_dc, sugerir_mapeo

CARPETA_PERFILES = raiz_recursos() / "conectores" / "perfiles"
ESTANDAR_CUADRA = {"asiento", "linea", "fecha", "cuenta", "descripcion", "monto", "usuario"}


def perfiles_disponibles() -> dict[str, dict]:
    """Devuelve {id: perfil} ordenado para mostrar al auditor."""
    lista: list[dict] = []
    carpeta = raiz_recursos() / "conectores" / "perfiles"
    for ruta in sorted(carpeta.glob("*.yaml")):
        with ruta.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data and "id" in data:
            lista.append(data)
    lista.sort(key=lambda p: (p.get("orden_ui", 99), p["id"]))
    return {p["id"]: p for p in lista}


def obtener_perfil(perfil_id: str) -> dict:
    perfiles = perfiles_disponibles()
    if perfil_id not in perfiles:
        raise ValueError(
            f"Perfil ERP desconocido: {perfil_id!r}. Disponibles: {', '.join(perfiles)}"
        )
    return perfiles[perfil_id]


def _frecuencia_alias(perfiles: dict[str, dict]) -> dict[str, int]:
    """Cuenta en cuántos perfiles aparece cada alias normalizado para dar mayor peso a los distintivos."""
    conteo: dict[str, int] = {}
    for p in perfiles.values():
        vistos: set[str] = set()
        for aliases in (p.get("aliases") or {}).values():
            for a in aliases:
                vistos.add(normalizar(a))
        for deb, cre in p.get("debito_credito_pares") or []:
            vistos.add(normalizar(deb))
            vistos.add(normalizar(cre))
        if p.get("indicador_dc"):
            for col in p["indicador_dc"].get("columnas", []):
                vistos.add(normalizar(col))
        for alias in vistos:
            if alias:
                conteo[alias] = conteo.get(alias, 0) + 1
    return conteo


def detectar_perfil(columnas: list[str]) -> tuple[dict | None, int]:
    """Detecta qué ERP del mercado panameño coincide mejor con las columnas dadas."""
    if not columnas:
        return None, 0
    cols_norm = {normalizar(c) for c in columnas if normalizar(c)}
    # Si ya usa exactamente los encabezados estándar de Cuadra, es genérico/estándar
    if {"asiento", "fecha", "cuenta", "monto"} <= cols_norm:
        return None, 0

    perfiles = perfiles_disponibles()
    freq = _frecuencia_alias(perfiles)

    mejor_perfil: dict | None = None
    mejor_puntaje = 0
    mejor_campos = 0

    for perfil in perfiles.values():
        puntaje = 0
        campos_unicos = 0
        aliases = perfil.get("aliases") or {}
        for std, lista_alias in aliases.items():
            for a in lista_alias:
                an = normalizar(a)
                if an in cols_norm:
                    campos_unicos += 1
                    # Bonus fuerte para alias exclusivos o poco compartidos entre ERPs
                    especificidad = 6 if freq.get(an, 99) == 1 else (3 if freq.get(an, 99) <= 2 else 0)
                    puntaje += 10 + especificidad
                    break

        par_encontrado = False
        for deb, cre in perfil.get("debito_credito_pares") or []:
            dn, cn = normalizar(deb), normalizar(cre)
            if dn in cols_norm and cn in cols_norm:
                par_encontrado = True
                especificidad = 6 if (freq.get(dn, 99) <= 2 or freq.get(cn, 99) <= 2) else 1
                puntaje += 12 + especificidad
                campos_unicos += 1
                break

        ind_encontrado = False
        ind_cfg = perfil.get("indicador_dc") or {}
        for col in ind_cfg.get("columnas", []):
            cn = normalizar(col)
            if cn in cols_norm:
                ind_encontrado = True
                puntaje += 16
                campos_unicos += 1
                break

        valido = campos_unicos >= 3 or (ind_encontrado and campos_unicos >= 2) or (par_encontrado and campos_unicos >= 3)
        if valido and puntaje > mejor_puntaje:
            mejor_perfil = perfil
            mejor_puntaje = puntaje
            mejor_campos = campos_unicos

    if mejor_perfil is None or mejor_campos < 2:
        return None, 0
    return mejor_perfil, mejor_puntaje


def proponer_opciones_perfil(
    perfil: dict | None,
    columnas: list[str],
    requeridas: list[str],
) -> dict:
    """Combina reglas de un perfil ERP (si existe) con sugerencias generales para preparar opciones de importación."""
    por_norm = {normalizar(c): c for c in columnas}

    debito_credito: tuple[str, str] | None = None
    indicador_dc: tuple[str, tuple[str, ...]] | None = None
    sinonimos_extra = (perfil or {}).get("aliases") or {}

    if perfil:
        for deb, cre in perfil.get("debito_credito_pares") or []:
            dn, cn = normalizar(deb), normalizar(cre)
            if dn in por_norm and cn in por_norm:
                debito_credito = (por_norm[dn], por_norm[cn])
                break
        if not debito_credito and perfil.get("indicador_dc"):
            cfg = perfil["indicador_dc"]
            for col in cfg.get("columnas", []):
                cn = normalizar(col)
                if cn in por_norm:
                    indicador_dc = (por_norm[cn], tuple(cfg.get("valores_credito", ["H", "C", "CR"])))
                    break

    if not debito_credito and "monto" in requeridas and not indicador_dc:
        tiene_monto_exacto = any(normalizar(c) in {"monto", "importe", "valor", "amount"} for c in columnas)
        if not tiene_monto_exacto:
            debito_credito = sugerir_debito_credito(columnas)
            if not debito_credito:
                ind_col = sugerir_indicador_dc(columnas)
                if ind_col:
                    indicador_dc = (ind_col, ("H", "C", "CR", "HABER", "CREDITO"))

    pedir = [r for r in requeridas if not (debito_credito and r == "monto")]
    mapeo_std_a_col = sugerir_mapeo(columnas, pedir, sinonimos_extra=sinonimos_extra)

    generar_linea = bool((perfil or {}).get("generar_linea_si_falta")) and ("linea" in requeridas) and (mapeo_std_a_col.get("linea") is None)
    usuario_defecto = None
    if perfil and perfil.get("usuario_defecto_si_falta") and ("usuario" in requeridas) and (mapeo_std_a_col.get("usuario") is None):
        usuario_defecto = perfil["usuario_defecto_si_falta"]

    return {
        "mapeo_std_a_col": mapeo_std_a_col,
        "debito_credito": debito_credito,
        "indicador_dc": indicador_dc,
        "separador_decimal": (perfil or {}).get("separador_decimal", "."),
        "formato_fecha": (perfil or {}).get("formato_fecha"),
        "generar_linea": generar_linea,
        "usuario_por_defecto": usuario_defecto,
    }
