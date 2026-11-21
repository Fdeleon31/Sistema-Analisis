"""Casos borde de importación (ronda 3 del ciclo de estrés de la Fase 0)."""
from datetime import datetime

import duckdb
import pandas as pd
import pytest

from motor.importador import ErrorImportacion, importar

H = "asiento,linea,fecha,cuenta,descripcion,monto,usuario\n"


def _csv(tmp_path, nombre, contenido):
    ruta = tmp_path / nombre
    ruta.write_text(H + contenido, encoding="utf-8")
    return ruta


def test_fechas_ambiguas_sin_formato_detienen_la_importacion(tmp_path):
    ruta = _csv(tmp_path, "a.csv", "1,1,03/04/2025,5101,G,10.00,a\n2,1,05/06/2025,5101,G,20.00,a\n")
    with pytest.raises(ErrorImportacion, match="ambiguas"):
        importar(duckdb.connect(), ruta, "m")


def test_fechas_ambiguas_con_formato_se_leen_bien(tmp_path):
    ruta = _csv(tmp_path, "a.csv", "1,1,03/04/2025,5101,G,10.00,a\n")
    con = duckdb.connect()
    importar(con, ruta, "m", formato_fecha="%d/%m/%Y")
    assert str(con.execute("SELECT fecha FROM m").fetchone()[0]) == "2025-04-03"


def test_monto_mal_formado_avisa_con_ejemplo(tmp_path):
    ruta = _csv(tmp_path, "m.csv", "1,1,2025-01-02,5101,G,12.34.56,a\n")
    with pytest.raises(ErrorImportacion, match="12.34.56"):
        importar(duckdb.connect(), ruta, "m")


def test_negativo_al_final_estilo_sap(tmp_path):
    ruta = _csv(tmp_path, "s.csv", '1,1,2025-01-02,5101,G,"1,500.00-",a\n1,2,2025-01-02,1101,G,"1,500.00",a\n')
    con = duckdb.connect()
    importar(con, ruta, "m")
    assert [float(x[0]) for x in con.execute("SELECT monto FROM m ORDER BY linea").fetchall()] == [-1500.0, 1500.0]


def test_mapeo_con_columna_inexistente_da_mensaje_claro(tmp_path):
    ruta = _csv(tmp_path, "s.csv", "1,1,2025-01-02,5101,G,10.00,a\n")
    with pytest.raises(ErrorImportacion, match="Importe"):
        importar(duckdb.connect(), ruta, "m", mapeo={"Importe": "monto"})


def test_excel_con_fechas_y_numeros_reales_conserva_ceros_a_la_izquierda(tmp_path):
    df = pd.DataFrame({
        "asiento": [1, 1], "linea": [1, 2], "fecha": [datetime(2025, 1, 2)] * 2,
        "cuenta": ["0101", "1101"], "descripcion": ["G", "G"], "monto": [10.5, -10.5], "usuario": ["a", "a"],
    })
    ruta = tmp_path / "real.xlsx"
    df.to_excel(ruta, index=False)
    con = duckdb.connect()
    control = importar(con, ruta, "m")
    assert str(con.execute("SELECT MIN(fecha) FROM m").fetchone()[0]) == "2025-01-02"
    assert con.execute("SELECT cuenta FROM m ORDER BY linea").fetchone()[0] == "0101"
    assert control["totales"]["monto"] == 0.0


def test_fecha_con_hora(tmp_path):
    ruta = _csv(tmp_path, "t.csv", "1,1,2025-01-02 14:35:00,5101,G,10.00,a\n")
    con = duckdb.connect()
    importar(con, ruta, "m")
    assert str(con.execute("SELECT fecha FROM m").fetchone()[0]) == "2025-01-02"


def test_linea_en_blanco_se_excluye_y_se_reporta(tmp_path):
    ruta = _csv(tmp_path, "b.csv", "1,1,2025-01-02,5101,G,10.00,a\n,,,,,,\n2,1,2025-01-03,5101,G,20.00,a\n")
    control = importar(duckdb.connect(), ruta, "m")
    assert (control["filas"], control["filas_excluidas"]) == (2, 1)
