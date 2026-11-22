"""Pruebas de Ficha 14: copiloto offline en español, SQL visible solo lectura y borrador NIA."""
from __future__ import annotations

from pathlib import Path

import pytest

from ia.copiloto import (
    ejecutar_propuesta_aprobada,
    preparar_conexion_copiloto,
    proponer_consulta_sql,
    redactar_borrador_hallazgo,
)
from motor.bitacora import Bitacora
from motor.sintetico import generar_diario_asientos, generar_estado_cuenta_bancos, generar_facturas_fe


def test_propone_sql_para_patrones_clave_y_calcula_determinista(tmp_path):
    mayor, balanza = generar_diario_asientos(tmp_path / "datos", semilla=7)
    encargo = {"cliente": "Empresa Test, S.A.", "fecha_cierre": "2025-12-31", "materialidad_ejecucion": 112500.0}
    con, cols = preparar_conexion_copiloto({"mayor": mayor, "balanza": balanza})

    try:
        # 1. Descuadrados (debe detectar exactamente el asiento 707 sembrado)
        p_desc = proponer_consulta_sql("Asientos descuadrados", cols, encargo)
        res_desc = ejecutar_propuesta_aprobada(con, p_desc.sql, p_desc.pregunta, p_desc.titulo, p_desc.nia, encargo=encargo)
        assert len(res_desc.tabla) == 1
        assert int(res_desc.tabla["asiento"].iloc[0]) == 707
        assert abs(float(res_desc.tabla["descuadre_neto"].iloc[0]) - 50.0) < 0.01

        # 2. Mayores a 25,000 en noviembre
        p_nov = proponer_consulta_sql("Muéstrame asientos mayores a 25,000 en noviembre", cols, encargo)
        assert "EXTRACT('month' FROM fecha) = 11" in p_nov.sql
        assert "ABS(monto) >= 25000.00" in p_nov.sql
        res_nov = ejecutar_propuesta_aprobada(con, p_nov.sql, p_nov.pregunta, p_nov.titulo, p_nov.nia, encargo=encargo)
        assert (res_nov.tabla["asiento"] == 1111).any()

        # 3. Fin de semana
        p_fds = proponer_consulta_sql("Asientos en fin de semana", cols, encargo)
        res_fds = ejecutar_propuesta_aprobada(con, p_fds.sql, p_fds.pregunta, p_fds.titulo, p_fds.nia, encargo=encargo)
        assert {101, 1111} <= set(res_fds.tabla["asiento"].astype(int).tolist())

        # 4. Resumen por usuario
        p_usr = proponer_consulta_sql("Resumen por usuario", cols, encargo)
        res_usr = ejecutar_propuesta_aprobada(con, p_usr.sql, p_usr.pregunta, p_usr.titulo, p_usr.nia, encargo=encargo)
        assert "admin.temporal" in set(res_usr.tabla["usuario"].astype(str))
    finally:
        con.close()


def test_bloquea_sql_mutante_y_registra_aprobacion_en_bitacora(tmp_path):
    mayor, _ = generar_diario_asientos(tmp_path / "datos", semilla=7)
    con, cols = preparar_conexion_copiloto({"mayor": mayor})
    bitacora = Bitacora(tmp_path / "bitacora.jsonl")

    try:
        with pytest.raises(ValueError):
            ejecutar_propuesta_aprobada(con, "DROP TABLE mayor", "ataque", bitacora=bitacora)

        prop = proponer_consulta_sql("Top 5 líneas con mayor monto", cols)
        assert "LIMIT 5" in prop.sql
        res = ejecutar_propuesta_aprobada(con, prop.sql, prop.pregunta, prop.titulo, prop.nia, bitacora=bitacora)
        assert len(res.tabla) == 5
        assert bitacora.verificar()
        eventos = bitacora.leer()
        assert len(eventos) == 1
        assert eventos[0]["evento"] == "consulta_copiloto_aprobada"
        assert "5 fila(s)" in res.borrador
    finally:
        con.close()


def test_copiloto_soporta_extracto_pdf_y_facturas_dgi(tmp_path):
    pdf, _ = generar_estado_cuenta_bancos(tmp_path / "bancos", semilla=33)
    zip_fe, _ = generar_facturas_fe(tmp_path / "fe", semilla=21)
    con, cols = preparar_conexion_copiloto({"extracto": pdf, "facturas": zip_fe})

    try:
        p_ext = proponer_consulta_sql("Cargos bancarios del extracto mayores a 100", cols)
        assert p_ext.tabla_objetivo == "extracto"
        res_ext = ejecutar_propuesta_aprobada(con, p_ext.sql, p_ext.pregunta, p_ext.titulo, p_ext.nia)
        assert not res_ext.tabla.empty and (res_ext.tabla["debito"] >= 100.0).all()

        p_fe = proponer_consulta_sql("Notas de crédito de facturas electrónicas DGI", cols)
        assert p_fe.tabla_objetivo == "facturas"
        res_fe = ejecutar_propuesta_aprobada(con, p_fe.sql, p_fe.pregunta, p_fe.titulo, p_fe.nia)
        assert len(res_fe.tabla) == 5
    finally:
        con.close()


def test_borrador_sin_hallazgos_informa_cero_registros():
    import pandas as pd
    texto = redactar_borrador_hallazgo("Prueba vacía", ["NIA 500"], pd.DataFrame(), encargo={"cliente": "Demo", "fecha_cierre": "2025-12-31"})
    assert "0 registros" in texto
    assert "0 fila(s)" in texto
