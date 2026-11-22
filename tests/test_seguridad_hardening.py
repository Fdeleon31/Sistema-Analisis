"""Pruebas adversarias de ciberseguridad · Oleada 1 / Ficha 20."""
from __future__ import annotations

import sqlite3
import zipfile
import zlib
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd
import pytest

from conectores.estado_cuenta_pdf import (
    _descomprimir_flujos_pdf,
    generar_pdf_estado_cuenta,
    leer_estado_cuenta,
)
from conectores.sql_fuente import (
    _cargar_dump_sql_en_memoria,
    enmascarar_uri,
    es_uri_sql,
    leer_archivo_sql,
    leer_conexion_sql,
    validar_consulta_solo_lectura,
)
from ia.copiloto import ejecutar_propuesta_aprobada, preparar_conexion_copiloto
from motor.bitacora import Bitacora
from motor.ejecutor import ResultadoPrueba
from motor.exportador import exportar_excel
from motor.factura_electronica import leer_facturas, leer_xml
from motor.importador import importar
from motor.seguridad import (
    ErrorSeguridad,
    bloquear_duckdb_externo,
    crear_directorio_temporal_seguro,
    descomprimir_zlib_seguro,
    leer_miembros_zip_seguros,
    nombre_archivo_seguro,
    sanitizar_valor_excel,
)
from motor.sintetico import generar_diario_asientos

RAIZ = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. Sandbox DuckDB, Copiloto y SQL de solo lectura
# ---------------------------------------------------------------------------


def test_copiloto_bloquea_acceso_externo_duckdb_y_es_idempotente(tmp_path):
    mayor, _ = generar_diario_asientos(tmp_path / "datos", semilla=11)
    con, _ = preparar_conexion_copiloto({"mayor": mayor})
    try:
        # Idempotencia sobre conexión ya bloqueada
        bloquear_duckdb_externo(con)

        # Un ataque directo a DuckDB saltando el validador no puede leer archivos del host
        with pytest.raises(duckdb.PermissionException):
            con.execute("SELECT * FROM read_text(?)", [str(RAIZ / "README.md")]).fetchall()

        # Tampoco puede usar funciones bloqueadas a través del copiloto
        with pytest.raises(ErrorSeguridad):
            ejecutar_propuesta_aprobada(
                con,
                "SELECT * FROM read_text('README.md')",
                pregunta="intento lectura archivo",
            )
    finally:
        con.close()


@pytest.mark.parametrize(
    "sql_hostil",
    [
        "SELECT * FROM read_text('README.md')",
        "SELECT * FROM read_csv('datos.csv')",
        "SELECT * FROM read_parquet('datos.parquet')",
        "SELECT * FROM glob('*')",
        "SELECT getenv('PATH')",
        "SELECT * FROM duckdb_secrets()",
        "SELECT * FROM pg_read_file('/etc/passwd')",
        "SELECT xp_cmdshell('dir')",
        "SELECT * INTO nueva_tabla FROM mayor",
        "SET enable_external_access = true",
        "SELECT 1 /* comentario /* anidado */ */ ; DROP TABLE mayor",
        "/* /* sin cerrar",
        "SELECT 'texto sin cerrar",
        "SELECT $$bloque_dollar$$",
    ],
)
def test_validador_sql_rechaza_vectores_hostiles(sql_hostil):
    with pytest.raises(ErrorSeguridad):
        validar_consulta_solo_lectura(sql_hostil)


def test_validador_acepta_comentario_anidado_valido_en_solo_lectura():
    sql = "/* nivel 1 /* nivel 2 */ fin */ SELECT asiento, monto FROM mayor WHERE monto > 0"
    assert validar_consulta_solo_lectura(sql) == sql


