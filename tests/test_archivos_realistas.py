"""Ciclo de estrés: variantes realistas de exportaciones de ERP.

Todas parten del mismo mayor sintético, así que el resultado correcto es
conocido. Si una variante falla, el importador tiene un problema.
"""
import duckdb
import pytest

from archivos_realistas import generar_variantes
from motor.ejecutor import cargar_manifiesto, correr_paquete
from motor.importador import ErrorImportacion, importar
from test_paquete_excepciones import PAQUETE

FILAS = 4994


@pytest.fixture(scope="module")
def variantes(tmp_path_factory):
    return generar_variantes(tmp_path_factory.mktemp("variantes"))


@pytest.mark.parametrize(
    "nombre",
    ["latin1_encabezados_es", "fechas_ddmmaaaa", "montos_texto", "titulo_y_totales",
     "debe_haber_excel", "asientos_alfanumericos", "utf8_bom", "coma_decimal", "quickbooks_journal"],
)
def test_variante_da_el_mismo_resultado(variantes, nombre):
    v = variantes[nombre]
    manifiesto = cargar_manifiesto(PAQUETE)
    con = duckdb.connect()
    control = importar(con, v["ruta"], "mayor", columnas_requeridas=manifiesto["archivos"][0]["columnas_requeridas"], **v["opciones"])
    assert control["filas"] == FILAS
    assert control["totales"]["monto"] == 0.0  # el libro diario cuadra
    r = {x.id: x for x in correr_paquete(con, manifiesto)}
    assert r["gaps-asientos"].tabla[["desde", "hasta"]].values.tolist() == [[1500, 1502], [2200, 2200]]
    assert len(r["duplicados-exactos"].tabla) == 4
    assert len(r["mismo-mismo-distinto"].tabla) == 2
    assert [d.isoformat() for d in r["gaps-fechas"].tabla["dia"].dt.date] == ["2025-07-15"]


def test_fila_de_total_se_excluye_y_se_reporta(variantes):
    v = variantes["titulo_y_totales"]
    control = importar(duckdb.connect(), v["ruta"], "mayor", **v["opciones"])
    assert control["filas_excluidas"] == 1


def test_quickbooks_journal_rellena_y_lo_reporta(variantes):
    """Sin relleno hacia abajo, las líneas de detalle se perdían como si fueran totales y los asientos
    quedaban descuadrados. Con relleno, solo se excluyen subtotales y el TOTAL, y queda constancia."""
    v = variantes["quickbooks_journal"]
    sin = dict(v["opciones"], rellenar_hacia_abajo=False)
    control_sin = importar(duckdb.connect(), v["ruta"], "mayor", **sin)
    assert control_sin["filas"] < FILAS  # comportamiento anterior: líneas reales perdidas
    control = importar(duckdb.connect(), v["ruta"], "mayor", **v["opciones"])
    assert control["filas"] == FILAS
    assert control["filas_rellenadas"] > 0
    assert any("copiados de la línea anterior" in t for t in control["transformaciones"])
    assert any("fila(s) de título" in t for t in control["transformaciones"])
