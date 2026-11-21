"""Fase 2 · Ficha 10: facturas electrónicas de la DGI contra el mayor."""
import json
import zipfile
from pathlib import Path

import pytest

from motor.ejecutor import cargar_encargo
from motor.factura_electronica import leer_facturas, leer_xml
from motor.servicio import ejecutar_encargo
from motor.sintetico import generar_facturas_fe

RAIZ = Path(__file__).resolve().parents[1]
E = json.loads((RAIZ / "paquetes" / "ventas-fe" / "casos" / "esperados.json").read_text(encoding="utf-8"))
ENCARGO = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")


@pytest.fixture(scope="module")
def corrida(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("fe")
    zip_fe, mayor = generar_facturas_fe(carpeta)
    c = ejecutar_encargo("ventas-fe", {"facturas": zip_fe, "mayor": mayor}, ENCARGO, carpeta / "salida")
    return c, {r.id: r for r in c.resultados}, zip_fe, carpeta


def test_lee_zip_y_reporta_ilegibles(corrida):
    c, _, _, _ = corrida
    control = c.controles[0]
    assert (control["archivos_xml"], control["filas"]) == (E["archivos_xml"], E["documentos_leidos"])
    assert [d.split(":")[0] for d in control["detalle_excluidas"]] == E["ilegibles"]


def test_lee_carpeta_igual_que_zip(corrida):
    _, _, zip_fe, carpeta = corrida
    assert len(leer_facturas(carpeta / "facturas_xml").facturas) == len(leer_facturas(zip_fe).facturas)


def test_pruebas_de_documentos_identicas(corrida):
    _, r, _, _ = corrida
    assert r["fe-consistencia"].tabla["numero"].tolist() == E["consistencia"]["numeros"]
    assert float(r["fe-consistencia"].tabla["diferencia_total"].iloc[0]) == E["consistencia"]["diferencia_total"]
    assert r["fe-cufe-duplicado"].tabla["numero"].tolist() == E["cufe_duplicado"]["numeros"]
    assert int(r["fe-cufe-duplicado"].tabla["veces"].iloc[0]) == E["cufe_duplicado"]["veces"]
    assert r["fe-gaps"].tabla.values.tolist() == E["gaps"]
    assert r["fe-fuera-periodo"].tabla["numero"].tolist() == E["fuera_periodo"]["numeros"]
    assert str(r["fe-fuera-periodo"].tabla["fecha_emision"].iloc[0])[:10] == E["fuera_periodo"]["fecha"]
    assert r["fe-ambiente-pruebas"].tabla["numero"].tolist() == E["ambiente_pruebas"]["numeros"]


def test_conciliacion_mensual_identica(corrida):
    _, r, zip_fe, _ = corrida
    t = r["fe-vs-mayor"].tabla
    con_dif = t[t["diferencia"].abs() > 0.005]
    assert con_dif["mes"].tolist() == E["conciliacion"]["meses_con_diferencia"]
    assert float(con_dif.loc[con_dif["mes"] == "2025-06", "diferencia"].item()) == E["conciliacion"]["diferencia_junio"]
    neto_300 = leer_facturas(zip_fe).facturas.query("numero == 300")["total_neto"].item()
    assert float(con_dif.loc[con_dif["mes"] == "2026-01", "diferencia"].item()) == pytest.approx(-neto_300)
    assert len(t) == E["conciliacion"]["meses"] and r["fe-vs-mayor"].excepciones == 2


def test_tolera_espacios_de_nombres_distintos():
    xml = b"""<?xml version="1.0"?><x:rFE xmlns:x="urn:otro"><x:dId>FE123</x:dId><x:gDGen><x:iAmb>1</x:iAmb>
    <x:dFechaEm>2025-02-01T09:00:00-05:00</x:dFechaEm><x:iDoc>06</x:iDoc><x:dPtoFacDF>002</x:dPtoFacDF><x:dNroDF>0000000009</x:dNroDF>
    </x:gDGen><x:gTot><x:dTotNeto>100.00</x:dTotNeto><x:dTotITBMS>7.00</x:dTotITBMS><x:dVTot>107.00</x:dVTot></x:gTot></x:rFE>"""
    f = leer_xml(xml, "a.xml")
    assert (f["cufe"], f["tipo_documento"], f["numero"], f["total"]) == ("FE123", "06", 9, 107.0)
    assert f["tipo_documento_nombre"] == "Nota de crédito genérica"


def test_sin_mayor_omite_la_conciliacion(tmp_path):
    zip_fe, _ = generar_facturas_fe(tmp_path)
    c = ejecutar_encargo("ventas-fe", {"facturas": zip_fe}, ENCARGO, tmp_path / "s")
    assert {r.id: r for r in c.resultados}["fe-vs-mayor"].omitida
