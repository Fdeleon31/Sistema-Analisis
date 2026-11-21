"""Cuadra · línea de comandos.

Ejemplos:
    python cuadra.py ejemplo
    python cuadra.py ejemplo-asientos
    python cuadra.py correr --paquete asientos-nia240 --encargo encargos/ejemplo-2025.yaml \
        --archivo mayor=datos/mayor.csv --archivo balanza=datos/balanza.xlsx
    python cuadra.py muestra --archivo datos/cxc.csv --id cliente --valor saldo --tolerable 45000
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from motor import __version__
from motor.bitacora import Bitacora
from motor.ejecutor import cargar_encargo, cargar_manifiesto, correr_paquete
from motor.exportador import exportar_excel
from motor.importador import ErrorImportacion, importar
from motor.muestreo import ErrorMuestreo, muestra_aleatoria, seleccionar_mus
from motor.sintetico import generar, generar_diario_asientos

RAIZ = Path(__file__).resolve().parent


def _mapeo(texto: str | None) -> dict[str, str]:
    if not texto:
        return {}
    pares = [p.split("=", 1) for p in texto.split(",") if p.strip()]
    return {origen.strip(): destino.strip() for origen, destino in pares}


def _archivos(valores: list[str], manifiesto: dict) -> dict[str, Path]:
    """"mayor=ruta" o solo "ruta" (se asigna al primer archivo del paquete)."""
    salida = {}
    for v in valores:
        if "=" in v and not Path(v).exists():
            tabla, ruta = v.split("=", 1)
        else:
            tabla, ruta = manifiesto["archivos"][0]["tabla"], v
        salida[tabla.strip()] = Path(ruta.strip())
    return salida


def correr(paquete: str, archivos: dict[str, Path], encargo_ruta: Path | None, salida: Path | None,
           mapeo: dict[str, str], decimal: str, **opciones) -> Path:
    manifiesto = cargar_manifiesto(RAIZ / "paquetes" / paquete)
    encargo = cargar_encargo(encargo_ruta)
    carpeta = salida or RAIZ / "salidas" / datetime.now().strftime("%Y%m%d-%H%M%S")
    carpeta.mkdir(parents=True, exist_ok=True)
    bitacora = Bitacora(carpeta / "bitacora.jsonl")
    bitacora.registrar("inicio", version_motor=__version__, paquete=manifiesto["id"],
                       version_paquete=manifiesto["version"], encargo=str(encargo_ruta) if encargo_ruta else None)

    con = duckdb.connect()
    controles = []
    for definicion in manifiesto["archivos"]:
        tabla = definicion["tabla"]
        if tabla not in archivos:
            if definicion.get("opcional"):
                continue
            raise ErrorImportacion(f"El paquete necesita el archivo '{tabla}'. Pásalo con --archivo {tabla}=ruta")
        es_principal = definicion is manifiesto["archivos"][0]
        controles.append(importar(
            con, archivos[tabla], tabla,
            mapeo=mapeo if es_principal else None,
            columnas_requeridas=definicion["columnas_requeridas"],
            columnas_monto=definicion.get("columnas_monto"),
            columnas_fecha=definicion.get("columnas_fecha"),
            claves=definicion.get("claves"),
            separador_decimal=decimal,
            bitacora=bitacora,
            **(opciones if es_principal else {}),
        ))

    resultados = correr_paquete(con, manifiesto, bitacora, encargo)
    ruta_excel = exportar_excel(resultados, controles, bitacora, carpeta / "cedula.xlsx", encargo=encargo)

    print(f"\nCuadra {__version__} · paquete {manifiesto['id']} {manifiesto['version']}")
    if encargo.get("cliente"):
        print(f"Encargo: {encargo['cliente']} · cierre {encargo.get('fecha_cierre')}")
    for control in controles:
        print(f"Archivo: {control['archivo']} · {control['filas']} filas · SHA-256 {control['sha256'][:16]}…")
        if control.get("filas_excluidas"):
            print(f"  Filas excluidas (totales o en blanco): {control['filas_excluidas']}")
    print()
    for r in resultados:
        if r.omitida:
            print(f"  [{r.ficha}] {r.nombre:<62} {r.omitida}")
            continue
        detalle = f"MAD {r.resumen['mad']} ({r.resumen['conformidad']})" if "mad" in r.resumen else ""
        if r.resumen.get("advertencia"):
            detalle += "  ⚠ muestra pequeña"
        print(f"  [{r.ficha}] {r.nombre:<62} resultado: {r.excepciones:>4}  {detalle}")
    print(f"\nBitácora íntegra: {'sí' if bitacora.verificar() else 'NO'}")
    print(f"Cédula: {ruta_excel}\n")
    return ruta_excel


def muestra(args) -> Path:
    ruta = Path(args.archivo)
    df = pd.read_excel(ruta) if ruta.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(ruta)
    carpeta = args.salida or RAIZ / "salidas" / datetime.now().strftime("%Y%m%d-%H%M%S")
    carpeta.mkdir(parents=True, exist_ok=True)
    if args.metodo == "mus":
        seleccion, plan = seleccionar_mus(
            df, args.id, args.valor, args.tolerable, args.confianza, args.esperado, args.factor_expansion,
            inicio=args.inicio, semilla=args.semilla,
        )
        resumen = pd.DataFrame([plan.como_dict()]).T.reset_index()
        resumen.columns = ["Parámetro", "Valor"]
        print(f"\nMUS · valor en libros {plan.valor_libros:,.2f} · n = {plan.tamano} · intervalo {plan.intervalo:,.2f} · inicio {plan.inicio:,.2f}")
        print(f"Partidas seleccionadas: {len(seleccion)} (superan el intervalo: {int(seleccion['supera_intervalo'].sum())})")
    else:
        seleccion = muestra_aleatoria(df, args.id, args.n, args.semilla)
        resumen = pd.DataFrame({"Parámetro": ["método", "tamaño", "semilla", "población"],
                                "Valor": ["aleatorio simple", args.n, args.semilla, len(df)]})
        print(f"\nAleatorio simple · n = {args.n} · semilla {args.semilla}")
    destino = carpeta / "muestra.xlsx"
    with pd.ExcelWriter(destino) as xls:
        resumen.to_excel(xls, sheet_name="Plan", index=False)
        seleccion.to_excel(xls, sheet_name="Seleccion", index=False)
    print(f"Muestra: {destino}\n")
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cuadra", description="Analítica de auditoría (prototipo)")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("ejemplo", help="Mayor sintético con el paquete de excepciones básicas")
    sub.add_parser("ejemplo-asientos", help="Diario y balanza sintéticos con el paquete de asientos NIA 240")

    p = sub.add_parser("correr", help="Corre un paquete sobre los archivos de un encargo")
    p.add_argument("--archivo", action="append", required=True, help='"mayor=ruta" o "balanza=ruta"; repetible')
    p.add_argument("--paquete", default="excepciones-basicas")
    p.add_argument("--encargo", type=Path, help="Archivo YAML con materialidad, fecha de cierre y demás parámetros")
    p.add_argument("--salida", type=Path)
    p.add_argument("--mapeo", help='Renombra columnas del mayor: "Columna original=nombre_estandar,..."')
    p.add_argument("--decimal", default=".", help='Separador decimal: "." o ","')
    p.add_argument("--formato-fecha", help='Formato de fecha, por ejemplo "%%d/%%m/%%Y"')
    p.add_argument("--saltar-filas", type=int, help="Filas de título antes del encabezado")
    p.add_argument("--hoja", help="Nombre de la hoja de Excel")
    p.add_argument("--debito-credito", help='Columnas de débito y crédito: "Debe,Haber"')

    m = sub.add_parser("muestra", help="Muestreo MUS o aleatorio sobre una población")
    m.add_argument("--archivo", required=True)
    m.add_argument("--id", required=True, help="Columna identificadora")
    m.add_argument("--valor", help="Columna de valor (MUS)")
    m.add_argument("--metodo", choices=["mus", "aleatorio"], default="mus")
    m.add_argument("--tolerable", type=float, help="Error tolerable (MUS)")
    m.add_argument("--confianza", type=int, default=95, choices=[90, 95])
    m.add_argument("--esperado", type=float, default=0.0, help="Error esperado (MUS)")
    m.add_argument("--factor-expansion", type=float, help="Obligatorio si el error esperado es mayor que cero")
    m.add_argument("--inicio", type=float, help="Inicio aleatorio explícito (si no, se calcula con la semilla)")
    m.add_argument("--semilla", type=int, default=2025)
    m.add_argument("--n", type=int, help="Tamaño (aleatorio simple)")
    m.add_argument("--salida", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.comando == "ejemplo":
            archivo = generar(RAIZ / "datos" / "ejemplo" / "mayor_sintetico_2025.csv")
            correr("excepciones-basicas", {"mayor": archivo}, None, None, {}, ".")
        elif args.comando == "ejemplo-asientos":
            mayor, balanza = generar_diario_asientos(RAIZ / "datos" / "ejemplo")
            correr("asientos-nia240", {"mayor": mayor, "balanza": balanza}, RAIZ / "encargos" / "ejemplo-2025.yaml", None, {}, ".")
        elif args.comando == "muestra":
            muestra(args)
        else:
            manifiesto = cargar_manifiesto(RAIZ / "paquetes" / args.paquete)
            opciones = {
                "formato_fecha": args.formato_fecha,
                "saltar_filas": args.saltar_filas,
                "hoja": args.hoja,
                "debito_credito": tuple(c.strip() for c in args.debito_credito.split(",")) if args.debito_credito else None,
            }
            correr(args.paquete, _archivos(args.archivo, manifiesto), args.encargo, args.salida,
                   _mapeo(args.mapeo), args.decimal, **opciones)
    except (ErrorImportacion, ErrorMuestreo, ValueError) as e:
        print(f"\nNo se pudo completar: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
