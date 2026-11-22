"""Pruebas de identidad ejecutiva Folio Auditor, constancia en tiempo real y encabezados Excel (Ficha 17)."""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.comun import (  # noqa: E402
    HERRAMIENTAS,
    LEMA_MARCA,
    NOMBRE_MARCA,
    calcular_periodo_inicio,
    constancia_tiempo_real,
    formatear_periodo_auditado,
    formula_contextual,
)
from motor.bitacora import Bitacora  # noqa: E402
from motor.ejecutor import ResultadoPrueba  # noqa: E402
from motor.exportador import exportar_excel  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Utilidades compartidas (app.comun)
# ---------------------------------------------------------------------------


def test_identidad_marca_comun():
    assert NOMBRE_MARCA == "FOLIO AUDITOR"
    assert "cuadra" not in NOMBRE_MARCA.lower()
    assert "cuadra" not in LEMA_MARCA.lower()


@pytest.mark.parametrize(
    "fecha_cierre,esperado",
    [
        (date(2025, 12, 31), date(2025, 1, 1)),
        ("2025-12-31", date(2025, 1, 1)),
        (date(2025, 6, 30), date(2024, 7, 1)),
        (datetime(2025, 3, 31, 18, 30, 0), date(2024, 4, 1)),
        (date(2026, 1, 31), date(2025, 2, 1)),
        (None, date(2025, 1, 1)),
        ("", date(2025, 1, 1)),
        ("fecha-invalida", date(2025, 1, 1)),
        (date(1, 5, 15), date(2025, 1, 1)),
    ],
)
def test_calcular_periodo_inicio(fecha_cierre, esperado):
    assert calcular_periodo_inicio(fecha_cierre) == esperado


@pytest.mark.parametrize(
    "inicio,cierre,esperado",
    [
        (date(2025, 1, 1), date(2025, 12, 31), "2025-01-01 al 2025-12-31"),
        ("2024-07-01", "2025-06-30", "2024-07-01 al 2025-06-30"),
        (None, date(2025, 6, 30), "2024-07-01 al 2025-06-30"),
        ("invalido", "2025-09-30", "2024-10-01 al 2025-09-30"),
        (None, None, "2025-01-01 al 2025-12-31"),
    ],
)
def test_formatear_periodo_auditado(inicio, cierre, esperado):
    assert formatear_periodo_auditado(inicio, cierre) == esperado


