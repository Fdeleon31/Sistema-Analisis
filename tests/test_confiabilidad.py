"""Pruebas de confiabilidad operativa, diagnóstico contable, PDF multipárrafo y formato Excel (Ficha 16)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd
import pytest

from conectores.estado_cuenta_pdf import _parsear_lineas_extracto, _resumen_saldo_extracto, leer_estado_cuenta
from motor.diagnostico import evaluar_confiabilidad_datos
from motor.ejecutor import cargar_encargo
from motor.estadistica import z_estadistico
from motor.importador import ErrorImportacion, importar
from motor.servicio import ejecutar_encargo

RAIZ = Path(__file__).resolve().parents[1]


def test_rechaza_texto_invalido_en_debito_credito(tmp_path):
    csv_malo = tmp_path / "mayor_dc_corrupto.csv"
    pd.DataFrame([
        {
            "asiento": "101", "linea": 1, "fecha": "2025-05-10", "cuenta": "1101",
            "descripcion": "Ingreso", "Debito": "1000.00", "Credito": "0.00", "usuario": "ana",
        },
        {
            "asiento": "101", "linea": 2, "fecha": "2025-05-10", "cuenta": "4101",
            "descripcion": "Contrapartida rota", "Debito": "0.00", "Credito": "N/D", "usuario": "ana",
        },
    ]).to_csv(csv_malo, index=False)

    con = duckdb.connect()
    try:
        with pytest.raises(ErrorImportacion, match="No se pudieron leer algunos montos"):
            importar(
                con,
                csv_malo,
                "mayor",
                columnas_requeridas=["asiento", "linea", "fecha", "cuenta", "descripcion", "monto", "usuario"],
                debito_credito=("Debito", "Credito"),
            )
    finally:
        con.close()


def test_z_estadistico_limites_seguros():
    assert z_estadistico(0.25, 0.0, 50) == 0.0
    assert z_estadistico(0.25, 1.0, 50) == 0.0
    assert z_estadistico(0.25, 0.30, 0) == 0.0


def test_pdf_bancario_multilinea_signo_final_y_cuadre_saldos():
    lineas_ok = [
        "BANCO GENERAL S.A.",
        "Cuenta: 03-45-01-998877-0",
        "Saldo Inicial: 10,000.00",
        "Fecha  Ref  Descripción  Débito  Crédito  Saldo",
        "15-ene-25  ACH-771  PAGO PROVEEDOR CENTRAL S.A.  1,250.00-  0.00  8,750.00",
        "FACTURA 9901 PAGO PARCIAL",
        "ene 20, 2025  DEP-102  DEPÓSITO CLIENTE NORTE  0.00  500.00  9,250.00",
        "Saldo Final: 9,250.00",
        "Generado automáticamente por banca en línea",
    ]
    filas, errores, _ = _parsear_lineas_extracto(lineas_ok, "extracto_prueba.pdf")
    assert errores == []
    assert len(filas) == 2
    assert filas[0]["fecha"] == date(2025, 1, 15)
    assert filas[0]["monto"] == -1250.0
    assert "FACTURA 9901 PAGO PARCIAL" in filas[0]["descripcion"]
    assert filas[1]["fecha"] == date(2025, 1, 20)
    assert filas[1]["monto"] == 500.0
    assert "Generado automáticamente" not in filas[1]["descripcion"]

    res_ok = _resumen_saldo_extracto(lineas_ok, filas, "extracto_prueba.pdf")
    assert res_ok["cuadra"] is True
    assert res_ok["diferencia"] == 0.0

    lineas_mal = list(lineas_ok)
    lineas_mal[7] = "Saldo Final: 9,500.00"
    res_mal = _resumen_saldo_extracto(lineas_mal, filas, "extracto_roto.pdf")
    assert res_mal["cuadra"] is False
    assert res_mal["diferencia"] == -250.0


def test_diagnostico_detecta_descuadre_claves_y_limpio(tmp_path):
    con = duckdb.connect()
    try:
        con.execute("""
            CREATE TABLE mayor AS
            SELECT '1' AS asiento, 1 AS linea, DATE '2025-03-10' AS fecha, '1101' AS cuenta, 'Cobro' AS descripcion, 500.00::DECIMAL(18,2) AS monto, 'eva' AS usuario
            UNION ALL
            SELECT '1' AS asiento, 2 AS linea, DATE '2025-03-10' AS fecha, '4101' AS cuenta, 'Venta' AS descripcion, -500.00::DECIMAL(18,2) AS monto, 'eva' AS usuario
        """)
        enc = {"cliente": "Empresa Sana, S.A.", "periodo_inicio": "2025-01-01", "fecha_cierre": "2025-12-31", "materialidad": 50000}
        diag_ok = evaluar_confiabilidad_datos(con, [{"tabla": "mayor", "transformaciones": []}], enc)
        assert diag_ok["estado_general"] == "OK"

        # Introducir descuadre global + clave duplicada (1, 2) + fecha fuera de período
        con.execute("""
            INSERT INTO mayor VALUES ('1', 2, DATE '2023-01-05', '5101', 'Registro duplicado', 100.00, 'eva')
        """)
        diag_alerta = evaluar_confiabilidad_datos(con, [{"tabla": "mayor", "transformaciones": []}], enc)
        assert diag_alerta["estado_general"] == "ALERTA"
        por_cod = {h["codigo"]: h for h in diag_alerta["hallazgos"]}
        assert por_cod["cuadre_diario"]["estado"] == "ALERTA"
        assert por_cod["claves_mayor"]["estado"] == "ALERTA"
        assert por_cod["fechas_mayor"]["estado"] == "ADVERTENCIA"
    finally:
        con.close()


def test_cedula_excel_formato_ejecutivo_y_hoja_diagnostico(tmp_path):
    csv_may = tmp_path / "mayor.csv"
    pd.DataFrame([
        {"asiento": "10", "linea": 1, "fecha": "2025-06-01", "cuenta": "1101", "descripcion": "Ingreso", "monto": 10000.0, "usuario": "ana"},
        {"asiento": "10", "linea": 2, "fecha": "2025-06-01", "cuenta": "4101", "descripcion": "Venta", "monto": -10000.0, "usuario": "ana"},
    ]).to_csv(csv_may, index=False)

    encargo = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")
    corrida = ejecutar_encargo("asientos-nia240", {"mayor": csv_may}, encargo, tmp_path / "sal")
    assert corrida.diagnostico["estado_general"] == "OK"

    wb = openpyxl.load_workbook(corrida.cedula)
    assert "Diagnostico" in wb.sheetnames
    ws_res = wb["Resumen"]
    assert ws_res.freeze_panes == "A2"
    assert ws_res.auto_filter.ref is not None
    assert ws_res["A1"].fill.start_color.rgb.endswith("0F2744")
    assert ws_res["A1"].font.bold is True

    ws_diag = wb["Diagnostico"]
    assert ws_diag["A2"].value == "OK"
    assert ws_diag["A2"].fill.start_color.rgb.endswith("DCFCE7")

    ws_punt = wb["asientos-puntaje"]
    encabezados = [ws_punt.cell(row=1, column=i).value for i in range(1, ws_punt.max_column + 1)]
    col_monto = encabezados.index("total_debito") + 1
    assert "#,##0.00" in ws_punt.cell(row=2, column=col_monto).number_format


def test_escritorio_muestra_diagnostico_y_cierra_limpio(tmp_path):
    PySide6 = pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _ = QApplication.instance() or QApplication([])

    from app.escritorio import VentanaCuadra

    v = VentanaCuadra()
    v.cargar_ejemplo_sintetico()
    corrida = v.ejecutar_sincrono("asientos-nia240")
    vista = v.vistas_paquetes["asientos-nia240"]
    nombres_tabs = [vista.tabs_resultados.tabText(i) for i in range(vista.tabs_resultados.count())]
    assert any(n.startswith("Diagnóstico") for n in nombres_tabs)
    assert "DATOS:" in v.lbl_sb_der.text()
    assert corrida.diagnostico
    assert v.close()
