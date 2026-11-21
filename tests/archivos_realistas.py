"""Variantes realistas del mayor sintético, como las que exportan los ERP.

Cada variante reproduce un problema típico de archivos de clientes. Todas parten
del mismo mayor sintético, así que el resultado correcto es conocido.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from motor.sintetico import generar

ENCABEZADOS_ES = ["No. Asiento", "Línea", "Fecha", "Cuenta", "Descripción", "Importe", "Usuario"]
MAPEO_ES = {
    "No. Asiento": "asiento", "Línea": "linea", "Fecha": "fecha", "Cuenta": "cuenta",
    "Descripción": "descripcion", "Importe": "monto", "Usuario": "usuario",
}
TILDES = {
    "Compra de mercancía": "Compra de mercancía",
    "Mantenimiento": "Mantenimiento de equipo de cómputo",
    "Publicidad": "Publicidad y diseño",
}


def base(carpeta: Path) -> pd.DataFrame:
    ruta = generar(carpeta / "base.csv")
    df = pd.read_csv(ruta, dtype={"cuenta": str})
    df["descripcion"] = df["descripcion"].replace(TILDES)
    return df


def _ddmmyyyy(iso: str) -> str:
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def _miles(valor: float) -> str:
    texto = f"{abs(valor):,.2f}"
    return f"({texto})" if valor < 0 else texto


def generar_variantes(carpeta: Path) -> dict[str, dict]:
    """Devuelve {nombre: {"ruta": Path, "opciones": dict de importar}}."""
    carpeta.mkdir(parents=True, exist_ok=True)
    df = base(carpeta)
    v: dict[str, dict] = {}

    # 1. Windows-1252 (tildes y eñes), encabezados en español
    ruta = carpeta / "latin1_encabezados_es.csv"
    salida = df.copy()
    salida.columns = ENCABEZADOS_ES
    salida.to_csv(ruta, index=False, encoding="cp1252")
    v["latin1_encabezados_es"] = {"ruta": ruta, "opciones": {"mapeo": MAPEO_ES}}

    # 2. Fechas dd/mm/aaaa
    ruta = carpeta / "fechas_ddmmaaaa.csv"
    salida = df.copy()
    salida["fecha"] = salida["fecha"].map(_ddmmyyyy)
    salida.to_csv(ruta, index=False)
    v["fechas_ddmmaaaa"] = {"ruta": ruta, "opciones": {"formato_fecha": "%d/%m/%Y"}}

    # 3. Montos con separador de miles y negativos entre paréntesis
    ruta = carpeta / "montos_texto.csv"
    salida = df.copy()
    salida["monto"] = salida["monto"].map(_miles)
    salida.to_csv(ruta, index=False, quoting=csv.QUOTE_NONNUMERIC)
    v["montos_texto"] = {"ruta": ruta, "opciones": {}}

    # 4. Filas de título arriba y fila de total al final
    ruta = carpeta / "titulo_y_totales.csv"
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["EMPRESA DEMO, S.A."])
        w.writerow(["Libro diario del 01/01/2025 al 31/12/2025"])
        w.writerow([])
        w.writerow(df.columns)
        w.writerows(df.values.tolist())
        w.writerow(["", "", "", "", "Total general", f"{df['monto'].sum():.2f}", ""])
    v["titulo_y_totales"] = {"ruta": ruta, "opciones": {"saltar_filas": 3}}

    # 5. Excel con Debe y Haber en columnas separadas y una hoja de portada
    ruta = carpeta / "debe_haber.xlsx"
    salida = df.copy()
    salida["Debe"] = salida["monto"].clip(lower=0)
    salida["Haber"] = (-salida["monto"]).clip(lower=0)
    salida = salida.drop(columns=["monto"])
    with pd.ExcelWriter(ruta) as xls:
        pd.DataFrame({"Reporte": ["Libro diario 2025", "Generado por el ERP"]}).to_excel(xls, sheet_name="Portada", index=False)
        salida.to_excel(xls, sheet_name="Diario", index=False)
    v["debe_haber_excel"] = {"ruta": ruta, "opciones": {"hoja": "Diario", "debito_credito": ("Debe", "Haber")}}

    # 6. Asientos alfanuméricos con prefijo
    ruta = carpeta / "asientos_alfanumericos.csv"
    salida = df.copy()
    salida["asiento"] = salida["asiento"].map(lambda n: f"AS-{n:06d}")
    salida.to_csv(ruta, index=False)
    v["asientos_alfanumericos"] = {"ruta": ruta, "opciones": {}}

    # 7. UTF-8 con BOM (lo que deja Excel al guardar como "CSV UTF-8")
    ruta = carpeta / "utf8_bom.csv"
    df.to_csv(ruta, index=False, encoding="utf-8-sig")
    v["utf8_bom"] = {"ruta": ruta, "opciones": {}}

    # 8. Coma decimal y punto y coma como separador (configuración regional española)
    ruta = carpeta / "coma_decimal.csv"
    salida = df.copy()
    salida["monto"] = salida["monto"].map(lambda x: f"{x:.2f}".replace(".", ","))
    salida.to_csv(ruta, index=False, sep=";")
    v["coma_decimal"] = {"ruta": ruta, "opciones": {"separador_decimal": ","}}

    return v