def test_constancia_tiempo_real_local_y_utc():
    antes = datetime.now(timezone.utc).replace(microsecond=0)
    local_txt, utc_txt = constancia_tiempo_real()
    despues = datetime.now(timezone.utc).replace(microsecond=0)

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2} \([^)]+\)", local_txt)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC", utc_txt)

    marca_utc = datetime.strptime(utc_txt, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    assert abs((marca_utc - antes).total_seconds()) <= 5
    assert abs((despues - marca_utc).total_seconds()) <= 5


def test_formula_contextual_refleja_cliente_y_periodo():
    cuadro, formula = formula_contextual(
        "asientos-nia240",
        "Distribuidora Istmo, S.A.",
        date(2025, 12, 31),
        150000.0,
        "INTEGRA",
        periodo_inicio=date(2025, 2, 1),
    )
    assert cuadro == "NIA-240"
    assert formula.startswith("=AUDITAR.DIARIO(")
    assert 'Cliente="Distribuidora Istmo, S.A."' in formula
    assert 'Periodo="2025-02-01 al 2025-12-31"' in formula
    assert 'Cierre="2025-12-31"' in formula
    assert "Materialidad=150,000.00" in formula

    cuadro_enc, formula_enc = formula_contextual(
        "encargos",
        "Distribuidora Istmo, S.A.",
        "2025-06-30",
        95000.0,
        "SIN_EJECUCION",
    )
    assert cuadro_enc == "PORTAFOLIO"
    assert 'Periodo="2024-07-01 al 2025-06-30"' in formula_enc

    for hid, _, _, _ in HERRAMIENTAS:
        nb, fx = formula_contextual(hid, "Demo, S.A.", date(2025, 12, 31), 100000.0, "INTEGRA")
        assert nb
        assert fx.startswith("=")


# ---------------------------------------------------------------------------
# 2. Cédula Excel y encabezados/pies de impresión (motor.exportador + openpyxl)
# ---------------------------------------------------------------------------


def _crear_insumos_exportacion(tmp_path: Path):
    bitacora = Bitacora(tmp_path / "bitacora.jsonl", usuario="auditor.nia")
    bitacora.registrar("inicio_prueba", tabla="mayor")
    resultado = ResultadoPrueba(
        id="asientos-criterios",
        nombre="Criterios de riesgo NIA 240",
        ficha="04",
        nia=["NIA 240"],
        tabla=pd.DataFrame([{"asiento": "1001", "monto": 12500.0, "detalle": "Registro de prueba"}]),
        resumen={"asientos_analizados": 1, "por_criterio": {}},
    )
    importaciones = [
        {
            "archivo": "mayor_demo.csv",
            "tabla": "mayor",
            "filas": 1,
            "filas_excluidas": 0,
            "monto_filas_excluidas": 0.0,
            "codificacion": "utf-8",
            "formato_fecha": "%Y-%m-%d",
            "transformaciones": [],
            "sha256": "a" * 64,
        }
    ]
    return [resultado], importaciones, bitacora


def test_exportar_excel_incluye_constancia_en_encargo_y_encabezado_impresion(tmp_path):
    resultados, importaciones, bitacora = _crear_insumos_exportacion(tmp_path)
    ruta_xlsx = tmp_path / "cedula.xlsx"
    encargo = {
        "cliente": "Distribuidora Canal, S.A.",
        "periodo_inicio": "2025-01-01",
        "fecha_cierre": "2025-12-31",
        "marco": "NIIF",
        "materialidad": 150000,
    }

    exportar_excel(resultados, importaciones, bitacora, ruta_xlsx, encargo=encargo)
    wb = openpyxl.load_workbook(ruta_xlsx)
    try:
        assert "Encargo" in wb.sheetnames
        ws_enc = wb["Encargo"]
        pares = {
            str(fila[0]): str(fila[1])
            for fila in ws_enc.iter_rows(min_row=2, values_only=True)
            if fila[0] is not None
        }

        for clave in ("aplicacion", "periodo_auditado", "fecha_hora_emision_local", "fecha_hora_emision_utc"):
            assert clave in pares

        assert "Folio Auditor" in pares["aplicacion"]
        assert pares["periodo_auditado"] == "2025-01-01 al 2025-12-31"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", pares["fecha_hora_emision_local"])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC", pares["fecha_hora_emision_utc"])

        for ws in wb.worksheets:
            izq = ws.oddHeader.left.text or ""
            assert "Folio Auditor" in izq
            assert "Distribuidora Canal, S.A." in izq
            assert "2025-01-01 al 2025-12-31" in izq
            assert ws.oddHeader.right.text == "&D &T"
            assert "Folio Auditor" in (ws.oddFooter.left.text or "")
            assert ws.oddFooter.right.text == "Página &P de &N"
    finally:
        wb.close()


