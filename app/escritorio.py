"""Programa nativo de escritorio (PySide6) con Cinta de Opciones estilo Excel.

Corre 100 % sin internet en Windows, lee archivos locales de cualquier tamaño
directamente desde disco sin copiarlos y ejecuta el motor determinista DuckDB.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path
import traceback
from typing import Any

import pandas as pd
from PySide6.QtCore import QDate, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableView,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if not getattr(sys, "frozen", False):
    _RAIZ_LOCAL = str(Path(__file__).resolve().parents[1])
    if _RAIZ_LOCAL not in sys.path:
        sys.path.insert(0, _RAIZ_LOCAL)

from motor.rutas import raiz_recursos, raiz_trabajo  # noqa: E402

RAIZ = raiz_trabajo()
RAIZ_RECURSOS = raiz_recursos()
if str(RAIZ_RECURSOS) not in sys.path:
    sys.path.insert(0, str(RAIZ_RECURSOS))

from app.componentes_qt import (  # noqa: E402
    ESTILO_CUADRA_QT,
    DelegadoBarraPuntaje,
    ModeloTablaPandas,
    TarjetaKPI,
    icono_cuadra,
)
from app.comun import (  # noqa: E402
    EXTENSIONES_SOPORTADAS,
    FORMATOS_FECHA,
    HERRAMIENTAS,
    LEMA_MARCA,
    NOMBRE_MARCA,
    SEPARADORES_DECIMALES,
    calcular_periodo_inicio,
    cargar_dataframe_muestreo,
    constancia_tiempo_real,
    filas_crudas,
    formatear_fechas_df,
    formatear_periodo_auditado,
    formatear_tamano,
    formula_contextual,
    hojas_excel,
    pesos_defecto_puntaje,
    vista_previa,
)
from app.login_qt import DialogoAdminSeguridad, DialogoCambiarContrasena, DialogoLoginFolio  # noqa: E402
from conectores.catalogo import detectar_perfil, perfiles_disponibles, proponer_opciones_perfil  # noqa: E402
from conectores.sql_fuente import es_uri_sql, leer_conexion_sql, listar_tablas_archivo_sql  # noqa: E402
from ia.copiloto import (  # noqa: E402
    CONSULTAS_SUGERIDAS,
    PropuestaCopiloto,
    ejecutar_propuesta_aprobada,
    preparar_conexion_copiloto,
    proponer_consulta_sql,
)
from motor.bitacora import Bitacora, _usuario_actual  # noqa: E402
from motor.usuarios import texto_estado_sello, verificar_sello_anclado  # noqa: E402
from motor.diagnostico import diagnostico_a_dataframe  # noqa: E402
from motor.ejecutor import CRITERIOS_ASIENTO, NOMBRES_CRITERIOS  # noqa: E402
from motor.exportador import detalle_resultado  # noqa: E402
from motor.importador import EXTENSIONES_EXCEL, EXTENSIONES_SQL, EXTENSIONES_TEXTO, _parece_sap_alv, detectar_codificacion  # noqa: E402
from motor.muestreo import ErrorMuestreo, evaluar_mus, seleccionar_mus  # noqa: E402
from motor.portafolio import guardar_encargo_yaml, listar_corridas_recientes, listar_encargos, resumen_corrida_carpeta  # noqa: E402
from motor.privacidad import (  # noqa: E402
    cifrar_carpeta_corrida,
    descifrar_carpeta_corrida,
    detectar_carpeta_sincronizada,
    exportar_diagnostico_anonimizado,
)
from motor.revision import (  # noqa: E402
    ESTADOS_REVISION,
    ROLES_FIRMA,
    cargar_revisiones,
    estado_archivo_nia230,
    firmar_papel_trabajo,
    reabrir_papel_trabajo,
    registrar_revision_prueba,
)
from motor.seguridad import ErrorSeguridad  # noqa: E402
from motor.servicio import Corrida, actualizar_cedula_corrida, ejecutar_encargo, paquetes_disponibles  # noqa: E402
from motor.sintetico import generar, generar_diario_asientos, generar_estado_cuenta_bancos, generar_facturas_fe  # noqa: E402
from motor.sugerencias import detectar_fila_encabezado, normalizar, sugerir_mapeo  # noqa: E402
from motor.usuarios import GestorUsuarios, SesionAutenticada  # noqa: E402


def _filtro_archivos_dialogo() -> str:
    exts = " ".join(f"*.{e}" for e in EXTENSIONES_SOPORTADAS)
    return f"Fuentes de auditoría ({exts});;Todos los archivos (*.*)"


def _estilo_tabla_base(tv: QTableView) -> None:
    tv.setAlternatingRowColors(True)
    tv.setSortingEnabled(True)
    tv.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tv.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tv.verticalHeader().setDefaultSectionSize(24)
    tv.verticalHeader().setVisible(False)
    tv.horizontalHeader().setStretchLastSection(True)


def _auto_ajustar_columnas(tv: QTableView, maximo: int = 280) -> None:
    tv.resizeColumnsToContents()
    hdr = tv.horizontalHeader()
    total = tv.model().columnCount() if tv.model() else 0
    for c in range(total):
        w = hdr.sectionSize(c)
        es_ultima = c == total - 1
        lim = maximo if not es_ultima else max(maximo, 360)
        if w > lim:
            hdr.resizeSection(c, lim)
        elif w < 72:
            hdr.resizeSection(c, 78)


def _analizar_fuente_inicial(
    origen: Path | str,
    definicion: dict,
    perfiles: dict[str, dict],
    tabla_sql: str | None = None,
    consulta_sql: str | None = None,
) -> tuple[pd.DataFrame, dict, list[str]]:
    """Previsualiza 20 filas y propone ERP + mapeo automático sin cargar el archivo completo."""
    requeridas = list(definicion.get("columnas_requeridas") or [])
    extra: dict[str, Any] = {
        "hoja": None,
        "saltar_filas": None,
        "formato_fecha": None,
        "separador_decimal": ".",
        "tabla_origen": tabla_sql,
        "consulta_sql": consulta_sql,
    }

    if isinstance(origen, str) and es_uri_sql(origen):
        previa, _ = leer_conexion_sql(origen, tabla_origen=tabla_sql, consulta_sql=consulta_sql, limite=20)
    else:
        ruta = Path(origen)
        ext = ruta.suffix.lower()
        if ext in EXTENSIONES_SQL:
            if not tabla_sql and not consulta_sql:
                tablas = listar_tablas_archivo_sql(ruta)
                tabla_sql = tablas[0] if tablas else None
                extra["tabla_origen"] = tabla_sql
            previa = vista_previa(ruta, tabla_sql=tabla_sql, consulta_sql=consulta_sql)
        elif ext in EXTENSIONES_EXCEL or ext in EXTENSIONES_TEXTO:
            hojas = hojas_excel(ruta)
            hoja = hojas[-1] if hojas else None
            extra["hoja"] = hoja
            saltar = 0
            if not (ext in EXTENSIONES_TEXTO and _parece_sap_alv(ruta, detectar_codificacion(ruta, max_bytes=262144), 0)):
                saltar = detectar_fila_encabezado(filas_crudas(ruta, hoja), requeridas)
            extra["saltar_filas"] = saltar or None
            previa = vista_previa(ruta, hoja=hoja, saltar=saltar)
        else:
            previa = vista_previa(ruta)

    columnas = [str(c) for c in previa.columns]
    perfil_auto, _ = detectar_perfil(columnas)
    prop = proponer_opciones_perfil(perfil_auto, columnas, requeridas)

    dc = prop["debito_credito"]
    ind = prop["indicador_dc"] if not dc else None
    pedir = [r for r in requeridas if not (dc and r == "monto")]
    sugerido = dict(prop["mapeo_std_a_col"])
    if "monto" in pedir and sugerido.get("monto") is None:
        sinonimos = (perfil_auto or {}).get("aliases")
        sugerido["monto"] = sugerir_mapeo(columnas, ["monto"], sinonimos_extra=sinonimos).get("monto")

    mapeo: dict[str, str] = {}
    faltan: list[str] = []
    for req in pedir:
        col_orig = sugerido.get(req)
        if col_orig in columnas:
            if col_orig != req:
                mapeo[col_orig] = req
        else:
            faltan.append(req)

    generar_linea = bool(prop["generar_linea"]) if "linea" in faltan else False
    if generar_linea:
        faltan.remove("linea")

    usuario_def = None
    if "usuario" in faltan and prop["usuario_por_defecto"]:
        usuario_def = prop["usuario_por_defecto"]
        faltan.remove("usuario")

    opciones = {
        **extra,
        "mapeo": mapeo,
        "debito_credito": dc,
        "indicador_dc": ind,
        "generar_linea": generar_linea or None,
        "usuario_por_defecto": usuario_def,
        "perfil_erp": perfil_auto["id"] if perfil_auto else None,
        "_columnas_detectadas": columnas,
        "_faltantes": faltan,
        "_total_req": len(pedir),
        "_confirmado_ui": True,
    }
    return previa, opciones, faltan


class TrabajadorEjecucion(QThread):
    """Ejecuta ejecutar_encargo en segundo plano para mantener fluida la ventana de escritorio."""

    completado = Signal(object)
    fallo = Signal(str)

    def __init__(self, paquete_id: str, archivos: dict, encargo: dict, opciones: dict, parent=None) -> None:
        super().__init__(parent)
        self.paquete_id = paquete_id
        self.archivos = archivos
        self.encargo = encargo
        self.opciones = opciones

    def run(self) -> None:
        try:
            corrida = ejecutar_encargo(self.paquete_id, self.archivos, self.encargo, opciones=self.opciones)
            self.completado.emit(corrida)
        except Exception as exc:  # noqa: BLE001
            self.fallo.emit(str(exc))


class DialogoPesosRiesgo(QDialog):
    """Diálogo modal para ajustar los 10 pesos de riesgo y umbrales de Ficha 11."""

    def __init__(
        self,
        pesos_defecto: dict[str, int],
        pesos_actuales: dict[str, int],
        umbral_alto: int,
        umbral_medio: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pesos del puntaje de riesgo (Ficha 11)")
        self.setWindowIcon(icono_cuadra("asientos-nia240", 28))
        self.resize(560, 440)
        self._pesos_def = dict(pesos_defecto)
        self._spins: dict[str, QSpinBox] = {}

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        info = QLabel("Ajusta la ponderación por criterio o los umbrales Alto / Medio aplicados al diario:")
        info.setWordWrap(True)
        lay.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for idx, (clave, val_def) in enumerate(pesos_defecto.items()):
            lbl = QLabel(NOMBRES_CRITERIOS.get(clave, clave))
            sp = QSpinBox()
            sp.setRange(0, 100)
            sp.setValue(int(pesos_actuales.get(clave, val_def)))
            self._spins[clave] = sp
            fila, col = divmod(idx, 2)
            grid.addWidget(lbl, fila, col * 2)
            grid.addWidget(sp, fila, col * 2 + 1)
        lay.addLayout(grid)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        umb = QHBoxLayout()
        umb.addWidget(QLabel("Umbral nivel alto ≥"))
        self.sp_alto = QSpinBox()
        self.sp_alto.setRange(1, 500)
        self.sp_alto.setValue(umbral_alto)
        umb.addWidget(self.sp_alto)
        umb.addSpacing(20)
        umb.addWidget(QLabel("Umbral nivel medio ≥"))
        self.sp_medio = QSpinBox()
        self.sp_medio.setRange(1, 500)
        self.sp_medio.setValue(umbral_medio)
        umb.addWidget(self.sp_medio)
        lay.addLayout(umb)

        pie = QHBoxLayout()
        btn_reset = QPushButton("Restaurar por defecto")
        btn_reset.clicked.connect(self._restaurar)
        pie.addWidget(btn_reset)
        pie.addStretch(1)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        pie.addWidget(botones)
        lay.addLayout(pie)

    def _restaurar(self) -> None:
        for k, v in self._pesos_def.items():
            self._spins[k].setValue(int(v))
        self.sp_alto.setValue(25)
        self.sp_medio.setValue(15)

    def resultado(self) -> tuple[dict[str, int], int, int]:
        pesos = {k: sp.value() for k, sp in self._spins.items()}
        return pesos, self.sp_alto.value(), self.sp_medio.value()


class DialogoConfigurarArchivo(QDialog):
    """Diálogo con vista previa de 20 filas, hoja/filas/fecha/decimal, perfil ERP y mapeo."""

    def __init__(
        self,
        origen: Path | str,
        definicion: dict,
        perfiles: dict[str, dict],
        opciones_actuales: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.origen = origen
        self.definicion = definicion
        self.perfiles = perfiles
        self.requeridas = list(definicion.get("columnas_requeridas") or [])
        self._es_sql = isinstance(origen, str) and es_uri_sql(origen) or (
            isinstance(origen, Path) and origen.suffix.lower() in EXTENSIONES_SQL
        )
        self._previa = pd.DataFrame()
        self._combos_mapeo: dict[str, QComboBox] = {}
        self._dc_par: tuple[str, str] | None = None
        self._ind_dc: tuple[str, tuple[str, ...]] | None = None

        self.setWindowTitle(f"Configurar origen de datos — {origen if isinstance(origen, str) else origen.name}")
        self.setWindowIcon(icono_cuadra("conectores", 28))
        self.resize(960, 680)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # 1. Parámetros de lectura
        card_lect = QFrame()
        card_lect.setProperty("class", "PanelCard")
        grid_l = QGridLayout(card_lect)
        grid_l.setContentsMargins(10, 8, 10, 8)

        self.cmb_hoja = QComboBox()
        self.sp_saltar = QSpinBox()
        self.sp_saltar.setRange(0, 100)
        self.cmb_fecha = QComboBox()
        self.cmb_fecha.addItems(list(FORMATOS_FECHA))
        self.cmb_decimal = QComboBox()
        self.cmb_decimal.addItems(list(SEPARADORES_DECIMALES))
        self.edt_tabla_sql = QLineEdit(str(opciones_actuales.get("tabla_origen") or ""))
        self.edt_consulta_sql = QPlainTextEdit(str(opciones_actuales.get("consulta_sql") or ""))
        self.edt_consulta_sql.setMaximumHeight(54)
        self.edt_consulta_sql.setPlaceholderText("SELECT ... (solo lectura)")

        if isinstance(origen, Path):
            hojas = hojas_excel(origen)
            self.cmb_hoja.addItems(hojas)
            if opciones_actuales.get("hoja") in hojas:
                self.cmb_hoja.setCurrentText(opciones_actuales["hoja"])
            self.sp_saltar.setValue(int(opciones_actuales.get("saltar_filas") or 0))
        fmt_act = opciones_actuales.get("formato_fecha")
        for etiqueta, val in FORMATOS_FECHA.items():
            if val == fmt_act:
                self.cmb_fecha.setCurrentText(etiqueta)
        dec_act = opciones_actuales.get("separador_decimal") or "."
        for etiqueta, val in SEPARADORES_DECIMALES.items():
            if val == dec_act:
                self.cmb_decimal.setCurrentText(etiqueta)

        if self._es_sql:
            grid_l.addWidget(QLabel("Tabla SQL:"), 0, 0)
            grid_l.addWidget(self.edt_tabla_sql, 0, 1)
            btn_ref = QPushButton("Probar SQL / Actualizar previa")
            btn_ref.clicked.connect(self._cargar_previa)
            grid_l.addWidget(btn_ref, 0, 2)
            grid_l.addWidget(QLabel("Consulta SQL:"), 1, 0)
            grid_l.addWidget(self.edt_consulta_sql, 1, 1, 1, 2)
        else:
            grid_l.addWidget(QLabel("Hoja:"), 0, 0)
            grid_l.addWidget(self.cmb_hoja, 0, 1)
            self.cmb_hoja.setEnabled(bool(self.cmb_hoja.count()))
            grid_l.addWidget(QLabel("Filas título:"), 0, 2)
            grid_l.addWidget(self.sp_saltar, 0, 3)
            grid_l.addWidget(QLabel("Fecha:"), 0, 4)
            grid_l.addWidget(self.cmb_fecha, 0, 5)
            grid_l.addWidget(QLabel("Decimal:"), 0, 6)
            grid_l.addWidget(self.cmb_decimal, 0, 7)
            btn_ref = QPushButton("Aplicar vista previa")
            btn_ref.clicked.connect(self._cargar_previa)
            grid_l.addWidget(btn_ref, 0, 8)
        lay.addWidget(card_lect)

        # 2. Vista previa tabular (máx 20 filas)
        lbl_pv = QLabel("VISTA PREVIA DE DATOS (primeras 20 filas)")
        lbl_pv.setProperty("class", "SectionHdr")
        lay.addWidget(lbl_pv)
        self.tv_previa = QTableView()
        _estilo_tabla_base(self.tv_previa)
        self.modelo_previa = ModeloTablaPandas()
        self.tv_previa.setModel(self.modelo_previa)
        self.tv_previa.setFixedHeight(190)
        lay.addWidget(self.tv_previa)

        # 3. Sistema contable y mapeo
        card_map = QFrame()
        card_map.setProperty("class", "PanelCard")
        v_map = QVBoxLayout(card_map)
        v_map.setContentsMargins(10, 8, 10, 8)

        erp_row = QHBoxLayout()
        erp_row.addWidget(QLabel("Sistema contable / ERP:"))
        self.cmb_erp = QComboBox()
        self._nombres_erp = {p["nombre"]: pid for pid, p in perfiles.items()}
        self.cmb_erp.addItem("Automático / Genérico")
        for nombre_erp in self._nombres_erp:
            self.cmb_erp.addItem(nombre_erp)
        pid_act = opciones_actuales.get("perfil_erp")
        if pid_act and pid_act in perfiles:
            self.cmb_erp.setCurrentText(perfiles[pid_act]["nombre"])
        self.cmb_erp.currentIndexChanged.connect(lambda: self._recalcular_mapeo(inicial=False))
        erp_row.addWidget(self.cmb_erp, 1)
        self.lbl_erp_auto = QLabel("")
        self.lbl_erp_auto.setStyleSheet("color: #107C41; font-weight: 600;")
        erp_row.addWidget(self.lbl_erp_auto)
        v_map.addLayout(erp_row)

        self.chk_dc = QCheckBox("")
        self.chk_dc.stateChanged.connect(self._actualizar_campos_mapeo)
        self.chk_ind = QCheckBox("")
        v_map.addWidget(self.chk_dc)
        v_map.addWidget(self.chk_ind)

        self.grid_mapeo = QGridLayout()
        v_map.addLayout(self.grid_mapeo)

        extras_row = QHBoxLayout()
        self.chk_gen_linea = QCheckBox("Generar número de línea secuencial por asiento")
        self.chk_usr_def = QCheckBox("Continuar sin columna de usuario ('(sin usuario en origen)')")
        self.chk_gen_linea.setChecked(bool(opciones_actuales.get("generar_linea")))
        self.chk_usr_def.setChecked(bool(opciones_actuales.get("usuario_por_defecto")))
        extras_row.addWidget(self.chk_gen_linea)
        extras_row.addWidget(self.chk_usr_def)
        v_map.addLayout(extras_row)
        lay.addWidget(card_map)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)

        self._opciones_iniciales = dict(opciones_actuales)
        self._cargar_previa(inicial=True)

    def _cargar_previa(self, inicial: bool = False) -> None:
        try:
            if isinstance(self.origen, str) and es_uri_sql(self.origen):
                self._previa, _ = leer_conexion_sql(
                    self.origen,
                    tabla_origen=self.edt_tabla_sql.text().strip() or None,
                    consulta_sql=self.edt_consulta_sql.toPlainText().strip() or None,
                    limite=20,
                )
            elif self._es_sql:
                self._previa = vista_previa(
                    Path(self.origen),
                    tabla_sql=self.edt_tabla_sql.text().strip() or None,
                    consulta_sql=self.edt_consulta_sql.toPlainText().strip() or None,
                )
            else:
                hoja = self.cmb_hoja.currentText() if self.cmb_hoja.count() else None
                self._previa = vista_previa(Path(self.origen), hoja=hoja, saltar=self.sp_saltar.value())
            self.modelo_previa.actualizar_df(self._previa)
            _auto_ajustar_columnas(self.tv_previa, 220)
            self._recalcular_mapeo(inicial=inicial)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Error de lectura", f"No pude obtener la vista previa:\n{exc}")

    def _recalcular_mapeo(self, inicial: bool = False) -> None:
        columnas = [str(c) for c in self._previa.columns]
        perfil_auto, _ = detectar_perfil(columnas)
        self.lbl_erp_auto.setText(f"Detectado: {perfil_auto['nombre']}" if perfil_auto else "Perfil genérico")

        erp_txt = self.cmb_erp.currentText()
        perfil = self.perfiles[self._nombres_erp[erp_txt]] if erp_txt in self._nombres_erp else None
        prop = proponer_opciones_perfil(perfil, columnas, self.requeridas)

        self._dc_par = prop["debito_credito"]
        self._ind_dc = prop["indicador_dc"] if not self._dc_par else None

        self.chk_dc.setVisible(bool(self._dc_par))
        if self._dc_par:
            self.chk_dc.setText(f"El monto viene en dos columnas: {self._dc_par[0]} (débito) y {self._dc_par[1]} (crédito)")
            self.chk_dc.setChecked(
                bool(self._opciones_iniciales.get("debito_credito")) if inicial else True
            )
        else:
            self.chk_dc.setChecked(False)

        self.chk_ind.setVisible(bool(self._ind_dc))
        if self._ind_dc:
            self.chk_ind.setText(
                f"Aplicar signo D/H con columna indicadora '{self._ind_dc[0]}' (créditos: {', '.join(self._ind_dc[1])})"
            )
            self.chk_ind.setChecked(
                bool(self._opciones_iniciales.get("indicador_dc")) if inicial else True
            )
        else:
            self.chk_ind.setChecked(False)

        self._prop_actual = prop
        self._perfil_actual = perfil
        self._actualizar_campos_mapeo(inicial=inicial)

    def _actualizar_campos_mapeo(self, *_args, inicial: bool = False) -> None:
        while self.grid_mapeo.count():
            item = self.grid_mapeo.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._combos_mapeo.clear()

        columnas = [str(c) for c in self._previa.columns]
        usar_dc = bool(self._dc_par and self.chk_dc.isChecked())
        pedir = [r for r in self.requeridas if not (usar_dc and r == "monto")]

        sugerido = dict(self._prop_actual["mapeo_std_a_col"])
        if "monto" in pedir and sugerido.get("monto") is None:
            sinonimos = (self._perfil_actual or {}).get("aliases")
            sugerido["monto"] = sugerir_mapeo(columnas, ["monto"], sinonimos_extra=sinonimos).get("monto")

        inv_inicial = {v: k for k, v in (self._opciones_iniciales.get("mapeo") or {}).items()}
        for i, req in enumerate(pedir):
            cmb = QComboBox()
            cmb.addItem("(falta)")
            cmb.addItems(columnas)
            val = (inv_inicial.get(req) or (req if req in columnas else None)) if inicial else sugerido.get(req)
            if not val:
                val = sugerido.get(req)
            if val in columnas:
                cmb.setCurrentText(val)
            self._combos_mapeo[req] = cmb
            fila, col = divmod(i, 4)
            box = QWidget()
            bv = QVBoxLayout(box)
            bv.setContentsMargins(0, 0, 0, 0)
            bv.setSpacing(2)
            lbl = QLabel(req)
            lbl.setStyleSheet("font-size: 7.8pt; font-weight: 700; color: #111111;")
            bv.addWidget(lbl)
            bv.addWidget(cmb)
            self.grid_mapeo.addWidget(box, fila, col)

        self.chk_gen_linea.setVisible("linea" in pedir)
        self.chk_usr_def.setVisible("usuario" in pedir)

    def opciones_confirmadas(self) -> dict:
        mapeo: dict[str, str] = {}
        faltan: list[str] = []
        for req, cmb in self._combos_mapeo.items():
            elegida = cmb.currentText()
            if elegida == "(falta)":
                faltan.append(req)
            elif elegida != req:
                mapeo[elegida] = req

        gen_linea = "linea" in faltan and self.chk_gen_linea.isChecked()
        if gen_linea:
            faltan.remove("linea")
        usr_def = None
        if "usuario" in faltan and self.chk_usr_def.isChecked():
            usr_def = (self._prop_actual or {}).get("usuario_por_defecto") or "(sin usuario en origen)"
            faltan.remove("usuario")

        erp_txt = self.cmb_erp.currentText()
        erp_id = self._nombres_erp.get(erp_txt)
        return {
            "hoja": self.cmb_hoja.currentText() if self.cmb_hoja.count() else None,
            "saltar_filas": self.sp_saltar.value() or None,
            "formato_fecha": FORMATOS_FECHA.get(self.cmb_fecha.currentText()),
            "separador_decimal": SEPARADORES_DECIMALES.get(self.cmb_decimal.currentText(), "."),
            "tabla_origen": self.edt_tabla_sql.text().strip() or None if self._es_sql else None,
            "consulta_sql": self.edt_consulta_sql.toPlainText().strip() or None if self._es_sql else None,
            "mapeo": mapeo,
            "debito_credito": self._dc_par if (self._dc_par and self.chk_dc.isChecked()) else None,
            "indicador_dc": self._ind_dc if (not (self._dc_par and self.chk_dc.isChecked()) and self._ind_dc and self.chk_ind.isChecked()) else None,
            "generar_linea": gen_linea or None,
            "usuario_por_defecto": usr_def,
            "perfil_erp": erp_id,
            "_faltantes": faltan,
            "_total_req": len(self._combos_mapeo),
            "_confirmado_ui": True,
        }


class TarjetaFuentePanel(QFrame):
    """Panel compacto para seleccionar y configurar un origen de datos local o SQL."""

    cambiado = Signal()

    def __init__(self, definicion: dict, perfiles: dict[str, dict], parent=None) -> None:
        super().__init__(parent)
        self.definicion = definicion
        self.perfiles = perfiles
        self.tabla = definicion["tabla"]
        self.tipo_especial = definicion.get("tipo")
        self.es_especial = self.tipo_especial in ("factura_electronica", "estado_cuenta_bancario")
        self.origen: Path | str | None = None
        self.opciones: dict[str, Any] = {}

        self.setProperty("class", "PanelCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        opcional = " (opcional)" if definicion.get("opcional") else " (obligatorio)"
        hdr = QLabel(f"{self.tabla.upper()}{opcional}")
        hdr.setProperty("class", "SectionHdr")
        lay.addWidget(hdr)

        desc = QLabel(definicion.get("descripcion", ""))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #333333; font-size: 7.8pt;")
        lay.addWidget(desc)

        if self.es_especial:
            es_banco = self.tipo_especial == "estado_cuenta_bancario"
            lbl_btn = "PDF / CSV / Excel / ZIP…" if es_banco else "Seleccionar ZIP / XML…"
            lbl_dir = "Carpeta PDFs…" if es_banco else "Carpeta XML…"
            row_fe = QHBoxLayout()
            btn_arch = QPushButton(lbl_btn)
            btn_arch.clicked.connect(self._elegir_archivo_especial)
            btn_dir = QPushButton(lbl_dir)
            btn_dir.clicked.connect(self._elegir_carpeta_especial)
            btn_clr = QPushButton("Quitar")
            btn_clr.clicked.connect(self.limpiar)
            row_fe.addWidget(btn_arch)
            row_fe.addWidget(btn_dir)
            row_fe.addWidget(btn_clr)
            lay.addLayout(row_fe)
            self.lbl_estado = QLabel("Sin archivos seleccionados.")
            self.lbl_estado.setWordWrap(True)
            lay.addWidget(self.lbl_estado)
            return

        modo_row = QHBoxLayout()
        self.rb_archivo = QRadioButton("Archivo local directo")
        self.rb_sql = QRadioButton("Conexión SQL (RO)")
        self.rb_archivo.setChecked(True)
        self.rb_archivo.toggled.connect(self._cambiar_modo)
        modo_row.addWidget(self.rb_archivo)
        modo_row.addWidget(self.rb_sql)
        lay.addLayout(modo_row)

        self.pnl_archivo = QWidget()
        ha = QHBoxLayout(self.pnl_archivo)
        ha.setContentsMargins(0, 0, 0, 0)
        btn_arch = QPushButton("Examinar archivo…")
        btn_arch.clicked.connect(self._elegir_archivo)
        self.btn_limpiar = QPushButton("Quitar")
        self.btn_limpiar.clicked.connect(self.limpiar)
        ha.addWidget(btn_arch, 1)
        ha.addWidget(self.btn_limpiar)
        lay.addWidget(self.pnl_archivo)

        self.pnl_sql = QWidget()
        hs = QHBoxLayout(self.pnl_sql)
        hs.setContentsMargins(0, 0, 0, 0)
        self.edt_uri = QLineEdit()
        self.edt_uri.setPlaceholderText("sqlite:///ruta/erp.db  o  mssql+pyodbc://...")
        btn_con = QPushButton("Conectar SQL…")
        btn_con.clicked.connect(self._conectar_sql)
        hs.addWidget(self.edt_uri, 1)
        hs.addWidget(btn_con)
        self.pnl_sql.setVisible(False)
        lay.addWidget(self.pnl_sql)

        self.lbl_estado = QLabel("Sin origen seleccionado.")
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setStyleSheet("color: #333333; font-size: 8pt;")
        lay.addWidget(self.lbl_estado)

        self.btn_config = QPushButton("Configurar columnas / Vista previa…")
        self.btn_config.setEnabled(False)
        self.btn_config.clicked.connect(self._abrir_dialogo_config)
        lay.addWidget(self.btn_config)

    def _cambiar_modo(self) -> None:
        archivo_activo = self.rb_archivo.isChecked()
        self.pnl_archivo.setVisible(archivo_activo)
        self.pnl_sql.setVisible(not archivo_activo)

    def _elegir_archivo_especial(self) -> None:
        if self.tipo_especial == "estado_cuenta_bancario":
            titulo = "Seleccionar extracto bancario (PDF, CSV, Excel o ZIP)"
            filtro = "Extractos bancarios (*.pdf *.zip *.csv *.tsv *.xlsx *.xls);;Todos (*.*)"
        else:
            titulo = "Seleccionar archivo ZIP o XML DGI"
            filtro = "Facturas DGI (*.zip *.xml)"
        ruta_str, _ = QFileDialog.getOpenFileName(self, titulo, str(RAIZ), filtro)
        if ruta_str:
            self.cargar_origen(Path(ruta_str))

    def _elegir_carpeta_especial(self) -> None:
        titulo = (
            "Seleccionar carpeta con extractos PDF"
            if self.tipo_especial == "estado_cuenta_bancario"
            else "Seleccionar carpeta con facturas XML"
        )
        dir_str = QFileDialog.getExistingDirectory(self, titulo, str(RAIZ))
        if dir_str:
            self.cargar_origen(Path(dir_str))

    def _elegir_archivo(self) -> None:
        ruta_str, _ = QFileDialog.getOpenFileName(
            self, f"Seleccionar archivo para {self.tabla}", str(RAIZ), _filtro_archivos_dialogo()
        )
        if ruta_str:
            self.cargar_origen(Path(ruta_str))

    def _conectar_sql(self) -> None:
        uri = self.edt_uri.text().strip()
        if not uri:
            QMessageBox.information(self, "Conexión SQL", "Ingresa una cadena de conexión SQL de solo lectura.")
            return
        self.origen = uri
        self.opciones = {"mapeo": {}}
        self._abrir_dialogo_config()

    def cargar_origen(self, origen: Path | str) -> None:
        self.origen = origen
        if self.es_especial:
            ruta = Path(origen)
            txt_tam = f" ({formatear_tamano(ruta.stat().st_size)})" if ruta.is_file() else " (carpeta local)"
            self.lbl_estado.setText(f"✓ Activo: {ruta.name}{txt_tam}")
            self.lbl_estado.setStyleSheet("color: #107C41; font-weight: 600; font-size: 8pt;")
            self.cambiado.emit()
            return

        if isinstance(origen, Path):
            self.rb_archivo.setChecked(True)
            tam = formatear_tamano(origen.stat().st_size)
            info_base = f"{origen.name} ({tam})"
        else:
            self.rb_sql.setChecked(True)
            self.edt_uri.setText(origen)
            info_base = origen

        try:
            _, self.opciones, _ = _analizar_fuente_inicial(origen, self.definicion, self.perfiles)
            self.btn_config.setEnabled(True)
            self._refrescar_etiqueta(info_base)
        except Exception as exc:  # noqa: BLE001
            self.opciones = {}
            self.btn_config.setEnabled(True)
            self.lbl_estado.setText(f"⚠ {info_base} · No pude previsualizar: {exc}")
            self.lbl_estado.setStyleSheet("color: #B91C1C; font-weight: 600; font-size: 8pt;")
        self.cambiado.emit()

    def _refrescar_etiqueta(self, info_base: str) -> None:
        faltan = self.opciones.get("_faltantes", [])
        tot = int(self.opciones.get("_total_req") or 0)
        ok_cnt = max(tot - len(faltan), 0)
        erp = self.opciones.get("perfil_erp")
        erp_nom = self.perfiles[erp]["nombre"] if erp and erp in self.perfiles else "Genérico"
        if not faltan:
            self.lbl_estado.setText(f"✓ {info_base}\nERP: {erp_nom} · {ok_cnt}/{tot} columnas confirmadas")
            self.lbl_estado.setStyleSheet("color: #107C41; font-weight: 600; font-size: 8pt;")
        else:
            self.lbl_estado.setText(f"⚠ {info_base}\nERP: {erp_nom} · Faltan: {', '.join(faltan)}")
            self.lbl_estado.setStyleSheet("color: #B45309; font-weight: 600; font-size: 8pt;")

    def _abrir_dialogo_config(self) -> None:
        if self.origen is None:
            return
        dlg = DialogoConfigurarArchivo(self.origen, self.definicion, self.perfiles, self.opciones, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.opciones = dlg.opciones_confirmadas()
            base = self.origen.name if isinstance(self.origen, Path) else str(self.origen)
            self._refrescar_etiqueta(base)
            self.cambiado.emit()

    def limpiar(self) -> None:
        self.origen = None
        self.opciones = {}
        self.lbl_estado.setText("Sin origen seleccionado.")
        self.lbl_estado.setStyleSheet("color: #333333; font-size: 8pt;")
        if hasattr(self, "btn_config"):
            self.btn_config.setEnabled(False)
        self.cambiado.emit()

    def esta_listo(self) -> bool:
        if self.origen is None:
            return bool(self.definicion.get("opcional"))
        if self.es_especial:
            return Path(self.origen).exists()
        return len(self.opciones.get("_faltantes", ["_"])) == 0


def _normalizar_fecha_ui(valor: Any, respaldo: date) -> date:
    """Convierte date, datetime o cadena ISO a date; devuelve respaldo si es inválido."""
    if isinstance(valor, datetime):
        return date(valor.year, valor.month, valor.day)
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        txt = valor.strip()
        if txt:
            try:
                return date.fromisoformat(txt[:10])
            except ValueError:
                pass
    return respaldo


class VistaPaqueteWidget(QWidget):
    """Área de trabajo de doble panel para paquetes NIA (Asientos, Excepciones, Factura DGI)."""

    encargo_modificado = Signal(dict)
    solicitar_ejecucion = Signal(str)

    def __init__(self, paquete_id: str, manifiesto: dict, perfiles: dict[str, dict], encargo_inicial: dict, parent=None) -> None:
        super().__init__(parent)
        self.paquete_id = paquete_id
        self.manifiesto = manifiesto
        self.perfiles = perfiles
        self.tarjetas_fuentes: dict[str, TarjetaFuentePanel] = {}
        self._pesos_personalizados: dict[str, int] = {}
        self._umbral_alto = 25
        self._umbral_medio = 15
        self._bloqueo_sync = False
        self._df_puntaje_completo = pd.DataFrame()
        self._modelo_puntaje: ModeloTablaPandas | None = None
        self._tv_puntaje: QTableView | None = None

        lay_root = QHBoxLayout(self)
        lay_root.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        lay_root.addWidget(splitter)

        # Panel izquierdo: Parámetros + Fuentes
        scroll_izq = QScrollArea()
        scroll_izq.setWidgetResizable(True)
        scroll_izq.setFrameShape(QFrame.Shape.NoFrame)
        scroll_izq.setMinimumWidth(390)
        scroll_izq.setMaximumWidth(480)
        cont_izq = QWidget()
        v_izq = QVBoxLayout(cont_izq)
        v_izq.setContentsMargins(2, 2, 6, 2)
        v_izq.setSpacing(8)

        card_param = QFrame()
        card_param.setProperty("class", "PanelCard")
        form_p = QVBoxLayout(card_param)
        form_p.setContentsMargins(10, 8, 10, 8)
        form_p.setSpacing(6)
        hdr_p = QLabel("1 · PARÁMETROS DEL ENCARGO")
        hdr_p.setProperty("class", "SectionHdr")
        form_p.addWidget(hdr_p)

        fl = QFormLayout()
        fl.setSpacing(5)
        self.edt_cliente = QLineEdit(str(encargo_inicial["cliente"]))
        fc = _normalizar_fecha_ui(encargo_inicial.get("fecha_cierre"), date(2025, 12, 31))
        pi_auto = calcular_periodo_inicio(fc)
        pi = _normalizar_fecha_ui(encargo_inicial.get("periodo_inicio"), pi_auto)
        self._ultimo_inicio_auto = pi_auto
        self.de_inicio = QDateEdit(QDate(pi.year, pi.month, pi.day))
        self.de_inicio.setCalendarPopup(True)
        self.de_inicio.setDisplayFormat("yyyy-MM-dd")
        self.de_cierre = QDateEdit(QDate(fc.year, fc.month, fc.day))
        self.de_cierre.setCalendarPopup(True)
        self.de_cierre.setDisplayFormat("yyyy-MM-dd")
        self.cmb_marco = QComboBox()
        self.cmb_marco.addItems(["NIIF", "NIIF para PYMES"])
        self.cmb_marco.setCurrentText(str(encargo_inicial["marco"]))

        self.sp_mat = self._spin_dinero(encargo_inicial["materialidad"])
        self.sp_mej = self._spin_dinero(encargo_inicial["materialidad_ejecucion"])
        self.sp_tri = self._spin_dinero(encargo_inicial["umbral_trivial"])
        self.sp_apr = self._spin_dinero(encargo_inicial["umbral_aprobacion"])

        for w in (self.edt_cliente, self.de_inicio, self.cmb_marco, self.sp_mat, self.sp_mej, self.sp_tri, self.sp_apr):
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self._emitir_encargo)
            elif isinstance(w, QDateEdit):
                w.dateChanged.connect(self._emitir_encargo)
            elif isinstance(w, QComboBox):
                w.currentTextChanged.connect(self._emitir_encargo)
            else:
                w.valueChanged.connect(self._emitir_encargo)
        self.de_cierre.dateChanged.connect(self._al_cambiar_cierre)

        fl.addRow("Cliente:", self.edt_cliente)
        fl.addRow("Período inicio:", self.de_inicio)
        fl.addRow("Fecha de cierre:", self.de_cierre)
        fl.addRow("Marco contable:", self.cmb_marco)
        fl.addRow("Materialidad:", self.sp_mat)
        fl.addRow("Mat. ejecución:", self.sp_mej)
        fl.addRow("Umbral trivial:", self.sp_tri)
        fl.addRow("Umbral aprobación:", self.sp_apr)
        form_p.addLayout(fl)

        if paquete_id == "asientos-nia240":
            self.btn_pesos = QPushButton("Pesos del puntaje de riesgo (10 criterios)…")
            self.btn_pesos.clicked.connect(self._abrir_pesos)
            form_p.addWidget(self.btn_pesos)
        v_izq.addWidget(card_param)

        hdr_f = QLabel("2 · FUENTES DE DATOS DEL CLIENTE")
        hdr_f.setProperty("class", "SectionHdr")
        v_izq.addWidget(hdr_f)
        for definicion in manifiesto["archivos"]:
            tarjeta = TarjetaFuentePanel(definicion, perfiles)
            tarjeta.cambiado.connect(self._actualizar_estado_boton)
            self.tarjetas_fuentes[definicion["tabla"]] = tarjeta
            v_izq.addWidget(tarjeta)

        self.btn_correr = QPushButton("Correr pruebas deterministas")
        self.btn_correr.setObjectName("BtnPrimary")
        self.btn_correr.setIcon(icono_cuadra("correr", 20))
        self.btn_correr.setEnabled(False)
        self.btn_correr.clicked.connect(lambda: self.solicitar_ejecucion.emit(self.paquete_id))
        v_izq.addWidget(self.btn_correr)
        v_izq.addStretch(1)

        scroll_izq.setWidget(cont_izq)
        splitter.addWidget(scroll_izq)

        # Panel derecho: 4 KPIs + Hojas de resultados estilo Excel
        panel_der = QWidget()
        v_der = QVBoxLayout(panel_der)
        v_der.setContentsMargins(6, 2, 2, 2)
        v_der.setSpacing(8)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self.kpis = [
            TarjetaKPI("Estado", "Listo", "Selecciona los datos de entrada", "neutro"),
            TarjetaKPI("Filas analizadas", "—", "", "neutro"),
            TarjetaKPI("Hallazgos", "—", "", "neutro"),
            TarjetaKPI("Bitácora SHA-256", "Sin ejecución", "", "neutro"),
        ]
        for k in self.kpis:
            kpi_row.addWidget(k)
        v_der.addLayout(kpi_row)

        self.tabs_resultados = QTabWidget()
        self.tabs_resultados.setTabPosition(QTabWidget.TabPosition.South)
        v_der.addWidget(self.tabs_resultados, 1)
        self._mostrar_placeholder_resultados()

        splitter.addWidget(panel_der)
        splitter.setSizes([430, 950])

    @staticmethod
    def _spin_dinero(valor: float) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0.0, 10_000_000_000.0)
        sp.setDecimals(2)
        sp.setSingleStep(1000.0)
        sp.setGroupSeparatorShown(True)
        sp.setValue(float(valor))
        return sp

    def _al_cambiar_cierre(self, qd_cierre: QDate) -> None:
        fc = date(qd_cierre.year(), qd_cierre.month(), qd_cierre.day())
        nuevo_auto = calcular_periodo_inicio(fc)
        if not self._bloqueo_sync:
            qd_ini = self.de_inicio.date()
            ini_actual = date(qd_ini.year(), qd_ini.month(), qd_ini.day())
            if ini_actual == self._ultimo_inicio_auto:
                self._bloqueo_sync = True
                try:
                    self.de_inicio.setDate(QDate(nuevo_auto.year, nuevo_auto.month, nuevo_auto.day))
                finally:
                    self._bloqueo_sync = False
        self._ultimo_inicio_auto = nuevo_auto
        self._emitir_encargo()

    def _emitir_encargo(self) -> None:
        if self._bloqueo_sync:
            return
        self.encargo_modificado.emit(self.obtener_encargo_ui())

    def aplicar_encargo_ui(self, datos: dict) -> None:
        self._bloqueo_sync = True
        try:
            self.edt_cliente.setText(str(datos["cliente"]))
            fc = _normalizar_fecha_ui(datos.get("fecha_cierre"), date(2025, 12, 31))
            pi_auto = calcular_periodo_inicio(fc)
            pi = _normalizar_fecha_ui(datos.get("periodo_inicio"), pi_auto)
            self._ultimo_inicio_auto = pi_auto
            self.de_inicio.setDate(QDate(pi.year, pi.month, pi.day))
            self.de_cierre.setDate(QDate(fc.year, fc.month, fc.day))
            self.cmb_marco.setCurrentText(str(datos["marco"]))
            self.sp_mat.setValue(float(datos["materialidad"]))
            self.sp_mej.setValue(float(datos["materialidad_ejecucion"]))
            self.sp_tri.setValue(float(datos["umbral_trivial"]))
            self.sp_apr.setValue(float(datos["umbral_aprobacion"]))
        finally:
            self._bloqueo_sync = False

    def obtener_encargo_ui(self) -> dict:
        qd_ini = self.de_inicio.date()
        qd = self.de_cierre.date()
        return {
            "cliente": self.edt_cliente.text().strip() or "Cliente Demo, S.A.",
            "periodo_inicio": date(qd_ini.year(), qd_ini.month(), qd_ini.day()),
            "fecha_cierre": date(qd.year(), qd.month(), qd.day()),
            "marco": self.cmb_marco.currentText(),
            "materialidad": self.sp_mat.value(),
            "materialidad_ejecucion": self.sp_mej.value(),
            "umbral_trivial": self.sp_tri.value(),
            "umbral_aprobacion": self.sp_apr.value(),
        }

    def construir_payload_ejecucion(self) -> tuple[dict, dict, dict]:
        ui = self.obtener_encargo_ui()
        fc: date = ui["fecha_cierre"]
        inicio: date = ui["periodo_inicio"]
        encargo: dict[str, Any] = {
            "cliente": ui["cliente"],
            "periodo_inicio": inicio.isoformat(),
            "fecha_cierre": fc.isoformat(),
            "marco": ui["marco"],
            "prefijo_ingresos": "4",
            "materialidad": ui["materialidad"],
            "materialidad_ejecucion": ui["materialidad_ejecucion"],
            "umbral_trivial": ui["umbral_trivial"],
            "umbral_aprobacion": ui["umbral_aprobacion"],
        }
        if self._pesos_personalizados:
            encargo["pesos_riesgo"] = dict(self._pesos_personalizados)
        if self._umbral_alto != 25:
            encargo["nivel_riesgo_alto"] = self._umbral_alto
        if self._umbral_medio != 15:
            encargo["nivel_riesgo_medio"] = self._umbral_medio

        archivos: dict[str, Path | str | None] = {}
        opciones: dict[str, dict] = {}
        for tabla, tarjeta in self.tarjetas_fuentes.items():
            archivos[tabla] = tarjeta.origen
            if tarjeta.opciones:
                opciones[tabla] = {
                    k: v
                    for k, v in tarjeta.opciones.items()
                    if not k.startswith("_") or k == "_confirmado_ui"
                }
        return encargo, archivos, opciones

    def _abrir_pesos(self) -> None:
        pesos_def, alto_def, medio_def = pesos_defecto_puntaje(self.manifiesto)
        dlg = DialogoPesosRiesgo(
            pesos_def,
            {k: self._pesos_personalizados.get(k, v) for k, v in pesos_def.items()},
            self._umbral_alto,
            self._umbral_medio,
            self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            nuevos, alto, medio = dlg.resultado()
            self._pesos_personalizados = {k: v for k, v in nuevos.items() if v != pesos_def.get(k)}
            self._umbral_alto = alto
            self._umbral_medio = medio

    def esta_listo(self) -> bool:
        return all(t.esta_listo() for t in self.tarjetas_fuentes.values())

    def _actualizar_estado_boton(self) -> None:
        self.btn_correr.setEnabled(self.esta_listo())

    def _mostrar_placeholder_resultados(self) -> None:
        self.tabs_resultados.clear()
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(
            f"Paquete listo: {self.manifiesto.get('nombre', self.paquete_id)}\n\n"
            "1. Selecciona los archivos del cliente en el panel izquierdo (lectura directa sin límite de tamaño)\n"
            "   o presiona «Cargar ejemplo sintético» en la barra superior para probar con datos de demostración.\n"
            "2. Confirma las columnas si el archivo usa encabezados personalizados.\n"
            "3. Haz clic en «Correr pruebas» para generar las hojas y la cédula Excel trazable."
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #333333; font-size: 9.5pt; line-height: 1.4;")
        lay.addWidget(lbl)
        self.tabs_resultados.addTab(w, "Resumen")

    def mostrar_corrida(self, corrida: Corrida) -> None:
        integra = corrida.bitacora.verificar()
        total_filas = sum(c["filas"] for c in corrida.controles)
        total_hallazgos = sum(r.excepciones for r in corrida.resultados if not r.omitida)
        r_puntaje = next((r for r in corrida.resultados if r.id == "asientos-puntaje" and not r.omitida), None)

        if r_puntaje:
            pn = r_puntaje.resumen.get("por_nivel", {"alto": 0, "medio": 0, "bajo": 0})
            um = r_puntaje.resumen.get("umbrales", {})
            analizados = r_puntaje.resumen.get("asientos_analizados", 0)
            self.kpis[0].lbl_titulo.setText("RIESGO ALTO")
            self.kpis[0].actualizar(str(pn.get("alto", 0)), f"Puntaje ≥ {um.get('alto', 25)}", "alto")
            self.kpis[1].lbl_titulo.setText("RIESGO MEDIO")
            self.kpis[1].actualizar(str(pn.get("medio", 0)), f"Puntaje ≥ {um.get('medio', 15)}", "medio")
            self.kpis[2].lbl_titulo.setText("ASIENTOS ANALIZADOS")
            self.kpis[2].actualizar(f"{analizados:,}", f"{r_puntaje.excepciones} con puntaje > 0", "bajo")
        else:
            ej = sum(1 for r in corrida.resultados if not r.omitida)
            self.kpis[0].lbl_titulo.setText("FILAS ANALIZADAS")
            self.kpis[0].actualizar(f"{total_filas:,}", f"{len(corrida.controles)} archivo(s)", "neutro")
            self.kpis[1].lbl_titulo.setText("PRUEBAS EJECUTADAS")
            self.kpis[1].actualizar(f"{ej}/{len(corrida.resultados)}", self.manifiesto["id"], "bajo")
            self.kpis[2].lbl_titulo.setText("HALLAZGOS TOTALES")
            self.kpis[2].actualizar(f"{total_hallazgos:,}", "Ver pestañas de detalle", "medio" if total_hallazgos else "ok")

        self.kpis[3].lbl_titulo.setText("BITÁCORA SHA-256")
        self.kpis[3].actualizar(
            "ÍNTEGRA" if integra else "ALTERADA",
            corrida.cedula.name,
            "ok" if integra else "alto",
        )

        self.tabs_resultados.clear()
        df_resumen = pd.DataFrame([
            {
                "Norma NIA": ", ".join(r.nia) if r.nia else "—",
                "Prueba": r.nombre,
                "Hallazgos": r.omitida or r.excepciones,
                "Resumen": "" if r.omitida else detalle_resultado(r),
            }
            for r in corrida.resultados
        ])
        diag = corrida.diagnostico or {}
        banner_diag = None
        if diag:
            est_d = diag.get("estado_general", "OK")
            etiquetas_d = {
                "OK": f"CONFIABILIDAD DE DATOS: OK · {diag.get('resumen', '')}",
                "ADVERTENCIA": f"ADVERTENCIA DE CONFIABILIDAD DE DATOS · {diag.get('resumen', '')} — Ver pestaña 'Diagnóstico'",
                "ALERTA": f"ALERTA CRÍTICA EN DATOS FUENTE · {diag.get('resumen', '')} — Revisar pestaña 'Diagnóstico' antes de concluir",
            }
            banner_diag = (est_d, etiquetas_d.get(est_d, diag.get("resumen", "")))
        self._agregar_hoja_tabla("Resumen", df_resumen, banner=banner_diag)

        if r_puntaje:
            self._agregar_hoja_puntaje(r_puntaje)

        for r in corrida.resultados:
            if r.omitida:
                continue
            if r.id == "asientos-puntaje":
                cols_m = [c for c in ["asiento", "puntaje", "nivel", *CRITERIOS_ASIENTO] if c in r.tabla.columns]
                df_t = r.tabla[cols_m].rename(columns=NOMBRES_CRITERIOS)
                titulo_tab = "Matriz criterios"
            else:
                df_t = formatear_fechas_df(r.tabla)
                corto = r.nombre if len(r.nombre) <= 20 else f"{r.nombre[:19].rstrip()}…"
                titulo_tab = f"{corto} ({r.excepciones})"
            self._agregar_hoja_tabla(titulo_tab, df_t, advertencia=r.resumen.get("advertencia"))

        if diag:
            df_diag = diagnostico_a_dataframe(diag).rename(columns={
                "estado": "Estado",
                "codigo": "Código",
                "nombre": "Control de integridad",
                "tabla": "Fuente",
                "valor": "Resultado medido",
                "detalle": "Explicación",
                "accion_sugerida": "Acción sugerida",
            })
            cont_d = diag.get("conteos") or {}
            avisos_d = int(cont_d.get("ALERTA", 0)) + int(cont_d.get("ADVERTENCIA", 0))
            self._agregar_hoja_tabla(f"Diagnóstico ({avisos_d})" if avisos_d else "Diagnóstico (OK)", df_diag)

        df_ctrl = pd.DataFrame([
            {
                "Archivo": c["archivo"],
                "Filas": c["filas"],
                "Excluidas": c.get("filas_excluidas", 0),
                "Codificación": c.get("codificacion", "Excel"),
                "ERP": c.get("perfil_erp") or "Genérico",
                "SHA-256": c["sha256"],
                "Transformaciones": " | ".join(c.get("transformaciones", [])) or "Ninguna",
            }
            for c in corrida.controles
        ])
        self._agregar_hoja_tabla("Control archivos", df_ctrl)

    def _agregar_hoja_tabla(
        self,
        titulo: str,
        df: pd.DataFrame,
        advertencia: str | None = None,
        banner: tuple[str, str] | None = None,
    ) -> None:
        cont = QWidget()
        lay = QVBoxLayout(cont)
        lay.setContentsMargins(6, 6, 6, 6)
        if banner and banner[1]:
            est_b, txt_b = banner
            estilos_banner = {
                "ALERTA": "background: #FEE2E2; border: 1px solid #DC2626; color: #991B1B; padding: 6px 10px; font-weight: 700;",
                "ADVERTENCIA": "background: #FEF3C7; border: 1px solid #D97706; color: #92400E; padding: 6px 10px; font-weight: 600;",
                "OK": "background: #DCFCE7; border: 1px solid #16A34A; color: #166534; padding: 6px 10px; font-weight: 600;",
            }
            lbl_b = QLabel(txt_b)
            lbl_b.setWordWrap(True)
            lbl_b.setStyleSheet(estilos_banner.get(est_b, estilos_banner["ADVERTENCIA"]))
            lay.addWidget(lbl_b)
        if advertencia:
            lbl_adv = QLabel(f"⚠ {advertencia}")
            lbl_adv.setStyleSheet("background: #FEF3C7; border: 1px solid #F59E0B; color: #92400E; padding: 5px 8px; font-weight: 600;")
            lay.addWidget(lbl_adv)
        tv = QTableView()
        _estilo_tabla_base(tv)
        modelo = ModeloTablaPandas(df)
        tv.setModel(modelo)
        _auto_ajustar_columnas(tv)
        lay.addWidget(tv)
        self.tabs_resultados.addTab(cont, titulo)

    def _agregar_hoja_puntaje(self, r_puntaje) -> None:
        cols_v = [c for c in ["asiento", "fecha", "usuario", "descripcion", "total_debito", "puntaje", "nivel", "explicacion"] if c in r_puntaje.tabla.columns]
        self._df_puntaje_completo = formatear_fechas_df(r_puntaje.tabla[cols_v])

        cont = QWidget()
        lay = QVBoxLayout(cont)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        barra = QHBoxLayout()
        self.edt_buscar_puntaje = QLineEdit()
        self.edt_buscar_puntaje.setPlaceholderText("Filtrar por asiento, usuario, descripción o explicación…")
        self.edt_buscar_puntaje.textChanged.connect(self._filtrar_puntaje)
        self.cmb_nivel_puntaje = QComboBox()
        self.cmb_nivel_puntaje.addItems(["Todos los niveles", "alto", "medio", "bajo"])
        self.cmb_nivel_puntaje.currentTextChanged.connect(self._filtrar_puntaje)
        barra.addWidget(self.edt_buscar_puntaje, 1)
        barra.addWidget(QLabel("Nivel:"))
        barra.addWidget(self.cmb_nivel_puntaje)
        lay.addLayout(barra)

        self._tv_puntaje = QTableView()
        _estilo_tabla_base(self._tv_puntaje)
        nombres = {
            "asiento": "Asiento",
            "fecha": "Fecha",
            "usuario": "Usuario",
            "descripcion": "Descripción",
            "total_debito": "Total débito",
            "puntaje": "Puntaje",
            "nivel": "Nivel",
            "explicacion": "Explicación",
        }
        self._modelo_puntaje = ModeloTablaPandas(self._df_puntaje_completo, nombres)
        self._tv_puntaje.setModel(self._modelo_puntaje)

        if "puntaje" in self._df_puntaje_completo.columns:
            col_p = list(self._df_puntaje_completo.columns).index("puntaje")
            col_n = list(self._df_puntaje_completo.columns).index("nivel") if "nivel" in self._df_puntaje_completo.columns else None
            pmax = int(r_puntaje.resumen.get("puntaje_maximo", 100) or 100)
            self._tv_puntaje.setItemDelegateForColumn(col_p, DelegadoBarraPuntaje(pmax, col_n, self._tv_puntaje))

        _auto_ajustar_columnas(self._tv_puntaje, 380)
        lay.addWidget(self._tv_puntaje)
        self.tabs_resultados.addTab(cont, "Puntaje de Riesgo (Ficha 11)")
        self.tabs_resultados.setCurrentIndex(self.tabs_resultados.count() - 1)

    def _filtrar_puntaje(self) -> None:
        if self._modelo_puntaje is None:
            return
        df = self._df_puntaje_completo
        nivel = self.cmb_nivel_puntaje.currentText()
        if nivel != "Todos los niveles" and "nivel" in df.columns:
            df = df[df["nivel"].astype(str).str.lower() == nivel]
        q = self.edt_buscar_puntaje.text().strip().lower()
        if q:
            mask = pd.Series(False, index=df.index)
            for col in [c for c in ("asiento", "usuario", "descripcion", "explicacion") if c in df.columns]:
                mask = mask | df[col].astype(str).str.lower().str.contains(q, na=False, regex=False)
            df = df[mask]
        self._modelo_puntaje.actualizar_df(df.reset_index(drop=True))


class VistaMuestreoWidget(QWidget):
    """Herramienta NIA 530: Selección sistemática MUS y Evaluación Stringer/Poisson."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._df_pob = pd.DataFrame()
        self._df_err = pd.DataFrame()
        self._df_seleccion = pd.DataFrame()
        self._df_eval = pd.DataFrame()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(splitter)

        # Panel izquierdo: Selección
        card_s = QFrame()
        card_s.setProperty("class", "PanelCard")
        vs = QVBoxLayout(card_s)
        vs.setContentsMargins(10, 8, 10, 8)
        hdr_s = QLabel("1 · SELECCIÓN ESTADÍSTICA MUS (NIA 530)")
        hdr_s.setProperty("class", "SectionHdr")
        vs.addWidget(hdr_s)

        r_btn_s = QHBoxLayout()
        btn_pob = QPushButton("Cargar población (CSV/Excel/Parquet)…")
        btn_pob.clicked.connect(self._cargar_poblacion)
        btn_pl_pob = QPushButton("Guardar plantilla CSV…")
        btn_pl_pob.clicked.connect(lambda: self._guardar_plantilla("plantilla_poblacion_mus.csv", "cliente,saldo\nC001,12500.00\nC002,48900.00\nC003,7200.50\n"))
        r_btn_s.addWidget(btn_pob, 1)
        r_btn_s.addWidget(btn_pl_pob)
        vs.addLayout(r_btn_s)

        gs = QGridLayout()
        self.cmb_mus_id = QComboBox()
        self.cmb_mus_val = QComboBox()
        self.sp_mus_tol = VistaPaqueteWidget._spin_dinero(45000.0)
        self.cmb_mus_conf = QComboBox()
        self.cmb_mus_conf.addItems(["95", "90"])
        self.sp_mus_sem = QSpinBox()
        self.sp_mus_sem.setRange(1, 999999)
        self.sp_mus_sem.setValue(2025)
        gs.addWidget(QLabel("ID:"), 0, 0)
        gs.addWidget(self.cmb_mus_id, 0, 1)
        gs.addWidget(QLabel("Valor libros:"), 0, 2)
        gs.addWidget(self.cmb_mus_val, 0, 3)
        gs.addWidget(QLabel("Tolerable:"), 1, 0)
        gs.addWidget(self.sp_mus_tol, 1, 1)
        gs.addWidget(QLabel("Confianza %:"), 1, 2)
        gs.addWidget(self.cmb_mus_conf, 1, 3)
        gs.addWidget(QLabel("Semilla:"), 2, 0)
        gs.addWidget(self.sp_mus_sem, 2, 1)
        self.btn_calc_mus = QPushButton("Calcular selección MUS")
        self.btn_calc_mus.setObjectName("BtnPrimary")
        self.btn_calc_mus.setEnabled(False)
        self.btn_calc_mus.clicked.connect(self._ejecutar_seleccion)
        gs.addWidget(self.btn_calc_mus, 2, 2, 1, 2)
        vs.addLayout(gs)

        ks = QHBoxLayout()
        self.kpi_vl = TarjetaKPI("Valor en libros", "—")
        self.kpi_n = TarjetaKPI("Tamaño (n)", "—")
        self.kpi_ini = TarjetaKPI("Inicio aleatorio", "—")
        for k in (self.kpi_vl, self.kpi_n, self.kpi_ini):
            ks.addWidget(k)
        vs.addLayout(ks)

        self.tv_sel = QTableView()
        _estilo_tabla_base(self.tv_sel)
        self.mod_sel = ModeloTablaPandas()
        self.tv_sel.setModel(self.mod_sel)
        vs.addWidget(self.tv_sel, 1)
        splitter.addWidget(card_s)

        # Panel derecho: Evaluación
        card_e = QFrame()
        card_e.setProperty("class", "PanelCard")
        ve = QVBoxLayout(card_e)
        ve.setContentsMargins(10, 8, 10, 8)
        hdr_e = QLabel("2 · EVALUACIÓN DE ERRORES MUS")
        hdr_e.setProperty("class", "SectionHdr")
        ve.addWidget(hdr_e)

        r_btn_e = QHBoxLayout()
        btn_err = QPushButton("Cargar partidas evaluadas…")
        btn_err.clicked.connect(self._cargar_errores)
        btn_pl_err = QPushButton("Guardar plantilla CSV…")
        btn_pl_err.clicked.connect(lambda: self._guardar_plantilla("plantilla_errores_mus.csv", "id,valor_libros,valor_auditado\nC001,12500.00,12500.00\nC002,48900.00,46400.00\n"))
        r_btn_e.addWidget(btn_err, 1)
        r_btn_e.addWidget(btn_pl_err)
        ve.addLayout(r_btn_e)

        ge = QGridLayout()
        self.cmb_ev_id = QComboBox()
        self.cmb_ev_lib = QComboBox()
        self.cmb_ev_aud = QComboBox()
        self.sp_ev_int = VistaPaqueteWidget._spin_dinero(15000.0)
        self.sp_ev_tol = VistaPaqueteWidget._spin_dinero(45000.0)
        self.cmb_ev_conf = QComboBox()
        self.cmb_ev_conf.addItems(["95", "90"])
        ge.addWidget(QLabel("Col. ID:"), 0, 0)
        ge.addWidget(self.cmb_ev_id, 0, 1)
        ge.addWidget(QLabel("V. Libros:"), 0, 2)
        ge.addWidget(self.cmb_ev_lib, 0, 3)
        ge.addWidget(QLabel("V. Auditado:"), 0, 4)
        ge.addWidget(self.cmb_ev_aud, 0, 5)
        ge.addWidget(QLabel("Intervalo J:"), 1, 0)
        ge.addWidget(self.sp_ev_int, 1, 1)
        ge.addWidget(QLabel("Tolerable:"), 1, 2)
        ge.addWidget(self.sp_ev_tol, 1, 3)
        ge.addWidget(QLabel("Confianza %:"), 1, 4)
        ge.addWidget(self.cmb_ev_conf, 1, 5)
        ve.addLayout(ge)

        self.btn_eval_mus = QPushButton("Evaluar muestra MUS")
        self.btn_eval_mus.setObjectName("BtnPrimary")
        self.btn_eval_mus.setEnabled(False)
        self.btn_eval_mus.clicked.connect(self._ejecutar_evaluacion)
        ve.addWidget(self.btn_eval_mus)

        ke = QHBoxLayout()
        self.kpi_proy = TarjetaKPI("Error proyectado", "—")
        self.kpi_marg = TarjetaKPI("Margen incremental", "—")
        self.kpi_lim = TarjetaKPI("Límite superior", "—")
        for k in (self.kpi_proy, self.kpi_marg, self.kpi_lim):
            ke.addWidget(k)
        ve.addLayout(ke)

        self.lbl_conclusion_mus = QLabel("")
        self.lbl_conclusion_mus.setWordWrap(True)
        self.lbl_conclusion_mus.setVisible(False)
        ve.addWidget(self.lbl_conclusion_mus)

        self.tv_ev = QTableView()
        _estilo_tabla_base(self.tv_ev)
        self.mod_ev = ModeloTablaPandas()
        self.tv_ev.setModel(self.mod_ev)
        ve.addWidget(self.tv_ev, 1)
        splitter.addWidget(card_e)

    def _guardar_plantilla(self, nombre_def: str, contenido: str) -> None:
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar plantilla CSV", str(RAIZ / nombre_def), "CSV (*.csv)")
        if destino:
            Path(destino).write_text(contenido, encoding="utf-8")

    def _cargar_poblacion(self) -> None:
        ruta_str, _ = QFileDialog.getOpenFileName(self, "Cargar población MUS", str(RAIZ), _filtro_archivos_dialogo())
        if not ruta_str:
            return
        try:
            self._df_pob = cargar_dataframe_muestreo(Path(ruta_str))
            cols = [str(c) for c in self._df_pob.columns]
            self.cmb_mus_id.clear()
            self.cmb_mus_id.addItems(cols)
            self.cmb_mus_val.clear()
            self.cmb_mus_val.addItems(cols)
            if len(cols) > 1:
                self.cmb_mus_val.setCurrentIndex(1)
            self.btn_calc_mus.setEnabled(bool(cols))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Muestreo MUS", str(exc))

    def _ejecutar_seleccion(self) -> None:
        try:
            sel, plan = seleccionar_mus(
                self._df_pob,
                self.cmb_mus_id.currentText(),
                self.cmb_mus_val.currentText(),
                self.sp_mus_tol.value(),
                int(self.cmb_mus_conf.currentText()),
                semilla=self.sp_mus_sem.value(),
            )
            self._df_seleccion = sel
            self.kpi_vl.actualizar(f"{plan.valor_libros:,.2f}", "", "neutro")
            self.kpi_n.actualizar(str(plan.tamano), f"Intervalo {plan.intervalo:,.2f}", "bajo")
            self.kpi_ini.actualizar(f"{plan.inicio:,.2f}", f"Semilla {self.sp_mus_sem.value()}", "ok")
            self.sp_ev_int.setValue(float(plan.intervalo))
            self.sp_ev_tol.setValue(float(plan.error_tolerable))
            self.mod_sel.actualizar_df(sel)
            _auto_ajustar_columnas(self.tv_sel)
        except ErrorMuestreo as exc:
            QMessageBox.warning(self, "Error MUS", str(exc))

    def _cargar_errores(self) -> None:
        ruta_str, _ = QFileDialog.getOpenFileName(self, "Cargar partidas evaluadas", str(RAIZ), _filtro_archivos_dialogo())
        if not ruta_str:
            return
        try:
            self._df_err = cargar_dataframe_muestreo(Path(ruta_str))
            cols = [str(c) for c in self._df_err.columns]
            for cmb in (self.cmb_ev_id, self.cmb_ev_lib, self.cmb_ev_aud):
                cmb.clear()
                cmb.addItems(cols)
            for cmb, cands, fb in (
                (self.cmb_ev_id, ("id", "cliente", "codigo", "cuenta"), 0),
                (self.cmb_ev_lib, ("valor libros", "saldo", "libros"), 1),
                (self.cmb_ev_aud, ("valor auditado", "auditado", "real"), 2),
            ):
                elegida = next((c for c in cols if normalizar(c) in cands), cols[min(fb, len(cols) - 1)] if cols else "")
                if elegida:
                    cmb.setCurrentText(elegida)
            self.btn_eval_mus.setEnabled(len(cols) >= 3)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Evaluación MUS", str(exc))

    def _ejecutar_evaluacion(self) -> None:
        try:
            ev = evaluar_mus(
                self._df_err,
                self.sp_ev_int.value(),
                self.sp_ev_tol.value(),
                int(self.cmb_ev_conf.currentText()),
                self.cmb_ev_id.currentText(),
                self.cmb_ev_lib.currentText(),
                self.cmb_ev_aud.currentText(),
            )
            supera = ev.limite_superior > self.sp_ev_tol.value()
            self.kpi_proy.actualizar(f"{ev.error_proyectado:,.2f}", "", "neutro")
            self.kpi_marg.actualizar(f"{ev.margen_incremental:,.2f}", "", "neutro")
            self.kpi_lim.actualizar(f"{ev.limite_superior:,.2f}", "", "alto" if supera else "ok")
            self.lbl_conclusion_mus.setVisible(True)
            self.lbl_conclusion_mus.setText(ev.conclusion)
            self.lbl_conclusion_mus.setStyleSheet(
                "padding: 6px 10px; font-weight: 600; border-radius: 0px; "
                + ("background:#FEE2E2; border:1px solid #B91C1C; color:#991B1B;" if supera else "background:#DCFCE7; border:1px solid #107C41; color:#065F46;")
            )
            self.mod_ev.actualizar_df(ev.detalle)
            _auto_ajustar_columnas(self.tv_ev)
        except ErrorMuestreo as exc:
            QMessageBox.warning(self, "Evaluación MUS", str(exc))


