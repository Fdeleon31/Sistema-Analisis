"""Sugerencias de mapeo, servicio único e interfaz (prueba de humo)."""
from pathlib import Path

import pytest

from archivos_realistas import ENCABEZADOS_ES
from motor.servicio import ejecutar_encargo, paquetes_disponibles
from motor.sintetico import generar_diario_asientos
from motor.sugerencias import sugerir_debito_credito, sugerir_mapeo

REQUERIDAS = ["asiento", "linea", "fecha", "cuenta", "descripcion", "monto", "usuario"]


def test_sugiere_encabezados_en_espanol():
    m = sugerir_mapeo(ENCABEZADOS_ES, REQUERIDAS)
    assert m == {"asiento": "No. Asiento", "linea": "Línea", "fecha": "Fecha", "cuenta": "Cuenta",
                 "descripcion": "Descripción", "monto": "Importe", "usuario": "Usuario"}


@pytest.mark.parametrize("columnas,esperado", [
    (["Comprobante", "Renglón", "Fecha contable", "Código cuenta", "Concepto", "Valor", "Creado por"],
     {"asiento": "Comprobante", "linea": "Renglón", "fecha": "Fecha contable", "cuenta": "Código cuenta",
      "descripcion": "Concepto", "monto": "Valor", "usuario": "Creado por"}),
    (["asiento", "linea", "fecha", "cuenta", "descripcion", "monto", "usuario"], {r: r for r in REQUERIDAS}),
])
def test_sugiere_variantes_comunes(columnas, esperado):
    assert sugerir_mapeo(columnas, REQUERIDAS) == esperado


def test_no_inventa_columnas_que_no_estan():
    m = sugerir_mapeo(["Fecha", "Cuenta", "Debe", "Haber"], REQUERIDAS)
    assert m["usuario"] is None and m["asiento"] is None
    assert sugerir_debito_credito(["Fecha", "Débito", "Crédito"]) == ("Débito", "Crédito")


def test_servicio_corre_el_paquete_y_deja_cedula(tmp_path):
    assert {"excepciones-basicas", "asientos-nia240"} <= set(paquetes_disponibles())
    mayor, balanza = generar_diario_asientos(tmp_path / "d", semilla=7)
    encargo = {"cliente": "Demo", "fecha_cierre": "2025-12-31", "materialidad_ejecucion": 112500,
               "umbral_trivial": 7500, "umbral_aprobacion": 10000}
    corrida = ejecutar_encargo("asientos-nia240", {"mayor": mayor, "balanza": balanza}, encargo, tmp_path / "s")
    r = {x.id: x for x in corrida.resultados}
    assert r["asientos-criterios"].excepciones == 11 and corrida.cedula.exists() and corrida.bitacora.verificar()


def test_interfaz_abre_sin_errores():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "inicio.py"), default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value == "Cuadra"
    boton = [b for b in app.button if b.label == "Correr pruebas"][0]
    assert boton.disabled  # sin archivos no se puede correr


def test_detecta_fila_de_encabezado_bajo_titulos():
    from motor.sugerencias import detectar_fila_encabezado
    filas = [["CLIENTE DEMO, S.A. - Balanza 2025"], [""], ["Cuenta", "Descripción", "Saldo inicial", "Saldo final"], ["1101", "Bancos", "1,000.00", "2,000.00"]]
    assert detectar_fila_encabezado(filas, ["cuenta", "saldo_inicial", "saldo_final"]) == 2
    assert detectar_fila_encabezado([["fecha", "cuenta", "debe", "haber"]], ["fecha", "cuenta", "monto"]) == 0
