"""Exporta los resultados a una cédula en Excel."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .bitacora import Bitacora
from .ejecutor import ResultadoPrueba

NOMBRES_CRITERIOS = {
    "fin_semana_feriado": "Fin de semana o feriado",
    "posterior_cierre": "Posterior al cierre",
    "cerca_cierre": "Cerca del cierre",
    "monto_redondo": "Monto redondo",
    "bajo_umbral": "Justo bajo el umbral de aprobación",
    "descripcion_sospechosa": "Descripción vacía o genérica",
    "usuario_poco_frecuente": "Usuario poco frecuente",
    "cuenta_poco_usada": "Cuenta poco usada",
    "descuadrado": "Asiento descuadrado",
    "sobre_materialidad": "Sobre materialidad de ejecución",
}


def _nombre_hoja(texto: str, usados: set[str]) -> str:
    base = "".join(c for c in texto if c not in '[]:*?/\\')[:28]
    nombre, i = base, 2
    while nombre in usados:
        nombre = f"{base[:26]}_{i}"
        i += 1
    usados.add(nombre)
    return nombre


def exportar_excel(
    resultados: list[ResultadoPrueba],
    importaciones: list[dict],
    bitacora: Bitacora,
    ruta: str | Path,
    encargo: dict | None = None,
) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    encargo = encargo or {}

    resumen = pd.DataFrame(
        [
            {
                "Ficha": r.ficha,
                "Prueba": r.nombre,
                "NIA": ", ".join(r.nia),
                "Resultado": r.omitida or r.excepciones,
                "Detalle": "" if r.omitida else _detalle(r),
                "Conclusión del auditor": "",
            }
            for r in resultados
        ]
    )
    control = pd.DataFrame(
        [
            {
                "Archivo": i["archivo"],
                "Tabla": i["tabla"],
                "Filas": i["filas"],
                "Filas excluidas": i.get("filas_excluidas", 0),
                "Monto excluido": i.get("monto_filas_excluidas", 0.0),
                "Codificación": i.get("codificacion", "Excel"),
                "Formato de fecha": i.get("formato_fecha", ""),
                "Transformaciones": "; ".join(i.get("transformaciones", [])),
                "SHA-256": i["sha256"],
            }
            for i in importaciones
        ]
    )
    registros = pd.DataFrame(
        [
            {
                "Fecha y hora (UTC)": r["fecha_hora_utc"],
                "Usuario": r["usuario"],
                "Evento": r["evento"],
                "Detalle": r["datos"].get("prueba") or r["datos"].get("archivo") or r["datos"].get("tabla"),
                "Hash": r["hash"],
            }
            for r in bitacora.leer()
        ]
    )

    usados: set[str] = {"Resumen", "Encargo", "Control de archivos", "Bitacora"}
    with pd.ExcelWriter(ruta, engine="openpyxl") as xls:
        resumen.to_excel(xls, sheet_name="Resumen", index=False)
        if encargo:
            datos = [(k, str(v)) for k, v in encargo.items() if not k.startswith("_")]
            pd.DataFrame(datos, columns=["Parámetro", "Valor"]).to_excel(xls, sheet_name="Encargo", index=False)
        control.to_excel(xls, sheet_name="Control de archivos", index=False)
        for r in resultados:
            if r.omitida:
                continue
            r.tabla.to_excel(xls, sheet_name=_nombre_hoja(r.id, usados), index=False)
        registros.to_excel(xls, sheet_name="Bitacora", index=False)
        for hoja in xls.sheets.values():
            for columna in hoja.columns:
                largo = max(len(str(c.value)) if c.value is not None else 0 for c in columna)
                hoja.column_dimensions[columna[0].column_letter].width = min(max(10, largo + 2), 60)
    return ruta


def _detalle(r: ResultadoPrueba) -> str:
    if "mad" in r.resumen:
        aviso = f" · {r.resumen['advertencia']}" if r.resumen.get("advertencia") else ""
        significativos = len(r.resumen["digitos_significativos"])
        return (
            f"MAD {r.resumen['mad']} · {r.resumen['conformidad']} · n = {r.resumen['n']} · "
            f"{significativos} {'dígito' if significativos == 1 else 'dígitos'} con desviación significativa (Z > 1.96){aviso}"
        )
    if "por_criterio" in r.resumen:
        partes = [f"{NOMBRES_CRITERIOS.get(k, k)}: {v}" for k, v in r.resumen["por_criterio"].items() if v]
        return f"{r.excepciones} de {r.resumen['asientos_analizados']} asientos con criterios · " + "; ".join(partes)
    if "periodos" in r.resumen:
        return f"{r.excepciones} de {r.resumen['periodos']} periodos con diferencia · diferencia neta {r.resumen['diferencia_total']:,.2f}"
    if r.resumen.get("informativo"):
        return "Informativo"
    if "regla" in r.resumen:
        return f"{r.excepciones} asientos seleccionados · regla: {r.resumen['regla']}"
    if "semilla" in r.resumen:
        return f"{r.excepciones} asientos al azar entre {r.resumen['poblacion_sin_criterios']} sin criterios · semilla {r.resumen['semilla']}"
    filas = len(r.tabla)
    return f"{filas} {'fila' if filas == 1 else 'filas'} para revisar"