class VistaConectoresWidget(QWidget):
    """Catálogo de los 10 ERP de Panamá + mapeo de encabezados + consultas SQL copiables."""

    def __init__(self, perfiles: dict[str, dict], parent=None) -> None:
        super().__init__(parent)
        self.perfiles = perfiles
        self._pids = list(perfiles.keys())

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(splitter)

        # Izquierda: Catálogo de los 10 ERPs de Panamá
        card_izq = QFrame()
        card_izq.setProperty("class", "PanelCard")
        vi = QVBoxLayout(card_izq)
        vi.setContentsMargins(10, 8, 10, 8)
        hdr_i = QLabel("CATÁLOGO DE SISTEMAS CONTABLES (PANAMÁ) Y FORMATOS")
        hdr_i.setProperty("class", "SectionHdr")
        vi.addWidget(hdr_i)
        lbl_fmt = QLabel(
            "Formatos aceptados sin internet: Excel (.xlsx/.xlsm/.xls), CSV/TSV/TXT (SAP ALV '|' y UTF-16/CP1252), "
            "Parquet, JSON/JSONL, SQLite, DuckDB, volcados .sql y conexiones SQL RO (SELECT/WITH)."
        )
        lbl_fmt.setWordWrap(True)
        lbl_fmt.setStyleSheet("color: #333333; font-size: 8.1pt;")
        vi.addWidget(lbl_fmt)

        df_cat = pd.DataFrame([
            {
                "Sistema contable / ERP": p["nombre"],
                "Segmento en Panamá": p.get("segmento_panama", ""),
                "Formatos": ", ".join(p.get("formatos_frecuentes", [])),
            }
            for p in perfiles.values()
        ])
        self.tv_cat = QTableView()
        _estilo_tabla_base(self.tv_cat)
        self.tv_cat.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tv_cat.setModel(ModeloTablaPandas(df_cat))
        self.tv_cat.selectionModel().currentRowChanged.connect(lambda idx, _: self._mostrar_perfil(idx.row()))
        _auto_ajustar_columnas(self.tv_cat, 260)
        vi.addWidget(self.tv_cat, 1)
        splitter.addWidget(card_izq)

        # Derecha: Detalle de alias y consultas SQL
        card_der = QFrame()
        card_der.setProperty("class", "PanelCard")
        vd = QVBoxLayout(card_der)
        vd.setContentsMargins(10, 8, 10, 8)
        self.lbl_perfil_nombre = QLabel("")
        self.lbl_perfil_nombre.setProperty("class", "SectionHdr")
        vd.addWidget(self.lbl_perfil_nombre)
        self.lbl_perfil_desc = QLabel("")
        self.lbl_perfil_desc.setWordWrap(True)
        vd.addWidget(self.lbl_perfil_desc)

        self.tv_alias = QTableView()
        _estilo_tabla_base(self.tv_alias)
        self.mod_alias = ModeloTablaPandas()
        self.tv_alias.setModel(self.mod_alias)
        self.tv_alias.setFixedHeight(230)
        vd.addWidget(self.tv_alias)

        self.lbl_reglas_dc = QLabel("")
        self.lbl_reglas_dc.setWordWrap(True)
        self.lbl_reglas_dc.setStyleSheet("color: #000080; font-weight: 600; font-size: 8.2pt;")
        vd.addWidget(self.lbl_reglas_dc)

        sql_hdr_row = QHBoxLayout()
        sql_hdr_row.addWidget(QLabel("CONSULTA SQL DE EXTRACCIÓN (SOLO LECTURA)"))
        sql_hdr_row.addStretch(1)
        self.btn_copiar_sql = QPushButton("Copiar SQL al portapapeles")
        self.btn_copiar_sql.clicked.connect(self._copiar_sql)
        sql_hdr_row.addWidget(self.btn_copiar_sql)
        vd.addLayout(sql_hdr_row)

        self.txt_sql = QPlainTextEdit()
        self.txt_sql.setReadOnly(True)
        self.txt_sql.setStyleSheet('font-family: "Consolas", monospace; font-size: 8.5pt;')
        vd.addWidget(self.txt_sql, 1)
        splitter.addWidget(card_der)
        splitter.setSizes([600, 740])

        if self._pids:
            self.tv_cat.selectRow(0)
            self._mostrar_perfil(0)

    def _mostrar_perfil(self, fila: int) -> None:
        if not (0 <= fila < len(self._pids)):
            return
        p = self.perfiles[self._pids[fila]]
        self.lbl_perfil_nombre.setText(f"{p['nombre'].upper()} · {p.get('motor_origen', '')}")
        self.lbl_perfil_desc.setText(p.get("descripcion", "").strip())

        df_alias = pd.DataFrame([
            {"Columna estándar": std, "Alias reconocidos": ", ".join(aliases)}
            for std, aliases in (p.get("aliases") or {}).items()
        ])
        self.mod_alias.actualizar_df(df_alias)
        _auto_ajustar_columnas(self.tv_alias, 420)

        notas: list[str] = []
        if p.get("debito_credito_pares"):
            notas.append("Débito/Crédito: " + ", ".join(" / ".join(par) for par in p["debito_credito_pares"]))
        if p.get("indicador_dc"):
            ind = p["indicador_dc"]
            notas.append(f"Indicador D/H: {', '.join(ind.get('columnas', []))} (créditos: {', '.join(ind.get('valores_credito', []))})")
        self.lbl_reglas_dc.setText(" · ".join(notas) if notas else "Columna directa de monto con signo o absoluto.")

        consultas = p.get("consultas_sql") or []
        if consultas:
            bloque = "\n\n".join(f"-- {q['titulo']}\n{q['sql'].strip()}" for q in consultas)
            self.txt_sql.setPlainText(bloque)
            self.btn_copiar_sql.setEnabled(True)
        else:
            self.txt_sql.setPlainText("-- Este ERP se importa directamente mediante exportación CSV, TXT o Excel desde sus reportes contables.")
            self.btn_copiar_sql.setEnabled(False)

    def _copiar_sql(self) -> None:
        QGuiApplication.clipboard().setText(self.txt_sql.toPlainText())


