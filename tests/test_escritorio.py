"""Pruebas automatizadas de la aplicación nativa de escritorio (PySide6, 100 % sin internet)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.escritorio import DialogoConfigurarArchivo, DialogoPesosRiesgo, VentanaCuadra  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    if QApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    return app


def test_ventana_inicializa_cinta_sin_marca_cuadra_y_con_iconos_3d(qapp):
    v = VentanaCuadra()
    assert "cuadra" not in v.windowTitle().lower()
    assert "cuadra" not in v.lbl_workbook_title.text().lower()
    assert "0.6.0" not in v.lbl_workbook_title.text()
    assert "0.6.0" not in v.lbl_workbook_sub.text()

    esperadas = {
        "asientos-nia240",
        "excepciones-basicas",
        "ventas-fe",
        "bancos-conciliacion",
        "muestreo-mus",
        "conectores",
        "copiloto",
        "bitacora",
        "encargos",
    }
    assert set(v.botones_cinta.keys()) == esperadas
    for tb in v.botones_cinta.values():
        assert not tb.icon().isNull()
    assert not v.btn_ribbon_correr.icon().isNull()
    assert not v.btn_ribbon_excel.icon().isNull()
    assert not v.btn_ribbon_correr.isEnabled()
    v.close()


def test_cargar_ejemplo_y_correr_nia240_en_escritorio(qapp):
    v = VentanaCuadra()
    v.cargar_ejemplo_sintetico()
    vista = v.vistas_paquetes["asientos-nia240"]
    assert vista.esta_listo()
    assert vista.btn_correr.isEnabled()
    assert v.btn_ribbon_correr.isEnabled()

    corrida = v.ejecutar_sincrono("asientos-nia240")
    assert corrida.bitacora.verificar()
    assert corrida.cedula.exists()
    r_puntaje = next(r for r in corrida.resultados if r.id == "asientos-puntaje")
    assert r_puntaje.excepciones == 11
    assert vista.kpis[0].lbl_valor.text() != "—"
    assert "SHA-256: VERIFICADO" in v.lbl_sb_der.text()
    assert v.btn_ribbon_excel.isEnabled()
    assert v.btn_top_excel.isEnabled()

    # Filtro en vivo de puntaje de riesgo (Ficha 11)
    assert vista._modelo_puntaje is not None
    total_filas = vista._modelo_puntaje.rowCount()
    assert total_filas == 11
    vista.cmb_nivel_puntaje.setCurrentText("alto")
    assert 0 < vista._modelo_puntaje.rowCount() <= total_filas

    v.close()


def test_navegar_todas_las_vistas_y_dialogos(qapp):
    v = VentanaCuadra()
    v.cargar_ejemplo_sintetico()

    for hid in ("excepciones-basicas", "ventas-fe", "bancos-conciliacion", "muestreo-mus", "conectores", "copiloto", "bitacora", "encargos", "asientos-nia240"):
        v.seleccionar_herramienta(hid)
        assert v.herramienta_actual == hid
        assert v.lbl_namebox.text() != ""
        assert v.lbl_formula.text().startswith("=")

    # Bancos PDF con ejemplo sintético desde escritorio
    v.seleccionar_herramienta("bancos-conciliacion")
    v.cargar_ejemplo_sintetico()
    corrida_b = v.ejecutar_sincrono("bancos-conciliacion")
    assert corrida_b.bitacora.verificar()
    assert {r.id: r.excepciones for r in corrida_b.resultados}["bancos-no-en-extracto"] == 2

    # Fase 3: Revisar prueba y firmar como Preparador desde Encargos y Firmas
    v.seleccionar_herramienta("encargos")
    assert v.vista_portafolio.mod_encargos.rowCount() >= 1
    assert v.vista_portafolio.mod_rev.rowCount() >= 5
    v.vista_portafolio.cmb_estado_rev.setCurrentText("Aclarado con evidencia")
    v.vista_portafolio.txt_conclusion.setPlainText("Conciliado en revisión de prueba escritorio.")
    v.vista_portafolio._guardar_conclusion_actual()
    v.vista_portafolio._firmar_rol_activo()
    assert corrida_b.bitacora.verificar()
    assert "Revisiones y Firmas" in __import__("pandas").ExcelFile(corrida_b.cedula).sheet_names

    # Copiloto SQL: proponer + aprobar + ejecutar en motor DuckDB + bitácora SHA-256 íntegra
    v.seleccionar_herramienta("copiloto")
    v.vista_copiloto.edt_pregunta.setText("Asientos descuadrados")
    v.vista_copiloto.proponer_sql()
    assert "SELECT" in v.vista_copiloto.txt_sql.toPlainText()
    v.vista_copiloto.aprobar_y_ejecutar()
    assert v.vista_copiloto.mod_res.rowCount() >= 1
    assert "PAPEL DE TRABAJO" in v.vista_copiloto.txt_borrador.toPlainText()
    assert corrida_b.bitacora.verificar()

    # Conectores muestra los 13 perfiles ERP (10 Panamá + 3 Latam regional)
    v.seleccionar_herramienta("conectores")
    assert v.vista_conectores.tv_cat.model().rowCount() == 13
    assert "SELECT" in v.vista_conectores.txt_sql.toPlainText().upper()

    v.seleccionar_herramienta("asientos-nia240")

    # Diálogo de pesos y diálogo de configuración/vista previa
    vista = v.vistas_paquetes["asientos-nia240"]
    tarjeta_mayor = vista.tarjetas_fuentes["mayor"]
    dlg_cfg = DialogoConfigurarArchivo(
        tarjeta_mayor.origen, tarjeta_mayor.definicion, vista.perfiles, tarjeta_mayor.opciones, v
    )
    assert dlg_cfg.modelo_previa.rowCount() > 0
    opc = dlg_cfg.opciones_confirmadas()
    assert opc["_faltantes"] == []
    dlg_cfg.close()

    dlg_pesos = DialogoPesosRiesgo({"fin_de_semana": 15}, {}, 25, 15, v)
    pesos, alto, medio = dlg_pesos.resultado()
    assert pesos["fin_de_semana"] == 15 and alto == 25 and medio == 15
    dlg_pesos.close()

    v.close()
