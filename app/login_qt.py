"""Pantalla de inicio de sesión dual, configuración inicial y administración de seguridad (PySide6).

Implementa las interfaces gráficas ejecutivas de Folio Auditor bajo estética clásica Win32:
- DialogoLoginFolio: configuración inicial en primer arranque y acceso dual Preparador/Auditor vs Administrador.
- DialogoAdminSeguridad: gestión de usuarios/roles, políticas de seguridad y bitácora SHA-256 de accesos.
- DialogoCambiarContrasena: cambio de contraseña conservando el par de claves Ed25519 del usuario.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.componentes_qt import ESTILO_CUADRA_QT, ModeloTablaPandas, icono_cuadra
from app.comun import LEMA_MARCA, NOMBRE_MARCA
from motor.seguridad import ErrorSeguridad
from motor.usuarios import (
    PERFIL_ADMIN,
    PERFIL_PREPARADOR,
    PERFILES_VALIDOS,
    GestorUsuarios,
    SesionAutenticada,
    validar_politica_contrasena,
)

_ESTILO_LOGIN_QT = (
    ESTILO_CUADRA_QT
    + """
QPushButton.BtnModoAcceso {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    border-radius: 0px;
    color: #111111;
    font-weight: 700;
    padding: 7px 12px;
    min-height: 28px;
}
QPushButton.BtnModoAcceso:hover {
    background-color: #E2DFD7;
    color: #000080;
}
QPushButton.BtnModoAcceso:checked {
    background-color: #000080;
    border-top: 2px solid #000033;
    border-left: 2px solid #000033;
    border-right: 1px solid #7EB4EA;
    border-bottom: 1px solid #7EB4EA;
    color: #FFFFFF;
}
#CardDescModo {
    background-color: #FFFFFF;
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    border-radius: 0px;
}
#LblDescModo {
    color: #111111;
    font-size: 8.5pt;
    background: transparent;
}
#LblErrorLogin, #LblErrorInit {
    color: #B91C1C;
    font-weight: 700;
    font-size: 8.6pt;
    background: transparent;
}
#LblEstadoOk {
    color: #107C41;
    font-weight: 700;
    font-size: 8.5pt;
    background: transparent;
}
#LblEstadoErr {
    color: #B91C1C;
    font-weight: 700;
    font-size: 8.5pt;
    background: transparent;
}
#LblBitEstadoOk {
    background-color: #107C41;
    border-top: 1px solid #064E3B;
    border-left: 1px solid #064E3B;
    border-right: 1px solid #86EFAC;
    border-bottom: 1px solid #86EFAC;
    color: #FFFFFF;
    font-size: 8pt;
    font-weight: 700;
    padding: 3px 10px;
}
#LblBitEstadoErr {
    background-color: #B91C1C;
    border-top: 1px solid #450A0A;
    border-left: 1px solid #450A0A;
    border-right: 1px solid #FCA5A5;
    border-bottom: 1px solid #FCA5A5;
    color: #FFFFFF;
    font-size: 8pt;
    font-weight: 700;
    padding: 3px 10px;
}
"""
)

_DESC_MODO_PREPARADOR = (
    "Preparador / Auditor: acceso a paquetes NIA, muestreo, conectores, copiloto, "
    "bitácora y firma de papeles según su rol (Preparador, Revisor, Socio)."
)
_DESC_MODO_ADMIN = (
    "Administrador: acceso al panel de gestión de usuarios, políticas de seguridad, "
    "desbloqueo/restablecimiento de cuentas y bitácora de accesos "
    "(sin auto-firmar auditorías por segregación)."
)


def _construir_banner_win32(
    titulo: str,
    subtitulo: str,
    insignia: str = "ACCESO LOCAL · SIN INTERNET",
) -> tuple[QFrame, QLabel]:
    """Construye la barra superior clásica Win32 con degradado azul e ícono 3D."""
    bar = QFrame()
    bar.setObjectName("AppBar")
    bar.setFixedHeight(64)

    hb = QHBoxLayout(bar)
    hb.setContentsMargins(12, 6, 12, 6)
    hb.setSpacing(10)

    lbl_logo = QLabel()
    lbl_logo.setPixmap(icono_cuadra("logo", 44).pixmap(44, 44))
    lbl_logo.setFixedSize(46, 46)
    lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hb.addWidget(lbl_logo)

    col = QVBoxLayout()
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(1)

    lbl_badge = QLabel(f"{NOMBRE_MARCA} · {LEMA_MARCA}")
    lbl_badge.setObjectName("BrandBadge")
    lbl_titulo = QLabel(titulo)
    lbl_titulo.setObjectName("WorkbookTitle")
    lbl_sub = QLabel(subtitulo)
    lbl_sub.setObjectName("WorkbookSubtitle")

    col.addWidget(lbl_badge)
    col.addWidget(lbl_titulo)
    col.addWidget(lbl_sub)
    hb.addLayout(col, 1)

    pill = QLabel(insignia)
    pill.setProperty("class", "PillInfo")
    hb.addWidget(pill, 0, Qt.AlignmentFlag.AlignVCenter)
    return bar, lbl_logo


def _estilo_tabla_base(tv: QTableView) -> None:
    """Configura una tabla de solo lectura estilo hoja de cálculo clásica."""
    tv.setAlternatingRowColors(True)
    tv.setSortingEnabled(True)
    tv.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tv.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tv.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tv.verticalHeader().setDefaultSectionSize(24)
    tv.verticalHeader().setVisible(False)
    tv.horizontalHeader().setStretchLastSection(True)


def _auto_ajustar_columnas(tv: QTableView, maximo: int = 260) -> None:
    """Ajusta los anchos de columna dentro de límites legibles."""
    tv.resizeColumnsToContents()
    hdr = tv.horizontalHeader()
    total = tv.model().columnCount() if tv.model() else 0
    for c in range(total):
        w = hdr.sectionSize(c)
        lim = maximo if c < total - 1 else max(maximo, 320)
        if w > lim:
            hdr.resizeSection(c, lim)
        elif w < 72:
            hdr.resizeSection(c, 76)


def _normalizar_modo_acceso(modo: str) -> str:
    """Normaliza la etiqueta de modo de acceso a 'Preparador' o 'Administrador'."""
    clave = (modo or "").strip().lower()
    if clave in ("administrador", "admin"):
        return PERFIL_ADMIN
    if clave in ("preparador", "preparador / auditor", "auditor", "revisor", "socio"):
        return PERFIL_PREPARADOR
    raise ErrorSeguridad(f"Modo de acceso no reconocido: {modo!r}")


def _formatear_datos_bitacora(datos: Any) -> str:
    """Serializa los datos de un evento de bitácora en texto compacto legible."""
    if not datos:
        return ""
    if isinstance(datos, dict):
        return ", ".join(f"{k}={v}" for k, v in datos.items())
    return json.dumps(datos, ensure_ascii=False, default=str)


class DialogoLoginFolio(QDialog):
    """Diálogo de configuración inicial y acceso dual (Preparador / Auditor vs Administrador)."""

    def __init__(
        self,
        gestor: GestorUsuarios | None = None,
        permitir_evaluacion: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.gestor = gestor if gestor is not None else GestorUsuarios()
        self.permitir_evaluacion = bool(permitir_evaluacion)
        self._sesion: SesionAutenticada | None = None
        self._modo_evaluacion: bool = False
        self._modo_actual: str = PERFIL_PREPARADOR
        self._es_primer_arranque: bool = not self.gestor.existe_configuracion()

        self.setWindowIcon(icono_cuadra("logo", 44))
        self.setStyleSheet(_ESTILO_LOGIN_QT)
        self.setModal(True)

        if self._es_primer_arranque:
            self._construir_primer_arranque()
        else:
            self._construir_login_operativo()

    def _construir_primer_arranque(self) -> None:
        self.setWindowTitle(f"{NOMBRE_MARCA} · Configuración Inicial de Seguridad")
        self.resize(590, 580)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner, self.lbl_logo = _construir_banner_win32(
            f"{NOMBRE_MARCA} · CONFIGURACIÓN INICIAL DE SEGURIDAD",
            "Primer arranque: registra el Administrador de seguridad y el Preparador inicial.",
        )
        lay.addWidget(banner)

        cuerpo = QWidget()
        vc = QVBoxLayout(cuerpo)
        vc.setContentsMargins(14, 12, 14, 14)
        vc.setSpacing(10)

        # Sección 1: Administrador obligatorio
        card_admin = QFrame()
        card_admin.setProperty("class", "PanelCard")
        va = QVBoxLayout(card_admin)
        va.setContentsMargins(10, 8, 10, 10)
        va.setSpacing(6)
        hdr_a = QLabel("1 · CUENTA ADMINISTRADOR (OBLIGATORIA)")
        hdr_a.setProperty("class", "SectionHdr")
        va.addWidget(hdr_a)

        fl_a = QFormLayout()
        fl_a.setHorizontalSpacing(12)
        fl_a.setVerticalSpacing(6)
        self.edt_admin_usr = QLineEdit()
        self.edt_admin_usr.setPlaceholderText("Ej. admin.firma")
        self.edt_admin_nom = QLineEdit()
        self.edt_admin_nom.setPlaceholderText("Nombre completo del Administrador")
        self.edt_admin_pwd = QLineEdit()
        self.edt_admin_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_admin_pwd.setPlaceholderText("Mínimo 10 caracteres, mayúscula, minúscula y dígito")
        self.edt_admin_pwd2 = QLineEdit()
        self.edt_admin_pwd2.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_admin_pwd2.setPlaceholderText("Repite la contraseña del Administrador")
        fl_a.addRow("Usuario Administrador:", self.edt_admin_usr)
        fl_a.addRow("Nombre completo:", self.edt_admin_nom)
        fl_a.addRow("Contraseña:", self.edt_admin_pwd)
        fl_a.addRow("Confirmar contraseña:", self.edt_admin_pwd2)
        va.addLayout(fl_a)
        vc.addWidget(card_admin)

        # Sección 2: Preparador inicial opcional
        card_prep = QFrame()
        card_prep.setProperty("class", "PanelCard")
        vp = QVBoxLayout(card_prep)
        vp.setContentsMargins(10, 8, 10, 10)
        vp.setSpacing(6)
        hdr_p = QLabel("2 · CUENTA PREPARADOR INICIAL (OPCIONAL)")
        hdr_p.setProperty("class", "SectionHdr")
        vp.addWidget(hdr_p)

        self.chk_crear_prep = QCheckBox("Crear cuenta Preparador inicial para operación de auditoría")
        self.chk_crear_prep.setChecked(True)
        vp.addWidget(self.chk_crear_prep)

        fl_p = QFormLayout()
        fl_p.setHorizontalSpacing(12)
        fl_p.setVerticalSpacing(6)
        self.edt_prep_usr = QLineEdit()
        self.edt_prep_usr.setPlaceholderText("Ej. preparador.nia")
        self.edt_prep_nom = QLineEdit()
        self.edt_prep_nom.setPlaceholderText("Nombre completo del Preparador")
        self.edt_prep_pwd = QLineEdit()
        self.edt_prep_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_prep_pwd.setPlaceholderText("Mínimo 10 caracteres, mayúscula, minúscula y dígito")
        self.edt_prep_pwd2 = QLineEdit()
        self.edt_prep_pwd2.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_prep_pwd2.setPlaceholderText("Repite la contraseña del Preparador")
        fl_p.addRow("Usuario Preparador:", self.edt_prep_usr)
        fl_p.addRow("Nombre completo:", self.edt_prep_nom)
        fl_p.addRow("Contraseña:", self.edt_prep_pwd)
        fl_p.addRow("Confirmar contraseña:", self.edt_prep_pwd2)
        vp.addLayout(fl_p)
        vc.addWidget(card_prep)

        self.chk_crear_prep.toggled.connect(self._alternar_campos_preparador)

        # Política de segregación NIA 220
        self.chk_segregacion = QCheckBox(
            "Exigir segregación estricta Preparador ≠ Revisor ≠ Socio (NIA 220)"
        )
        self.chk_segregacion.setChecked(True)
        vc.addWidget(self.chk_segregacion)

        self.lbl_error_init = QLabel("")
        self.lbl_error_init.setObjectName("LblErrorInit")
        self.lbl_error_init.setWordWrap(True)
        vc.addWidget(self.lbl_error_init)

        pie = QHBoxLayout()
        pie.setSpacing(8)
        if self.permitir_evaluacion:
            self.btn_evaluacion = QPushButton("Continuar en modo evaluación local")
            self.btn_evaluacion.clicked.connect(self._continuar_evaluacion)
            pie.addWidget(self.btn_evaluacion)
        else:
            self.btn_evaluacion = None
        pie.addStretch(1)
        self.btn_inicializar = QPushButton("Crear cuentas e iniciar como Administrador")
        self.btn_inicializar.setObjectName("BtnPrimary")
        self.btn_inicializar.setDefault(True)
        self.btn_inicializar.clicked.connect(self.intentar_inicializar)
        pie.addWidget(self.btn_inicializar)
        vc.addLayout(pie)

        lay.addWidget(cuerpo, 1)

    def _construir_login_operativo(self) -> None:
        self.setWindowTitle(f"{NOMBRE_MARCA} · Inicio de Sesión")
        self.resize(540, 445)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner, self.lbl_logo = _construir_banner_win32(
            NOMBRE_MARCA,
            LEMA_MARCA,
        )
        lay.addWidget(banner)

        cuerpo = QWidget()
        vc = QVBoxLayout(cuerpo)
        vc.setContentsMargins(14, 12, 14, 14)
        vc.setSpacing(10)

        # Selector visual de modo de acceso
        card_modo = QFrame()
        card_modo.setProperty("class", "PanelCard")
        vm = QVBoxLayout(card_modo)
        vm.setContentsMargins(10, 8, 10, 10)
        vm.setSpacing(8)

        hdr_m = QLabel("SELECCIONA EL MODO DE ACCESO")
        hdr_m.setProperty("class", "SectionHdr")
        vm.addWidget(hdr_m)

        fila_modos = QHBoxLayout()
        fila_modos.setSpacing(8)
        self._grupo_modo = QButtonGroup(self)
        self._grupo_modo.setExclusive(True)

        self.btn_modo_preparador = QPushButton("Preparador / Auditor")
        self.btn_modo_preparador.setCheckable(True)
        self.btn_modo_preparador.setProperty("class", "BtnModoAcceso")
        self.btn_modo_preparador.clicked.connect(lambda: self.seleccionar_modo(PERFIL_PREPARADOR))

        self.btn_modo_admin = QPushButton("Administrador")
        self.btn_modo_admin.setCheckable(True)
        self.btn_modo_admin.setProperty("class", "BtnModoAcceso")
        self.btn_modo_admin.clicked.connect(lambda: self.seleccionar_modo(PERFIL_ADMIN))

        self._grupo_modo.addButton(self.btn_modo_preparador)
        self._grupo_modo.addButton(self.btn_modo_admin)
        fila_modos.addWidget(self.btn_modo_preparador, 1)
        fila_modos.addWidget(self.btn_modo_admin, 1)
        vm.addLayout(fila_modos)

        desc_box = QFrame()
        desc_box.setObjectName("CardDescModo")
        vd = QVBoxLayout(desc_box)
        vd.setContentsMargins(8, 6, 8, 6)
        self.lbl_desc_modo = QLabel("")
        self.lbl_desc_modo.setObjectName("LblDescModo")
        self.lbl_desc_modo.setWordWrap(True)
        vd.addWidget(self.lbl_desc_modo)
        vm.addWidget(desc_box)
        vc.addWidget(card_modo)

        # Credenciales
        card_cred = QFrame()
        card_cred.setProperty("class", "PanelCard")
        vf = QVBoxLayout(card_cred)
        vf.setContentsMargins(10, 8, 10, 10)
        vf.setSpacing(6)

        hdr_c = QLabel("CREDENCIALES LOCALES")
        hdr_c.setProperty("class", "SectionHdr")
        vf.addWidget(hdr_c)

        fl = QFormLayout()
        fl.setHorizontalSpacing(12)
        fl.setVerticalSpacing(6)
        self.edt_usuario = QLineEdit()
        self.edt_usuario.setPlaceholderText("Nombre de usuario")
        self.edt_contrasena = QLineEdit()
        self.edt_contrasena.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_contrasena.setPlaceholderText("Contraseña")
        fl.addRow("Usuario:", self.edt_usuario)
        fl.addRow("Contraseña:", self.edt_contrasena)
        vf.addLayout(fl)

        self.chk_mostrar_pwd = QCheckBox("Mostrar contraseña")
        self.chk_mostrar_pwd.toggled.connect(self._alternar_visibilidad_pwd)
        vf.addWidget(self.chk_mostrar_pwd)
        vc.addWidget(card_cred)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("LblErrorLogin")
        self.lbl_error.setWordWrap(True)
        vc.addWidget(self.lbl_error)

        pie = QHBoxLayout()
        pie.addStretch(1)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_ingresar = QPushButton("Ingresar")
        self.btn_ingresar.setObjectName("BtnPrimary")
        self.btn_ingresar.setDefault(True)
        self.btn_ingresar.clicked.connect(self.intentar_login)
        pie.addWidget(self.btn_cancelar)
        pie.addWidget(self.btn_ingresar)
        vc.addLayout(pie)

        lay.addWidget(cuerpo, 1)
        self.seleccionar_modo(PERFIL_PREPARADOR)

    def _alternar_campos_preparador(self, habilitar: bool) -> None:
        for campo in (self.edt_prep_usr, self.edt_prep_nom, self.edt_prep_pwd, self.edt_prep_pwd2):
            campo.setEnabled(habilitar)

    def _alternar_visibilidad_pwd(self, visible: bool) -> None:
        modo = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        self.edt_contrasena.setEchoMode(modo)

    def _continuar_evaluacion(self) -> None:
        self._sesion = None
        self._modo_evaluacion = True
        self.accept()

    def modo_evaluacion(self) -> bool:
        """Indica si el usuario eligió continuar en modo evaluación local."""
        return self._modo_evaluacion

    def seleccionar_modo(self, modo: str) -> None:
        """Selecciona el modo de acceso ('Preparador' o 'Administrador') y actualiza la descripción."""
        modo_norm = _normalizar_modo_acceso(modo)
        self._modo_actual = modo_norm
        if hasattr(self, "btn_modo_preparador"):
            es_admin = modo_norm == PERFIL_ADMIN
            self.btn_modo_admin.setChecked(es_admin)
            self.btn_modo_preparador.setChecked(not es_admin)
            self.lbl_desc_modo.setText(_DESC_MODO_ADMIN if es_admin else _DESC_MODO_PREPARADOR)
            self.lbl_error.setText("")

    def intentar_inicializar(self) -> bool:
        """Valida cuentas iniciales, inicializa la firma, autentica como Administrador y acepta."""
        self.lbl_error_init.setText("")
        admin_usr = self.edt_admin_usr.text().strip()
        admin_nom = self.edt_admin_nom.text().strip()
        admin_pwd = self.edt_admin_pwd.text()
        admin_pwd2 = self.edt_admin_pwd2.text()

        try:
            if not admin_usr:
                raise ErrorSeguridad("Ingresa el usuario para la cuenta Administrador.")
            if not admin_nom:
                raise ErrorSeguridad("Ingresa el nombre completo del Administrador.")
            if admin_pwd != admin_pwd2:
                raise ErrorSeguridad("La contraseña del Administrador y su confirmación no coinciden.")
            validar_politica_contrasena(admin_pwd)

            preparador_datos: dict[str, str] | None = None
            if self.chk_crear_prep.isChecked():
                prep_usr = self.edt_prep_usr.text().strip()
                prep_nom = self.edt_prep_nom.text().strip()
                prep_pwd = self.edt_prep_pwd.text()
                prep_pwd2 = self.edt_prep_pwd2.text()
                if not prep_usr:
                    raise ErrorSeguridad("Ingresa el usuario para la cuenta Preparador inicial.")
                if not prep_nom:
                    raise ErrorSeguridad("Ingresa el nombre completo del Preparador inicial.")
                if prep_usr.lower() == admin_usr.lower():
                    raise ErrorSeguridad("El usuario Preparador debe ser distinto al Administrador.")
                if prep_pwd != prep_pwd2:
                    raise ErrorSeguridad("La contraseña del Preparador y su confirmación no coinciden.")
                validar_politica_contrasena(prep_pwd)
                preparador_datos = {
                    "usuario": prep_usr,
                    "nombre_completo": prep_nom,
                    "contrasena": prep_pwd,
                }

            self.gestor.inicializar_firma(
                admin_usr,
                admin_nom,
                admin_pwd,
                preparador=preparador_datos,
                segregacion_estricta=self.chk_segregacion.isChecked(),
            )
            sesion = self.gestor.autenticar(admin_usr, admin_pwd, modo_acceso=PERFIL_ADMIN)
        except (ErrorSeguridad, ValueError) as exc:
            self.lbl_error_init.setText(str(exc))
            return False

        self._sesion = sesion
        self._modo_evaluacion = False
        self.accept()
        return True

    def intentar_login(self) -> bool:
        """Autentica contra el gestor en el modo seleccionado; si tiene éxito guarda sesión y acepta."""
        self.lbl_error.setText("")
        usuario = self.edt_usuario.text().strip()
        contrasena = self.edt_contrasena.text()
        if not usuario or not contrasena:
            self.lbl_error.setText("Ingresa usuario y contraseña para iniciar sesión.")
            return False

        modo = PERFIL_ADMIN if self.btn_modo_admin.isChecked() else PERFIL_PREPARADOR
        try:
            sesion = self.gestor.autenticar(usuario, contrasena, modo_acceso=modo)
        except (ErrorSeguridad, ValueError) as exc:
            self.lbl_error.setText(str(exc))
            return False

        self._sesion = sesion
        self._modo_evaluacion = False
        self.accept()
        return True

    def sesion_autenticada(self) -> SesionAutenticada | None:
        """Devuelve la sesión autenticada resultante o None si no se completó el acceso."""
        return self._sesion


class DialogoAdminSeguridad(QDialog):
    """Panel de administración de usuarios, políticas de seguridad y bitácora de accesos."""

    def __init__(
        self,
        gestor: GestorUsuarios,
        sesion_admin: SesionAutenticada,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if sesion_admin is None or not getattr(sesion_admin, "es_admin", False):
            raise ErrorSeguridad("Solo un usuario con perfil Administrador puede acceder a este panel.")

        self.gestor = gestor
        self.sesion_admin = sesion_admin
        self._usuarios_cache: list[dict[str, Any]] = []

        self.setWindowTitle(f"{NOMBRE_MARCA} · Panel de Administración de Seguridad")
        self.setWindowIcon(icono_cuadra("logo", 44))
        self.setStyleSheet(_ESTILO_LOGIN_QT)
        self.setModal(True)
        self.resize(820, 600)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner, self.lbl_logo = _construir_banner_win32(
            f"{NOMBRE_MARCA} · ADMINISTRACIÓN DE SEGURIDAD",
            f"Sesión administrativa activa: {sesion_admin.etiqueta_ui}",
            insignia="CONTROL DE ACCESO RBAC",
        )
        lay.addWidget(banner)

        cuerpo = QWidget()
        vc = QVBoxLayout(cuerpo)
        vc.setContentsMargins(12, 10, 12, 12)
        vc.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._construir_tab_usuarios(), "Usuarios y Roles")
        self.tabs.addTab(self._construir_tab_politicas(), "Políticas de Seguridad")
        self.tabs.addTab(self._construir_tab_bitacora(), "Bitácora de Accesos")
        vc.addWidget(self.tabs, 1)

        pie = QHBoxLayout()
        pie.addStretch(1)
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_cerrar.clicked.connect(self.accept)
        pie.addWidget(self.btn_cerrar)
        vc.addLayout(pie)

        lay.addWidget(cuerpo, 1)

        self.refrescar_usuarios()
        self._cargar_politicas()
        self.refrescar_bitacora_accesos()

    def _construir_tab_usuarios(self) -> QWidget:
        tab = QWidget()
        vt = QVBoxLayout(tab)
        vt.setContentsMargins(10, 10, 10, 10)
        vt.setSpacing(8)

        self.tv_usuarios = QTableView()
        _estilo_tabla_base(self.tv_usuarios)
        self.mod_usuarios = ModeloTablaPandas()
        self.tv_usuarios.setModel(self.mod_usuarios)
        vt.addWidget(self.tv_usuarios, 1)

        # Acciones sobre el usuario seleccionado
        card_acc = QFrame()
        card_acc.setProperty("class", "PanelCard")
        ha = QHBoxLayout(card_acc)
        ha.setContentsMargins(10, 8, 10, 8)
        ha.setSpacing(8)
        self.btn_toggle_estado = QPushButton("Activar / Desactivar")
        self.btn_toggle_estado.clicked.connect(self.alternar_estado_seleccionado)
        self.edt_reset_pwd = QLineEdit()
        self.edt_reset_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_reset_pwd.setPlaceholderText("Nueva contraseña para el usuario seleccionado")
        self.btn_reset_pwd = QPushButton("Restablecer contraseña")
        self.btn_reset_pwd.clicked.connect(self.restablecer_contrasena_seleccionado)
        ha.addWidget(self.btn_toggle_estado)
        ha.addWidget(self.edt_reset_pwd, 1)
        ha.addWidget(self.btn_reset_pwd)
        vt.addWidget(card_acc)

        # Formulario de creación de usuario
        card_nuevo = QFrame()
        card_nuevo.setProperty("class", "PanelCard")
        vn = QVBoxLayout(card_nuevo)
        vn.setContentsMargins(10, 8, 10, 10)
        vn.setSpacing(6)
        hdr = QLabel("CREAR NUEVO USUARIO")
        hdr.setProperty("class", "SectionHdr")
        vn.addWidget(hdr)

        fl = QFormLayout()
        fl.setHorizontalSpacing(12)
        fl.setVerticalSpacing(6)
        self.edt_nuevo_usr = QLineEdit()
        self.edt_nuevo_usr.setPlaceholderText("Ej. revisor.nia")
        self.edt_nuevo_nom = QLineEdit()
        self.edt_nuevo_nom.setPlaceholderText("Nombre completo")
        self.cmb_nuevo_perfil = QComboBox()
        self.cmb_nuevo_perfil.addItems(list(PERFILES_VALIDOS))
        if PERFIL_PREPARADOR in PERFILES_VALIDOS:
            self.cmb_nuevo_perfil.setCurrentText(PERFIL_PREPARADOR)
        self.edt_nuevo_pwd = QLineEdit()
        self.edt_nuevo_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_nuevo_pwd.setPlaceholderText("Mínimo 10 caracteres, mayúscula, minúscula y dígito")
        fl.addRow("Usuario:", self.edt_nuevo_usr)
        fl.addRow("Nombre completo:", self.edt_nuevo_nom)
        fl.addRow("Perfil / Rol:", self.cmb_nuevo_perfil)
        fl.addRow("Contraseña inicial:", self.edt_nuevo_pwd)
        vn.addLayout(fl)

        fila_btn = QHBoxLayout()
        self.lbl_estado_usuarios = QLabel("")
        self.lbl_estado_usuarios.setObjectName("LblEstadoOk")
        self.lbl_estado_usuarios.setWordWrap(True)
        self.btn_crear_usr = QPushButton("Crear usuario")
        self.btn_crear_usr.setObjectName("BtnPrimary")
        self.btn_crear_usr.clicked.connect(self.crear_usuario_desde_formulario)
        fila_btn.addWidget(self.lbl_estado_usuarios, 1)
        fila_btn.addWidget(self.btn_crear_usr)
        vn.addLayout(fila_btn)

        vt.addWidget(card_nuevo)
        return tab

    def _construir_tab_politicas(self) -> QWidget:
        tab = QWidget()
        vp = QVBoxLayout(tab)
        vp.setContentsMargins(10, 10, 10, 10)
        vp.setSpacing(10)

        card = QFrame()
        card.setProperty("class", "PanelCard")
        vc = QVBoxLayout(card)
        vc.setContentsMargins(12, 10, 12, 12)
        vc.setSpacing(8)

        hdr = QLabel("POLÍTICAS DE SEGURIDAD Y ARCHIVO NIA 220 / 230")
        hdr.setProperty("class", "SectionHdr")
        vc.addWidget(hdr)

        self.chk_pol_segregacion = QCheckBox(
            "Exigir segregación estricta Preparador ≠ Revisor ≠ Socio (NIA 220)"
        )
        vc.addWidget(self.chk_pol_segregacion)

        fl = QFormLayout()
        fl.setHorizontalSpacing(14)
        fl.setVerticalSpacing(8)
        self.spn_pol_ventana = QSpinBox()
        self.spn_pol_ventana.setRange(1, 3650)
        self.spn_pol_ventana.setSuffix(" días")
        self.spn_pol_intentos = QSpinBox()
        self.spn_pol_intentos.setRange(1, 50)
        self.spn_pol_intentos.setSuffix(" intentos")
        fl.addRow("Ventana de archivo definitivo (NIA 230):", self.spn_pol_ventana)
        fl.addRow("Máximo de intentos fallidos antes de bloqueo:", self.spn_pol_intentos)
        vc.addLayout(fl)

        self.chk_pol_nube = QCheckBox(
            "Alertar si la carpeta de trabajo reside en sincronización en nube (OneDrive / Dropbox)"
        )
        vc.addWidget(self.chk_pol_nube)

        pie = QHBoxLayout()
        self.lbl_estado_politicas = QLabel("")
        self.lbl_estado_politicas.setObjectName("LblEstadoOk")
        self.lbl_estado_politicas.setWordWrap(True)
        self.btn_guardar_politicas = QPushButton("Guardar políticas")
        self.btn_guardar_politicas.setObjectName("BtnPrimary")
        self.btn_guardar_politicas.clicked.connect(self.guardar_politicas)
        pie.addWidget(self.lbl_estado_politicas, 1)
        pie.addWidget(self.btn_guardar_politicas)
        vc.addLayout(pie)

        vp.addWidget(card)
        vp.addStretch(1)
        return tab

    def _construir_tab_bitacora(self) -> QWidget:
        tab = QWidget()
        vb = QVBoxLayout(tab)
        vb.setContentsMargins(10, 10, 10, 10)
        vb.setSpacing(8)

        cab = QHBoxLayout()
        cab.setSpacing(8)
        cab.addWidget(QLabel("Estado de integridad SHA-256:"))
        self.lbl_bit_accesos_estado = QLabel("ÍNTEGRA")
        self.lbl_bit_accesos_estado.setObjectName("LblBitEstadoOk")
        cab.addWidget(self.lbl_bit_accesos_estado)
        cab.addStretch(1)
        self.btn_refrescar_bitacora = QPushButton("Actualizar bitácora")
        self.btn_refrescar_bitacora.clicked.connect(self.refrescar_bitacora_accesos)
        cab.addWidget(self.btn_refrescar_bitacora)
        vb.addLayout(cab)

        self.tv_bitacora = QTableView()
        _estilo_tabla_base(self.tv_bitacora)
        self.mod_bitacora = ModeloTablaPandas()
        self.tv_bitacora.setModel(self.mod_bitacora)
        vb.addWidget(self.tv_bitacora, 1)
        return tab

    def _fijar_estado_etiqueta(self, lbl: QLabel, mensaje: str, es_error: bool = False) -> None:
        lbl.setObjectName("LblEstadoErr" if es_error else "LblEstadoOk")
        lbl.style().unpolish(lbl)
        lbl.style().polish(lbl)
        lbl.setText(mensaje)

    def _usuario_seleccionado(self) -> dict[str, Any] | None:
        idx = self.tv_usuarios.currentIndex()
        df = self.mod_usuarios.dataframe()
        if not idx.isValid() or df.empty or idx.row() >= len(df):
            return None
        usr_id = str(df.iloc[idx.row()]["usuario"])
        for u in self._usuarios_cache:
            if str(u.get("usuario", "")) == usr_id:
                return u
        return None

    def refrescar_usuarios(self) -> None:
        """Recarga la tabla de usuarios registrados desde el gestor."""
        self._usuarios_cache = list(self.gestor.listar_usuarios())
        filas = []
        for u in self._usuarios_cache:
            activo = bool(u.get("activo", True))
            estado = "Activo" if activo else "Inactivo"
            if u.get("bloqueado_hasta_utc"):
                estado = f"{estado} (Bloqueado)"
            huella = str(u.get("huella_clave") or "")
            filas.append(
                {
                    "usuario": u.get("usuario", ""),
                    "nombre_completo": u.get("nombre_completo", ""),
                    "perfil": u.get("perfil", ""),
                    "rol_auditoria": u.get("rol_auditoria") or "—",
                    "estado": estado,
                    "huella_clave": huella,
                    "intentos_fallidos": int(u.get("intentos_fallidos", 0) or 0),
                }
            )
        cols = [
            "usuario",
            "nombre_completo",
            "perfil",
            "rol_auditoria",
            "estado",
            "huella_clave",
            "intentos_fallidos",
        ]
        df = pd.DataFrame(filas, columns=cols)
        nombres = {
            "usuario": "Usuario",
            "nombre_completo": "Nombre completo",
            "perfil": "Perfil",
            "rol_auditoria": "Rol auditoría",
            "estado": "Estado",
            "huella_clave": "Huella Ed25519",
            "intentos_fallidos": "Intentos fallidos",
        }
        self.mod_usuarios.actualizar_df(df, nombres)
        _auto_ajustar_columnas(self.tv_usuarios)
        if len(df) > 0:
            self.tv_usuarios.selectRow(0)

    def _cargar_politicas(self) -> None:
        pol = self.gestor.politicas()
        self.chk_pol_segregacion.setChecked(bool(pol.get("segregacion_estricta", True)))
        self.spn_pol_ventana.setValue(int(pol.get("ventana_archivo_dias", 60)))
        self.spn_pol_intentos.setValue(int(pol.get("max_intentos", 5)))
        self.chk_pol_nube.setChecked(bool(pol.get("alerta_nube", True)))

    def refrescar_bitacora_accesos(self) -> None:
        """Recarga la bitácora de accesos y verifica su integridad SHA-256."""
        eventos, integra = self.gestor.leer_bitacora_accesos()
        self.lbl_bit_accesos_estado.setText("ÍNTEGRA" if integra else "ALTERADA")
        self.lbl_bit_accesos_estado.setObjectName("LblBitEstadoOk" if integra else "LblBitEstadoErr")
        self.lbl_bit_accesos_estado.style().unpolish(self.lbl_bit_accesos_estado)
        self.lbl_bit_accesos_estado.style().polish(self.lbl_bit_accesos_estado)

        filas = [
            {
                "fecha_hora_utc": ev.get("fecha_hora_utc", ""),
                "evento": ev.get("evento", ""),
                "usuario": ev.get("usuario", ""),
                "detalle": _formatear_datos_bitacora(ev.get("datos")),
                "hash": str(ev.get("hash", ""))[:16],
            }
            for ev in reversed(eventos)
        ]
        df = pd.DataFrame(filas, columns=["fecha_hora_utc", "evento", "usuario", "detalle", "hash"])
        nombres = {
            "fecha_hora_utc": "Fecha UTC",
            "evento": "Evento",
            "usuario": "Actor",
            "detalle": "Detalle",
            "hash": "Hash SHA-256",
        }
        self.mod_bitacora.actualizar_df(df, nombres)
        _auto_ajustar_columnas(self.tv_bitacora)

    def crear_usuario_desde_formulario(self) -> bool:
        """Crea un usuario nuevo usando los campos del formulario de administración."""
        usuario = self.edt_nuevo_usr.text().strip()
        nombre = self.edt_nuevo_nom.text().strip()
        perfil = self.cmb_nuevo_perfil.currentText().strip()
        contrasena = self.edt_nuevo_pwd.text()

        try:
            self.gestor.crear_usuario(
                self.sesion_admin,
                usuario=usuario,
                nombre_completo=nombre,
                contrasena=contrasena,
                perfil=perfil,
            )
        except (ErrorSeguridad, ValueError) as exc:
            self._fijar_estado_etiqueta(self.lbl_estado_usuarios, str(exc), es_error=True)
            return False

        self.edt_nuevo_usr.clear()
        self.edt_nuevo_nom.clear()
        self.edt_nuevo_pwd.clear()
        self.refrescar_usuarios()
        self.refrescar_bitacora_accesos()
        self._fijar_estado_etiqueta(
            self.lbl_estado_usuarios,
            f"Usuario '{usuario}' ({perfil}) creado correctamente.",
            es_error=False,
        )
        return True

    def alternar_estado_seleccionado(self) -> bool:
        """Activa o desactiva el usuario seleccionado en la tabla."""
        sel = self._usuario_seleccionado()
        if sel is None:
            self._fijar_estado_etiqueta(
                self.lbl_estado_usuarios,
                "Selecciona un usuario de la tabla para cambiar su estado.",
                es_error=True,
            )
            return False

        usr = str(sel["usuario"])
        nuevo_estado = not bool(sel.get("activo", True))
        try:
            self.gestor.cambiar_estado_usuario(self.sesion_admin, usr, nuevo_estado)
        except (ErrorSeguridad, ValueError) as exc:
            self._fijar_estado_etiqueta(self.lbl_estado_usuarios, str(exc), es_error=True)
            return False

        self.refrescar_usuarios()
        self.refrescar_bitacora_accesos()
        estado_txt = "activado" if nuevo_estado else "desactivado"
        self._fijar_estado_etiqueta(
            self.lbl_estado_usuarios,
            f"Usuario '{usr}' {estado_txt}.",
            es_error=False,
        )
        return True

    def restablecer_contrasena_seleccionado(self) -> bool:
        """Restablece la contraseña del usuario seleccionado y rota su par de claves Ed25519."""
        sel = self._usuario_seleccionado()
        if sel is None:
            self._fijar_estado_etiqueta(
                self.lbl_estado_usuarios,
                "Selecciona un usuario de la tabla para restablecer su contraseña.",
                es_error=True,
            )
            return False

        nueva = self.edt_reset_pwd.text()
        if not nueva:
            self._fijar_estado_etiqueta(
                self.lbl_estado_usuarios,
                "Ingresa la nueva contraseña antes de restablecer.",
                es_error=True,
            )
            return False

        usr = str(sel["usuario"])
        try:
            self.gestor.restablecer_contrasena_admin(self.sesion_admin, usr, nueva)
        except (ErrorSeguridad, ValueError) as exc:
            self._fijar_estado_etiqueta(self.lbl_estado_usuarios, str(exc), es_error=True)
            return False

        self.edt_reset_pwd.clear()
        self.refrescar_usuarios()
        self.refrescar_bitacora_accesos()
        self._fijar_estado_etiqueta(
            self.lbl_estado_usuarios,
            f"Contraseña restablecida y llave Ed25519 rotada para '{usr}'.",
            es_error=False,
        )
        return True

    def guardar_politicas(self) -> bool:
        """Persiste las políticas de seguridad editadas en la pestaña correspondiente."""
        try:
            self.gestor.actualizar_politicas(
                self.sesion_admin,
                segregacion_estricta=self.chk_pol_segregacion.isChecked(),
                ventana_archivo_dias=self.spn_pol_ventana.value(),
                max_intentos=self.spn_pol_intentos.value(),
                alerta_nube=self.chk_pol_nube.isChecked(),
            )
        except (ErrorSeguridad, ValueError) as exc:
            self._fijar_estado_etiqueta(self.lbl_estado_politicas, str(exc), es_error=True)
            return False

        self.refrescar_bitacora_accesos()
        self._fijar_estado_etiqueta(
            self.lbl_estado_politicas,
            "Políticas de seguridad guardadas correctamente.",
            es_error=False,
        )
        return True


class DialogoCambiarContrasena(QDialog):
    """Diálogo para que el usuario autenticado cambie su propia contraseña."""

    def __init__(
        self,
        gestor: GestorUsuarios,
        sesion: SesionAutenticada,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if sesion is None:
            raise ErrorSeguridad("Se requiere una sesión autenticada para cambiar la contraseña.")

        self.gestor = gestor
        self.sesion = sesion
        self._cambiada = False

        self.setWindowTitle(f"{NOMBRE_MARCA} · Cambiar Contraseña")
        self.setWindowIcon(icono_cuadra("logo", 44))
        self.setStyleSheet(_ESTILO_LOGIN_QT)
        self.setModal(True)
        self.resize(490, 340)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner, self.lbl_logo = _construir_banner_win32(
            f"{NOMBRE_MARCA} · CAMBIO DE CONTRASEÑA",
            f"Usuario activo: {sesion.etiqueta_ui}",
            insignia="LLAVE ED25519 PROTEGIDA",
        )
        lay.addWidget(banner)

        cuerpo = QWidget()
        vc = QVBoxLayout(cuerpo)
        vc.setContentsMargins(14, 12, 14, 14)
        vc.setSpacing(10)

        card = QFrame()
        card.setProperty("class", "PanelCard")
        vf = QVBoxLayout(card)
        vf.setContentsMargins(10, 8, 10, 10)
        vf.setSpacing(6)

        hdr = QLabel("ACTUALIZACIÓN DE CREDENCIALES")
        hdr.setProperty("class", "SectionHdr")
        vf.addWidget(hdr)

        fl = QFormLayout()
        fl.setHorizontalSpacing(12)
        fl.setVerticalSpacing(6)
        self.edt_actual = QLineEdit()
        self.edt_actual.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_nueva = QLineEdit()
        self.edt_nueva.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_nueva.setPlaceholderText("Mínimo 10 caracteres, mayúscula, minúscula y dígito")
        self.edt_confirmacion = QLineEdit()
        self.edt_confirmacion.setEchoMode(QLineEdit.EchoMode.Password)
        fl.addRow("Contraseña actual:", self.edt_actual)
        fl.addRow("Nueva contraseña:", self.edt_nueva)
        fl.addRow("Confirmar nueva contraseña:", self.edt_confirmacion)
        vf.addLayout(fl)

        self.chk_mostrar_pwd = QCheckBox("Mostrar contraseñas")
        self.chk_mostrar_pwd.toggled.connect(self._alternar_visibilidad)
        vf.addWidget(self.chk_mostrar_pwd)
        vc.addWidget(card)

        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("LblErrorLogin")
        self.lbl_error.setWordWrap(True)
        vc.addWidget(self.lbl_error)

        pie = QHBoxLayout()
        pie.addStretch(1)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_guardar = QPushButton("Actualizar contraseña")
        self.btn_guardar.setObjectName("BtnPrimary")
        self.btn_guardar.setDefault(True)
        self.btn_guardar.clicked.connect(self.intentar_cambiar)
        pie.addWidget(self.btn_cancelar)
        pie.addWidget(self.btn_guardar)
        vc.addLayout(pie)

        lay.addWidget(cuerpo, 1)

    def _alternar_visibilidad(self, visible: bool) -> None:
        modo = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        for edt in (self.edt_actual, self.edt_nueva, self.edt_confirmacion):
            edt.setEchoMode(modo)

    def intentar_cambiar(self) -> bool:
        """Valida las contraseñas y actualiza la credencial del usuario activo."""
        self.lbl_error.setText("")
        actual = self.edt_actual.text()
        nueva = self.edt_nueva.text()
        confirmacion = self.edt_confirmacion.text()

        try:
            if not actual:
                raise ErrorSeguridad("Ingresa tu contraseña actual.")
            if nueva != confirmacion:
                raise ErrorSeguridad("La nueva contraseña y su confirmación no coinciden.")
            validar_politica_contrasena(nueva)
            self.gestor.cambiar_contrasena(self.sesion.usuario, actual, nueva)
        except (ErrorSeguridad, ValueError) as exc:
            self.lbl_error.setText(str(exc))
            return False

        self._cambiada = True
        self.accept()
        return True
