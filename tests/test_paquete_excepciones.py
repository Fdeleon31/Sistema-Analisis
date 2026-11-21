"""Paridad contra los resultados esperados de las fichas 00 a 03.

Cada prueba compara el prototipo contra valores calculados a mano
(paquetes/excepciones-basicas/casos/esperados.json).
"""
import json
from pathlib import Path

import duckdb
import pytest

from motor.bitacora import Bitacora
from motor.ejecutor import cargar_auxiliares, cargar_manifiesto, correr_paquete, correr_prueba
from motor.exportador import exportar_excel
from motor.importador import importar
from motor.sintetico import generar

PAQUETE = Path(__file__).resolve().parents[1] / "paquetes" / "excepciones-basicas"
CASOS = PAQUETE / "casos"
ESPERADOS = json.loads((CASOS / "esperados.json").read_text(encoding="utf-8"))


@pytest.fixture
def con():
    c = duckdb.connect()
    cargar_auxiliares(c, cargar_manifiesto(PAQUETE))
    yield c
    c.close()


def _prueba(manifiesto_id: str, **cambios) -> dict:
    prueba = next(p for p in cargar_manifiesto(PAQUETE)["pruebas"] if p["id"] == manifiesto_id)
    return {**prueba, **cambios}


# Ficha 00 · Importación y bitácora

def test_importar_dos_veces_da_mismo_hash_y_totales(con):
    a = importar(con, CASOS / "duplicados.csv", "t1")
    b = importar(con, CASOS / "duplicados.csv", "t2")
    assert a["sha256"] == b["sha256"]
    assert a["filas"] == b["filas"] == 8
    assert a["totales"]["monto"] == b["totales"]["monto"] == 0.0


def test_importar_avisa_columnas_faltantes(con):
    with pytest.raises(ValueError, match="Faltan columnas"):
        importar(con, CASOS / "benford_ideal.csv", "t", columnas_requeridas=["fecha", "monto"])


def test_importar_rechaza_archivo_vacio(con, tmp_path):
    vacio = tmp_path / "vacio.csv"
    vacio.write_text("")
    with pytest.raises(ValueError, match="vacío"):
        importar(con, vacio, "t")


def test_importar_rechaza_nombres_peligrosos(con):
    with pytest.raises(ValueError):
        importar(con, CASOS / "duplicados.csv", 'mayor"; DROP TABLE x; --')


def test_bitacora_detecta_alteraciones(tmp_path):
    bitacora = Bitacora(tmp_path / "b.jsonl", usuario="prueba")
    bitacora.registrar("uno", valor=1)
    bitacora.registrar("dos", valor=2)
    assert bitacora.verificar()
    lineas = bitacora.ruta.read_text(encoding="utf-8").splitlines()
    lineas[0] = lineas[0].replace('"valor": 1', '"valor": 999')
    bitacora.ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    assert not bitacora.verificar()


# Ficha 01 · Benford

@pytest.mark.parametrize("caso", ["benford_todo_uno", "benford_ideal"])
def test_benford_coincide_con_calculo_manual(con, caso):
    esperado = ESPERADOS[caso]
    importar(con, CASOS / esperado["archivo"], "mayor")
    r = correr_prueba(con, PAQUETE, _prueba("benford-primer-digito"))
    assert r.resumen["n"] == esperado["n"]
    assert r.resumen["mad"] == pytest.approx(esperado["mad"], abs=1e-6)
    assert r.resumen["conformidad"] == esperado["conformidad"]
    if "z_digito_1" in esperado:
        assert r.tabla.loc[r.tabla["digito"] == 1, "z"].item() == pytest.approx(esperado["z_digito_1"], abs=1e-3)


def test_benford_dos_digitos_tiene_90_filas(con):
    importar(con, CASOS / "benford_ideal.csv", "mayor")
    r = correr_prueba(con, PAQUETE, _prueba("benford-dos-digitos"))
    assert len(r.tabla) == 90
    assert r.tabla["digito"].tolist() == list(range(10, 100))


# Ficha 02 · Duplicados

def test_duplicados_exactos(con):
    esperado = ESPERADOS["duplicados_exactos"]
    importar(con, CASOS / esperado["archivo"], "mayor")
    r = correr_prueba(con, PAQUETE, _prueba("duplicados-exactos"))
    assert len(r.tabla) == esperado["filas"]
    assert sorted(r.tabla["asiento"].unique().tolist()) == esperado["asientos"]
    assert set(r.tabla["veces"]) == {esperado["veces"]}


