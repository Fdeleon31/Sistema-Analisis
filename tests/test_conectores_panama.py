"""Pruebas de conectores ERP del mercado panameño, SAP y fuentes SQL/multiformato (Ficha 12)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from archivos_realistas import base
from conectores import (
    detectar_perfil,
    enmascarar_uri,
    leer_conexion_sql,
    perfiles_disponibles,
    validar_consulta_solo_lectura,
)
from motor.importador import ErrorImportacion, detectar_codificacion
from motor.servicio import ejecutar_encargo

FILAS_BASE = 4994


@pytest.fixture(scope="module")
def df_base(tmp_path_factory):
    return base(tmp_path_factory.mktemp("panama_base"))


def _verificar_resultados_excepciones(corrida, perfil_esperado: str | None = None):
    control = corrida.controles[0]
    assert control["filas"] == FILAS_BASE
    assert control["totales"]["monto"] == 0.0
    if perfil_esperado:
        assert control.get("perfil_erp") == perfil_esperado
    r = {x.id: x for x in corrida.resultados}
    assert r["gaps-asientos"].tabla[["desde", "hasta"]].values.tolist() == [[1500, 1502], [2200, 2200]]
    assert len(r["duplicados-exactos"].tabla) == 4
    assert len(r["mismo-mismo-distinto"].tabla) == 2
    assert [d.isoformat() for d in r["gaps-fechas"].tabla["dia"].dt.date] == ["2025-07-15"]
    assert corrida.bitacora.verificar()


def test_sap_ecc_alv_pipe_shkzg_yyyymmdd(df_base, tmp_path):
    ruta = tmp_path / "fbl3n_alv.txt"
    lineas = [
        "-" * 92,
        "|BELNR     |BUZEI|BUDAT   |HKONT |SGTXT                              |DMBTR       |SHKZG|USNAM     |",
        "-" * 92,
    ]
    for _, f in df_base.iterrows():
        fecha_sap = str(f["fecha"]).replace("-", "")
        monto = float(f["monto"])
        ind = "S" if monto >= 0 else "H"
        monto_txt = f"{abs(monto):,.2f}"
        lineas.append(
            f"|{int(f['asiento']):<10}|{int(f['linea']):<5}|{fecha_sap}|{f['cuenta']:<6}|"
            f"{str(f['descripcion']):<35}|{monto_txt:>12}|{ind:<5}|{f['usuario']:<10}|"
        )
    lineas.append("-" * 92)
    ruta.write_text("\n".join(lineas), encoding="utf-8")

    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": ruta},
        salida=tmp_path / "sal_sap_ecc",
        opciones={"mayor": {"perfil_erp": "auto"}},
    )
    _verificar_resultados_excepciones(corrida, "sap-ecc-s4")
    trans = " ".join(corrida.controles[0]["transformaciones"])
    assert "SAP ALV" in trans
    assert "SHKZG" in trans


def test_sap_business_one_sqlite_join(df_base, tmp_path):
    ruta = tmp_path / "sap_b1.sqlite"
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE OJDT (TransId INTEGER PRIMARY KEY, RefDate TEXT, U_NAME TEXT)")
    con.execute(
        "CREATE TABLE JDT1 (TransId INTEGER, Line_ID INTEGER, RefDate TEXT, Account TEXT, LineMemo TEXT, Debit REAL, Credit REAL)"
    )
    encabezados = df_base[["asiento", "fecha", "usuario"]].drop_duplicates(subset=["asiento"])
    con.executemany(
        "INSERT INTO OJDT (TransId, RefDate, U_NAME) VALUES (?, ?, ?)",
        [(int(r.asiento), str(r.fecha), str(r.usuario)) for r in encabezados.itertuples()],
    )
    con.executemany(
        "INSERT INTO JDT1 (TransId, Line_ID, RefDate, Account, LineMemo, Debit, Credit) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                int(r.asiento),
                int(r.linea),
                str(r.fecha),
                str(r.cuenta),
                str(r.descripcion),
                max(float(r.monto), 0.0),
                max(-float(r.monto), 0.0),
            )
            for r in df_base.itertuples()
        ],
    )
    con.commit()
    con.close()

    consulta = (
        "SELECT h.TransId AS TransId, l.Line_ID AS Line_ID, l.RefDate AS RefDate, "
        "l.Account AS Account, l.LineMemo AS LineMemo, l.Debit AS Debit, l.Credit AS Credit, "
        "h.U_NAME AS U_NAME FROM OJDT h INNER JOIN JDT1 l ON l.TransId = h.TransId"
    )
    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": ruta},
        salida=tmp_path / "sal_sap_b1",
        opciones={"mayor": {"perfil_erp": "auto", "consulta_sql": consulta}},
    )
    _verificar_resultados_excepciones(corrida, "sap-b1")
    assert corrida.controles[0]["codificacion"] == "SQLite"


def test_softland_exactus_sql_dump(df_base, tmp_path):
    ruta = tmp_path / "softland_diario.sql"
    lineas = [
        "-- Volcado sintético estilo Softland / Exactus",
        "SET NOCOUNT ON;",
        "CREATE TABLE dbo.DIARIO ("
        "ASIENTO INT, CONSECUTIVO INT, FECHA VARCHAR(10), CUENTA_CONTABLE VARCHAR(20), "
        "REFERENCIA NVARCHAR(120), DEBITO_LOCAL MONEY, CREDITO_LOCAL MONEY, USUARIO VARCHAR(40));",
    ]
    for r in df_base.itertuples():
        fecha_s = str(r.fecha).replace("-", "")
        desc = str(r.descripcion).replace("'", "''")
        deb = max(float(r.monto), 0.0)
        cre = max(-float(r.monto), 0.0)
        lineas.append(
            f"INSERT INTO dbo.DIARIO VALUES ({int(r.asiento)}, {int(r.linea)}, '{fecha_s}', "
            f"'{r.cuenta}', '{desc}', {deb:.2f}, {cre:.2f}, '{r.usuario}');"
        )
    ruta.write_text("\n".join(lineas), encoding="utf-8")

    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": ruta},
        salida=tmp_path / "sal_softland",
        opciones={"mayor": {"perfil_erp": "auto"}},
    )
    _verificar_resultados_excepciones(corrida, "softland-exactus")
    assert corrida.controles[0]["codificacion"] == "SQL dump"


def test_sage50_peachtree_sin_linea_ni_usuario(df_base, tmp_path):
    ruta = tmp_path / "sage50_gl.csv"
    df_sage = pd.DataFrame({
        "Reference": df_base["asiento"],
        "Date": pd.to_datetime(df_base["fecha"]).dt.strftime("%m/%d/%y"),
        "Account ID": df_base["cuenta"],
        "Description": df_base["descripcion"],
        "Debit Amt": df_base["monto"].clip(lower=0),
        "Credit Amt": (-df_base["monto"]).clip(lower=0),
    })
    df_sage.to_csv(ruta, index=False)

    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": ruta},
        salida=tmp_path / "sal_sage",
        opciones={"mayor": {"perfil_erp": "auto"}},
    )
    _verificar_resultados_excepciones(corrida, "sage50-peachtree")
    trans = " ".join(corrida.controles[0]["transformaciones"])
    assert "linea: generada secuencialmente" in trans
    assert "(sin usuario en origen)" in trans


def test_quickbooks_csv_sin_linea(df_base, tmp_path):
    ruta = tmp_path / "quickbooks_journal.csv"
    df_qb = pd.DataFrame({
        "DOCNUM": df_base["asiento"],
        "DATE": pd.to_datetime(df_base["fecha"]).dt.strftime("%m/%d/%Y"),
        "ACCNT": df_base["cuenta"],
        "MEMO": df_base["descripcion"],
        "AMOUNT": df_base["monto"],
        "CREATED BY": df_base["usuario"],
    })
    df_qb.to_csv(ruta, index=False)

    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": ruta},
        salida=tmp_path / "sal_qb",
        opciones={"mayor": {"perfil_erp": "auto"}},
    )
    _verificar_resultados_excepciones(corrida, "quickbooks")


def test_odoo_parquet(df_base, tmp_path):
    ruta = tmp_path / "odoo_apuntes.parquet"
    df_odoo = pd.DataFrame({
        "move_id/name": df_base["asiento"],
        "date": df_base["fecha"],
        "account_id/code": df_base["cuenta"],
        "name": df_base["descripcion"],
        "debit": df_base["monto"].clip(lower=0),
        "credit": (-df_base["monto"]).clip(lower=0),
        "create_uid": df_base["usuario"],
    })
    df_odoo.to_parquet(ruta, index=False)

    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": ruta},
        salida=tmp_path / "sal_odoo",
        opciones={"mayor": {"perfil_erp": "auto"}},
    )
    _verificar_resultados_excepciones(corrida, "odoo")
    assert corrida.controles[0]["codificacion"] == "Parquet"


def test_dynamics_gp_duckdb(df_base, tmp_path):
    ruta = tmp_path / "dynamics_gp.duckdb"
    df_gp = pd.DataFrame({
        "JRNENTRY": df_base["asiento"],
        "SEQNUMBR": df_base["linea"],
        "TRXDATE": df_base["fecha"],
        "ACTNUMST": df_base["cuenta"],
        "REFRENCE": df_base["descripcion"],
        "DEBITAMT": df_base["monto"].clip(lower=0),
        "CRDTAMNT": (-df_base["monto"]).clip(lower=0),
        "USWHPSTD": df_base["usuario"],
    })
    con = duckdb.connect(str(ruta))
    con.register("_gp", df_gp)
    con.execute("CREATE TABLE GL20000 AS SELECT * FROM _gp")
    con.close()

    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": ruta},
        salida=tmp_path / "sal_gp",
        opciones={"mayor": {"perfil_erp": "auto", "tabla_origen": "GL20000"}},
    )
    _verificar_resultados_excepciones(corrida, "dynamics")
    assert corrida.controles[0]["codificacion"] == "DuckDB"


def test_alegra_interfuerza_jsonl(df_base, tmp_path):
    ruta = tmp_path / "alegra_diario.jsonl"
    df_alegra = pd.DataFrame({
        "Comprobante": df_base["asiento"],
        "Fecha": df_base["fecha"],
        "Código cuenta": df_base["cuenta"],
        "Observaciones": df_base["descripcion"],
        "Débito": df_base["monto"].clip(lower=0),
        "Crédito": (-df_base["monto"]).clip(lower=0),
    })
    df_alegra.to_json(ruta, orient="records", lines=True, force_ascii=False)

    corrida = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": ruta},
        salida=tmp_path / "sal_alegra",
        opciones={"mayor": {"perfil_erp": "auto"}},
    )
    _verificar_resultados_excepciones(corrida, "alegra-interfuerza")
    assert corrida.controles[0]["codificacion"] == "JSON"


def test_utf16_tsv(df_base, tmp_path):
    ruta = tmp_path / "mayor_unicode.tsv"
    df_base.to_csv(ruta, sep="\t", index=False, encoding="utf-16")
    assert detectar_codificacion(ruta) == "utf-16"

    corrida = ejecutar_encargo("excepciones-basicas", {"mayor": ruta}, salida=tmp_path / "sal_utf16")
    _verificar_resultados_excepciones(corrida)
    assert corrida.controles[0]["codificacion"] == "utf-16"


def test_seguridad_y_control_nada_en_silencio(df_base, tmp_path):
    # 1. Indicador Debe/Haber con valor desconocido detiene la importación
    mal_ind = tmp_path / "mal_ind.csv"
    mal_ind.write_text(
        "asiento,linea,fecha,cuenta,descripcion,monto,ind,usuario\n"
        "1,1,2025-01-02,5101,Gasto,100.00,X,ana\n",
        encoding="utf-8",
    )
    with pytest.raises(ErrorImportacion, match="desconocido"):
        ejecutar_encargo(
            "excepciones-basicas",
            {"mayor": mal_ind},
            salida=tmp_path / "sal_mal",
            opciones={"mayor": {"indicador_dc": "ind"}},
        )

    # 2. Consultas SQL peligrosas rechazadas
    for mala in [
        "DROP TABLE mayor",
        "DELETE FROM mayor",
        "UPDATE mayor SET monto = 0",
        "INSERT INTO mayor VALUES (1)",
        "ATTACH DATABASE 'x.db' AS x",
        "SELECT * FROM mayor; DROP TABLE mayor",
    ]:
        with pytest.raises(ValueError):
            validar_consulta_solo_lectura(mala)
    assert validar_consulta_solo_lectura("WITH x AS (SELECT 1 AS a) SELECT * FROM x;") == "WITH x AS (SELECT 1 AS a) SELECT * FROM x"

    # 3. URI SQLite + enmascaramiento de credenciales
    uri_secreta = "mssql+pyodbc://auditor:ClaveSuperSecreta@servidor-erp:1433/Softland"
    enmascarada = enmascarar_uri(uri_secreta)
    assert "ClaveSuperSecreta" not in enmascarada and "***" in enmascarada

    db_ruta = tmp_path / "diario.sqlite"
    con = sqlite3.connect(db_ruta)
    df_base.to_sql("mayor_erp", con, index=False)
    con.close()
    uri_sqlite = f"sqlite:///{db_ruta.as_posix()}"
    df_leido, meta = leer_conexion_sql(uri_sqlite, tabla_origen="mayor_erp")
    assert len(df_leido) == FILAS_BASE and len(meta["sha256"]) == 64

    corrida_uri = ejecutar_encargo(
        "excepciones-basicas",
        {"mayor": uri_sqlite},
        salida=tmp_path / "sal_uri",
        opciones={"mayor": {"tabla_origen": "mayor_erp"}},
    )
    _verificar_resultados_excepciones(corrida_uri)


@pytest.mark.parametrize(
    "columnas,perfil_esperado",
    [
        (["BELNR", "BUZEI", "BUDAT", "HKONT", "SGTXT", "DMBTR", "SHKZG", "USNAM"], "sap-ecc-s4"),
        (["TransId", "Line_ID", "RefDate", "Account", "LineMemo", "Debit", "Credit", "U_NAME"], "sap-b1"),
        (["ASIENTO", "CONSECUTIVO", "FECHA", "CUENTA_CONTABLE", "REFERENCIA", "DEBITO_LOCAL", "CREDITO_LOCAL", "USUARIO"], "softland-exactus"),
        (["Reference", "Date", "Account ID", "Description", "Debit Amt", "Credit Amt"], "sage50-peachtree"),
        (["DOCNUM", "DATE", "ACCNT", "MEMO", "AMOUNT", "CREATED BY"], "quickbooks"),
        (["move_id/name", "date", "account_id/code", "name", "debit", "credit", "create_uid"], "odoo"),
        (["JRNENTRY", "SEQNUMBR", "TRXDATE", "ACTNUMST", "REFRENCE", "DEBITAMT", "CRDTAMNT", "USWHPSTD"], "dynamics"),
        (["Document Number", "Line ID", "Date", "Account", "Memo", "Amount (Debit)", "Amount (Credit)", "Created By"], "netsuite"),
        (["Comprobante", "Fecha", "Código cuenta", "Observaciones", "Débito", "Crédito"], "alegra-interfuerza"),
        (["Nro. Asiento", "Fecha", "Cod. Cuenta", "Concepto", "Debe", "Haber"], "monica-saint"),
        (["Comprobante contable", "Fecha elaboración", "Código cuenta contable", "Descripción movimiento", "Débito", "Crédito"], "siigo-colombia"),
        (["Póliza", "No. Mov", "Fecha Póliza", "Código Cuenta CONTPAQi", "Concepto Movimiento", "Cargos", "Abonos"], "contpaqi-aspel-mx"),
        (["Numero_Asiento", "Linea_Asiento", "Fecha_Asiento", "Cuenta_Local", "Detalle_Movimiento", "Monto_Debito_Local", "Monto_Credito_Local"], "softland-cr-latam"),
    ],
)
def test_autodeteccion_10_perfiles_panama(columnas, perfil_esperado):
    assert len(perfiles_disponibles()) == 13
    perfil, puntaje = detectar_perfil(columnas)
    assert perfil is not None and puntaje > 0
    assert perfil["id"] == perfil_esperado
