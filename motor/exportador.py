"""Exporta los resultados a una cédula en Excel."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from .bitacora import Bitacora
from .diagnostico import diagnostico_a_dataframe
from .ejecutor import NOMBRES_CRITERIOS, ResultadoPrueba
from .formato_excel import estilizar_libro
from .revision import ROLES_FIRMA, cargar_revisiones
from .seguridad import sanitizar_dataframe_excel

MAX_FILAS_EXCEL = 1_000_000


def _como_fecha_iso(val) -> str:
    """Normaliza una fecha o texto a su representación ISO."""
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return str(val or "").strip()


def _inicio_fiscal_estandar(cierre_iso: str) -> str | None:
    """Calcula el inicio de un ejercicio fiscal de 12 meses a partir de la fecha de cierre."""
    try:
        fc = date.fromisoformat(cierre_iso[:10])
    except ValueError:
        return None
    ini = date(fc.year, 1, 1) if fc.month == 12 else date(fc.year - 1, fc.month + 1, 1)
    return ini.isoformat()


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
    revisiones: dict | None = None,
    diagnostico: dict | None = None,
) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    encargo = dict(encargo or {})
    if revisiones is None and (ruta.parent / "revisiones.json").exists():
        revisiones = cargar_revisiones(ruta.parent, [r.id for r in resultados])
    eventos_bitacora = bitacora.leer()
    if diagnostico is None:
        ev_diag = next((e["datos"] for e in reversed(eventos_bitacora) if e.get("evento") == "diagnostico"), None)
        if ev_diag:
            diagnostico = ev_diag

    tiene_rev = bool(revisiones and (
        revisiones.get("firmas")
        or any(
            v.get("estado", "Pendiente") != "Pendiente" or v.get("conclusion")
            for v in (revisiones.get("por_prueba") or {}).values()
        )
    ))
    por_prueba = (revisiones or {}).get("por_prueba") or {}
    firmas = (revisiones or {}).get("firmas") or {}

    if "Preparador" in firmas:
        encargo["preparo"] = f"{firmas['Preparador']['auditor']} ({firmas['Preparador']['fecha_utc']})"
    if "Revisor" in firmas:
        encargo["reviso"] = f"{firmas['Revisor']['auditor']} ({firmas['Revisor']['fecha_utc']})"
    if "Socio" in firmas:
        encargo["aprobo"] = f"{firmas['Socio']['auditor']} ({firmas['Socio']['fecha_utc']})"

    resumen_filas = []
    for r in resultados:
        rev_p = por_prueba.get(r.id, {})
        fila_r = {
            "Ficha": r.ficha,
            "Prueba": r.nombre,
            "NIA": ", ".join(r.nia),
            "Resultado": r.omitida or r.excepciones,
            "Detalle": "" if r.omitida else _detalle(r),
            "Conclusión del auditor": rev_p.get("conclusion", ""),
        }
        if tiene_rev:
            fila_r["Estado revisión"] = rev_p.get("estado", "Pendiente")
            fila_r["Revisado por"] = f"{rev_p['auditor']} ({rev_p['rol']})" if rev_p.get("auditor") else ""
        resumen_filas.append(fila_r)
    resumen = pd.DataFrame(resumen_filas)
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
                "Detalle": (
                    r["datos"].get("prueba")
                    or r["datos"].get("archivo")
                    or r["datos"].get("tabla")
                    or r["datos"].get("estado_general")
                    or r["datos"].get("rol")
                    or ""
                ),
                "Hash": r["hash"],
            }
            for r in eventos_bitacora
        ]
    )

    encargo.setdefault("aplicacion", "Folio Auditor · Analítica Determinista")
    cierre = _como_fecha_iso(encargo.get("fecha_cierre"))
    if cierre:
        ini = _como_fecha_iso(encargo.get("periodo_inicio")) or _inicio_fiscal_estandar(cierre)
        if ini:
            encargo.setdefault("periodo_auditado", f"{ini} al {cierre}")
    encargo.setdefault("fecha_hora_emision_local", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
    encargo.setdefault("fecha_hora_emision_utc", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    encabezado_imp = (
        f"Folio Auditor | Cliente: {encargo.get('cliente') or 'N/D'} "
        f"| Período: {encargo.get('periodo_auditado') or encargo.get('fecha_cierre') or 'N/D'} "
        f"| Emitido: {encargo['fecha_hora_emision_local']}"
    )

    usados: set[str] = {"Resumen", "Encargo", "Control de archivos", "Diagnostico", "Bitacora", "Revisiones y Firmas"}
    with pd.ExcelWriter(ruta, engine="openpyxl") as xls:
        sanitizar_dataframe_excel(resumen).to_excel(xls, sheet_name="Resumen", index=False)
        if encargo:
            datos = [(k, str(v)) for k, v in encargo.items() if not k.startswith("_")]
            sanitizar_dataframe_excel(pd.DataFrame(datos, columns=["Parámetro", "Valor"])).to_excel(
                xls, sheet_name="Encargo", index=False
            )
        if tiene_rev:
            filas_firmas = [
                {
                    "Rol": rol,
                    "Auditor": firmas[rol].get("auditor", "") if rol in firmas else "",
                    "Estado": "Firmado" if rol in firmas else "Pendiente",
                    "Fecha (UTC)": firmas[rol].get("fecha_utc", "") if rol in firmas else "",
                    "Observación": firmas[rol].get("observacion", "") if rol in firmas else "",
                    "Hash SHA-256": firmas[rol].get("hash_bitacora", "") if rol in firmas else "",
                }
                for rol in ROLES_FIRMA
            ]
            sanitizar_dataframe_excel(pd.DataFrame(filas_firmas)).to_excel(
                xls, sheet_name="Revisiones y Firmas", index=False
            )
        sanitizar_dataframe_excel(control).to_excel(xls, sheet_name="Control de archivos", index=False)
        if diagnostico:
            sanitizar_dataframe_excel(diagnostico_a_dataframe(diagnostico)).to_excel(
                xls, sheet_name="Diagnostico", index=False
            )
        for r in resultados:
            if r.omitida:
                continue
            df_hoja = sanitizar_dataframe_excel(r.tabla)
            if len(df_hoja) > MAX_FILAS_EXCEL:
                nombre_csv = f"{r.id}_completo.csv"
                df_hoja.to_csv(ruta.parent / nombre_csv, index=False, encoding="utf-8-sig")
                r.resumen["csv_completo"] = nombre_csv
                df_hoja = df_hoja.head(MAX_FILAS_EXCEL)
            df_hoja.to_excel(xls, sheet_name=_nombre_hoja(r.id, usados), index=False)
        sanitizar_dataframe_excel(registros).to_excel(xls, sheet_name="Bitacora", index=False)
        estilizar_libro(xls, encabezado_impresion=encabezado_imp)
    return ruta


def _detalle(r: ResultadoPrueba) -> str:
    if "por_nivel" in r.resumen:
        pn = r.resumen["por_nivel"]
        u = r.resumen["umbrales"]
        a = int(u["alto"]) if float(u["alto"]).is_integer() else u["alto"]
        m = int(u["medio"]) if float(u["medio"]).is_integer() else u["medio"]
        return (
            f"{pn['alto']} alto · {pn['medio']} medio · {pn['bajo']} bajo · "
            f"de {r.resumen['asientos_analizados']} asientos · puntaje máximo {r.resumen['puntaje_maximo']} · "
            f"alto ≥ {a}, medio ≥ {m}"
        )
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
    extra_csv = (
        f" (Excel limitado a {MAX_FILAS_EXCEL:,} filas; completo en {r.resumen['csv_completo']})"
        if r.resumen.get("csv_completo")
        else ""
    )
    return f"{filas} {'fila' if filas == 1 else 'filas'} para revisar{extra_csv}"


detalle_resultado = _detalle