def test_mismo_mismo_distinto(con):
    esperado = ESPERADOS["mismo_mismo_distinto"]
    importar(con, CASOS / esperado["archivo"], "mayor")
    r = correr_prueba(con, PAQUETE, _prueba("mismo-mismo-distinto"))
    assert len(r.tabla) == esperado["filas"]
    assert r.tabla["asiento"].unique().tolist() == esperado["asientos"]


# Ficha 03 · Gaps

def test_gaps_numericos(con):
    importar(con, CASOS / "gaps.csv", "mayor")
    r = correr_prueba(con, PAQUETE, _prueba("gaps-asientos"))
    assert r.tabla[["desde", "hasta", "faltantes"]].values.tolist() == ESPERADOS["gaps_numericos"]["rangos"]


@pytest.mark.parametrize("solo_habiles,caso", [(True, "gaps_fechas_habiles"), (False, "gaps_fechas_todos")])
def test_gaps_fechas(con, solo_habiles, caso):
    importar(con, CASOS / "gaps.csv", "mayor")
    r = correr_prueba(con, PAQUETE, _prueba("gaps-fechas", parametros={"solo_habiles": solo_habiles, "excluir_feriados": False}))
    assert [d.isoformat() for d in r.tabla["dia"].dt.date] == ESPERADOS[caso]["dias"]


def test_gaps_fechas_excluye_feriados_de_panama(con, tmp_path):
    # 8 y 10 de enero de 2025 con registros; el 9 (Día de los Mártires) vacío no es excepción
    archivo = tmp_path / "feriado.csv"
    archivo.write_text(
        "asiento,linea,fecha,cuenta,descripcion,monto,usuario\n"
        "1,1,2025-01-08,5101,Gasto,10.00,ana\n"
        "2,1,2025-01-10,5101,Gasto,20.00,ana\n",
        encoding="utf-8",
    )
    importar(con, archivo, "mayor")
    con_feriados = correr_prueba(con, PAQUETE, _prueba("gaps-fechas"))
    sin_feriados = correr_prueba(con, PAQUETE, _prueba("gaps-fechas", parametros={"solo_habiles": True, "excluir_feriados": False}))
    assert len(con_feriados.tabla) == 0
    assert [d.isoformat() for d in sin_feriados.tabla["dia"].dt.date] == ["2025-01-09"]


def test_gaps_alfanumericos_por_prefijo(con, tmp_path):
    archivo = tmp_path / "alfa.csv"
    archivo.write_text(
        "asiento,linea,fecha,cuenta,descripcion,monto,usuario\n"
        "AS-0001,1,2025-01-08,5101,Gasto,10.00,ana\n"
        "AS-0003,1,2025-01-08,5101,Gasto,10.00,ana\n"
        "NC-0010,1,2025-01-08,5101,Nota,10.00,ana\n"
        "NC-0013,1,2025-01-08,5101,Nota,10.00,ana\n",
        encoding="utf-8",
    )
    importar(con, archivo, "mayor")
    r = correr_prueba(con, PAQUETE, _prueba("gaps-asientos"))
    assert r.tabla[["prefijo", "desde", "hasta", "faltantes"]].values.tolist() == [["AS-", 2, 2, 1], ["NC-", 11, 12, 2]]


def test_benford_avisa_muestra_pequena(con):
    importar(con, CASOS / "benford_todo_uno.csv", "mayor")
    r = correr_prueba(con, PAQUETE, _prueba("benford-primer-digito"))
    assert "Muestra pequeña" in r.resumen["advertencia"]


# Integración · mayor sintético con anomalías sembradas

def test_paquete_completo_encuentra_lo_sembrado(con, tmp_path):
    archivo = generar(tmp_path / "mayor.csv")
    manifiesto = cargar_manifiesto(PAQUETE)
    bitacora = Bitacora(tmp_path / "bitacora.jsonl", usuario="prueba")
    control = importar(con, archivo, "mayor", columnas_requeridas=manifiesto["archivos"][0]["columnas_requeridas"], bitacora=bitacora)
    resultados = {r.id: r for r in correr_paquete(con, manifiesto, bitacora)}

    assert resultados["gaps-asientos"].tabla[["desde", "hasta"]].values.tolist() == [[1500, 1502], [2200, 2200]]
    assert sorted(resultados["duplicados-exactos"].tabla["asiento"].unique().tolist()) == [100, 2501]
    assert resultados["mismo-mismo-distinto"].tabla["asiento"].unique().tolist() == [777]
    assert [d.isoformat() for d in resultados["gaps-fechas"].tabla["dia"].dt.date] == ["2025-07-15"]
    assert 99 in resultados["benford-dos-digitos"].resumen["digitos_significativos"]

    ruta = exportar_excel(list(resultados.values()), [control], bitacora, tmp_path / "cedula.xlsx")
    assert ruta.exists()
    assert bitacora.verificar()
