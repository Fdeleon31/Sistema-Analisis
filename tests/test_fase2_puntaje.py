"""Pruebas del puntaje de riesgo explicable por asiento (Ficha 11, Fase 2)."""
from pathlib import Path

import duckdb
import pytest

from motor.ejecutor import cargar_manifiesto, correr_paquete
from motor.importador import importar
from motor.sintetico import generar_diario_asientos
from test_fase1 import ENCARGO, ESPERADO_1, ESPERADOS, MAPEO_ERP, PAQUETE, _correr


def _correr_con_encargo(mayor, balanza, encargo):
    manifiesto = cargar_manifiesto(PAQUETE)
    defs = {a["tabla"]: a for a in manifiesto["archivos"]}
    con = duckdb.connect()
    for tabla, ruta in (("mayor", mayor), ("balanza", balanza)):
        d = defs[tabla]
        importar(
            con, ruta, tabla,
            columnas_requeridas=d["columnas_requeridas"],
            columnas_monto=d["columnas_monto"],
            columnas_fecha=d["columnas_fecha"],
            claves=d["claves"],
        )
    return {r.id: r for r in correr_paquete(con, manifiesto, encargo=encargo)}


@pytest.fixture(scope="module")
def resultados_d1(tmp_path_factory):
    mayor, balanza = generar_diario_asientos(tmp_path_factory.mktemp("p1"), semilla=7)
    r, _ = _correr(mayor, balanza)
    return r


def test_puntaje_dataset_1_identico_a_esperados(resultados_d1):
    res = resultados_d1["asientos-puntaje"]
    t = res.tabla
    obtenido = {str(f["asiento"]): [int(f["puntaje"]), f["nivel"]] for _, f in t.iterrows()}
    assert obtenido == ESPERADO_1["puntaje"]
    assert [str(a) for a in t["asiento"].head(4)] == ESPERADO_1["puntaje_primeros"]
    assert res.resumen["por_nivel"] == ESPERADO_1["puntaje_por_nivel"]
    assert res.excepciones == 11
    assert res.resumen["asientos_analizados"] == 1200


def test_explicacion_asiento_1111_conserva_orden_estable(resultados_d1):
    t = resultados_d1["asientos-puntaje"].tabla
    fila = t.loc[t["asiento"].astype(str) == "1111"].iloc[0]
    assert fila["explicacion"] == (
        "Fin de semana o feriado (+8); Descripción vacía o genérica (+8); "
        "Usuario poco frecuente (+8); Monto redondo (+5)"
    )


def test_pesos_personalizados_en_encargo(tmp_path):
    mayor, balanza = generar_diario_asientos(tmp_path, semilla=7)
    encargo = {**ENCARGO, "pesos_riesgo": {"monto_redondo": 30}}
    r = _correr_con_encargo(mayor, balanza, encargo)
    t = r["asientos-puntaje"].tabla
    fila_303 = t.loc[t["asiento"].astype(str) == "303"].iloc[0]
    assert int(fila_303["puntaje"]) == 30
    assert fila_303["nivel"] == "alto"


def test_criterio_invalido_y_umbrales_invalidos_fallan(tmp_path):
    mayor, balanza = generar_diario_asientos(tmp_path, semilla=7)
    with pytest.raises(ValueError, match="inventado"):
        _correr_con_encargo(mayor, balanza, {**ENCARGO, "pesos_riesgo": {"inventado": 5}})

    with pytest.raises(ValueError, match="Umbrales"):
        _correr_con_encargo(mayor, balanza, {**ENCARGO, "nivel_riesgo_medio": 30, "nivel_riesgo_alto": 20})


def test_puntaje_dataset_2_erp_con_prefijo_je(tmp_path):
    mayor, balanza = generar_diario_asientos(tmp_path, semilla=11, formato="dificil")
    r, _ = _correr(
        mayor, balanza,
        opciones_mayor={"hoja": "Diario", "mapeo": MAPEO_ERP, "debito_credito": ("Debe", "Haber"), "formato_fecha": "%d/%m/%Y"},
        opciones_balanza={"saltar_filas": 1},
    )
    e = ESPERADOS["dataset_2_erp"]
    a_erp = lambda a: f"{e['prefijo']}{int(a):0{e['ancho']}d}"  # noqa: E731
    esperado = {a_erp(k): v for k, v in ESPERADO_1["puntaje"].items()}
    t = r["asientos-puntaje"].tabla
    obtenido = {str(f["asiento"]): [int(f["puntaje"]), f["nivel"]] for _, f in t.iterrows()}
    assert obtenido == esperado
    assert [str(a) for a in t["asiento"].head(4)] == [a_erp(a) for a in ESPERADO_1["puntaje_primeros"]]
