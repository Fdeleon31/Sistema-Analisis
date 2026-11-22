"""Pruebas automatizadas de las pantallas PySide6 de inicio de sesión y administración (offscreen)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
)

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.login_qt import (  # noqa: E402
    DialogoAdminSeguridad,
    DialogoCambiarContrasena,
    DialogoLoginFolio,
)
from motor.seguridad import ErrorSeguridad  # noqa: E402
from motor.usuarios import GestorUsuarios, PERFIL_ADMIN, PERFIL_PREPARADOR, PERFIL_REVISOR  # noqa: E402

PWD_ADMIN = "AdminFolio2026!"
PWD_PREP = "PrepFolio2026!"
PWD_REV = "RevFolio2026!"
PWD_NUEVA = "NuevaClave2027!"


@pytest.fixture(scope="module")
def qapp():
    if QApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _textos_visibles_dialogo(dlg) -> list[str]:
    textos = [dlg.windowTitle()]
    for w in dlg.findChildren(QLabel):
        textos.append(w.text())
    for w in dlg.findChildren(QPushButton):
        textos.append(w.text())
    for w in dlg.findChildren(QCheckBox):
        textos.append(w.text())
    for w in dlg.findChildren(QComboBox):
        for i in range(w.count()):
            textos.append(w.itemText(i))
    for w in dlg.findChildren(QTabWidget):
        for i in range(w.count()):
            textos.append(w.tabText(i))
    return [t for t in textos if t]


def _verificar_identidad_dialogo(dlg) -> None:
    textos = _textos_visibles_dialogo(dlg)
    assert any("folio auditor" in t.lower() for t in textos)
    for t in textos:
        assert "cuadra" not in t.lower(), f"Marca prohibida detectada en UI: {t!r}"
        assert not re.search(r"\b0\.[68]\.\d+\b", t), f"Versión visible detectada en UI: {t!r}"
    assert not dlg.windowIcon().isNull()
    assert hasattr(dlg, "lbl_logo")
    pm = dlg.lbl_logo.pixmap()
    assert pm is not None and not pm.isNull()


def _inicializar_firma_desde_ui(tmp_path: Path) -> GestorUsuarios:
    gestor = GestorUsuarios(tmp_path)
    dlg = DialogoLoginFolio(gestor=gestor, permitir_evaluacion=True)
    try:
        dlg.edt_admin_usr.setText("admin.firma")
        dlg.edt_admin_nom.setText("Elena Vargas")
        dlg.edt_admin_pwd.setText(PWD_ADMIN)
        dlg.edt_admin_pwd2.setText(PWD_ADMIN)
        dlg.chk_crear_prep.setChecked(True)
        dlg.edt_prep_usr.setText("prep.nia")
        dlg.edt_prep_nom.setText("Carlos Mendoza")
        dlg.edt_prep_pwd.setText(PWD_PREP)
        dlg.edt_prep_pwd2.setText(PWD_PREP)
        dlg.chk_segregacion.setChecked(True)
        assert dlg.intentar_inicializar() is True
    finally:
        dlg.close()
    return gestor


def test_primer_arranque_inicializa_admin_y_preparador(qapp, tmp_path):
    gestor = GestorUsuarios(tmp_path)
    assert not gestor.existe_configuracion()

    dlg_sin_eval = DialogoLoginFolio(gestor=gestor, permitir_evaluacion=False)
    try:
        assert dlg_sin_eval.btn_evaluacion is None
    finally:
        dlg_sin_eval.close()

    dlg = DialogoLoginFolio(gestor=gestor, permitir_evaluacion=True)
    try:
        assert dlg.btn_evaluacion is not None
        assert dlg.btn_evaluacion.text() == "Continuar en modo evaluación local"
        assert dlg.edt_admin_pwd.echoMode() == QLineEdit.EchoMode.Password

        # Opción evaluación local no autentica usuario ni crea usuarios.json
        dlg.btn_evaluacion.click()
        assert dlg.modo_evaluacion() is True
        assert dlg.sesion_autenticada() is None
        assert not gestor.existe_configuracion()

        # Validación de error cuando contraseñas no coinciden
        dlg.edt_admin_usr.setText("admin.firma")
        dlg.edt_admin_nom.setText("Elena Vargas")
        dlg.edt_admin_pwd.setText(PWD_ADMIN)
        dlg.edt_admin_pwd2.setText("OtraClave2026!")
        assert dlg.intentar_inicializar() is False
        assert dlg.lbl_error_init.text() != ""
        assert dlg.sesion_autenticada() is None

        # Inicialización válida de Administrador + Preparador
        dlg.edt_admin_pwd2.setText(PWD_ADMIN)
        dlg.chk_crear_prep.setChecked(True)
        dlg.edt_prep_usr.setText("prep.nia")
        dlg.edt_prep_nom.setText("Carlos Mendoza")
        dlg.edt_prep_pwd.setText(PWD_PREP)
        dlg.edt_prep_pwd2.setText(PWD_PREP)
        dlg.chk_segregacion.setChecked(True)

        assert dlg.intentar_inicializar() is True
        sesion = dlg.sesion_autenticada()
        assert sesion is not None
        assert sesion.es_admin is True
        assert sesion.perfil == PERFIL_ADMIN
        assert sesion.usuario == "admin.firma"
        assert gestor.existe_configuracion() is True
        assert len(gestor.listar_usuarios()) == 2
        assert gestor.politicas()["segregacion_estricta"] is True
    finally:
        dlg.close()

    # Inicialización solo Administrador (sin Preparador opcional)
    gestor_solo = GestorUsuarios(tmp_path / "solo_admin")
    dlg_solo = DialogoLoginFolio(gestor=gestor_solo, permitir_evaluacion=False)
    try:
        dlg_solo.edt_admin_usr.setText("admin.solo")
        dlg_solo.edt_admin_nom.setText("Sofía Morales")
        dlg_solo.edt_admin_pwd.setText(PWD_ADMIN)
        dlg_solo.edt_admin_pwd2.setText(PWD_ADMIN)
        dlg_solo.chk_crear_prep.setChecked(False)
        assert not dlg_solo.edt_prep_usr.isEnabled()
        assert dlg_solo.intentar_inicializar() is True
        assert len(gestor_solo.listar_usuarios()) == 1
    finally:
        dlg_solo.close()


def test_login_preparador_exito_y_rechazo_en_modo_admin(qapp, tmp_path):
    gestor = _inicializar_firma_desde_ui(tmp_path)
    dlg = DialogoLoginFolio(gestor=gestor, permitir_evaluacion=True)
    try:
        dlg.show()
        qapp.processEvents()
        assert dlg.edt_contrasena.echoMode() == QLineEdit.EchoMode.Password
        dlg.chk_mostrar_pwd.setChecked(True)
        assert dlg.edt_contrasena.echoMode() == QLineEdit.EchoMode.Normal
        dlg.chk_mostrar_pwd.setChecked(False)

        # Preparador rechazado si selecciona modo Administrador
        dlg.seleccionar_modo(PERFIL_ADMIN)
        assert "gestión de usuarios" in dlg.lbl_desc_modo.text().lower()
        dlg.edt_usuario.setText("prep.nia")
        dlg.edt_contrasena.setText(PWD_PREP)
        assert dlg.intentar_login() is False
        assert dlg.sesion_autenticada() is None
        assert dlg.lbl_error.isVisible()
        assert dlg.lbl_error.text().strip() != ""

        # Preparador aceptado en modo Preparador
        dlg.seleccionar_modo(PERFIL_PREPARADOR)
        assert "paquetes nia" in dlg.lbl_desc_modo.text().lower()
        assert dlg.lbl_error.text() == ""
        assert dlg.intentar_login() is True
        sesion = dlg.sesion_autenticada()
        assert sesion is not None
        assert sesion.usuario == "prep.nia"
        assert sesion.perfil == PERFIL_PREPARADOR
        assert sesion.es_admin is False
    finally:
        dlg.close()


def test_login_admin_abre_panel_crea_revisor_cambia_politicas_y_rechaza_preparador(qapp, tmp_path):
    gestor = _inicializar_firma_desde_ui(tmp_path)

    # Preparador no puede abrir DialogoAdminSeguridad
    sesion_prep = gestor.autenticar("prep.nia", PWD_PREP, modo_acceso=PERFIL_PREPARADOR)
    with pytest.raises(ErrorSeguridad):
        DialogoAdminSeguridad(gestor, sesion_prep)

    # Login de Administrador desde UI
    dlg_login = DialogoLoginFolio(gestor=gestor)
    try:
        dlg_login.seleccionar_modo(PERFIL_ADMIN)
        dlg_login.edt_usuario.setText("admin.firma")
        dlg_login.edt_contrasena.setText(PWD_ADMIN)
        assert dlg_login.intentar_login() is True
        sesion_admin = dlg_login.sesion_autenticada()
        assert sesion_admin is not None and sesion_admin.es_admin
    finally:
        dlg_login.close()

    # Panel de administración
    panel = DialogoAdminSeguridad(gestor, sesion_admin)
    try:
        assert panel.tabs.count() == 3
        assert panel.mod_usuarios.rowCount() == 2
        assert panel.lbl_bit_accesos_estado.text() == "ÍNTEGRA"
        assert panel.mod_bitacora.rowCount() >= 2

        # Crear un Revisor
        panel.edt_nuevo_usr.setText("rev.nia")
        panel.edt_nuevo_nom.setText("Lucía Paredes")
        panel.cmb_nuevo_perfil.setCurrentText(PERFIL_REVISOR)
        panel.edt_nuevo_pwd.setText(PWD_REV)
        panel.btn_crear_usr.click()

        assert panel.mod_usuarios.rowCount() == 3
        usuarios = {u["usuario"]: u for u in gestor.listar_usuarios()}
        assert "rev.nia" in usuarios
        assert usuarios["rev.nia"]["perfil"] == PERFIL_REVISOR

        # Cambiar políticas de seguridad
        panel.chk_pol_segregacion.setChecked(True)
        panel.spn_pol_ventana.setValue(45)
        panel.spn_pol_intentos.setValue(4)
        panel.chk_pol_nube.setChecked(False)
        panel.btn_guardar_politicas.click()

        pol = gestor.politicas()
        assert pol["ventana_archivo_dias"] == 45
        assert pol["max_intentos"] == 4
        assert pol["alerta_nube"] is False
        assert panel.lbl_bit_accesos_estado.text() == "ÍNTEGRA"

        # Seleccionar el revisor y alternar estado + restablecer contraseña
        df_u = panel.mod_usuarios.dataframe()
        fila_rev = int(df_u.index[df_u["usuario"] == "rev.nia"][0])
        panel.tv_usuarios.selectRow(fila_rev)
        panel.btn_toggle_estado.click()
        with pytest.raises(ErrorSeguridad):
            gestor.autenticar("rev.nia", PWD_REV, modo_acceso=PERFIL_PREPARADOR)

        df_u = panel.mod_usuarios.dataframe()
        fila_rev = int(df_u.index[df_u["usuario"] == "rev.nia"][0])
        panel.tv_usuarios.selectRow(fila_rev)
        panel.btn_toggle_estado.click()

        df_u = panel.mod_usuarios.dataframe()
        fila_rev = int(df_u.index[df_u["usuario"] == "rev.nia"][0])
        panel.tv_usuarios.selectRow(fila_rev)
        panel.edt_reset_pwd.setText(PWD_NUEVA)
        panel.btn_reset_pwd.click()
        sesion_rev = gestor.autenticar("rev.nia", PWD_NUEVA, modo_acceso=PERFIL_PREPARADOR)
        assert sesion_rev.perfil == PERFIL_REVISOR

        # Alterar 1 línea de bitácora de accesos debe mostrarse como ALTERADA
        texto_bit = gestor.ruta_bitacora.read_text(encoding="utf-8")
        gestor.ruta_bitacora.write_text(texto_bit.replace("login_exitoso", "login_alterado", 1), encoding="utf-8")
        panel.refrescar_bitacora_accesos()
        assert panel.lbl_bit_accesos_estado.text() == "ALTERADA"
    finally:
        panel.close()


def test_dialogo_cambiar_contrasena(qapp, tmp_path):
    gestor = _inicializar_firma_desde_ui(tmp_path)
    sesion_prep = gestor.autenticar("prep.nia", PWD_PREP, modo_acceso=PERFIL_PREPARADOR)
    huella_original = sesion_prep.huella_clave

    dlg_pwd = DialogoCambiarContrasena(gestor, sesion_prep)
    try:
        # Contraseña actual incorrecta falla
        dlg_pwd.edt_actual.setText("Incorrecta2026!")
        dlg_pwd.edt_nueva.setText(PWD_NUEVA)
        dlg_pwd.edt_confirmacion.setText(PWD_NUEVA)
        assert dlg_pwd.intentar_cambiar() is False
        assert dlg_pwd.lbl_error.text() != ""

        # Cambio exitoso con contraseña actual correcta
        dlg_pwd.edt_actual.setText(PWD_PREP)
        assert dlg_pwd.intentar_cambiar() is True
    finally:
        dlg_pwd.close()

    with pytest.raises(ErrorSeguridad):
        gestor.autenticar("prep.nia", PWD_PREP, modo_acceso=PERFIL_PREPARADOR)

    sesion_nueva = gestor.autenticar("prep.nia", PWD_NUEVA, modo_acceso=PERFIL_PREPARADOR)
    assert sesion_nueva.huella_clave == huella_original


def test_identidad_ejecutiva_sin_marca_heredada_y_con_iconos_3d(qapp, tmp_path):
    gestor_vacio = GestorUsuarios(tmp_path / "vacio")
    dlg_init = DialogoLoginFolio(gestor=gestor_vacio)
    try:
        _verificar_identidad_dialogo(dlg_init)
    finally:
        dlg_init.close()

    gestor = _inicializar_firma_desde_ui(tmp_path / "activo")
    dlg_login = DialogoLoginFolio(gestor=gestor)
    try:
        _verificar_identidad_dialogo(dlg_login)
    finally:
        dlg_login.close()

    sesion_admin = gestor.autenticar("admin.firma", PWD_ADMIN, modo_acceso=PERFIL_ADMIN)
    panel = DialogoAdminSeguridad(gestor, sesion_admin)
    try:
        _verificar_identidad_dialogo(panel)
    finally:
        panel.close()

    dlg_pwd = DialogoCambiarContrasena(gestor, sesion_admin)
    try:
        _verificar_identidad_dialogo(dlg_pwd)
    finally:
        dlg_pwd.close()

    assert not (RAIZ / "seguridad" / "usuarios.json").exists()
