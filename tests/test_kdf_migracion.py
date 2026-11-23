"""Costo scrypt vigente y migración de registros antiguos (refuerzo de Ficha 21).

Esperado por diseño:
- Contraseñas y claves privadas nuevas usan N = 2^17 (OWASP), r = 8, p = 1.
- Un usuario creado con N = 2^14 (versiones <= 0.9.0) entra con su contraseña de siempre y su registro
  se migra a 2^17 en ese mismo inicio de sesión, conservando la misma clave de firma.
- Parámetros fuera de rango en usuarios.json se rechazan (ni debilitar ni congelar).
- Un usuario inexistente cuesta lo mismo que uno real (sin enumeración por tiempo).
"""
from __future__ import annotations

import json
import time

import pytest

from motor import cripto
from motor.cripto import derivar_clave_scrypt, hashear_contrasena
from motor.seguridad import ErrorSeguridad
from motor.usuarios import PERFIL_PREPARADOR, GestorUsuarios


@pytest.mark.scrypt_real
def test_costo_vigente_es_2_17():
    reg = hashear_contrasena("ContrasenaSegura2026!")
    assert (reg["n"], reg["r"], reg["p"]) == (2**17, 8, 1)


def test_parametros_fuera_de_rango_se_rechazan():
    with pytest.raises(ErrorSeguridad):
        derivar_clave_scrypt("x", b"sal-sintetica", n=2**10)
    with pytest.raises(ErrorSeguridad):
        derivar_clave_scrypt("x", b"sal-sintetica", n=2**22)


def test_migracion_de_registro_antiguo_al_iniciar_sesion(tmp_path, monkeypatch):
    # Crear la firma con el costo antiguo (2^14), como en 0.9.0
    monkeypatch.setattr(cripto, "SCRYPT_N", 2**14)
    gestor = GestorUsuarios(tmp_path)
    gestor.inicializar_firma(
        "adm_mig", "Admin Migración", "AdminMig2026!",
        preparador={"usuario": "prep_mig", "nombre_completo": "Prep Migración", "contrasena": "PrepMig2026!"},
    )
    antes = {u["usuario"]: u for u in json.loads(gestor.ruta_usuarios.read_text(encoding="utf-8"))["usuarios"]}
    assert antes["prep_mig"]["contrasena_hash"]["n"] == 2**14
    huella_antes = antes["prep_mig"]["huella_clave"]

    # Subir el costo vigente y entrar: el registro se migra
    monkeypatch.setattr(cripto, "SCRYPT_N", 2**15)
    ses = gestor.autenticar("prep_mig", "PrepMig2026!", modo_acceso=PERFIL_PREPARADOR)
    despues = {u["usuario"]: u for u in json.loads(gestor.ruta_usuarios.read_text(encoding="utf-8"))["usuarios"]}
    assert despues["prep_mig"]["contrasena_hash"]["n"] == 2**15
    assert despues["prep_mig"]["clave_privada_cifrada"]["n"] == 2**15
    assert despues["prep_mig"]["huella_clave"] == huella_antes == ses.huella_clave
    assert despues["adm_mig"]["contrasena_hash"]["n"] == 2**14  # solo migra quien entra

    # Vuelve a entrar con la misma contraseña y la clave de firma intacta
    ses2 = gestor.autenticar("prep_mig", "PrepMig2026!", modo_acceso=PERFIL_PREPARADOR)
    assert ses2.semilla_privada_bytes == ses.semilla_privada_bytes
    eventos = [e["evento"] for e in gestor.leer_bitacora_accesos()[0]]
    assert eventos.count("migracion_kdf") == 1


@pytest.mark.scrypt_real
def test_usuario_inexistente_cuesta_lo_mismo_que_uno_real(tmp_path):
    gestor = GestorUsuarios(tmp_path)
    gestor.inicializar_firma(
        "adm_t", "Admin Tiempo", "AdminTiempo2026!",
        preparador={"usuario": "prep_t", "nombre_completo": "Prep Tiempo", "contrasena": "PrepTiempo2026!"},
    )

    def medir(usuario: str) -> float:
        t = time.perf_counter()
        with pytest.raises(ErrorSeguridad):
            gestor.autenticar(usuario, "ContrasenaErronea1!")
        return time.perf_counter() - t

    medir("nadie")  # calienta el señuelo
    t_real = medir("prep_t")
    t_falso = medir("usuario_que_no_existe")
    assert t_falso > 0.5 * t_real
