"""Estados de cuenta en PDF como los genera un banco (fuentes incrustadas), Ficha 13.

Los PDF de tests/fixtures son sintéticos: se generaron con Chromium desde HTML inventado, que
incrusta las fuentes en subconjuntos (Identity-H + ToUnicode) igual que los sistemas bancarios.

Resultados esperados calculados a mano (estado_cuenta_fuentes_incrustadas.pdf):
  Saldo inicial 10,000.00
  05/01/2025 ACH Pago proveedor Distribuidora XYZ  débito 1,250.00  saldo  8,750.00
  10/01/2025 Depósito cliente ABC                  crédito 3,000.00 saldo 11,750.00
  15/01/2025 Cargo por servicio                    débito    12.50  saldo 11,737.50
  Saldo final 11,737.50 -> 10,000 + 3,000 - 1,262.50 = 11,737.50 (cuadra)

Antes de este arreglo el parser propio leía códigos de glifo (\\x16\\x14…) y devolvía 0 movimientos sin error.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtPdf")

from conectores.estado_cuenta_pdf import _proporcion_legible, leer_estado_cuenta  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def test_pdf_con_fuentes_incrustadas_se_lee_y_cuadra():
    lec = leer_estado_cuenta(FIX / "estado_cuenta_fuentes_incrustadas.pdf")
    assert lec.metodo == "pdf (QtPdf)"
    mov = lec.movimientos
    assert list(mov["fecha"]) == [date(2025, 1, 5), date(2025, 1, 10), date(2025, 1, 15)]
    assert list(mov["debito"]) == [1250.00, 0.00, 12.50]
    assert list(mov["credito"]) == [0.00, 3000.00, 0.00]
    assert list(mov["saldo"]) == [8750.00, 11750.00, 11737.50]
    assert mov.loc[0, "banco"] == "Banco General"
    res = lec.resumen_saldos[0]
    assert res["saldo_inicial"] == 10000.00
    assert res["saldo_final_reportado"] == 11737.50
    assert res["cuadra"] is True
    assert lec.errores == []


def test_pdf_sin_movimientos_detiene_la_lectura_con_error():
    with pytest.raises(ValueError, match="No se reconoció ningún movimiento"):
        leer_estado_cuenta(FIX / "estado_cuenta_sin_movimientos.pdf")


def test_texto_de_glifos_se_considera_ilegible():
    assert _proporcion_legible(["\x16\x14\x12\x13\x14  6DOGR\x03ILQDO"]) < 0.9
    assert _proporcion_legible(["05/01/2025 ACH Pago proveedor 1,250.00 8,750.00"]) == 1.0
