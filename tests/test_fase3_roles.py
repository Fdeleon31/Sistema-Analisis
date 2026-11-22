"""Pruebas de Fase 3 (Ficha 15): revisión por roles NIA 220/230, portafolio y rutas portátiles .exe."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from motor.ejecutor import cargar_encargo
from motor.portafolio import guardar_encargo_yaml, listar_corridas_recientes, listar_encargos
from motor.revision import (
    cargar_revisiones,
    firmar_papel_trabajo,
    reabrir_papel_trabajo,
    registrar_revision_prueba,
)
from motor.rutas import raiz_recursos, raiz_trabajo
from motor.servicio import actualizar_cedula_corrida, ejecutar_encargo
from motor.sintetico import generar

RAIZ = Path(__file__).resolve().parents[1]


def test_flujo_revision_y_firmas_nia220_y_excel(tmp_path):
    mayor = generar(tmp_path / "mayor.csv")
    encargo = cargar_encargo(RAIZ / "encargos" / "ejemplo-2025.yaml")
    corrida = ejecutar_encargo("excepciones-basicas", {"mayor": mayor}, encargo, tmp_path / "corrida_1")
    ids = [r.id for r in corrida.resultados if not r.omitida]

    # Socio no puede firmar sin firma previa del Preparador ni con pruebas pendientes
    with pytest.raises(ValueError, match="Preparador"):
        firmar_papel_trabajo(corrida.carpeta, "Socio", "C. Mendoza", bitacora=corrida.bitacora, pruebas_ejecutadas=ids)

    # Documentar todas excepto la última -> Preparador firma, pero Socio aún bloqueado por 'Pendiente'
    for pid in ids[:-1]:
        registrar_revision_prueba(
            corrida.carpeta, pid, "Aclarado con evidencia", f"Revisado {pid}", "A. Gómez", "Preparador", corrida.bitacora
        )
    firmar_papel_trabajo(corrida.carpeta, "Preparador", "A. Gómez", bitacora=corrida.bitacora, pruebas_ejecutadas=ids)

    with pytest.raises(ValueError, match="Pendiente"):
        firmar_papel_trabajo(corrida.carpeta, "Socio", "C. Mendoza", bitacora=corrida.bitacora, pruebas_ejecutadas=ids)

    # Concluir última prueba, firmar Revisor y cerrar como Socio
    registrar_revision_prueba(
        corrida.carpeta, ids[-1], "Hallazgo confirmado", "Requiere carta a gerencia", "M. Ríos", "Revisor", corrida.bitacora
    )
    firmar_papel_trabajo(corrida.carpeta, "Revisor", "M. Ríos", bitacora=corrida.bitacora, pruebas_ejecutadas=ids)
    estado = firmar_papel_trabajo(corrida.carpeta, "Socio", "C. Mendoza", bitacora=corrida.bitacora, pruebas_ejecutadas=ids)
    assert estado["bloqueado"] is True

    # Papel cerrado no permite editar conclusiones
    with pytest.raises(ValueError, match="cerrado"):
        registrar_revision_prueba(
            corrida.carpeta, ids[0], "En revisión", "Cambio tardío", "A. Gómez", "Preparador", corrida.bitacora
        )

    # Regenerar cédula Excel reflejando conclusiones y hoja de firmas
    actualizar_cedula_corrida(corrida)
    xls = pd.ExcelFile(corrida.cedula)
    assert "Revisiones y Firmas" in xls.sheet_names
    resumen = pd.read_excel(xls, sheet_name="Resumen")
    assert "Estado revisión" in resumen.columns
    assert "Hallazgo confirmado" in resumen["Estado revisión"].astype(str).tolist()
    assert "Requiere carta a gerencia" in resumen["Conclusión del auditor"].astype(str).tolist()

    hoja_firmas = pd.read_excel(xls, sheet_name="Revisiones y Firmas")
    assert set(hoja_firmas["Auditor"].dropna()) == {"A. Gómez", "M. Ríos", "C. Mendoza"}
    assert corrida.bitacora.verificar()


def test_reapertura_papel_limpia_socio_y_deja_huella(tmp_path):
    mayor = generar(tmp_path / "mayor.csv")
    corrida = ejecutar_encargo("excepciones-basicas", {"mayor": mayor}, {}, tmp_path / "corrida_r")
    ids = [r.id for r in corrida.resultados if not r.omitida]
    for pid in ids:
        registrar_revision_prueba(corrida.carpeta, pid, "Aclarado con evidencia", "OK", "Ana", "Preparador", corrida.bitacora)
    firmar_papel_trabajo(corrida.carpeta, "Preparador", "Ana", bitacora=corrida.bitacora, pruebas_ejecutadas=ids)
    firmar_papel_trabajo(corrida.carpeta, "Socio", "Carlos", bitacora=corrida.bitacora, pruebas_ejecutadas=ids)

    with pytest.raises(ValueError, match="motivo"):
        reabrir_papel_trabajo(corrida.carpeta, "   ", "Carlos", bitacora=corrida.bitacora)

    estado = reabrir_papel_trabajo(
        corrida.carpeta, "Recibida aclaración adicional de Gerencia", "Carlos", bitacora=corrida.bitacora
    )
    assert estado["bloqueado"] is False
    assert "Socio" not in estado["firmas"]
    assert "Preparador" in estado["firmas"]
    assert any(r["evento"] == "reapertura_papel_trabajo" for r in corrida.bitacora.leer())
    assert corrida.bitacora.verificar()


def test_portafolio_encargos_y_corridas_detecta_corrupcion(tmp_path):
    # Encargos YAML
    carp_enc = tmp_path / "encargos"
    ruta_yaml = guardar_encargo_yaml(
        {"cliente": "Importadora Pacífico, S.A.", "fecha_cierre": "2025-12-31", "marco": "NIIF", "materialidad": 250000},
        carp_enc / "pacifico.yaml",
    )
    assert ruta_yaml.exists()
    lista = listar_encargos(carp_enc)
    assert len(lista) == 1 and lista[0]["cliente"] == "Importadora Pacífico, S.A."

    # Corridas históricas + detección de alteración SHA-256
    carp_sal = tmp_path / "salidas"
    mayor = generar(tmp_path / "mayor.csv")
    c = ejecutar_encargo("excepciones-basicas", {"mayor": mayor}, {"cliente": "Cliente Hist"}, carp_sal / "20261122-010000")
    hist_ok = listar_corridas_recientes(carp_sal)
    assert len(hist_ok) == 1 and hist_ok[0]["sha256_integro"] is True and hist_ok[0]["cliente"] == "Cliente Hist"

    # Alterar 1 línea de bitácora y validar que el portafolio lo reporta
    bit_p = c.carpeta / "bitacora.jsonl"
    contenido = bit_p.read_text(encoding="utf-8").replace("Cliente Hist", "Cliente Alterado")
    bit_p.write_text(contenido, encoding="utf-8")
    hist_bad = listar_corridas_recientes(carp_sal)
    assert hist_bad[0]["sha256_integro"] is False


def test_rutas_portatiles_desarrollo_y_pyinstaller(tmp_path, monkeypatch):
    assert (raiz_recursos() / "paquetes").exists()
    assert (raiz_trabajo() / "motor").exists()

    meipass = tmp_path / "_mei"
    exe_dir = tmp_path / "dist" / "LibroAuditoria"
    exe_dir.mkdir(parents=True)
    exe_bin = exe_dir / "LibroAuditoria.exe"
    exe_bin.write_bytes(b"")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_bin))

    assert raiz_recursos() == meipass
    assert raiz_trabajo() == exe_dir.resolve()
