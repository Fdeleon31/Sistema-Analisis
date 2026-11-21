"""Puerta de la Fase 1: tres datasets con resultados idénticos a los esperados.

Dataset 1: diario y balanza estándar. Dataset 2: el mismo diseño exportado como un ERP
poco amable. Dataset 3: muestreo MUS calculado a mano.
"""
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from motor.ejecutor import CRITERIOS_ASIENTO, cargar_encargo, cargar_manifiesto, correr_paquete
from motor.importador import importar
from motor.muestreo import ErrorMuestreo, muestra_aleatoria, seleccionar_mus, tamano_mus
from motor.sintetico import generar_diario_asientos

RAIZ = Path(__file__).resolve().parents[1]
PAQUETE = RAIZ / "paquetes" / "asientos-nia240"
ESPERADOS = json.loads((PAQUETE / "casos" / "esperados.json").read_text(encoding="utf-8"))
ENCARGO = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")
MAPEO_ERP = {"No. Asiento": "asiento", "Línea": "linea", "Fecha": "fecha", "Cuenta": "cuenta",
             "Descripción": "descripcion", "Usuario": "usuario"}


def _correr(mayor, balanza, opciones_mayor=None, opciones_balanza=None):
    manifiesto = cargar_manifiesto(PAQUETE)
    defs = {a["tabla"]: a for a in manifiesto["archivos"]}
    con = duckdb.connect()
    controles = []
    for tabla, ruta, opciones in (("mayor", mayor, opciones_mayor or {}), ("balanza", balanza, opciones_balanza or {})):
        d = defs[tabla]
        controles.append(importar(con, ruta, tabla, columnas_requeridas=d["columnas_requeridas"],
                                  columnas_monto=d["columnas_monto"], columnas_fecha=d["columnas_fecha"],
                                  claves=d["claves"], **opciones))
    return {r.id: r for r in correr_paquete(con, manifiesto, encargo=ENCARGO)}, controles


def _criterios(tabla: pd.DataFrame, id_texto) -> dict[str, list[str]]:
    return {id_texto(f["asiento"]): sorted(c for c in CRITERIOS_ASIENTO if f[c]) for _, f in tabla.iterrows()}


@pytest.fixture(scope="module")
def dataset_1(tmp_path_factory):
    mayor, balanza = generar_diario_asientos(tmp_path_factory.mktemp("d1"), semilla=7)
    return _correr(mayor, balanza)


@pytest.fixture(scope="module")
def dataset_2(tmp_path_factory):
    mayor, balanza = generar_diario_asientos(tmp_path_factory.mktemp("d2"), semilla=11, formato="dificil")
    return _correr(
        mayor, balanza,
        opciones_mayor={"hoja": "Diario", "mapeo": MAPEO_ERP, "debito_credito": ("Debe", "Haber"), "formato_fecha": "%d/%m/%Y"},
        opciones_balanza={"saltar_filas": 1},
    )


ESPERADO_1 = ESPERADOS["dataset_1_estandar"]
CRITERIOS_ESPERADOS = {k: sorted(v) for k, v in ESPERADO_1["criterios_por_asiento"].items()}


# Dataset 1 · estándar

def test_d1_criterios_por_asiento_identicos(dataset_1):
    r, _ = dataset_1
    assert r["asientos-criterios"].resumen["asientos_analizados"] == ESPERADO_1["asientos_analizados"]
    assert _criterios(r["asientos-criterios"].tabla, str) == CRITERIOS_ESPERADOS


def test_d1_seleccion_identica(dataset_1):
    r, _ = dataset_1
    assert [str(a) for a in r["asientos-seleccion"].tabla["asiento"]] == ESPERADO_1["seleccion"]


def test_d1_integridad_balanza_identica(dataset_1):
    r, _ = dataset_1
    t = r["integridad-balanza"].tabla
    obtenido = [[f["cuenta"], None if f["cuenta"] == "6999" else round(float(f["diferencia"]), 2), f["observacion"]] for _, f in t.iterrows()]
    assert obtenido == ESPERADO_1["integridad_balanza"]


def test_d1_muestra_impredecible_sin_criterios_y_repetible(dataset_1, tmp_path):
    r, _ = dataset_1
    muestra = r["asientos-impredecible"].tabla
    assert len(muestra) == ESPERADO_1["tamano_muestra_impredecible"]
    assert (muestra["criterios"] == 0).all()
    mayor, balanza = generar_diario_asientos(tmp_path, semilla=7)
    otra, _ = _correr(mayor, balanza)
    assert muestra["asiento"].tolist() == otra["asientos-impredecible"].tabla["asiento"].tolist()


