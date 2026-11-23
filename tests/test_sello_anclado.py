"""Sello anclado a un registro de claves (Ficha 21, refuerzo).

Resultados esperados fijados por diseño antes de correr el motor:
- Una carpeta re-sellada con una clave inventada a nombre del Socio se RECHAZA si se entrega el registro de claves.
- Sin registro, la firma es íntegra pero `firmante_verificado` es None (no se puede afirmar quién firmó).
- Un archivo agregado después del sellado invalida el sello (versión 2).
- Una clave registrada a nombre de otro usuario no puede firmar como el Socio.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from motor.bitacora import Bitacora
from motor.cripto import (
    generar_par_ed25519,
    huella_clave_publica,
    sellar_corrida,
    verificar_sello_corrida,
)

RAIZ = Path(__file__).resolve().parents[1]


def _carpeta_corrida(tmp_path: Path) -> Path:
    carp = tmp_path / "corrida"
    carp.mkdir()
    bit = Bitacora(carp / "bitacora.jsonl", usuario="preparador")
    bit.registrar("inicio")
    bit.registrar("prueba", id="asientos-criterios", resultado=3)
    (carp / "cedula.xlsx").write_bytes(b"cedula sintetica v1")
    (carp / "muestra.xlsx").write_bytes(b"muestra MUS sintetica")
    return carp


def _registro(usuario: str, pub: bytes) -> dict:
    return {huella_clave_publica(pub): {"usuario": usuario, "perfil": "Socio", "activo": True}}


def test_resello_con_clave_inventada_se_rechaza_con_registro(tmp_path):
    carp = _carpeta_corrida(tmp_path)
    s_real, p_real = generar_par_ed25519()
    registro = _registro("socio.real", p_real)
    sellar_corrida(carp, "socio.real", "Socio", s_real, p_real)

    ok = verificar_sello_corrida(carp, claves_registradas=registro)
    assert ok["valido"] is True and ok["firmante_verificado"] is True

    # Alterar la cédula y re-sellar con una clave nueva a nombre del mismo Socio
    (carp / "cedula.xlsx").write_bytes(b"cedula ALTERADA")
    s_falsa, p_falsa = generar_par_ed25519()
    sellar_corrida(carp, "socio.real", "Socio", s_falsa, p_falsa)

    sin_ancla = verificar_sello_corrida(carp)
    assert sin_ancla["valido"] is True
    assert sin_ancla["firmante_verificado"] is None
    assert "NO está verificado" in sin_ancla["motivo"]

    anclado = verificar_sello_corrida(carp, claves_registradas=registro)
    assert anclado["valido"] is False
    assert anclado["firmante_verificado"] is False
    assert "no está registrada" in anclado["motivo"]


def test_clave_registrada_de_otro_usuario_no_firma_como_socio(tmp_path):
    carp = _carpeta_corrida(tmp_path)
    s_prep, p_prep = generar_par_ed25519()
    _, p_soc = generar_par_ed25519()
    registro = {**_registro("preparador", p_prep), **_registro("socio.real", p_soc)}
    sellar_corrida(carp, "socio.real", "Socio", s_prep, p_prep)  # el preparador firma diciendo ser el socio

    res = verificar_sello_corrida(carp, claves_registradas=registro)
    assert res["valido"] is False
    assert "pertenece a 'preparador'" in res["motivo"]


def test_sello_cubre_todos_los_archivos_y_detecta_agregados(tmp_path):
    carp = _carpeta_corrida(tmp_path)
    s, p = generar_par_ed25519()
    sellar_corrida(carp, "socio.real", "Socio", s, p)
    sello = json.loads((carp / "sello.json").read_text(encoding="utf-8"))
    assert sello["version"] == 2
    assert set(sello["manifiesto"]["archivos"]) == {"bitacora.jsonl", "cedula.xlsx", "muestra.xlsx"}

    # Alterar un archivo que antes NO estaba protegido (muestra MUS)
    original = (carp / "muestra.xlsx").read_bytes()
    (carp / "muestra.xlsx").write_bytes(b"muestra cambiada")
    assert verificar_sello_corrida(carp)["valido"] is False
    (carp / "muestra.xlsx").write_bytes(original)
    assert verificar_sello_corrida(carp)["valido"] is True

    # Agregar un archivo después del sellado
    (carp / "evidencia_extra.pdf").write_bytes(b"%PDF-1.4 sintetico")
    res = verificar_sello_corrida(carp)
    assert res["valido"] is False
    assert "agregaron archivos" in res["motivo"]


def test_cli_verificar_distingue_firmante_sin_verificar_y_falsificado(tmp_path):
    carp = _carpeta_corrida(tmp_path)
    s_real, p_real = generar_par_ed25519()
    sellar_corrida(carp, "socio.real", "Socio", s_real, p_real)
    claves = tmp_path / "claves_firma.json"
    claves.write_text(
        json.dumps({"tipo": "registro_claves_folio", "version": 1, "claves": _registro("socio.real", p_real)}),
        encoding="utf-8",
    )

    def correr(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RAIZ / "cuadra.py"), "verificar", str(carp), *extra],
            capture_output=True, text=True, cwd=tmp_path,
        )

    r = correr("--claves", str(claves))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VÁLIDO" in r.stdout

    s_f, p_f = generar_par_ed25519()
    sellar_corrida(carp, "socio.real", "Socio", s_f, p_f)
    r = correr("--claves", str(claves))
    assert r.returncode == 1
    assert "INVÁLIDO" in r.stdout


def test_firma_socio_regenera_cedula_antes_de_sellar(tmp_path):
    """La cédula regenerada con las firmas debe quedar DENTRO del sello (antes quedaba 'alterada' al instante)."""
    import base64

    from motor.revision import firmar_papel_trabajo, guardar_revisiones, cargar_revisiones
    from motor.usuarios import SesionAutenticada

    carp = _carpeta_corrida(tmp_path)
    estado = cargar_revisiones(carp, ["asientos-criterios"])
    estado["por_prueba"]["asientos-criterios"]["estado"] = "Aclarado con evidencia"
    estado["firmas"]["Preparador"] = {"auditor": "Ana Preparadora", "usuario": "ana.prep"}
    guardar_revisiones(carp, estado)

    semilla, pub = generar_par_ed25519()
    sesion = SesionAutenticada(
        usuario="sofia.soc", nombre_completo="Sofía Socia", perfil="Socio", rol_auditoria=None,
        clave_publica_b64=base64.b64encode(pub).decode("ascii"), huella_clave=huella_clave_publica(pub),
        fecha_login_utc="2026-11-23T00:00:00+00:00", _semilla_privada=semilla,
    )
    llamadas = []

    def regenerar():
        llamadas.append("cedula")
        (carp / "cedula.xlsx").write_bytes(b"cedula con firmas de Preparador y Socio")

    firmar_papel_trabajo(
        carp, "Socio", "Sofía Socia", bitacora=Bitacora(carp / "bitacora.jsonl", usuario="sofia.soc"),
        pruebas_ejecutadas=["asientos-criterios"], sesion=sesion, regenerar_cedula=regenerar,
    )
    assert llamadas == ["cedula"]
    res = verificar_sello_corrida(carp, claves_registradas=_registro("sofia.soc", pub))
    assert res["valido"] is True, res["motivo"]
    assert res["firmante_verificado"] is True
