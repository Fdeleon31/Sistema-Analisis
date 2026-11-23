"""Integridad de usuarios.json (refuerzo de Ficha 21).

Esperado por diseño:
- Subirse a Administrador editando usuarios.json bloquea el inicio de sesión de todos (archivo alterado).
- Cambiar la clave pública de otro usuario también se detecta.
- Cambiar la contraseña/clave privada de otro por las propias no permite firmar como él.
- Un archivo de una versión anterior (sin firma) sigue funcionando y lo firma el primer Administrador que entra.
- Los contadores de login (intentos, último acceso) no rompen la firma.
"""
from __future__ import annotations

import json

import pytest

from motor.seguridad import ErrorSeguridad
from motor.usuarios import PERFIL_ADMIN, PERFIL_PREPARADOR, GestorUsuarios


def _firma(tmp_path):
    g = GestorUsuarios(tmp_path)
    g.inicializar_firma(
        "adm_int", "Admin Integridad", "AdminInt2026!",
        preparador={"usuario": "prep_int", "nombre_completo": "Prep Integridad", "contrasena": "PrepInt2026!"},
    )
    return g


def _editar(g, fn):
    datos = json.loads(g.ruta_usuarios.read_text(encoding="utf-8"))
    fn(datos)
    g.ruta_usuarios.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")


def _usuario(datos, nombre):
    return next(u for u in datos["usuarios"] if u["usuario"] == nombre)


def test_archivo_nuevo_queda_firmado_y_los_logins_no_rompen_la_firma(tmp_path):
    g = _firma(tmp_path)
    assert g.estado_integridad()["estado"] == "firmado"
    with pytest.raises(ErrorSeguridad):
        g.autenticar("prep_int", "ClaveErronea2026!")  # suma un intento fallido
    g.autenticar("prep_int", "PrepInt2026!", modo_acceso=PERFIL_PREPARADOR)
    assert g.estado_integridad()["estado"] == "firmado"


def test_subirse_a_administrador_editando_el_archivo_se_detecta(tmp_path):
    g = _firma(tmp_path)
    _editar(g, lambda d: _usuario(d, "prep_int").update(perfil=PERFIL_ADMIN))
    assert g.estado_integridad()["estado"] == "alterado"
    with pytest.raises(ErrorSeguridad, match="modificado fuera de Folio Auditor"):
        g.autenticar("prep_int", "PrepInt2026!", modo_acceso=PERFIL_ADMIN)
    with pytest.raises(ErrorSeguridad):
        g.registro_claves()


def test_bajar_politicas_editando_el_archivo_se_detecta(tmp_path):
    g = _firma(tmp_path)
    _editar(g, lambda d: d["politicas"].update(max_intentos=1000))
    assert g.estado_integridad()["estado"] == "alterado"


def test_usar_la_clave_privada_propia_en_otro_usuario_no_permite_firmar_como_el(tmp_path):
    g = _firma(tmp_path)

    def suplantar(d):
        adm, prep = _usuario(d, "adm_int"), _usuario(d, "prep_int")
        adm["contrasena_hash"] = prep["contrasena_hash"]
        adm["clave_privada_cifrada"] = prep["clave_privada_cifrada"]

    _editar(g, suplantar)
    with pytest.raises(ErrorSeguridad, match="no corresponde a la clave pública"):
        g.autenticar("adm_int", "PrepInt2026!", modo_acceso=PERFIL_ADMIN)


def test_archivo_de_version_anterior_lo_firma_el_primer_administrador(tmp_path):
    g = _firma(tmp_path)
    _editar(g, lambda d: d.pop("firma_identidad"))
    assert g.estado_integridad()["estado"] == "sin_firma"
    g.autenticar("prep_int", "PrepInt2026!", modo_acceso=PERFIL_PREPARADOR)  # un no-admin no la firma
    assert g.estado_integridad()["estado"] == "sin_firma"
    g.autenticar("adm_int", "AdminInt2026!", modo_acceso=PERFIL_ADMIN)
    assert g.estado_integridad()["estado"] == "firmado"


def test_operaciones_del_administrador_mantienen_la_firma(tmp_path):
    g = _firma(tmp_path)
    adm = g.autenticar("adm_int", "AdminInt2026!", modo_acceso=PERFIL_ADMIN)
    g.crear_usuario(adm, "rev_int", "Revisor Integridad", "RevInt2026!", "Revisor")
    g.actualizar_politicas(adm, max_intentos=4)
    g.cambiar_estado_usuario(adm, "rev_int", False)
    assert g.estado_integridad()["estado"] == "firmado"
