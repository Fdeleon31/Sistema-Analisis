"""Pruebas de Ficha 13: lectura offline de estados de cuenta PDF y paquete bancos-conciliacion."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

from conectores.estado_cuenta_pdf import generar_pdf_estado_cuenta, leer_estado_cuenta
from motor.ejecutor import cargar_encargo
from motor.servicio import ejecutar_encargo
from motor.sintetico import generar_estado_cuenta_bancos

RAIZ = Path(__file__).resolve().parents[1]


def test_bancos_pdf_formato_y_esperados(tmp_path):
    pdf, mayor = generar_estado_cuenta_bancos(tmp_path / "datos", semilla=33)
    encargo = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")

    corrida = ejecutar_encargo(
        "bancos-conciliacion",
        {"extracto": pdf, "mayor": mayor},
        encargo,
        tmp_path / "salida",
    )
    esperados = json.loads((RAIZ / "paquetes" / "bancos-conciliacion" / "casos" / "esperados.json").read_text(encoding="utf-8"))
    observados = {r.id: r.excepciones for r in corrida.resultados}

    assert observados == esperados["resultados"]
    assert corrida.bitacora.verificar()
    assert corrida.cedula.exists()
    assert corrida.controles[0]["codificacion"] == "PDF"
    assert corrida.controles[0]["filas_excluidas"] > 0


def test_detecta_bancos_panama_zip_y_signos_cr_db(tmp_path):
    pdf = tmp_path / "banistmo_enero.pdf"
    generar_pdf_estado_cuenta(
        pdf,
        [
            "BANISTMO PANAMA S.A.",
            "Cuenta: 010-224455-8",
            "Periodo: enero 2025",
        ],
        [
            {"fecha": "2025-01-10", "referencia": "DEP-001", "descripcion": "Depósito cliente", "debito": 0.0, "credito": 1500.0, "saldo": 11500.0},
            {"fecha": "2025-01-12", "referencia": "ACH-002", "descripcion": "Pago alquiler", "debito": 500.0, "credito": 0.0, "saldo": 11000.0},
        ],
        compresion=False,
    )
    ruta_zip = tmp_path / "extractos.zip"
    with zipfile.ZipFile(ruta_zip, "w") as z:
        z.write(pdf, pdf.name)

    lec = leer_estado_cuenta(ruta_zip)
    assert lec.archivos == 1
    assert len(lec.movimientos) == 2
    assert lec.movimientos["banco"].iloc[0] == "Banistmo"
    assert lec.movimientos["cuenta_bancaria"].iloc[0] == "010-224455-8"
    assert lec.movimientos["monto"].tolist() == [1500.0, -500.0]


def test_emparejamiento_1a1_con_montos_repetidos_prioriza_fecha_cercana(tmp_path):
    csv_ext = tmp_path / "extracto.csv"
    pd.DataFrame([
        {"fecha": "2025-01-02", "referencia": "ND-1", "descripcion": "Cargo bancario sin registrar", "debito": 25.0, "credito": 0.0, "saldo": 975.0},
        {"fecha": "2025-01-20", "referencia": "ND-2", "descripcion": "Cargo bancario contabilizado", "debito": 25.0, "credito": 0.0, "saldo": 950.0},
    ]).to_csv(csv_ext, index=False)

    csv_may = tmp_path / "mayor.csv"
    pd.DataFrame([
        {"asiento": "1", "linea": 1, "fecha": "2025-01-20", "cuenta": "1101", "descripcion": "Cargo bancario ND-2", "monto": -25.0, "usuario": "ana"},
        {"asiento": "1", "linea": 2, "fecha": "2025-01-20", "cuenta": "5201", "descripcion": "Gasto bancario", "monto": 25.0, "usuario": "ana"},
    ]).to_csv(csv_may, index=False)

    encargo = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")
    corrida = ejecutar_encargo("bancos-conciliacion", {"extracto": csv_ext, "mayor": csv_may}, encargo, tmp_path / "sal")
    por_id = {r.id: r for r in corrida.resultados}

    assert por_id["bancos-no-en-mayor"].excepciones == 1
    assert str(por_id["bancos-no-en-mayor"].tabla["referencia"].iloc[0]) == "ND-1"
    assert por_id["bancos-no-en-extracto"].excepciones == 0


def test_solo_extracto_omite_conciliacion_sin_fallar(tmp_path):
    pdf, _ = generar_estado_cuenta_bancos(tmp_path / "datos", semilla=33)
    encargo = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")
    corrida = ejecutar_encargo("bancos-conciliacion", {"extracto": pdf}, encargo, tmp_path / "sal")
    por_id = {r.id: r for r in corrida.resultados}

    assert por_id["bancos-continuidad"].excepciones == 1
    assert por_id["bancos-no-en-mayor"].omitida is not None
    assert por_id["bancos-no-en-extracto"].omitida is not None