def test_leer_archivo_sql_protege_duckdb_y_dumps_sql(tmp_path):
    # .duckdb en modo solo lectura con acceso externo deshabilitado
    ruta_ddb = tmp_path / "diario.duckdb"
    c_ddb = duckdb.connect(str(ruta_ddb))
    c_ddb.execute("CREATE TABLE mayor (asiento INT, monto DOUBLE)")
    c_ddb.execute("INSERT INTO mayor VALUES (1, 100.0)")
    c_ddb.close()

    df, meta = leer_archivo_sql(ruta_ddb, tabla_origen="mayor")
    assert len(df) == 1 and meta["codificacion"] == "DuckDB"
    with pytest.raises(ErrorSeguridad):
        leer_archivo_sql(ruta_ddb, consulta_sql="SELECT * FROM read_text('README.md')")

    # Dumps .sql con instrucciones prohibidas
    for instr in [
        "ATTACH DATABASE ':memory:' AS extra;",
        "CREATE TRIGGER tr AFTER INSERT ON mayor BEGIN SELECT 1; END;",
    ]:
        dump = tmp_path / "hostil.sql"
        dump.write_text(
            "CREATE TABLE mayor (asiento INT, monto REAL);\n" + instr,
            encoding="utf-8",
        )
        with pytest.raises(ErrorSeguridad):
            leer_archivo_sql(dump, tabla_origen="mayor")

    # Límite de tamaño en dump .sql
    dump_ok = tmp_path / "ok.sql"
    dump_ok.write_text("CREATE TABLE t (id INT);\nINSERT INTO t VALUES (1);\n", encoding="utf-8")
    with pytest.raises(ErrorSeguridad, match="límite"):
        _cargar_dump_sql_en_memoria(dump_ok, max_bytes=10)


def test_uri_por_entorno_y_enmascaramiento_de_secretos(tmp_path, monkeypatch):
    uri_secreta = "postgresql://auditor:ClaveMuySecreta@db.interna:5432/erp?password=OtroSecreto&sslmode=require"
    enmascarada = enmascarar_uri(uri_secreta)
    assert "ClaveMuySecreta" not in enmascarada
    assert "OtroSecreto" not in enmascarada
    assert "***" in enmascarada

    assert es_uri_sql("env:TEST_FOLIO_SQL_URI")
    assert enmascarar_uri("env:TEST_FOLIO_SQL_URI") == "env:TEST_FOLIO_SQL_URI"

    monkeypatch.delenv("TEST_FOLIO_SQL_URI", raising=False)
    with pytest.raises(ErrorSeguridad):
        leer_conexion_sql("env:TEST_FOLIO_SQL_URI", tabla_origen="mayor")

    db_ruta = tmp_path / "fuente.sqlite"
    con = sqlite3.connect(db_ruta)
    con.execute("CREATE TABLE mayor (asiento INT, monto REAL)")
    con.execute("INSERT INTO mayor VALUES (10, 250.0)")
    con.commit()
    con.close()

    uri_real = f"sqlite:///{db_ruta.as_posix()}"
    monkeypatch.setenv("TEST_FOLIO_SQL_URI", uri_real)
    df, meta = leer_conexion_sql("env:TEST_FOLIO_SQL_URI", tabla_origen="mayor")
    assert len(df) == 1
    assert "env:TEST_FOLIO_SQL_URI" in meta["archivo"]
    assert db_ruta.as_posix() not in meta["archivo"]


# ---------------------------------------------------------------------------
# 2. Inyección en identificadores y formato de fecha
# ---------------------------------------------------------------------------


def test_importador_escapa_comillas_en_encabezados_y_rechaza_formato_fecha_hostil(tmp_path):
    csv_comilla = tmp_path / "comillas.csv"
    csv_comilla.write_text(
        'asiento,linea,fecha,cuenta,descripcion,monto,usuario,"nota""mal"\n'
        '1,1,2025-02-01,1101,Prueba,100.00,ana,valor\n'
        '1,2,2025-02-01,4101,Prueba,-100.00,ana,valor\n',
        encoding="utf-8",
    )
    con = duckdb.connect()
    try:
        ctrl = importar(con, csv_comilla, "mayor")
        assert ctrl["filas"] == 2
        assert 'nota"mal' in ctrl["columnas"]
    finally:
        con.close()

    con2 = duckdb.connect()
    try:
        with pytest.raises(ErrorSeguridad):
            importar(con2, csv_comilla, "mayor", formato_fecha="%Y-%m-%d') OR 1=1 --")
    finally:
        con2.close()