class VistaBitacoraWidget(QWidget):
    """Trazabilidad encadenada SHA-256, control de archivos y exportación Excel."""

    solicitar_guardar_excel = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._carpeta_actual: Path | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        kpi_row = QHBoxLayout()
        self.kpis = [
            TarjetaKPI("Último paquete", "—"),
            TarjetaKPI("Fuentes importadas", "—"),
            TarjetaKPI("Eventos en bitácora", "—"),
            TarjetaKPI("Integridad SHA-256", "Sin ejecución"),
        ]
        for k in self.kpis:
            kpi_row.addWidget(k)
        lay.addLayout(kpi_row)

        acc_row = QHBoxLayout()
        self.btn_excel = QPushButton("Guardar Cédula Excel…")
        self.btn_excel.setIcon(icono_cuadra("excel", 18))
        self.btn_excel.setEnabled(False)
        self.btn_excel.clicked.connect(self.solicitar_guardar_excel.emit)
        self.btn_carpeta = QPushButton("Abrir carpeta de resultados")
        self.btn_carpeta.setEnabled(False)
        self.btn_carpeta.clicked.connect(self._abrir_carpeta)
        acc_row.addWidget(self.btn_excel)
        acc_row.addWidget(self.btn_carpeta)
        acc_row.addStretch(1)
        lay.addLayout(acc_row)

        self.tabs = QTabWidget()
        self.tv_ctrl = QTableView()
        _estilo_tabla_base(self.tv_ctrl)
        self.mod_ctrl = ModeloTablaPandas()
        self.tv_ctrl.setModel(self.mod_ctrl)

        self.tv_reg = QTableView()
        _estilo_tabla_base(self.tv_reg)
        self.mod_reg = ModeloTablaPandas()
        self.tv_reg.setModel(self.mod_reg)

        self.tabs.addTab(self.tv_ctrl, "Control de archivos importados")
        self.tabs.addTab(self.tv_reg, "Registro encadenado SHA-256")
        lay.addWidget(self.tabs, 1)

    def actualizar_corrida(self, corrida: Corrida) -> None:
        self._carpeta_actual = corrida.carpeta
        integra = corrida.bitacora.verificar()
        registros = corrida.bitacora.leer()

        self.kpis[0].actualizar(corrida.manifiesto["id"], f"Esquema {corrida.manifiesto['version']}", "neutro")
        self.kpis[1].actualizar(str(len(corrida.controles)), "", "bajo")
        self.kpis[2].actualizar(str(len(registros)), "", "bajo")
        self.kpis[3].actualizar("ÍNTEGRA" if integra else "ALTERADA", "", "ok" if integra else "alto")

        self.btn_excel.setEnabled(corrida.cedula.exists())
        self.btn_carpeta.setEnabled(corrida.carpeta.exists())

        df_ctrl = pd.DataFrame([
            {
                "Archivo": c["archivo"],
                "Tabla": c["tabla"],
                "Filas": c["filas"],
                "Excluidas": c.get("filas_excluidas", 0),
                "Codificación": c.get("codificacion", "Excel"),
                "ERP": c.get("perfil_erp") or "Genérico",
                "SHA-256": c["sha256"],
                "Transformaciones": " | ".join(c.get("transformaciones", [])) or "Ninguna",
            }
            for c in corrida.controles
        ])
        self.mod_ctrl.actualizar_df(df_ctrl)
        _auto_ajustar_columnas(self.tv_ctrl, 340)

        df_reg = pd.DataFrame([
            {
                "Fecha y hora (UTC)": r["fecha_hora_utc"],
                "Usuario": r["usuario"],
                "Evento": r["evento"],
                "Detalle": r["datos"].get("prueba") or r["datos"].get("archivo") or r["datos"].get("tabla") or "",
                "Hash SHA-256": r["hash"],
            }
            for r in registros
        ])
        self.mod_reg.actualizar_df(df_reg)
        _auto_ajustar_columnas(self.tv_reg, 360)

    def _abrir_carpeta(self) -> None:
        if self._carpeta_actual and self._carpeta_actual.exists():
            QDesktopServices.openUrl(self._carpeta_actual.as_uri())