def test_exportar_excel_calcula_periodo_si_falta_inicio(tmp_path):
    resultados, importaciones, bitacora = _crear_insumos_exportacion(tmp_path)
    ruta_xlsx = tmp_path / "cedula_quebrada.xlsx"
    encargo = {
        "cliente": "Grupo Pacífico, S.A.",
        "fecha_cierre": "2025-06-30",
    }

    exportar_excel(resultados, importaciones, bitacora, ruta_xlsx, encargo=encargo)
    wb = openpyxl.load_workbook(ruta_xlsx)
    try:
        ws_enc = wb["Encargo"]
        pares = {
            str(fila[0]): str(fila[1])
            for fila in ws_enc.iter_rows(min_row=2, values_only=True)
            if fila[0] is not None
        }
        assert pares["periodo_auditado"] == "2024-07-01 al 2025-06-30"
        header_res = wb["Resumen"].oddHeader.left.text or ""
        assert "Grupo Pacífico, S.A." in header_res
        assert "2024-07-01 al 2025-06-30" in header_res
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# 3. Escritorio PySide6 (VentanaCuadra)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_escritorio_identidad_constancia_tiempo_real_y_timer(qapp):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QLabel, QWidget

    from app.escritorio import VentanaCuadra

    v = VentanaCuadra()
    try:
        # Sin marca 'cuadra' en títulos visibles e identidad Folio Auditor + íconos 3D intactos
        assert "cuadra" not in v.windowTitle().lower()
        assert "cuadra" not in v.lbl_workbook_title.text().lower()
        if hasattr(v, "lbl_workbook_sub"):
            assert "cuadra" not in v.lbl_workbook_sub.text().lower()
        assert "cuadra" not in v.lbl_constancia_periodo.text().lower()
        assert "cuadra" not in v.lbl_constancia_reloj.text().lower()

        appbar = v.findChild(QWidget, "AppBar")
        textos_titulo = [v.windowTitle(), *(lbl.text() for lbl in v.findChildren(QLabel))]
        if appbar is not None:
            for lbl in appbar.findChildren(QLabel):
                assert "cuadra" not in lbl.text().lower()
        for btn_t, _ in getattr(v, "ribbon_tabs", []):
            assert "cuadra" not in btn_t.text().lower()
        for tb in v.botones_cinta.values():
            assert "cuadra" not in tb.text().lower()
            assert not tb.icon().isNull()

        assert any("folio auditor" in txt.lower() for txt in textos_titulo)
        assert not v.windowIcon().isNull()
        assert not v.btn_ribbon_correr.icon().isNull()
        assert not v.btn_ribbon_excel.icon().isNull()

        # Constancia inicial en barra superior: cliente, período y reloj en tiempo real
        cliente_inicial = str(v.encargo_datos["cliente"])
        periodo_inicial = formatear_periodo_auditado(
            v.encargo_datos.get("periodo_inicio"),
            v.encargo_datos["fecha_cierre"],
        )
        ini_iso, fin_iso = periodo_inicial.split(" al ")

        assert cliente_inicial in v.lbl_workbook_title.text()
        assert ini_iso in v.lbl_constancia_periodo.text()
        assert fin_iso in v.lbl_constancia_periodo.text()

        reloj_txt = v.lbl_constancia_reloj.text()
        assert re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", reloj_txt)
        assert "UTC" in reloj_txt

        # Timer de reloj activo durante la sesión
        assert v._timer_reloj.isActive()

        # Actualización en vivo inmediata al editar cliente, fecha de cierre y fecha de inicio
        vista = v.vistas_paquetes["asientos-nia240"]

        vista.edt_cliente.setText("Naviera del Canal, S.A.")
        qapp.processEvents()
        assert "Naviera del Canal, S.A." in v.lbl_workbook_title.text()
        assert "Naviera del Canal, S.A." in v.lbl_formula.text()

        vista.de_cierre.setDate(QDate(2026, 3, 31))
        qapp.processEvents()
        assert "2026-03-31" in v.lbl_constancia_periodo.text()

        vista.de_inicio.setDate(QDate(2025, 4, 1))
        qapp.processEvents()
        assert "2025-04-01" in v.lbl_constancia_periodo.text()
        assert "2026-03-31" in v.lbl_constancia_periodo.text()
    finally:
        v.close()
        qapp.processEvents()

    assert not v._timer_reloj.isActive()


# ---------------------------------------------------------------------------
# 4. Interfaz Web (Streamlit AppTest)
# ---------------------------------------------------------------------------


def test_web_arranca_sin_errores():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(RAIZ / "app" / "inicio.py"), default_timeout=60).run()
    assert not app.exception