# ---------------------------------------------------------------------------
# 3. Inyección de fórmulas Excel/CSV (CWE-1236)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("=1+1", "'=1+1"),
        ('=HYPERLINK("http://x","y")', '\'=HYPERLINK("http://x","y")'),
        ("+CMD|' /C calc'!A0", "'+CMD|' /C calc'!A0"),
        ("-2+3+cmd|' /C calc'!A0", "'-2+3+cmd|' /C calc'!A0"),
        ("@SUM(1+1)", "'@SUM(1+1)"),
        ("\t=1+1", "'\t=1+1"),
        ("  =1+1", "'  =1+1"),
        ("-", "-"),
        ("-125.50", "-125.50"),
        ("+45", "+45"),
        ("Pago normal de factura", "Pago normal de factura"),
        (123.45, 123.45),
        (-50, -50),
    ],
)
def test_sanitizar_valor_excel_neutraliza_formulas_y_conserva_numeros(entrada, esperado):
    assert sanitizar_valor_excel(entrada) == esperado


def test_exportar_excel_neutraliza_formulas_en_cedula_sin_alterar_montos(tmp_path):
    df_riesgo = pd.DataFrame([
        {"asiento": 1, "descripcion": "=CMD|' /C calc'!A0", "monto": 1250.50, "estado": "ALERTA"},
        {"asiento": 2, "descripcion": "+2+3", "monto": -1250.50, "estado": "OK"},
    ])
    res = ResultadoPrueba(
        id="prueba-formulas",
        nombre="Prueba con descripciones hostiles",
        ficha="20",
        nia=["NIA 500"],
        tabla=df_riesgo,
    )
    bit = Bitacora(tmp_path / "bitacora.jsonl", usuario="auditor")
    bit.registrar("inicio", paquete="test")
    ruta_xlsx = tmp_path / "cedula.xlsx"

    exportar_excel(
        [res],
        [{"archivo": "=1+1.csv", "tabla": "mayor", "filas": 2, "sha256": "a" * 64}],
        bit,
        ruta_xlsx,
        encargo={"cliente": "@Empresa", "fecha_cierre": "2025-12-31"},
    )

    wb = openpyxl.load_workbook(ruta_xlsx)
    try:
        ws = wb["prueba-formulas"]
        assert ws["B2"].data_type == "s"
        assert ws["B2"].value == "'=CMD|' /C calc'!A0"
        assert ws["B3"].data_type == "s"
        assert ws["B3"].value == "'+2+3"
        assert ws["C2"].value == 1250.50
        assert ws["C3"].value == -1250.50
        assert "#,##0.00" in ws["C2"].number_format

        ws_ctrl = wb["Control de archivos"]
        assert ws_ctrl["A2"].value == "'=1+1.csv"

        ws_enc = wb["Encargo"]
        cliente_val = next(r[1] for r in ws_enc.iter_rows(min_row=2, values_only=True) if r[0] == "cliente")
        assert cliente_val == "'@Empresa"
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# 4. XML XXE / Billion Laughs y ZIP Bomb (Factura Electrónica)
# ---------------------------------------------------------------------------


def test_xml_xxe_y_billion_laughs_rechazados(tmp_path):
    xml_xxe = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<!DOCTYPE foo [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
        b"<rFE><dId>&lol2;</dId></rFE>"
    )
    with pytest.raises(ErrorSeguridad, match="DTD/ENTITY"):
        leer_xml(xml_xxe, "xxe.xml")

    xml_utf16 = ('<?xml version="1.0"?><!DOCTYPE rFE [<!ENTITY x SYSTEM "file:///etc/passwd">]><rFE/>').encode("utf-16-le")
    with pytest.raises(ErrorSeguridad):
        leer_xml(xml_utf16, "xxe_utf16.xml")

    zip_xxe = tmp_path / "fe_xxe.zip"
    with zipfile.ZipFile(zip_xxe, "w") as z:
        z.writestr("hostil.xml", xml_xxe)

    lec = leer_facturas(zip_xxe)
    assert lec.facturas.empty
    assert len(lec.errores) == 1
    assert "DTD/ENTITY" in lec.errores[0]["error"]