class VistaCopilotoWidget(QWidget):
    """Copiloto sin internet: español -> SQL SELECT visible -> aprobación -> DuckDB + borrador NIA."""

    def __init__(self, proveedor_contexto, al_ejecutar_bitacora=None, parent=None) -> None:
        super().__init__(parent)
        self._proveedor_contexto = proveedor_contexto
        self._al_ejecutar_bitacora = al_ejecutar_bitacora
        self._propuesta_actual: PropuestaCopiloto | None = None
        self._archivo_propio: dict[str, Path] = {}
        self._df_resultado = pd.DataFrame()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Panel superior: Origen + Pregunta + SQL propuesto
        card_top = QFrame()
        card_top.setProperty("class", "PanelCard")
        vt = QVBoxLayout(card_top)
        vt.setContentsMargins(10, 8, 10, 8)
        vt.setSpacing(6)

        hdr = QLabel("COPILOTO ANALÍTICO 100 % SIN INTERNET · EL COPILOTO PROPONE, DUCKDB CALCULA Y EL AUDITOR APRUEBA")
        hdr.setProperty("class", "SectionHdr")
        vt.addWidget(hdr)

        fuentes_row = QHBoxLayout()
        self.lbl_fuentes = QLabel("Fuente activa: se usarán las tablas cargadas en el encargo (o ejemplo sintético si no hay carga).")
        self.lbl_fuentes.setStyleSheet("color: #111111; font-size: 8.2pt; font-weight: 600;")
        btn_otro = QPushButton("Cargar archivo externo para consultar…")
        btn_otro.clicked.connect(self._cargar_archivo_propio)
        self.btn_limpiar_arch = QPushButton("Usar tablas del encargo")
        self.btn_limpiar_arch.clicked.connect(self._usar_tablas_encargo)
        self.btn_limpiar_arch.setVisible(False)
        fuentes_row.addWidget(self.lbl_fuentes, 1)
        fuentes_row.addWidget(btn_otro)
        fuentes_row.addWidget(self.btn_limpiar_arch)
        vt.addLayout(fuentes_row)

        sug_row = QHBoxLayout()
        sug_row.setSpacing(5)
        for etq, preg in CONSULTAS_SUGERIDAS:
            b = QPushButton(etq)
            b.clicked.connect(lambda _=False, p=preg: self._usar_sugerencia(p))
            sug_row.addWidget(b)
        vt.addLayout(sug_row)

        q_row = QHBoxLayout()
        self.edt_pregunta = QLineEdit()
        self.edt_pregunta.setPlaceholderText(
            "Pregunta en español: ej. 'asientos mayores a 25,000 en noviembre' o 'resumen por usuario'…"
        )
        self.edt_pregunta.returnPressed.connect(self.proponer_sql)
        self.btn_proponer = QPushButton("1 · Proponer SQL (visible)")
        self.btn_proponer.clicked.connect(self.proponer_sql)
        q_row.addWidget(self.edt_pregunta, 1)
        q_row.addWidget(self.btn_proponer)
        vt.addLayout(q_row)

        self.lbl_explicacion = QLabel("Propuesta SQL lista para inspección y edición antes de ejecutar:")
        self.lbl_explicacion.setStyleSheet("color: #000080; font-size: 8.1pt; font-weight: 600;")
        vt.addWidget(self.lbl_explicacion)

        sql_split = QHBoxLayout()
        self.txt_sql = QPlainTextEdit()
        self.txt_sql.setFixedHeight(105)
        self.txt_sql.setStyleSheet('font-family: "Consolas", monospace; font-size: 8.8pt;')
        self.txt_sql.setPlaceholderText("-- El SQL SELECT propuesto aparecerá aquí para que lo revises o ajustes…")
        sql_split.addWidget(self.txt_sql, 1)

        acc_v = QVBoxLayout()
        self.btn_aprobar = QPushButton("2 · Aprobar y ejecutar en DuckDB")
        self.btn_aprobar.setObjectName("BtnPrimary")
        self.btn_aprobar.setIcon(icono_cuadra("correr", 18))
        self.btn_aprobar.clicked.connect(self.aprobar_y_ejecutar)
        self.btn_copiar_sql = QPushButton("Copiar SQL")
        self.btn_copiar_sql.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.txt_sql.toPlainText()))
        acc_v.addWidget(self.btn_aprobar)
        acc_v.addWidget(self.btn_copiar_sql)
        acc_v.addStretch(1)
        sql_split.addLayout(acc_v)
        vt.addLayout(sql_split)

        lay.addWidget(card_top)

        # Panel inferior: Tabla determinista + Borrador NIA
        splitter = QSplitter(Qt.Orientation.Horizontal)

        card_res = QFrame()
        card_res.setProperty("class", "PanelCard")
        vr = QVBoxLayout(card_res)
        vr.setContentsMargins(10, 8, 10, 8)
        res_hdr = QHBoxLayout()
        self.lbl_res_info = QLabel("RESULTADO DETERMINISTA (DUCKDB)")
        self.lbl_res_info.setProperty("class", "SectionHdr")
        btn_exp_csv = QPushButton("Exportar tabla CSV…")
        btn_exp_csv.clicked.connect(self._exportar_csv)
        res_hdr.addWidget(self.lbl_res_info, 1)
        res_hdr.addWidget(btn_exp_csv)
        vr.addLayout(res_hdr)

        self.tv_res = QTableView()
        _estilo_tabla_base(self.tv_res)
        self.mod_res = ModeloTablaPandas()
        self.tv_res.setModel(self.mod_res)
        vr.addWidget(self.tv_res, 1)
        splitter.addWidget(card_res)

        card_bor = QFrame()
        card_bor.setProperty("class", "PanelCard")
        vb = QVBoxLayout(card_bor)
        vb.setContentsMargins(10, 8, 10, 8)
        bor_hdr = QHBoxLayout()
        lbl_bor = QLabel("BORRADOR DE HALLAZGO (NIA)")
        lbl_bor.setProperty("class", "SectionHdr")
        btn_copiar_b = QPushButton("Copiar borrador")
        btn_copiar_b.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.txt_borrador.toPlainText()))
        bor_hdr.addWidget(lbl_bor, 1)
        bor_hdr.addWidget(btn_copiar_b)
        vb.addLayout(bor_hdr)

        self.txt_borrador = QPlainTextEdit()
        self.txt_borrador.setPlaceholderText("Al aprobar y ejecutar la consulta, el borrador de papel de trabajo NIA aparecerá aquí.")
        vb.addWidget(self.txt_borrador, 1)
        splitter.addWidget(card_bor)
        splitter.setSizes([820, 520])

        lay.addWidget(splitter, 1)

    def actualizar_info_fuentes(self) -> None:
        if self._archivo_propio:
            txt = ", ".join(f"{t}={p.name}" for t, p in self._archivo_propio.items())
            self.lbl_fuentes.setText(f"Archivo externo activo para Copiloto: {txt}")
            self.btn_limpiar_arch.setVisible(True)
            return
        fuentes, _, _, _ = self._proveedor_contexto()
        self.btn_limpiar_arch.setVisible(False)
        if fuentes:
            desc = ", ".join(f"{t} ({Path(r).name if isinstance(r, (Path, str)) and not es_uri_sql(r) else 'SQL'})" for t, r in fuentes.items())
            self.lbl_fuentes.setText(f"Tablas activas desde el encargo: {desc}")
        else:
            self.lbl_fuentes.setText("Sin archivos cargados aún: al proponer/ejecutar se cargará el diario sintético de demostración.")

    def _cargar_archivo_propio(self) -> None:
        ruta_str, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo para Copiloto", str(RAIZ), _filtro_archivos_dialogo())
        if ruta_str:
            p = Path(ruta_str)
            tabla = "extracto" if p.suffix.lower() == ".pdf" else "mayor"
            self._archivo_propio = {tabla: p}
            self.actualizar_info_fuentes()

    def _usar_tablas_encargo(self) -> None:
        self._archivo_propio.clear()
        self.actualizar_info_fuentes()

    def _usar_sugerencia(self, pregunta: str) -> None:
        self.edt_pregunta.setText(pregunta)
        self.proponer_sql()

    def _resolver_fuentes(self) -> tuple[dict, dict, dict, Any]:
        fuentes_enc, opciones_enc, encargo, bitacora = self._proveedor_contexto()
        if self._archivo_propio:
            return dict(self._archivo_propio), {}, encargo, bitacora
        if fuentes_enc:
            return fuentes_enc, opciones_enc, encargo, bitacora
        mayor, balanza = generar_diario_asientos(RAIZ / "datos" / "ejemplo")
        return {"mayor": mayor, "balanza": balanza}, {}, encargo, bitacora

    def proponer_sql(self) -> None:
        pregunta = self.edt_pregunta.text().strip()
        if not pregunta:
            QMessageBox.information(self, "Copiloto SQL", "Escribe una pregunta o selecciona una consulta rápida.")
            return
        fuentes, _, encargo, _ = self._resolver_fuentes()
        tablas_disp = {t: [] for t in fuentes}
        prop = proponer_consulta_sql(pregunta, tablas_disp, encargo)
        self._propuesta_actual = prop
        self.txt_sql.setPlainText(prop.sql)
        self.lbl_explicacion.setText(f"Propuesta [{', '.join(prop.nia)} · tabla `{prop.tabla_objetivo}`]: {prop.explicacion}")

    def aprobar_y_ejecutar(self) -> None:
        sql = self.txt_sql.toPlainText().strip()
        if not sql:
            self.proponer_sql()
            sql = self.txt_sql.toPlainText().strip()
            if not sql:
                return
        fuentes, opciones, encargo, bitacora = self._resolver_fuentes()
        try:
            con, _ = preparar_conexion_copiloto(fuentes, opciones)
            try:
                prop = self._propuesta_actual
                res = ejecutar_propuesta_aprobada(
                    con,
                    sql,
                    pregunta=self.edt_pregunta.text().strip(),
                    titulo=prop.titulo if prop else "Consulta SQL aprobada",
                    nia=prop.nia if prop else ["NIA 500", "NIA 230"],
                    explicacion=prop.explicacion if prop else "",
                    bitacora=bitacora,
                    encargo=encargo,
                )
            finally:
                con.close()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Validación / ejecución SQL", str(exc))
            return

        self._df_resultado = formatear_fechas_df(res.tabla)
        self.mod_res.actualizar_df(self._df_resultado)
        _auto_ajustar_columnas(self.tv_res, 300)
        self.lbl_res_info.setText(f"RESULTADO DETERMINISTA · {len(res.tabla):,} FILA(S) · SHA-256 {res.sql_sha256[:12]}…")
        self.txt_borrador.setPlainText(res.borrador)
        if self._al_ejecutar_bitacora:
            self._al_ejecutar_bitacora(res)

    def _exportar_csv(self) -> None:
        if self._df_resultado.empty:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Exportar resultado SQL", str(RAIZ / "consulta_copiloto.csv"), "CSV (*.csv)")
        if dest:
            self._df_resultado.to_csv(dest, index=False)


