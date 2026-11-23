"""Cuadra · línea de comandos.

Ejemplos:
    python cuadra.py ejemplo
    python cuadra.py ejemplo-asientos
    python cuadra.py conectores
    python cuadra.py escritorio
    python cuadra.py correr --paquete asientos-nia240 --encargo encargos/ejemplo-2025.yaml \
        --archivo mayor=datos/mayor.csv --archivo balanza=datos/balanza.xlsx
    python cuadra.py muestra --archivo datos/cxc.csv --id cliente --valor saldo --tolerable 45000
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from conectores.catalogo import obtener_perfil, perfiles_disponibles
from conectores.sql_fuente import es_uri_sql
from herramientas.seguridad_build import (
    escanear_seguridad_estatico,
    generar_lockfile_entorno,
    generar_sbom_cyclonedx,
)
from ia.copiloto import ejecutar_propuesta_aprobada, preparar_conexion_copiloto, proponer_consulta_sql
from motor import __version__
from motor.bitacora import Bitacora
from motor.cripto import verificar_sello_corrida
from motor.ejecutor import cargar_encargo, cargar_manifiesto
from motor.importador import ErrorImportacion
from motor.muestreo import ErrorMuestreo, evaluar_mus, seleccionar_mus
from motor.privacidad import (
    aplicar_acl_solo_usuario_actual,
    cifrar_carpeta_corrida,
    descifrar_carpeta_corrida,
    evaluar_postura_entorno,
    exportar_diagnostico_anonimizado,
    purgar_corridas_expiradas,
)
from motor.rutas import raiz_recursos, raiz_trabajo
from motor.seguridad import ErrorSeguridad, sanitizar_dataframe_excel
from motor.servicio import ejecutar_encargo
from motor.sintetico import generar, generar_diario_asientos, generar_estado_cuenta_bancos, generar_facturas_fe

RAIZ = raiz_trabajo()


def _registro_claves_para_verificar(ruta: Path | None) -> tuple[dict | None, str]:
    """Carga el ancla de claves para `verificar`: archivo exportado o seguridad/usuarios.json local."""
    if ruta is not None:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        claves = datos.get("claves") if isinstance(datos, dict) else None
        if not isinstance(claves, dict):
            raise ErrorSeguridad(f"{ruta} no es un registro de claves de Folio Auditor.")
        return claves, str(ruta)
    from motor.usuarios import GestorUsuarios

    registro = GestorUsuarios(RAIZ).registro_claves()
    if registro:
        return registro, "seguridad/usuarios.json (local)"
    return None, "ninguno (usa --claves con el registro exportado por la firma)"


def _mapeo(texto: str | None) -> dict[str, str]:
    if not texto:
        return {}
    pares = [p.split("=", 1) for p in texto.split(",") if p.strip()]
    return {origen.strip(): destino.strip() for origen, destino in pares}


def _indicador_dc(texto: str | None) -> str | tuple[str, tuple[str, ...]] | None:
    if not texto:
        return None
    if ":" in texto:
        col, vals = texto.split(":", 1)
        return (col.strip(), tuple(v.strip() for v in vals.split(",") if v.strip()))
    return texto.strip()


def _archivos(valores: list[str], manifiesto: dict) -> dict[str, Path | str]:
    """"mayor=ruta", "mayor=uri_sql" o solo "ruta"/"uri_sql"."""
    salida: dict[str, Path | str] = {}
    for v in valores:
        v_limpio = v.strip()
        if es_uri_sql(v_limpio):
            tabla, destino = manifiesto["archivos"][0]["tabla"], v_limpio
        elif "=" in v_limpio and not Path(v_limpio).exists() and "://" not in v_limpio.split("=", 1)[0]:
            tabla, destino = v_limpio.split("=", 1)
        else:
            tabla, destino = manifiesto["archivos"][0]["tabla"], v_limpio
        destino = destino.strip()
        salida[tabla.strip()] = destino if es_uri_sql(destino) else Path(destino)
    return salida


def correr(paquete: str, archivos: dict[str, Path | str], encargo_ruta: Path | None, salida: Path | None,
           mapeo: dict[str, str], decimal: str, **opciones) -> Path:
    manifiesto = cargar_manifiesto(raiz_recursos() / "paquetes" / paquete)
    encargo = cargar_encargo(encargo_ruta)
    principal = manifiesto["archivos"][0]["tabla"]
    corrida = ejecutar_encargo(paquete, archivos, encargo, salida,
                               opciones={principal: {"mapeo": mapeo, **opciones}}, separador_decimal=decimal)

    print(f"\nCuadra {__version__} · paquete {manifiesto['id']} {manifiesto['version']}")
    if encargo.get("cliente"):
        print(f"Encargo: {encargo['cliente']} · cierre {encargo.get('fecha_cierre')}")
    for control in corrida.controles:
        erp = f" · perfil {control['perfil_erp']}" if control.get("perfil_erp") else ""
        print(f"Archivo: {control['archivo']} · {control['filas']} filas · SHA-256 {control['sha256'][:16]}…{erp}")
        if control.get("filas_excluidas"):
            motivo = "XML ilegibles" if "archivos_xml" in control else "Filas excluidas (totales o en blanco)"
            print(f"  {motivo}: {control['filas_excluidas']}")
    print()
    for r in corrida.resultados:
        if r.omitida:
            print(f"  [{r.ficha}] {r.nombre:<62} {r.omitida}")
            continue
        detalle = f"MAD {r.resumen['mad']} ({r.resumen['conformidad']})" if "mad" in r.resumen else ""
        if "por_nivel" in r.resumen:
            pn = r.resumen["por_nivel"]
            detalle = f"alto {pn['alto']}, medio {pn['medio']}, bajo {pn['bajo']}"
        if r.resumen.get("advertencia"):
            detalle += "  ⚠ muestra pequeña"
        print(f"  [{r.ficha}] {r.nombre:<62} resultado: {r.excepciones:>4}  {detalle}")
    print(f"\nBitácora íntegra: {'sí' if corrida.bitacora.verificar() else 'NO'}")
    print(f"Cédula: {corrida.cedula}\n")
    return corrida.cedula


def listar_conectores(erp_id: str | None = None) -> None:
    if erp_id:
        p = obtener_perfil(erp_id)
        print(f"\n{p['nombre']} ({p['id']})")
        print(f"Segmento en Panamá: {p.get('segmento_panama', '')}")
        print(f"Origen: {p.get('motor_origen', '')}")
        print(f"Formatos: {', '.join(p.get('formatos_frecuentes', []))}")
        print(f"\n{p.get('descripcion', '').strip()}")
        print("\nMapeo de columnas estándar:")
        for std, aliases in (p.get("aliases") or {}).items():
            print(f"  {std:<12} <- {', '.join(aliases)}")
        if p.get("debito_credito_pares"):
            pares = [" / ".join(par) for par in p["debito_credito_pares"]]
            print(f"  debe/haber   <- {', '.join(pares)}")
        if p.get("indicador_dc"):
            ind = p["indicador_dc"]
            print(f"  indicador    <- {', '.join(ind.get('columnas', []))} (crédito: {', '.join(ind.get('valores_credito', []))})")
        for q in p.get("consultas_sql") or []:
            print(f"\n--- {q['titulo']} ---")
            print(q["sql"].strip())
        print()
        return

    perfiles = perfiles_disponibles()
    print(f"\nConectores ERP del mercado panameño ({len(perfiles)} perfiles):")
    print("Formatos soportados: CSV, TSV, TXT (incluido SAP ALV '|'), Excel, Parquet, JSON/JSONL, SQLite, DuckDB, .sql y URI SQL.\n")
    for pid, p in perfiles.items():
        print(f"  {pid:<20} {p['nombre']:<38} {p.get('segmento_panama', '')}")
    print("\nUsa `python cuadra.py conectores --erp <id>` para ver alias y consultas SQL.\n")


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
        sanitizar_dataframe_excel(resumen).to_excel(xls, sheet_name="Plan", index=False)
        sanitizar_dataframe_excel(seleccion).to_excel(xls, sheet_name="Seleccion", index=False)
    print(f"Muestra: {destino}\n")
    return destino


def evaluar(args) -> Path:
    ruta = Path(args.errores)
    df = pd.read_excel(ruta) if ruta.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(ruta)
    r = evaluar_mus(df, args.intervalo, args.tolerable, args.confianza, args.id, args.libros, args.auditado)
    carpeta = args.salida or RAIZ / "salidas" / datetime.now().strftime("%Y%m%d-%H%M%S")
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / "evaluacion_mus.xlsx"
    with pd.ExcelWriter(destino) as xls:
        sanitizar_dataframe_excel(pd.DataFrame(list(r.resumen().items()), columns=["Concepto", "Valor"])).to_excel(
            xls, sheet_name="Resumen", index=False
        )
        sanitizar_dataframe_excel(r.detalle).to_excel(xls, sheet_name="Sobrestimaciones", index=False)
        sanitizar_dataframe_excel(r.subestimaciones).to_excel(xls, sheet_name="Subestimaciones", index=False)
    print(f"\nEvaluación MUS · precisión básica {r.precision_basica:,.2f} · proyectado {r.error_proyectado:,.2f} · "
          f"margen {r.margen_incremental:,.2f} · límite superior {r.limite_superior:,.2f}")
    print(r.conclusion)
    print(f"Evaluación: {destino}\n")
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cuadra", description="Analítica de auditoría (prototipo)")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("ejemplo", help="Mayor sintético con el paquete de excepciones básicas")
    sub.add_parser("ejemplo-asientos", help="Diario y balanza sintéticos con el paquete de asientos NIA 240")
    sub.add_parser("ejemplo-fe", help="Facturas electrónicas sintéticas contra el mayor de ventas")
    sub.add_parser("ejemplo-bancos", help="Extracto bancario en PDF y mayor sintéticos con conciliación bancaria")

    c = sub.add_parser("conectores", help="Lista los perfiles ERP de Panamá y formatos SQL/datos soportados")
    c.add_argument("--erp", help="Muestra el detalle, alias y consulta SQL de un perfil específico")

    esc = sub.add_parser("escritorio", help="Abre la aplicación nativa de escritorio (PySide6, 100 %% sin internet)")
    esc.add_argument("--autoprueba", action="store_true", help="Ejecuta la autoprueba de escritorio sin mostrar ventana y sale")
    esc.add_argument("--sin-login", action="store_true", help="Abre el escritorio sin inicio de sesión (solo si el control de acceso no está activado)")

    ver = sub.add_parser("verificar", help="Verifica integridad criptográfica (Ed25519 + SHA-256) de una carpeta de corrida")
    ver.add_argument("carpeta", type=Path, help="Ruta de la carpeta de salida a verificar")
    ver.add_argument(
        "--claves", type=Path,
        help="Registro de claves de la firma (JSON de 'seguridad --exportar-claves'). Por defecto usa seguridad/usuarios.json",
    )

    seg = sub.add_parser("seguridad", help="Controles de ciberseguridad: SAST, SBOM, lockfile, bóveda, ACLs y anonimización")
    seg.add_argument("--escanear", action="store_true", help="Ejecuta el escaneo estático SAST/secretos/configuración")
    seg.add_argument("--sbom", type=Path, help="Genera el SBOM CycloneDX 1.5 en la ruta indicada")
    seg.add_argument("--lockfile", type=Path, help="Genera el archivo requirements.lock del entorno activo")
    seg.add_argument("--entorno", action="store_true", help="Evalúa la postura local de seguridad y nube (Ley 81)")
    seg.add_argument("--anonimizar", type=Path, help="Exporta un diagnóstico técnico anonimizado de una corrida")
    seg.add_argument("--salida", type=Path, help="Archivo JSON de salida para --anonimizar")
    seg.add_argument("--cifrar", type=Path, help="Cifra en bóveda AES-256-GCM (.folioenc) los archivos de una carpeta")
    seg.add_argument("--descifrar", type=Path, help="Descifra archivos .folioenc dentro de una carpeta")
    seg.add_argument("--dpapi", action="store_true", help="Usa Windows DPAPI al cifrar con --cifrar")
    seg.add_argument("--borrar-origen", action="store_true", help="Sobrescribe y elimina los archivos en claro tras --cifrar")
    seg.add_argument("--aplicar-acl", type=Path, help="Restringe permisos NTFS/POSIX de la ruta al usuario actual")
    seg.add_argument("--purgar-expiradas", type=Path, help="Detecta (y elimina con --ejecutar-purga) corridas expiradas")
    seg.add_argument("--dias-retencion", type=int, default=1825, help="Días de retención para --purgar-expiradas (defecto 1825)")
    seg.add_argument("--exportar-claves", type=Path, help="Exporta el registro público de claves de firma (huellas) a un JSON para el auditor externo")
    seg.add_argument("--ejecutar-purga", action="store_true", help="Elimina efectivamente las corridas detectadas por --purgar-expiradas")

    cop = sub.add_parser("copiloto", help="Traduce una pregunta en español a SQL visible y la ejecuta si se aprueba")
    cop.add_argument("--pregunta", required=True, help="Pregunta analítica en lenguaje natural")
    cop.add_argument("--archivo", action="append", default=[], help='"mayor=ruta" (opcional; por defecto usa ejemplo sintético)')
    cop.add_argument("--encargo", type=Path)
    cop.add_argument("--aprobar", action="store_true", help="Aprueba y ejecuta en DuckDB el SQL propuesto")

    p = sub.add_parser("correr", help="Corre un paquete sobre los archivos o fuentes SQL de un encargo")
    p.add_argument("--archivo", action="append", required=True, help='"mayor=ruta_o_uri" o "balanza=ruta_o_uri"; repetible')
    p.add_argument("--paquete", default="excepciones-basicas")
    p.add_argument("--encargo", type=Path, help="Archivo YAML con materialidad, fecha de cierre y demás parámetros")
    p.add_argument("--salida", type=Path)
    p.add_argument("--erp", help='"auto" o id de perfil ERP (ej. sap-ecc-s4, sap-b1, softland-exactus, sage50-peachtree)')
    p.add_argument("--mapeo", help='Renombra columnas del mayor: "Columna original=nombre_estandar,..."')
    p.add_argument("--decimal", default=".", help='Separador decimal: "." o ","')
    p.add_argument("--formato-fecha", help='Formato de fecha, por ejemplo "%%d/%%m/%%Y"')
    p.add_argument("--saltar-filas", type=int, help="Filas de título antes del encabezado")
    p.add_argument("--hoja", help="Nombre de la hoja de Excel")
    p.add_argument("--debito-credito", help='Columnas de débito y crédito: "Debe,Haber"')
    p.add_argument("--indicador-dc", help='Columna indicadora D/H (ej. "SHKZG" o "SHKZG:H,C")')
    p.add_argument("--generar-linea", action="store_true", help='Genera "linea" secuencial por asiento si el origen no la trae')
    p.add_argument("--usuario-defecto", help='Asigna un valor por defecto a "usuario" si el origen no lo trae')
    p.add_argument("--tabla-origen", help="Tabla a consultar cuando el origen es SQL (.sqlite, .duckdb, .sql o URI)")
    p.add_argument("--consulta-sql", help="Consulta SELECT de solo lectura para extraer datos desde una fuente SQL")

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

    ev = sub.add_parser("evaluar", help="Evalúa una muestra MUS con los errores encontrados")
    ev.add_argument("--errores", required=True, help="CSV o Excel con id, valor en libros y valor auditado")
    ev.add_argument("--intervalo", type=float, required=True)
    ev.add_argument("--tolerable", type=float, required=True)
    ev.add_argument("--confianza", type=int, default=95, choices=[90, 95])
    ev.add_argument("--id", default="id")
    ev.add_argument("--libros", default="valor_libros")
    ev.add_argument("--auditado", default="valor_auditado")
    ev.add_argument("--salida", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.comando == "ejemplo":
            archivo = generar(RAIZ / "datos" / "ejemplo" / "mayor_sintetico_2025.csv")
            correr("excepciones-basicas", {"mayor": archivo}, None, None, {}, ".")
        elif args.comando == "ejemplo-asientos":
            mayor, balanza = generar_diario_asientos(RAIZ / "datos" / "ejemplo")
            correr("asientos-nia240", {"mayor": mayor, "balanza": balanza}, RAIZ / "encargos" / "ejemplo-2025.yaml", None, {}, ".")
        elif args.comando == "ejemplo-fe":
            zip_fe, mayor = generar_facturas_fe(RAIZ / "datos" / "ejemplo")
            correr("ventas-fe", {"facturas": zip_fe, "mayor": mayor}, RAIZ / "encargos" / "ejemplo-2025.yaml", None, {}, ".")
        elif args.comando == "ejemplo-bancos":
            pdf, mayor = generar_estado_cuenta_bancos(RAIZ / "datos" / "ejemplo")
            correr("bancos-conciliacion", {"extracto": pdf, "mayor": mayor}, RAIZ / "encargos" / "ejemplo-2025.yaml", None, {}, ".")
        elif args.comando == "conectores":
            listar_conectores(args.erp)
        elif args.comando == "escritorio":
            from app.escritorio import iniciar_escritorio
            esc_argv: list[str] = []
            if args.autoprueba:
                esc_argv.append("--autoprueba")
            if args.sin_login:
                esc_argv.append("--sin-login")
            return iniciar_escritorio(esc_argv)
        elif args.comando == "verificar":
            carpeta_ver = Path(args.carpeta)
            if (carpeta_ver / "sello.json").exists():
                registro, origen_registro = _registro_claves_para_verificar(args.claves)
                res = verificar_sello_corrida(carpeta_ver, claves_registradas=registro)
                if not res["valido"]:
                    estado = "INVÁLIDO"
                elif res["firmante_verificado"]:
                    estado = "VÁLIDO"
                else:
                    estado = "ÍNTEGRO, FIRMANTE SIN VERIFICAR"
                print(f"\nVerificación de sello Ed25519 ({carpeta_ver}): {estado}")
                print(f"Motivo: {res['motivo']}")
                if res.get("huella_clave"):
                    print(f"Firmante: {res.get('usuario')} ({res.get('rol')}) · Huella {res['huella_clave'][:16]}…")
                print(f"Registro de claves usado: {origen_registro}")
                if not res["valido"]:
                    return 1
                return 0 if res["firmante_verificado"] else 2
            ruta_bit = carpeta_ver / "bitacora.jsonl"
            if not ruta_bit.exists():
                print(f"\nNo se encontró bitacora.jsonl ni sello.json en {carpeta_ver}\n")
                return 1
            integra = Bitacora(ruta_bit).verificar()
            print(f"\nSin sello.json; cadena SHA-256 de bitácora: {'ÍNTEGRA' if integra else 'ALTERADA'}\n")
            return 0 if integra else 1
        elif args.comando == "seguridad":
            acciones = [
                args.escanear, args.sbom, args.lockfile, args.entorno, args.anonimizar,
                args.cifrar, args.descifrar, args.aplicar_acl, args.purgar_expiradas, args.exportar_claves,
            ]
            if not any(acciones):
                print("\nUsa --escanear, --sbom, --lockfile, --entorno, --anonimizar, --cifrar, --descifrar, --aplicar-acl o --purgar-expiradas.\n")
                return 0
            codigo_seg = 0
            if args.escanear:
                hallazgos = escanear_seguridad_estatico(RAIZ)
                if hallazgos:
                    for h in hallazgos:
                        print(f"[{h['severidad']}] {h['regla']} {h['archivo']}:{h['linea']} - {h['detalle']}")
                    codigo_seg = 1
                else:
                    print("Escaneo estático limpio: 0 hallazgos.")
            if args.exportar_claves is not None:
                from motor.usuarios import GestorUsuarios

                registro = GestorUsuarios(RAIZ).registro_claves()
                if not registro:
                    print("No hay usuarios registrados (seguridad/usuarios.json); nada que exportar.")
                    codigo_seg = 1
                else:
                    args.exportar_claves.parent.mkdir(parents=True, exist_ok=True)
                    args.exportar_claves.write_text(
                        json.dumps({"tipo": "registro_claves_folio", "version": 1, "claves": registro}, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(f"Registro de {len(registro)} clave(s) exportado en {args.exportar_claves}. Entrégalo al auditor externo para `verificar --claves`.")
            if args.sbom is not None:
                sbom = generar_sbom_cyclonedx(args.sbom)
                print(f"SBOM CycloneDX {sbom['specVersion']} generado en {args.sbom} ({len(sbom['components'])} componentes).")
            if args.lockfile is not None:
                ruta_lock = generar_lockfile_entorno(args.lockfile)
                print(f"Lockfile generado en {ruta_lock}.")
            if args.entorno:
                postura = evaluar_postura_entorno(RAIZ)
                print(json.dumps(postura, indent=2, ensure_ascii=False))
            if args.anonimizar is not None:
                diag = exportar_diagnostico_anonimizado(args.anonimizar, destino=args.salida)
                print(json.dumps(diag, indent=2, ensure_ascii=False))
            if args.cifrar is not None:
                if args.dpapi:
                    rutas_enc = cifrar_carpeta_corrida(args.cifrar, usar_dpapi=True, borrar_origen=args.borrar_origen)
                else:
                    clave = os.environ.get("FOLIO_BOVEDA_PASS") or ""
                    if not clave and sys.stdin and sys.stdin.isatty():
                        c1 = getpass.getpass("Contraseña para cifrar bóveda: ")
                        c2 = getpass.getpass("Confirmar contraseña: ")
                        if c1 != c2:
                            raise ErrorSeguridad("Las contraseñas ingresadas no coinciden.")
                        clave = c1
                    if not clave:
                        raise ErrorSeguridad("Define FOLIO_BOVEDA_PASS o indica --dpapi para cifrar la carpeta.")
                    rutas_enc = cifrar_carpeta_corrida(args.cifrar, contrasena=clave, borrar_origen=args.borrar_origen)
                print(f"Bóveda cifrada: {len(rutas_enc)} archivo(s) .folioenc generados.")
            if args.descifrar is not None:
                clave = os.environ.get("FOLIO_BOVEDA_PASS") or None
                try:
                    rutas_dec = descifrar_carpeta_corrida(args.descifrar, contrasena=clave)
                except ErrorSeguridad as exc:
                    if not clave and "contraseña" in str(exc).lower() and sys.stdin and sys.stdin.isatty():
                        clave = getpass.getpass("Contraseña de bóveda (.folioenc): ")
                        rutas_dec = descifrar_carpeta_corrida(args.descifrar, contrasena=clave)
                    else:
                        raise
                print(f"Bóveda descifrada: {len(rutas_dec)} archivo(s) restaurados.")
            if args.aplicar_acl is not None:
                res_acl = aplicar_acl_solo_usuario_actual(args.aplicar_acl)
                print(json.dumps(res_acl, indent=2, ensure_ascii=False))
                if not res_acl.get("aplicado"):
                    codigo_seg = 1
            if args.purgar_expiradas is not None:
                expiradas = purgar_corridas_expiradas(
                    args.purgar_expiradas,
                    dias_retencion=args.dias_retencion,
                    simular=not args.ejecutar_purga,
                )
                print(json.dumps({
                    "modo": "ejecucion" if args.ejecutar_purga else "simulacion",
                    "dias_retencion": args.dias_retencion,
                    "carpetas": [str(p) for p in expiradas],
                }, indent=2, ensure_ascii=False))
            return codigo_seg
        elif args.comando == "copiloto":
            enc = cargar_encargo(args.encargo) if args.encargo else cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")
            if not args.archivo:
                mayor_ruta, _ = generar_diario_asientos(RAIZ / "datos" / "ejemplo")
                fuentes = {"mayor": mayor_ruta}
            else:
                fuentes = {}
                for item in args.archivo:
                    t, r = item.split("=", 1) if "=" in item else ("mayor", item)
                    fuentes[t.strip()] = Path(r.strip())
            con, tablas_cols = preparar_conexion_copiloto(fuentes)
            prop = proponer_consulta_sql(args.pregunta, tablas_cols, enc)
            print(f"\n[{prop.titulo}] ({', '.join(prop.nia)})\n{prop.explicacion}\n\nSQL propuesto:\n{prop.sql}\n")
            if args.aprobar:
                res = ejecutar_propuesta_aprobada(
                    con, prop.sql, prop.pregunta, prop.titulo, prop.nia, prop.explicacion, encargo=enc
                )
                print(f"Filas: {len(res.tabla)} · SHA-256: {res.sql_sha256[:16]}…\n")
                if not res.tabla.empty:
                    print(res.tabla.head(15).to_string(index=False))
                print(f"\n{res.borrador}")
            else:
                print("(Agrega --aprobar para ejecutar esta consulta en DuckDB.)\n")
            con.close()
        elif args.comando == "muestra":
            muestra(args)
        elif args.comando == "evaluar":
            evaluar(args)
        else:
            manifiesto = cargar_manifiesto(raiz_recursos() / "paquetes" / args.paquete)
            opciones = {
                "formato_fecha": args.formato_fecha,
                "saltar_filas": args.saltar_filas,
                "hoja": args.hoja,
                "debito_credito": tuple(c.strip() for c in args.debito_credito.split(",")) if args.debito_credito else None,
                "indicador_dc": _indicador_dc(args.indicador_dc),
                "generar_linea": True if args.generar_linea else None,
                "usuario_por_defecto": args.usuario_defecto,
                "tabla_origen": args.tabla_origen,
                "consulta_sql": args.consulta_sql,
                "perfil_erp": args.erp,
            }
            correr(args.paquete, _archivos(args.archivo, manifiesto), args.encargo, args.salida,
                   _mapeo(args.mapeo), args.decimal, **opciones)
    except (ErrorImportacion, ErrorMuestreo, ValueError) as e:
        print(f"\nNo se pudo completar: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