def test_zip_traversal_y_zip_bomb_rechazados(tmp_path):
    zip_trav = tmp_path / "traversal.zip"
    with zipfile.ZipFile(zip_trav, "w") as z:
        z.writestr("../../evil.xml", b"<rFE></rFE>")

    with pytest.raises(ErrorSeguridad, match="Path traversal"):
        leer_facturas(zip_trav)

    zip_bomb = tmp_path / "bomba.zip"
    with zipfile.ZipFile(zip_bomb, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("inflado.xml", b"0" * (1_500_000))

    with pytest.raises(ErrorSeguridad, match="ratio"):
        list(leer_miembros_zip_seguros(zip_bomb, extensiones=(".xml",), max_ratio=100.0))

    with pytest.raises(ErrorSeguridad, match="límite"):
        list(leer_miembros_zip_seguros(zip_bomb, extensiones=(".xml",), max_bytes_archivo=500_000))


# ---------------------------------------------------------------------------
# 5. PDF zlib bomb y colisión de ZIP en extractos bancarios
# ---------------------------------------------------------------------------


def test_pdf_zlib_bomb_rechazada_y_zip_sin_colision_de_nombres(tmp_path):
    flujo_grande = zlib.compress(b"BT (hola) Tj ET " * 5000)
    with pytest.raises(ErrorSeguridad, match="bomba"):
        descomprimir_zlib_seguro(flujo_grande, max_bytes=1024)

    pdf_falso = (
        b"%PDF-1.4\n1 0 obj\n<< /Length "
        + str(len(flujo_grande)).encode("ascii")
        + b" /Filter /FlateDecode >>\nstream\n"
        + flujo_grande
        + b"\nendstream\nendobj\n%%EOF"
    )
    with pytest.raises(ErrorSeguridad):
        _descomprimir_flujos_pdf(pdf_falso, max_bytes_flujo=1024)

    # ZIP con traversal en extracto bancario
    zip_trav = tmp_path / "ext_trav.zip"
    with zipfile.ZipFile(zip_trav, "w") as z:
        z.writestr("../escape.pdf", b"%PDF-1.4")
    with pytest.raises(ErrorSeguridad):
        leer_estado_cuenta(zip_trav)

    # ZIP con dos PDFs con el mismo nombre en subcarpetas distintas no debe sobrescribirse
    pdf_ene = tmp_path / "ene.pdf"
    pdf_feb = tmp_path / "feb.pdf"
    generar_pdf_estado_cuenta(
        pdf_ene,
        ["BANCO GENERAL", "Cuenta: 04-01-99-123456-7"],
        [{"fecha": "2025-01-15", "referencia": "DEP-1", "descripcion": "Abono enero", "debito": 0.0, "credito": 100.0, "saldo": 100.0}],
    )
    generar_pdf_estado_cuenta(
        pdf_feb,
        ["BANCO GENERAL", "Cuenta: 04-01-99-123456-7"],
        [{"fecha": "2025-02-15", "referencia": "DEP-2", "descripcion": "Abono febrero", "debito": 0.0, "credito": 200.0, "saldo": 300.0}],
    )
    zip_dup = tmp_path / "extractos_meses.zip"
    with zipfile.ZipFile(zip_dup, "w") as z:
        z.write(pdf_ene, "ene/estado.pdf")
        z.write(pdf_feb, "feb/estado.pdf")

    lec = leer_estado_cuenta(zip_dup)
    assert lec.archivos == 2
    assert len(lec.movimientos) == 2
    assert set(lec.movimientos["referencia"]) == {"DEP-1", "DEP-2"}


# ---------------------------------------------------------------------------
# 6. Aislamiento de interfaz web local y archivos temporales
# ---------------------------------------------------------------------------


def test_configuracion_web_local_y_saneamiento_de_temporales():
    cfg = (RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'address = "127.0.0.1"' in cfg
    assert "enableXsrfProtection = true" in cfg
    assert "enableCORS = false" in cfg
    assert "gatherUsageStats = false" in cfg

    bat = (RAIZ / "iniciar.bat").read_text(encoding="utf-8")
    assert "--server.address 127.0.0.1" in bat
    assert "--server.enableXsrfProtection true" in bat

    for malo in ["../../secreto.csv", "..\\secreto.csv", "/etc/passwd", "C:\\temp\\a.csv", "a\x00b.csv", ""]:
        with pytest.raises(ErrorSeguridad):
            nombre_archivo_seguro(malo)

    assert nombre_archivo_seguro("mayor_2025.xlsx") == "mayor_2025.xlsx"

    tmp_dir = crear_directorio_temporal_seguro("test_folio_")
    assert tmp_dir.exists() and tmp_dir.is_dir()
    tmp_dir.rmdir()