class DialogoPerfilAuditor(QDialog):
    """Permite identificar al auditor activo y su rol (Preparador, Revisor o Socio)."""

    def __init__(self, auditor: str, rol: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Perfil y Rol del Auditor (NIA 220)")
        self.setWindowIcon(icono_cuadra("encargos", 28))
        self.resize(390, 165)

        lay = QVBoxLayout(self)
        fl = QFormLayout()
        self.edt_auditor = QLineEdit(auditor)
        self.cmb_rol = QComboBox()
        self.cmb_rol.addItems(list(ROLES_FIRMA))
        if rol in ROLES_FIRMA:
            self.cmb_rol.setCurrentText(rol)
        fl.addRow("Auditor / Iniciales:", self.edt_auditor)
        fl.addRow("Rol activo:", self.cmb_rol)
        lay.addLayout(fl)

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)

    def resultado(self) -> tuple[str, str]:
        return self.edt_auditor.text().strip() or _usuario_actual(), self.cmb_rol.currentText()


class VistaPortafolioWidget(QWidget):
    """Portafolio de encargos (.yaml), historial de corridas y flujo de revisión por roles (NIA 220/230)."""

    cargar_encargo_en_sesion = Signal(dict)

    def __init__(
        self,
        proveedor_sesion,
        al_actualizar_revision=None,
        proveedor_seguridad=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._proveedor_sesion = proveedor_sesion
        self._al_actualizar_revision = al_actualizar_revision
        self._proveedor_seguridad = proveedor_seguridad
        self._encargos: list[dict] = []
        self._corridas_hist: list[dict] = []
        self._carpeta_activa: Path | None = None
        self._corrida_obj: Corrida | None = None
        self._pruebas_visibles: list[dict] = []

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(splitter)

        # Panel izquierdo: Portafolio de encargos + Historial de corridas
        izq = QWidget()
        vi = QVBoxLayout(izq)
        vi.setContentsMargins(0, 0, 4, 0)
        vi.setSpacing(8)

        card_enc = QFrame()
        card_enc.setProperty("class", "PanelCard")
        ve = QVBoxLayout(card_enc)
        ve.setContentsMargins(10, 8, 10, 8)
        hdr_e = QLabel("1 · PORTAFOLIO DE ENCARGOS (encargos/*.yaml)")
        hdr_e.setProperty("class", "SectionHdr")
        ve.addWidget(hdr_e)

        self.tv_encargos = QTableView()
        _estilo_tabla_base(self.tv_encargos)
        self.tv_encargos.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mod_encargos = ModeloTablaPandas()
        self.tv_encargos.setModel(self.mod_encargos)
        self.tv_encargos.setFixedHeight(190)
        ve.addWidget(self.tv_encargos)

        btn_enc_row = QHBoxLayout()
        btn_cargar_e = QPushButton("Cargar encargo en sesión")
        btn_cargar_e.clicked.connect(self._cargar_encargo_seleccionado)
        btn_guardar_e = QPushButton("Guardar encargo actual como YAML…")
        btn_guardar_e.clicked.connect(self._guardar_encargo_dialogo)
        btn_enc_row.addWidget(btn_cargar_e)
        btn_enc_row.addWidget(btn_guardar_e)
        ve.addLayout(btn_enc_row)
        vi.addWidget(card_enc)

        card_hist = QFrame()
        card_hist.setProperty("class", "PanelCard")
        vh = QVBoxLayout(card_hist)
        vh.setContentsMargins(10, 8, 10, 8)
        hdr_h_row = QHBoxLayout()
        hdr_h = QLabel("2 · HISTORIAL DE CORRIDAS AUDITADAS (salidas/)")
        hdr_h.setProperty("class", "SectionHdr")
        btn_ref_h = QPushButton("Actualizar")
        btn_ref_h.clicked.connect(self.refrescar_portafolio)
        hdr_h_row.addWidget(hdr_h, 1)
        hdr_h_row.addWidget(btn_ref_h)
        vh.addLayout(hdr_h_row)

        self.tv_hist = QTableView()
        _estilo_tabla_base(self.tv_hist)
        self.tv_hist.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mod_hist = ModeloTablaPandas()
        self.tv_hist.setModel(self.mod_hist)
        self.tv_hist.selectionModel().currentRowChanged.connect(lambda idx, _: self._seleccionar_corrida_hist(idx.row()))
        vh.addWidget(self.tv_hist, 1)
        vi.addWidget(card_hist, 1)

        splitter.addWidget(izq)

        # Panel derecho: Revisión de pruebas y Firmas por Rol
        der = QFrame()
        der.setProperty("class", "PanelCard")
        vd = QVBoxLayout(der)
        vd.setContentsMargins(10, 8, 10, 8)
        vd.setSpacing(8)

        self.lbl_rev_titulo = QLabel("3 · REVISIÓN Y FIRMA DEL PAPEL DE TRABAJO (NIA 220 / 230)")
        self.lbl_rev_titulo.setProperty("class", "SectionHdr")
        vd.addWidget(self.lbl_rev_titulo)

        roles_row = QHBoxLayout()
        self.kpi_roles: dict[str, TarjetaKPI] = {}
        for rol in ROLES_FIRMA:
            card_r = TarjetaKPI(rol.upper(), "Pendiente", "Sin firma")
            self.kpi_roles[rol] = card_r
            roles_row.addWidget(card_r)
        self.kpi_bloqueo = TarjetaKPI("Estado papel", "Sin selección", "")
        roles_row.addWidget(self.kpi_bloqueo)
        vd.addLayout(roles_row)

        self.tv_rev = QTableView()
        _estilo_tabla_base(self.tv_rev)
        self.tv_rev.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.mod_rev = ModeloTablaPandas()
        self.tv_rev.setModel(self.mod_rev)
        self.tv_rev.selectionModel().currentRowChanged.connect(lambda idx, _: self._cargar_prueba_en_editor(idx.row()))
        vd.addWidget(self.tv_rev, 1)

        box_ed = QFrame()
        box_ed.setObjectName("BoxEditor")
        box_ed.setStyleSheet(
            "#BoxEditor { background-color: #D4D0C8; border-top: 1px solid #808080; "
            "border-left: 1px solid #808080; border-right: 1px solid #FFFFFF; "
            "border-bottom: 1px solid #FFFFFF; border-radius: 0px; }"
        )
        ved = QVBoxLayout(box_ed)
        ved.setContentsMargins(10, 8, 10, 8)
        ved.setSpacing(6)

        ed_top = QHBoxLayout()
        self.lbl_prueba_sel = QLabel("Selecciona una prueba arriba para documentar su conclusión:")
        self.lbl_prueba_sel.setStyleSheet("font-weight: 700; color: #000080; background: transparent; border: none;")
        self.cmb_estado_rev = QComboBox()
        self.cmb_estado_rev.addItems(list(ESTADOS_REVISION))
        ed_top.addWidget(self.lbl_prueba_sel, 1)
        ed_top.addWidget(QLabel("Estado:"))
        ed_top.addWidget(self.cmb_estado_rev)
        ved.addLayout(ed_top)

        self.txt_conclusion = QPlainTextEdit()
        self.txt_conclusion.setFixedHeight(64)
        self.txt_conclusion.setPlaceholderText("Conclusión de auditoría y evidencia verificada para el papel de trabajo…")
        ved.addWidget(self.txt_conclusion)

        btn_rev_row = QHBoxLayout()
        self.btn_guardar_rev = QPushButton("Guardar conclusión de prueba")
        self.btn_guardar_rev.clicked.connect(self._guardar_conclusion_actual)
        self.btn_marcar_ok = QPushButton("Aclarar pruebas sin hallazgos")
        self.btn_marcar_ok.clicked.connect(self._marcar_sin_hallazgos)
        self.btn_firmar = QPushButton("Firmar como Preparador")
        self.btn_firmar.setObjectName("BtnPrimary")
        self.btn_firmar.clicked.connect(self._firmar_rol_activo)
        self.btn_reabrir = QPushButton("Reabrir papel…")
        self.btn_reabrir.clicked.connect(self._reabrir_papel)
        self.btn_reabrir.setVisible(False)
        self.btn_seg_corrida = QPushButton("Seguridad / Bóveda ▾")
        self.btn_seg_corrida.setToolTip("Verificar sello Ed25519, cifrar/descifrar bóveda o exportar diagnóstico anonimizado")
        self.btn_seg_corrida.clicked.connect(self._mostrar_menu_seguridad_corrida)
        btn_rev_row.addWidget(self.btn_guardar_rev)
        btn_rev_row.addWidget(self.btn_marcar_ok)
        btn_rev_row.addWidget(self.btn_firmar)
        btn_rev_row.addWidget(self.btn_reabrir)
        btn_rev_row.addWidget(self.btn_seg_corrida)
        ved.addLayout(btn_rev_row)
        vd.addWidget(box_ed)

        splitter.addWidget(der)
        splitter.setSizes([520, 860])

    def refrescar_portafolio(self) -> None:
        _, auditor, rol_activo, _ = self._proveedor_sesion()
        self.btn_firmar.setText(f"Firmar como {rol_activo} ({auditor})")

        self._encargos = listar_encargos()
        df_enc = pd.DataFrame([
            {
                "Archivo": e["archivo"],
                "Cliente": e["cliente"],
                "Cierre": e["fecha_cierre"],
                "Marco": e["marco"],
                "Materialidad": e["materialidad"],
            }
            for e in self._encargos
        ])
        self.mod_encargos.actualizar_df(df_enc)
        _auto_ajustar_columnas(self.tv_encargos, 130)

        self._corridas_hist = listar_corridas_recientes()
        df_hist = pd.DataFrame([
            {
                "Corrida": c["nombre"],
                "Paquete": c["paquete"],
                "Cliente": c["cliente"],
                "Firmas": c["estado_firmas"],
                "SHA-256": "ÍNTEGRO" if c["sha256_integro"] else "ALTERADO",
            }
            for c in self._corridas_hist
        ])
        self.mod_hist.actualizar_df(df_hist)
        _auto_ajustar_columnas(self.tv_hist, 125)

    def vincular_corrida_activa(self, corrida: Corrida | None) -> None:
        self._corrida_obj = corrida
        if corrida is not None:
            self._carpeta_activa = corrida.carpeta
        self.refrescar_portafolio()
        if self._carpeta_activa and self._carpeta_activa.exists():
            self._cargar_panel_revision(self._carpeta_activa)

    def _cargar_encargo_seleccionado(self) -> None:
        idx = self.tv_encargos.currentIndex()
        fila = idx.row() if idx.isValid() else (0 if self._encargos else -1)
        if not (0 <= fila < len(self._encargos)):
            return
        datos = dict(self._encargos[fila]["datos"])
        self.cargar_encargo_en_sesion.emit(datos)

    def _guardar_encargo_dialogo(self) -> None:
        enc_actual, _, _, _ = self._proveedor_sesion()
        sugerido = str((RAIZ / "encargos" / "nuevo-encargo.yaml"))
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar parámetros de encargo YAML", sugerido, "YAML (*.yaml)")
        if not destino:
            return
        guardar_encargo_yaml(enc_actual, Path(destino))
        self.refrescar_portafolio()

    def _seleccionar_corrida_hist(self, fila: int) -> None:
        if not (0 <= fila < len(self._corridas_hist)):
            return
        carpeta = self._corridas_hist[fila]["carpeta"]
        if self._corrida_obj and self._corrida_obj.carpeta != carpeta:
            self._corrida_obj = None
        self._cargar_panel_revision(carpeta)

    def _cargar_panel_revision(self, carpeta: Path) -> None:
        info = resumen_corrida_carpeta(carpeta)
        if not info:
            return
        self._carpeta_activa = carpeta
        self._pruebas_visibles = info["pruebas_ejecutadas"]
        rev = cargar_revisiones(carpeta, [p["id"] for p in self._pruebas_visibles if p["id"]])
        firmas = rev.get("firmas", {})
        bloqueado = bool(rev.get("bloqueado"))

        self.lbl_rev_titulo.setText(f"3 · REVISIÓN Y FIRMAS · {info['paquete']} ({carpeta.name})")
        for rol in ROLES_FIRMA:
            if rol in firmas:
                f = firmas[rol]
                self.kpi_roles[rol].actualizar(f["auditor"], f["fecha_utc"], "ok")
            else:
                self.kpi_roles[rol].actualizar("Pendiente", "Sin firma", "neutro")

        integra = info["sha256_integro"]
        ruta_sello = carpeta / "sello.json"
        est_nia = estado_archivo_nia230(
            carpeta,
            ventana_dias=int(rev.get("ventana_archivo_dias") or 60),
        )
        if ruta_sello.exists():
            res_sello = verificar_sello_anclado(carpeta, RAIZ)
            sello_ok = bool(res_sello.get("valido"))
            sub_nia = (
                f"SELLO Ed25519 VÁLIDO · NIA 230: {est_nia['dias_restantes']}d rest."
                if (sello_ok and est_nia.get("cerrado"))
                else ("SELLO Ed25519 VÁLIDO" if sello_ok else "SELLO INVÁLIDO")
            )
            self.kpi_bloqueo.actualizar(
                "CERRADO" if (bloqueado and sello_ok) else ("ALTERADO" if not sello_ok else "ABIERTO"),
                sub_nia,
                "ok" if sello_ok else "alto",
            )
        else:
            sub_base = "SHA-256 ÍNTEGRO" if integra else "BITÁCORA ALTERADA"
            if bloqueado and est_nia.get("cerrado") and integra:
                sub_base = f"SHA-256 ÍNTEGRO · NIA 230: {est_nia['dias_restantes']}d rest."
            self.kpi_bloqueo.actualizar(
                "CERRADO" if bloqueado else "ABIERTO",
                sub_base,
                "ok" if (integra and bloqueado) else ("bajo" if integra else "alto"),
            )

        self.btn_guardar_rev.setEnabled(not bloqueado)
        self.btn_marcar_ok.setEnabled(not bloqueado)
        self.btn_reabrir.setVisible(bloqueado)

        filas_rev = []
        por_p = rev.get("por_prueba", {})
        for p in self._pruebas_visibles:
            pid = p["id"]
            rp = por_p.get(pid, {})
            filas_rev.append({
                "Prueba": pid,
                "Hallazgos": p["filas"],
                "Estado revisión": rp.get("estado", "Pendiente"),
                "Auditor": f"{rp['auditor']} ({rp['rol']})" if rp.get("auditor") else "",
                "Conclusión": rp.get("conclusion", ""),
            })
        self.mod_rev.actualizar_df(pd.DataFrame(filas_rev))
        _auto_ajustar_columnas(self.tv_rev, 320)
        if filas_rev:
            self.tv_rev.selectRow(0)
            self._cargar_prueba_en_editor(0)

    def _cargar_prueba_en_editor(self, fila: int) -> None:
        if not (0 <= fila < len(self._pruebas_visibles)) or not self._carpeta_activa:
            return
        pid = self._pruebas_visibles[fila]["id"]
        rev = cargar_revisiones(self._carpeta_activa, [pid])
        rp = rev["por_prueba"].get(pid, {})
        self.lbl_prueba_sel.setText(f"Prueba seleccionada: {pid}")
        est = rp.get("estado", "Pendiente")
        if est in ESTADOS_REVISION:
            self.cmb_estado_rev.setCurrentText(est)
        self.txt_conclusion.setPlainText(rp.get("conclusion", ""))

    def _bitacora_activa(self) -> Bitacora | None:
        if not self._carpeta_activa:
            return None
        _, auditor, _, _ = self._proveedor_sesion()
        return Bitacora(self._carpeta_activa / "bitacora.jsonl", usuario=auditor)

    def _regenerar_cedula_activa(self) -> None:
        if self._corrida_obj and self._carpeta_activa and self._corrida_obj.carpeta == self._carpeta_activa:
            actualizar_cedula_corrida(self._corrida_obj)

    def _post_cambio_revision(self, regenerar: bool = True) -> None:
        if regenerar:
            self._regenerar_cedula_activa()
        if self._carpeta_activa:
            self._cargar_panel_revision(self._carpeta_activa)
        self.refrescar_portafolio()
        if self._al_actualizar_revision:
            self._al_actualizar_revision()

    def _guardar_conclusion_actual(self) -> None:
        if not self._carpeta_activa or not self._pruebas_visibles:
            return
        idx = self.tv_rev.currentIndex()
        fila = idx.row() if idx.isValid() else 0
        if not (0 <= fila < len(self._pruebas_visibles)):
            return
        pid = self._pruebas_visibles[fila]["id"]
        _, auditor, rol, _ = self._proveedor_sesion()
        try:
            registrar_revision_prueba(
                self._carpeta_activa,
                pid,
                self.cmb_estado_rev.currentText(),
                self.txt_conclusion.toPlainText(),
                auditor,
                rol,
                bitacora=self._bitacora_activa(),
            )
            self._post_cambio_revision()
        except ValueError as exc:
            QMessageBox.warning(self, "Revisión de prueba", str(exc))

    def _marcar_sin_hallazgos(self) -> None:
        if not self._carpeta_activa or not self._pruebas_visibles:
            return
        _, auditor, rol, _ = self._proveedor_sesion()
        bit = self._bitacora_activa()
        try:
            for p in self._pruebas_visibles:
                if int(p["filas"]) == 0:
                    registrar_revision_prueba(
                        self._carpeta_activa,
                        p["id"],
                        "Aclarado con evidencia",
                        "Sin excepciones detectadas por el motor determinista.",
                        auditor,
                        rol,
                        bitacora=bit,
                    )
            self._post_cambio_revision()
        except ValueError as exc:
            QMessageBox.warning(self, "Revisión masiva", str(exc))

    def _firmar_rol_activo(self) -> None:
        if not self._carpeta_activa:
            QMessageBox.information(self, "Firmas", "Ejecuta o selecciona una corrida antes de firmar.")
            return
        _, auditor, rol, _ = self._proveedor_sesion()
        sesion_act, gestor = self._proveedor_seguridad() if self._proveedor_seguridad else (None, None)
        politicas = gestor.politicas() if gestor else {}
        exigir_seg = bool(politicas.get("segregacion_estricta", True)) if sesion_act is not None else False
        ventana_dias = int(politicas.get("ventana_archivo_dias", 60))
        ids = [p["id"] for p in self._pruebas_visibles if p["id"]]
        try:
            firmar_papel_trabajo(
                self._carpeta_activa,
                rol,
                auditor,
                observacion=f"Firma desde aplicación local como {rol}",
                bitacora=self._bitacora_activa(),
                pruebas_ejecutadas=ids,
                exigir_segregacion=exigir_seg,
                sesion=sesion_act,
                ventana_archivo_dias=ventana_dias,
                regenerar_cedula=self._regenerar_cedula_activa,
            )
            self._post_cambio_revision(regenerar=False)
        except ValueError as exc:
            QMessageBox.warning(self, "Control de calidad NIA 220", str(exc))

    def _reabrir_papel(self) -> None:
        if not self._carpeta_activa:
            return
        from PySide6.QtWidgets import QInputDialog
        motivo, ok = QInputDialog.getText(
            self, "Reabrir papel de trabajo", "Motivo obligatorio (quedará en bitácora SHA-256):"
        )
        if not ok or not motivo.strip():
            return
        _, auditor, rol, _ = self._proveedor_sesion()
        sesion_act, _ = self._proveedor_seguridad() if self._proveedor_seguridad else (None, None)
        try:
            reabrir_papel_trabajo(
                self._carpeta_activa,
                motivo,
                auditor,
                rol=rol,
                bitacora=self._bitacora_activa(),
                sesion=sesion_act,
            )
            self._post_cambio_revision()
        except ValueError as exc:
            QMessageBox.warning(self, "Reapertura", str(exc))

    def _mostrar_menu_seguridad_corrida(self) -> None:
        if not self._carpeta_activa:
            QMessageBox.information(self, "Seguridad de corrida", "Selecciona una corrida primero.")
            return
        menu = QMenu(self)
        act_ver = menu.addAction("Verificar sello Ed25519 y cadena SHA-256")
        act_cif = menu.addAction("Cifrar corrida en bóveda (Windows DPAPI)")
        act_dec = menu.addAction("Descifrar bóveda (.folioenc)")
        act_ano = menu.addAction("Exportar diagnóstico anonimizado (Ley 81)…")

        act_ver.triggered.connect(self._accion_verificar_sello)
        act_cif.triggered.connect(self._accion_cifrar_corrida_dpapi)
        act_dec.triggered.connect(self._accion_descifrar_corrida)
        act_ano.triggered.connect(self._accion_exportar_anonimizado)
        menu.exec(self.btn_seg_corrida.mapToGlobal(self.btn_seg_corrida.rect().bottomLeft()))

    def _accion_verificar_sello(self) -> None:
        if not self._carpeta_activa:
            return
        carp = self._carpeta_activa
        if (carp / "sello.json").exists():
            res = verificar_sello_anclado(carp, RAIZ)
            detalle = (
                f"Estado: {texto_estado_sello(res)}\n"
                f"Motivo: {res.get('motivo')}\n"
                f"Firmante: {res.get('usuario', '')} ({res.get('rol', '')})\n"
                f"Huella Ed25519: {res.get('huella_clave', '')}"
            )
            if res.get("valido"):
                QMessageBox.information(self, "Verificación criptográfica", detalle)
            else:
                QMessageBox.warning(self, "Alerta de integridad", detalle)
            return
        bit_ruta = carp / "bitacora.jsonl"
        integra = bit_ruta.exists() and Bitacora(bit_ruta).verificar()
        QMessageBox.information(
            self,
            "Verificación SHA-256",
            f"La corrida aún no tiene sello.json (cierre por Socio).\nCadena SHA-256 de bitácora: {'ÍNTEGRA' if integra else 'ALTERADA'}.",
        )

    def _accion_cifrar_corrida_dpapi(self) -> None:
        if not self._carpeta_activa:
            return
        try:
            generados = cifrar_carpeta_corrida(self._carpeta_activa, usar_dpapi=True, borrar_origen=False)
            QMessageBox.information(
                self,
                "Bóveda cifrada",
                f"Se generaron {len(generados)} respaldo(s) cifrado(s) .folioenc (AES-256-GCM + Windows DPAPI).",
            )
        except ErrorSeguridad as exc:
            QMessageBox.warning(self, "Bóveda cifrada", str(exc))

    def _accion_descifrar_corrida(self) -> None:
        if not self._carpeta_activa:
            return
        try:
            restaurados = descifrar_carpeta_corrida(self._carpeta_activa)
            QMessageBox.information(
                self,
                "Bóveda descifrada",
                f"Se descifraron {len(restaurados)} archivo(s) desde .folioenc.",
            )
        except ErrorSeguridad as exc:
            QMessageBox.warning(self, "Bóveda descifrada", str(exc))

    def _accion_exportar_anonimizado(self) -> None:
        if not self._carpeta_activa:
            return
        sugerido = str(self._carpeta_activa / "diagnostico_soporte_anonimizado.json")
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar diagnóstico anonimizado (Ley 81)", sugerido, "JSON (*.json)")
        if not destino:
            return
        try:
            exportar_diagnostico_anonimizado(self._carpeta_activa, destino=Path(destino))
            QMessageBox.information(self, "Diagnóstico anonimizado", f"Exportado sin PII ni montos en:\n{destino}")
        except ErrorSeguridad as exc:
            QMessageBox.warning(self, "Diagnóstico anonimizado", str(exc))


class VentanaCuadra(QMainWindow):
    """Ventana principal ejecutiva de escritorio con Cinta de Opciones estilo Excel."""

    PAQUETES_TOOLS = ("asientos-nia240", "excepciones-basicas", "ventas-fe", "bancos-conciliacion")
    TAB_DE_HERRAMIENTA = {
        "asientos-nia240": 0,
        "excepciones-basicas": 0,
        "ventas-fe": 0,
        "bancos-conciliacion": 0,
        "conectores": 1,
        "copiloto": 1,
        "muestreo-mus": 2,
        "bitacora": 3,
        "encargos": 3,
    }

    def __init__(
        self,
        sesion: SesionAutenticada | None = None,
        gestor_usuarios: GestorUsuarios | None = None,
    ) -> None:
        super().__init__()
        self.paquetes = paquetes_disponibles()
        self.perfiles = perfiles_disponibles()
        self.corridas: dict[str, Corrida] = {}
        self.ultima_corrida: Corrida | None = None
        self.herramienta_actual = "asientos-nia240"
        self._trabajador: TrabajadorEjecucion | None = None
        self.gestor_usuarios = gestor_usuarios or GestorUsuarios(RAIZ)
        self.sesion_actual: SesionAutenticada | None = sesion
        if sesion is not None:
            self.auditor_actual = sesion.nombre_completo
            self.rol_actual = sesion.rol_auditoria or sesion.perfil
        else:
            self.auditor_actual = _usuario_actual()
            self.rol_actual = "Preparador"
        self.encargo_datos: dict[str, Any] = {
            "cliente": "Cliente Demo, S.A.",
            "periodo_inicio": date(2025, 1, 1),
            "fecha_cierre": date(2025, 12, 31),
            "marco": "NIIF",
            "materialidad": 150000.0,
            "materialidad_ejecucion": 112500.0,
            "umbral_trivial": 7500.0,
            "umbral_aprobacion": 10000.0,
        }

        self.setWindowTitle(f"{NOMBRE_MARCA} · Mesa de Auditoría — {self.encargo_datos['cliente']}")
        self.setWindowIcon(icono_cuadra("logo", 36))
        self.resize(1420, 880)

        raiz_w = QWidget()
        self.setCentralWidget(raiz_w)
        v_main = QVBoxLayout(raiz_w)
        v_main.setContentsMargins(0, 0, 0, 0)
        v_main.setSpacing(0)

        self._construir_appbar(v_main)
        self._construir_cinta(v_main)

        area_trabajo = QWidget()
        v_work = QVBoxLayout(area_trabajo)
        v_work.setContentsMargins(10, 6, 10, 6)
        v_work.setSpacing(6)
        self._construir_formulabar(v_work)

        self.stack = QStackedWidget()
        self.vistas_paquetes: dict[str, VistaPaqueteWidget] = {}
        self._indice_vista: dict[str, int] = {}

        for pid in self.PAQUETES_TOOLS:
            vista = VistaPaqueteWidget(pid, self.paquetes[pid], self.perfiles, self.encargo_datos)
            vista.encargo_modificado.connect(self._sincronizar_encargo)
            vista.solicitar_ejecucion.connect(self.ejecutar_asincrono)
            idx = self.stack.addWidget(vista)
            self.vistas_paquetes[pid] = vista
            self._indice_vista[pid] = idx

        self.vista_mus = VistaMuestreoWidget()
        self._indice_vista["muestreo-mus"] = self.stack.addWidget(self.vista_mus)

        self.vista_conectores = VistaConectoresWidget(self.perfiles)
        self._indice_vista["conectores"] = self.stack.addWidget(self.vista_conectores)

        self.vista_copiloto = VistaCopilotoWidget(self._contexto_para_copiloto, self._tras_consulta_copiloto)
        self._indice_vista["copiloto"] = self.stack.addWidget(self.vista_copiloto)

        self.vista_bitacora = VistaBitacoraWidget()
        self.vista_bitacora.solicitar_guardar_excel.connect(self._guardar_cedula_dialogo)
        self._indice_vista["bitacora"] = self.stack.addWidget(self.vista_bitacora)

        self.vista_portafolio = VistaPortafolioWidget(
            self._sesion_para_portafolio,
            self._al_actualizar_revision_portafolio,
            proveedor_seguridad=self._seguridad_para_portafolio,
        )
        self.vista_portafolio.cargar_encargo_en_sesion.connect(self._aplicar_encargo_cargado)
        self._indice_vista["encargos"] = self.stack.addWidget(self.vista_portafolio)

        v_work.addWidget(self.stack, 1)
        v_main.addWidget(area_trabajo, 1)

        self._construir_statusbar()
        self.setStyleSheet(ESTILO_CUADRA_QT)
        self._timer_reloj = QTimer(self)
        self._timer_reloj.timeout.connect(self._actualizar_reloj)
        self._timer_reloj.start(1000)
        self._actualizar_reloj()
        self.seleccionar_herramienta("asientos-nia240")

    def _construir_appbar(self, parent_lay: QVBoxLayout) -> None:
        bar = QFrame()
        bar.setObjectName("AppBar")
        bar.setFixedHeight(58)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(10, 3, 10, 3)
        hb.setSpacing(6)

        titulos = QVBoxLayout()
        titulos.setContentsMargins(0, 0, 0, 0)
        titulos.setSpacing(0)
        self.lbl_brand = QLabel(f"{NOMBRE_MARCA} · {LEMA_MARCA}")
        self.lbl_brand.setObjectName("BrandBadge")
        cli_ini = self.encargo_datos["cliente"]
        cierre_ini = self.encargo_datos["fecha_cierre"]
        periodo_ini = formatear_periodo_auditado(self.encargo_datos.get("periodo_inicio"), cierre_ini)
        self.lbl_workbook_title = QLabel(f"Cliente: {cli_ini}")
        self.lbl_workbook_title.setObjectName("WorkbookTitle")
        self.lbl_workbook_sub = QLabel(
            f"Período auditado: {periodo_ini} · Marco {self.encargo_datos['marco']} · Cierre {cierre_ini.isoformat()}"
        )
        self.lbl_workbook_sub.setObjectName("WorkbookSubtitle")
        for lbl_t in (self.lbl_brand, self.lbl_workbook_title, self.lbl_workbook_sub):
            lbl_t.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            lbl_t.setMinimumWidth(140)
            titulos.addWidget(lbl_t)
        hb.addLayout(titulos, 1)

        box_constancia = QFrame()
        box_constancia.setObjectName("ConstanciaBox")
        vb_const = QVBoxLayout(box_constancia)
        vb_const.setContentsMargins(0, 0, 0, 0)
        vb_const.setSpacing(0)
        self.lbl_constancia_reloj = QLabel("")
        self.lbl_constancia_reloj.setObjectName("ConstanciaReloj")
        self.lbl_constancia_periodo = QLabel(f"PERÍODO AUDITADO: {periodo_ini}")
        self.lbl_constancia_periodo.setObjectName("ConstanciaPeriodo")
        vb_const.addWidget(self.lbl_constancia_reloj)
        vb_const.addWidget(self.lbl_constancia_periodo)
        self.box_constancia = box_constancia
        hb.addWidget(box_constancia)

        texto_perfil = (
            f"{self.sesion_actual.perfil}: {self.sesion_actual.nombre_completo}"
            if self.sesion_actual is not None
            else f"Auditor: {self.auditor_actual} · {self.rol_actual}"
        )
        self.btn_perfil = QPushButton(texto_perfil)
        self.btn_perfil.setObjectName("BtnQuick")
        self.btn_perfil.clicked.connect(self._cambiar_perfil_auditor)
        hb.addWidget(self.btn_perfil)

        self.btn_admin_seg = QPushButton("Admin Seguridad")
        self.btn_admin_seg.setObjectName("BtnQuick")
        self.btn_admin_seg.setToolTip("Panel de administración de usuarios, políticas de seguridad y bitácora de accesos")
        self.btn_admin_seg.clicked.connect(self._abrir_admin_seguridad)
        self.btn_admin_seg.setVisible(bool(self.sesion_actual and self.sesion_actual.es_admin))
        hb.addWidget(self.btn_admin_seg)

        self.btn_demo = QPushButton("Ejemplo sintético")
        self.btn_demo.setObjectName("BtnQuick")
        self.btn_demo.setToolTip("Cargar datos de ejemplo sintético (100 % local)")
        self.btn_demo.clicked.connect(self.cargar_ejemplo_sintetico)
        hb.addWidget(self.btn_demo)

        pill_offline = QLabel("SIN INTERNET")
        pill_offline.setProperty("class", "PillInfo")
        pill_offline.setToolTip("Ejecución local 100 % sin internet")
        hb.addWidget(pill_offline)

        self.lbl_pill_bitacora = QLabel("BITÁCORA SIN EJECUCIÓN")
        self.lbl_pill_bitacora.setProperty("class", "PillInfo")
        hb.addWidget(self.lbl_pill_bitacora)

        self.btn_top_excel = QPushButton("Guardar Cédula Excel…")
        self.btn_top_excel.setObjectName("BtnQuickExcel")
        self.btn_top_excel.setIcon(icono_cuadra("excel", 18))
        self.btn_top_excel.setIconSize(QSize(18, 18))
        self.btn_top_excel.setEnabled(False)
        self.btn_top_excel.clicked.connect(self._guardar_cedula_dialogo)
        hb.addWidget(self.btn_top_excel)

        parent_lay.addWidget(bar)

    def _actualizar_reloj(self) -> None:
        local_txt, utc_txt = constancia_tiempo_real()
        utc_corta = utc_txt.split(" ", 1)[1] if " " in utc_txt else utc_txt
        self.lbl_constancia_reloj.setText(f"{local_txt} · {utc_corta}")
        tip = f"Constancia temporal en vivo · {utc_txt} · Local: {local_txt}"
        self.lbl_constancia_reloj.setToolTip(tip)
        self.box_constancia.setToolTip(tip)

    def _construir_cinta(self, parent_lay: QVBoxLayout) -> None:
        tabs_bar = QFrame()
        tabs_bar.setObjectName("RibbonTabs")
        ht = QHBoxLayout(tabs_bar)
        ht.setContentsMargins(10, 0, 10, 0)
        ht.setSpacing(2)

        self.ribbon_tabs: list[tuple[QPushButton, str]] = []
        espec_tabs = [
            ("INICIO · AUDITORÍA", "asientos-nia240"),
            ("DATOS Y ERP (PANAMÁ)", "conectores"),
            ("MUESTREO NIA 530", "muestreo-mus"),
            ("EVIDENCIA, ROLES Y CÉDULA", "bitacora"),
        ]
        for texto, destino in espec_tabs:
            btn_t = QPushButton(texto)
            btn_t.setProperty("class", "RibbonTab")
            btn_t.clicked.connect(lambda _=False, h=destino: self.seleccionar_herramienta(h))
            ht.addWidget(btn_t)
            self.ribbon_tabs.append((btn_t, destino))

        ht.addStretch(1)
        lbl_r = QLabel("Motor DuckDB Determinista · Trazabilidad SHA-256")
        lbl_r.setObjectName("RibbonRight")
        ht.addWidget(lbl_r)
        parent_lay.addWidget(tabs_bar)

        cuerpo = QFrame()
        cuerpo.setObjectName("RibbonBody")
        hb = QHBoxLayout(cuerpo)
        hb.setContentsMargins(6, 5, 10, 4)
        hb.setSpacing(8)

        grip = QFrame()
        grip.setProperty("class", "ToolbarGrip")
        grip.setFixedWidth(4)
        hb.addWidget(grip)

        self.botones_cinta: dict[str, QToolButton] = {}
        grupos = [
            ("PRUEBAS DE AUDITORÍA (NIA)", HERRAMIENTAS[0:4]),
            ("MUESTREO (NIA 530)", HERRAMIENTAS[4:5]),
            ("ERP, SQL Y COPILOTO", HERRAMIENTAS[5:7]),
            ("EVIDENCIA, ROLES Y EXCEL", HERRAMIENTAS[7:9]),
        ]
        for g_idx, (g_titulo, items) in enumerate(grupos):
            gv = QVBoxLayout()
            gv.setSpacing(3)
            gh = QHBoxLayout()
            gh.setSpacing(6)
            for hid, nombre, tip, _ in items:
                tb = QToolButton()
                tb.setText(nombre)
                tb.setToolTip(tip)
                tb.setIcon(icono_cuadra(hid, 34))
                tb.setIconSize(QSize(34, 34))
                tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                tb.setCheckable(True)
                tb.setFixedHeight(74)
                tb.setProperty("class", "RibbonBtn")
                tb.clicked.connect(lambda _=False, h=hid: self.seleccionar_herramienta(h))
                gh.addWidget(tb)
                self.botones_cinta[hid] = tb
            gv.addLayout(gh)
            lbl_g = QLabel(g_titulo)
            lbl_g.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_g.setProperty("class", "RibbonGroupLbl")
            gv.addWidget(lbl_g)
            hb.addLayout(gv)

            sep = QFrame()
            sep.setProperty("class", "RibbonSep")
            hb.addWidget(sep)

        # 5.º grupo de ejecución rápida estilo Excel
        gv_ej = QVBoxLayout()
        gv_ej.setSpacing(3)
        gh_ej = QHBoxLayout()
        gh_ej.setSpacing(6)

        self.btn_ribbon_correr = QToolButton()
        self.btn_ribbon_correr.setText("Correr pruebas")
        self.btn_ribbon_correr.setIcon(icono_cuadra("correr", 34))
        self.btn_ribbon_correr.setIconSize(QSize(34, 34))
        self.btn_ribbon_correr.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.btn_ribbon_correr.setFixedHeight(74)
        self.btn_ribbon_correr.setProperty("class", "RibbonActionRun")
        self.btn_ribbon_correr.setEnabled(False)
        self.btn_ribbon_correr.clicked.connect(self._correr_desde_cinta)

        self.btn_ribbon_excel = QToolButton()
        self.btn_ribbon_excel.setText("Exportar Excel")
        self.btn_ribbon_excel.setIcon(icono_cuadra("excel", 34))
        self.btn_ribbon_excel.setIconSize(QSize(34, 34))
        self.btn_ribbon_excel.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.btn_ribbon_excel.setFixedHeight(74)
        self.btn_ribbon_excel.setProperty("class", "RibbonActionExcel")
        self.btn_ribbon_excel.setEnabled(False)
        self.btn_ribbon_excel.clicked.connect(self._guardar_cedula_dialogo)

        gh_ej.addWidget(self.btn_ribbon_correr)
        gh_ej.addWidget(self.btn_ribbon_excel)
        gv_ej.addLayout(gh_ej)
        lbl_ej = QLabel("EJECUCIÓN")
        lbl_ej.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ej.setProperty("class", "RibbonGroupLbl")
        gv_ej.addWidget(lbl_ej)
        hb.addLayout(gv_ej)
        hb.addStretch(1)

        parent_lay.addWidget(cuerpo)

    def _construir_formulabar(self, parent_lay: QVBoxLayout) -> None:
        fb = QFrame()
        fb.setObjectName("FormulaBar")
        fb.setFixedHeight(32)
        hf = QHBoxLayout(fb)
        hf.setContentsMargins(4, 3, 6, 3)
        hf.setSpacing(4)

        self.lbl_namebox = QLabel("NIA-240")
        self.lbl_namebox.setObjectName("NameBox")
        self.lbl_namebox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_fx = QLabel("fx")
        lbl_fx.setObjectName("FxIcon")
        self.lbl_formula = QLabel("")
        self.lbl_formula.setObjectName("FormulaText")
        self.lbl_formula.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_formula.setMinimumWidth(200)

        self.nias_layout = QHBoxLayout()
        self.nias_layout.setSpacing(4)

        hf.addWidget(self.lbl_namebox)
        hf.addWidget(lbl_fx)
        hf.addWidget(self.lbl_formula, 1)
        hf.addLayout(self.nias_layout)
        parent_lay.addWidget(fb)

    def _texto_estado_base(self) -> str:
        base = "LISTO · EJECUCIÓN LOCAL 100 % SIN INTERNET"
        try:
            pol = self.gestor_usuarios.politicas()
            if pol.get("alerta_nube", True):
                nube = detectar_carpeta_sincronizada(RAIZ)
                if nube.get("en_nube"):
                    return f"{base} · ⚠ RUTA EN NUBE ({nube['proveedor']})"
        except Exception:  # noqa: BLE001
            pass
        return base

    def _construir_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lbl_sb_izq = QLabel(self._texto_estado_base())
        self.lbl_sb_der = QLabel("FILAS: 0 | PRUEBAS: 0 | HALLAZGOS: 0 | SHA-256: SIN EJECUCIÓN")
        sb.addWidget(self.lbl_sb_izq, 1)
        sb.addPermanentWidget(self.lbl_sb_der)

    def _sincronizar_encargo(self, nuevos_datos: dict) -> None:
        self.encargo_datos.update(nuevos_datos)
        for pid, v in self.vistas_paquetes.items():
            if pid != self.herramienta_actual:
                v.aplicar_encargo_ui(self.encargo_datos)
        self._actualizar_encabezados()

    def _actualizar_encabezados(self) -> None:
        cli = self.encargo_datos["cliente"]
        cierre = self.encargo_datos["fecha_cierre"]
        cierre_txt = cierre.isoformat() if isinstance(cierre, date) else str(cierre)
        periodo_ini = self.encargo_datos.get("periodo_inicio")
        periodo_txt = formatear_periodo_auditado(periodo_ini, cierre)
        marco = self.encargo_datos["marco"]
        self.setWindowTitle(f"{NOMBRE_MARCA} · Mesa de Auditoría — {cli}")
        self.lbl_workbook_title.setText(f"Cliente: {cli}")
        self.lbl_workbook_sub.setText(f"Período auditado: {periodo_txt} · Marco {marco} · Cierre {cierre_txt}")
        self.lbl_constancia_periodo.setText(f"PERÍODO AUDITADO: {periodo_txt}")

        est = "INTEGRA" if (self.ultima_corrida and self.ultima_corrida.bitacora.verificar()) else (
            "ALTERADA" if self.ultima_corrida else "SIN_EJECUCION"
        )
        cuadro, formula = formula_contextual(
            self.herramienta_actual,
            cli,
            cierre,
            float(self.encargo_datos["materialidad"]),
            est,
            periodo_inicio=periodo_ini,
        )
        self.lbl_namebox.setText(cuadro)
        self.lbl_formula.setText(formula)

    def seleccionar_herramienta(self, hid: str) -> None:
        self.herramienta_actual = hid
        for b_id, tb in self.botones_cinta.items():
            tb.setChecked(b_id == hid)

        tab_idx = self.TAB_DE_HERRAMIENTA.get(hid, 0)
        for i, (btn_t, _) in enumerate(self.ribbon_tabs):
            btn_t.setProperty("active", "true" if i == tab_idx else "false")
            btn_t.style().unpolish(btn_t)
            btn_t.style().polish(btn_t)

        self.stack.setCurrentIndex(self._indice_vista[hid])
        meta = next(h for h in HERRAMIENTAS if h[0] == hid)
        while self.nias_layout.count():
            item = self.nias_layout.takeAt(0)
            w_old = item.widget()
            if w_old is not None:
                w_old.hide()
                w_old.setParent(None)
                w_old.deleteLater()
        for tag in meta[3]:
            lbl = QLabel(tag)
            lbl.setProperty("class", "NiaTag")
            self.nias_layout.addWidget(lbl)

        if hid == "copiloto":
            self.vista_copiloto.actualizar_info_fuentes()
        elif hid == "encargos":
            self.vista_portafolio.vincular_corrida_activa(self.ultima_corrida)
        self._actualizar_botones_ejecucion()
        self._actualizar_encabezados()

    def _sesion_para_portafolio(self) -> tuple[dict, str, str, Corrida | None]:
        return dict(self.encargo_datos), self.auditor_actual, self.rol_actual, self.ultima_corrida

    def _seguridad_para_portafolio(self) -> tuple[SesionAutenticada | None, GestorUsuarios]:
        return self.sesion_actual, self.gestor_usuarios

    def _aplicar_sesion_autenticada(self, sesion: SesionAutenticada) -> None:
        self.sesion_actual = sesion
        self.auditor_actual = sesion.nombre_completo
        self.rol_actual = sesion.rol_auditoria or sesion.perfil
        self.btn_perfil.setText(f"{sesion.perfil}: {sesion.nombre_completo}")
        self.btn_admin_seg.setVisible(sesion.es_admin)
        self.vista_portafolio.refrescar_portafolio()
        self.lbl_sb_izq.setText(f"SESIÓN ACTIVA · {sesion.etiqueta_ui}")

    def _abrir_admin_seguridad(self) -> None:
        if self.sesion_actual is None or not self.sesion_actual.es_admin:
            QMessageBox.warning(
                self,
                "Control de acceso",
                "Solo un usuario con perfil 'Administrador' puede abrir el panel de seguridad.",
            )
            return
        try:
            dlg = DialogoAdminSeguridad(self.gestor_usuarios, self.sesion_actual, self)
            dlg.exec()
            self.lbl_sb_izq.setText(self._texto_estado_base())
        except ErrorSeguridad as exc:
            QMessageBox.warning(self, "Administración de seguridad", str(exc))

    def _cambiar_perfil_auditor(self) -> None:
        if self.sesion_actual is not None:
            menu = QMenu(self)
            if self.sesion_actual.es_admin:
                act_admin = menu.addAction("Panel de Administración y Seguridad…")
                act_admin.triggered.connect(self._abrir_admin_seguridad)
            act_pwd = menu.addAction("Cambiar mi contraseña…")
            act_pwd.triggered.connect(lambda: DialogoCambiarContrasena(self.gestor_usuarios, self.sesion_actual, self).exec())
            act_login = menu.addAction("Cambiar de usuario / Cerrar sesión…")

            def _reautenticar() -> None:
                dlg = DialogoLoginFolio(self.gestor_usuarios, permitir_evaluacion=False, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted and dlg.sesion_autenticada() is not None:
                    self._aplicar_sesion_autenticada(dlg.sesion_autenticada())

            act_login.triggered.connect(_reautenticar)
            menu.exec(self.btn_perfil.mapToGlobal(self.btn_perfil.rect().bottomLeft()))
            return

        if self.gestor_usuarios.existe_configuracion():
            dlg_login = DialogoLoginFolio(self.gestor_usuarios, permitir_evaluacion=False, parent=self)
            if dlg_login.exec() == QDialog.DialogCode.Accepted and dlg_login.sesion_autenticada() is not None:
                self._aplicar_sesion_autenticada(dlg_login.sesion_autenticada())
            return

        dlg = DialogoPerfilAuditor(self.auditor_actual, self.rol_actual, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.auditor_actual, self.rol_actual = dlg.resultado()
            self.btn_perfil.setText(f"Auditor: {self.auditor_actual} · {self.rol_actual}")
            self.vista_portafolio.refrescar_portafolio()

    def _aplicar_encargo_cargado(self, datos: dict) -> None:
        fc_dt = _normalizar_fecha_ui(datos.get("fecha_cierre"), self.encargo_datos["fecha_cierre"])
        pi_dt = _normalizar_fecha_ui(datos.get("periodo_inicio"), calcular_periodo_inicio(fc_dt))

        nuevos = {
            "cliente": str(datos.get("cliente") or self.encargo_datos["cliente"]),
            "periodo_inicio": pi_dt,
            "fecha_cierre": fc_dt,
            "marco": str(datos.get("marco") or self.encargo_datos["marco"]),
            "materialidad": float(datos.get("materialidad") or self.encargo_datos["materialidad"]),
            "materialidad_ejecucion": float(datos.get("materialidad_ejecucion") or self.encargo_datos["materialidad_ejecucion"]),
            "umbral_trivial": float(datos.get("umbral_trivial") or self.encargo_datos["umbral_trivial"]),
            "umbral_aprobacion": float(datos.get("umbral_aprobacion") or self.encargo_datos["umbral_aprobacion"]),
        }
        self._sincronizar_encargo(nuevos)
        for v in self.vistas_paquetes.values():
            v.aplicar_encargo_ui(self.encargo_datos)
        self.lbl_sb_izq.setText(f"ENCARGO CARGADO: {nuevos['cliente']}")

    def _al_actualizar_revision_portafolio(self) -> None:
        if self.ultima_corrida is not None:
            self.vista_bitacora.actualizar_corrida(self.ultima_corrida)
            integra = self.ultima_corrida.bitacora.verificar()
            self.lbl_pill_bitacora.setText("BITÁCORA ÍNTEGRA · SHA-256" if integra else "BITÁCORA ALTERADA")

    def _contexto_para_copiloto(self) -> tuple[dict, dict, dict, Any]:
        fuentes: dict[str, Path | str] = {}
        opciones: dict[str, dict] = {}
        ultima_vista = self.vistas_paquetes.get(self.herramienta_actual)
        candidatos = [ultima_vista] if ultima_vista else []
        candidatos.extend(v for v in self.vistas_paquetes.values() if v is not ultima_vista)
        for v in candidatos:
            _, arch, opc = v.construir_payload_ejecucion()
            cargados = {k: val for k, val in arch.items() if val is not None}
            if cargados:
                fuentes = cargados
                opciones = opc
                break
        bitacora = self.ultima_corrida.bitacora if self.ultima_corrida else None
        return fuentes, opciones, dict(self.encargo_datos), bitacora

    def _tras_consulta_copiloto(self, res) -> None:
        if self.ultima_corrida is not None:
            self.vista_bitacora.actualizar_corrida(self.ultima_corrida)
        self.lbl_sb_izq.setText(f"CONSULTA APROBADA · {len(res.tabla):,} FILA(S) · SHA-256 {res.sql_sha256[:10]}…")

    def _actualizar_botones_ejecucion(self) -> None:
        if self.herramienta_actual in self.vistas_paquetes:
            v = self.vistas_paquetes[self.herramienta_actual]
            v._actualizar_estado_boton()
            listo = v.esta_listo()
        else:
            listo = False
        self.btn_ribbon_correr.setEnabled(listo)
        tiene_excel = bool(self.ultima_corrida and self.ultima_corrida.cedula.exists())
        self.btn_ribbon_excel.setEnabled(tiene_excel)
        self.btn_top_excel.setEnabled(tiene_excel)

    def _correr_desde_cinta(self) -> None:
        if self.herramienta_actual in self.vistas_paquetes:
            self.ejecutar_asincrono(self.herramienta_actual)

    def cargar_ejemplo_sintetico(self) -> None:
        """Genera y carga datos sintéticos según la herramienta activa para demostración 100 % offline."""
        carpeta = RAIZ / "datos" / "ejemplo"
        if self.herramienta_actual == "excepciones-basicas":
            mayor = generar(carpeta / "mayor_sintetico_2025.csv")
            v = self.vistas_paquetes["excepciones-basicas"]
            v.tarjetas_fuentes["mayor"].cargar_origen(mayor)
        elif self.herramienta_actual == "ventas-fe":
            zip_fe, mayor = generar_facturas_fe(carpeta)
            v = self.vistas_paquetes["ventas-fe"]
            v.tarjetas_fuentes["facturas"].cargar_origen(zip_fe)
            v.tarjetas_fuentes["mayor"].cargar_origen(mayor)
        elif self.herramienta_actual == "bancos-conciliacion":
            pdf_ext, mayor = generar_estado_cuenta_bancos(carpeta)
            v = self.vistas_paquetes["bancos-conciliacion"]
            v.tarjetas_fuentes["extracto"].cargar_origen(pdf_ext)
            v.tarjetas_fuentes["mayor"].cargar_origen(mayor)
        else:
            if self.herramienta_actual not in self.vistas_paquetes:
                self.seleccionar_herramienta("asientos-nia240")
            mayor, balanza = generar_diario_asientos(carpeta)
            v = self.vistas_paquetes["asientos-nia240"]
            v.tarjetas_fuentes["mayor"].cargar_origen(mayor)
            v.tarjetas_fuentes["balanza"].cargar_origen(balanza)
        self._actualizar_botones_ejecucion()
        self.lbl_sb_izq.setText("LISTO · DATOS SINTÉTICOS CARGADOS (100 % LOCAL)")

    def ejecutar_sincrono(self, paquete_id: str) -> Corrida:
        """Ejecuta un paquete de forma síncrona (usado en pruebas automatizadas y fallback)."""
        vista = self.vistas_paquetes[paquete_id]
        encargo, archivos, opciones = vista.construir_payload_ejecucion()
        corrida = ejecutar_encargo(paquete_id, archivos, encargo, opciones=opciones)
        self._registrar_corrida(paquete_id, corrida)
        return corrida

    def ejecutar_asincrono(self, paquete_id: str) -> None:
        if self._trabajador and self._trabajador.isRunning():
            return
        vista = self.vistas_paquetes[paquete_id]
        encargo, archivos, opciones = vista.construir_payload_ejecucion()
        vista.btn_correr.setEnabled(False)
        self.btn_ribbon_correr.setEnabled(False)
        self.lbl_sb_izq.setText("PROCESANDO EN MOTOR DUCKDB DETERMINISTA…")

        self._trabajador = TrabajadorEjecucion(paquete_id, archivos, encargo, opciones, self)
        self._trabajador.completado.connect(lambda c, pid=paquete_id: self._al_terminar_corrida(pid, c))
        self._trabajador.fallo.connect(lambda err: self._al_fallar_corrida(err))
        self._trabajador.start()

    def _al_terminar_corrida(self, paquete_id: str, corrida: Corrida) -> None:
        self._registrar_corrida(paquete_id, corrida)
        self._actualizar_botones_ejecucion()

    def _al_fallar_corrida(self, mensaje: str) -> None:
        self.lbl_sb_izq.setText("ERROR EN EJECUCIÓN")
        self._actualizar_botones_ejecucion()
        QMessageBox.critical(self, "Error en ejecución", mensaje)

    def _registrar_corrida(self, paquete_id: str, corrida: Corrida) -> None:
        self.corridas[paquete_id] = corrida
        self.ultima_corrida = corrida
        self.vistas_paquetes[paquete_id].mostrar_corrida(corrida)
        self.vista_bitacora.actualizar_corrida(corrida)
        self.vista_portafolio.vincular_corrida_activa(corrida)

        integra = corrida.bitacora.verificar()
        self.lbl_pill_bitacora.setText("BITÁCORA ÍNTEGRA · SHA-256" if integra else "BITÁCORA ALTERADA")
        self.lbl_pill_bitacora.setProperty("class", "PillOk" if integra else "PillErr")
        self.lbl_pill_bitacora.style().unpolish(self.lbl_pill_bitacora)
        self.lbl_pill_bitacora.style().polish(self.lbl_pill_bitacora)

        filas = sum(c["filas"] for c in corrida.controles)
        pruebas = sum(1 for r in corrida.resultados if not r.omitida)
        hallazgos = sum(r.excepciones for r in corrida.resultados if not r.omitida)
        est = "VERIFICADO" if integra else "ALTERADO"
        self.lbl_sb_izq.setText("LISTO · EJECUCIÓN LOCAL 100 % SIN INTERNET")
        est_datos = (corrida.diagnostico or {}).get("estado_general", "OK")
        self.lbl_sb_der.setText(
            f"FILAS: {filas:,} | PRUEBAS: {pruebas} | HALLAZGOS: {hallazgos:,} | DATOS: {est_datos} | SHA-256: {est}"
        )
        self._actualizar_botones_ejecucion()
        self._actualizar_encabezados()

    def closeEvent(self, event: QCloseEvent) -> None:
        if hasattr(self, "_timer_reloj"):
            self._timer_reloj.stop()
        if self._trabajador and self._trabajador.isRunning():
            self.lbl_sb_izq.setText("ESPERANDO FINALIZACIÓN DEL MOTOR ANTES DE CERRAR…")
            if not self._trabajador.wait(4000):
                self._trabajador.terminate()
                self._trabajador.wait(1000)
        super().closeEvent(event)

    def _guardar_cedula_dialogo(self) -> None:
        if not self.ultima_corrida or not self.ultima_corrida.cedula.exists():
            return
        sugerido = str(RAIZ / f"cedula_{self.ultima_corrida.manifiesto['id']}.xlsx")
        destino, _ = QFileDialog.getSaveFileName(self, "Guardar cédula de auditoría Excel", sugerido, "Excel (*.xlsx)")
        if destino:
            Path(destino).write_bytes(self.ultima_corrida.cedula.read_bytes())
            self.lbl_sb_izq.setText(f"CÉDULA GUARDADA EN: {destino}")


def _instalar_manejador_errores(ventana: VentanaCuadra) -> None:
    if "pytest" in sys.modules:
        return
    previo = sys.excepthook

    def _manejador(tipo, valor, tb):
        detalle = "".join(traceback.format_exception(tipo, valor, tb))
        try:
            sal = RAIZ / "salidas"
            sal.mkdir(parents=True, exist_ok=True)
            (sal / "ultimo_error.log").write_text(detalle, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        if isinstance(valor, KeyboardInterrupt):
            previo(tipo, valor, tb)
            return
        try:
            QMessageBox.critical(
                ventana,
                "Error inesperado en Libro de Auditoría",
                f"{valor}\n\nSe guardó el detalle en salidas/ultimo_error.log.",
            )
        except Exception:  # noqa: BLE001
            previo(tipo, valor, tb)

    sys.excepthook = _manejador


def iniciar_escritorio(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    gestor = GestorUsuarios(RAIZ)
    sesion: SesionAutenticada | None = None
    if "--autoprueba" not in args and "--sin-login" not in args:
        dlg_login = DialogoLoginFolio(
            gestor=gestor,
            permitir_evaluacion=not gestor.existe_configuracion(),
        )
        if dlg_login.exec() != QDialog.DialogCode.Accepted:
            return 0
        sesion = dlg_login.sesion_autenticada()
    ventana = VentanaCuadra(sesion=sesion, gestor_usuarios=gestor)
    if "--autoprueba" in args:
        ventana.cargar_ejemplo_sintetico()
        corrida = ventana.ejecutar_sincrono("asientos-nia240")
        ok = corrida.bitacora.verificar() and corrida.cedula.exists()
        ventana.close()
        return 0 if ok else 1
    _instalar_manejador_errores(ventana)
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(iniciar_escritorio())