def test_d1_estratos_cuadran_con_el_mayor(dataset_1):
    r, _ = dataset_1
    assert int(r["estratificacion"].tabla["lineas"].sum()) == ESPERADO_1["lineas"]
    assert float(r["estratificacion"].tabla["porcentaje_valor"].sum()) == pytest.approx(100.0, abs=0.05)


def test_d1_todas_las_cuentas_tienen_rubro(dataset_1):
    r, _ = dataset_1
    t = r["sumarizacion-rubros"].tabla
    assert "Sin rubro" not in t["rubro"].tolist()
    assert int(t["lineas"].sum()) == ESPERADO_1["lineas"]


# Dataset 2 · exportación de ERP

def test_d2_lee_el_formato_erp_completo(dataset_2):
    _, controles = dataset_2
    mayor, balanza = controles
    assert mayor["filas"] == ESPERADO_1["lineas"]
    assert balanza["filas"] == 10 and balanza["filas_excluidas"] == 1  # fila de total
    assert balanza["codificacion"] == "cp1252"


def test_d2_criterios_y_seleccion_identicos(dataset_2):
    r, _ = dataset_2
    e = ESPERADOS["dataset_2_erp"]
    a_erp = lambda a: f"{e['prefijo']}{int(a):0{e['ancho']}d}"  # noqa: E731
    esperado = {a_erp(k): v for k, v in CRITERIOS_ESPERADOS.items()}
    assert _criterios(r["asientos-criterios"].tabla, str) == esperado
    assert r["asientos-seleccion"].tabla["asiento"].tolist() == [a_erp(a) for a in ESPERADO_1["seleccion"]]


def test_d2_integridad_balanza_identica(dataset_2):
    r, _ = dataset_2
    t = r["integridad-balanza"].tabla
    assert t["cuenta"].tolist() == ["2999", "5204", "6999"]
    assert round(float(t.loc[t["cuenta"] == "5204", "diferencia"].item()), 2) == -1234.56


# Dataset 3 · muestreo MUS calculado a mano

E3 = ESPERADOS["dataset_3_mus"]
CXC = pd.read_csv(PAQUETE / "casos" / E3["archivo"])


def test_d3_mus_seleccion_identica_al_calculo_manual():
    seleccion, plan = seleccionar_mus(CXC, "cliente", "saldo", E3["error_tolerable"], 95, inicio=E3["confianza_95"]["inicio"])
    esperado = E3["confianza_95"]
    assert plan.valor_libros == E3["valor_libros"]
    assert (plan.tamano, plan.intervalo) == (esperado["n"], esperado["intervalo"])
    assert dict(zip(seleccion["cliente"], seleccion["puntos"])) == esperado["seleccion"]
    assert sorted(seleccion.loc[seleccion["supera_intervalo"], "cliente"]) == esperado["superan_intervalo"]
    assert plan.excluidos == E3["excluidos"]


def test_d3_mus_tamanos_por_confianza_y_error_esperado():
    assert tamano_mus(E3["valor_libros"], E3["error_tolerable"], 90)[0] == E3["confianza_90"]["n"]
    assert tamano_mus(E3["valor_libros"], E3["error_tolerable"], 95, 5000, 1.6)[0] == E3["error_esperado_5000_factor_1_6"]["n"]


def test_d3_mus_exige_factor_de_expansion():
    with pytest.raises(ErrorMuestreo, match="factor de expansión"):
        tamano_mus(E3["valor_libros"], E3["error_tolerable"], 95, 5000)


def test_d3_mus_con_semilla_es_repetible():
    a, plan_a = seleccionar_mus(CXC, "cliente", "saldo", E3["error_tolerable"], semilla=99)
    b, plan_b = seleccionar_mus(CXC, "cliente", "saldo", E3["error_tolerable"], semilla=99)
    assert plan_a.inicio == plan_b.inicio and a["cliente"].tolist() == b["cliente"].tolist()
    assert set(E3["confianza_95"]["superan_intervalo"]) <= set(a["cliente"])  # las grandes salen siempre


def test_d3_aleatorio_simple_repetible():
    a = muestra_aleatoria(CXC, "cliente", 4, semilla=1)
    b = muestra_aleatoria(CXC, "cliente", 4, semilla=1)
    assert a["cliente"].tolist() == b["cliente"].tolist() and len(a) == 4
