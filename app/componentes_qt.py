"""Componentes gráficos reutilizables e iconos 3D offline (QPainter) estilo Excel ejecutivo."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QFrame, QLabel, QStyle, QStyledItemDelegate, QVBoxLayout

COLUMNAS_MONETARIAS = {
    "monto", "total_debito", "diferencia", "saldo_inicial", "saldo_final",
    "debito", "credito", "debit", "credit", "valor_libros", "valor_auditado",
    "error_proyectado", "proyectado", "margen_incremental", "precision_basica",
    "limite_superior", "monto_facturas", "monto_mayor", "desde_valor", "hasta_valor",
}

ESTILO_CUADRA_QT = """
QMainWindow, QDialog {
    background-color: #D4D0C8;
    color: #000000;
    font-family: "Segoe UI", "Tahoma", Arial, sans-serif;
    font-size: 9.5pt;
}
QScrollArea, QStackedWidget {
    background-color: #D4D0C8;
    border: none;
}
#qt_scrollarea_viewport {
    background-color: #D4D0C8;
}
QSplitter::handle {
    background-color: #D4D0C8;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
}
QCheckBox, QRadioButton {
    color: #000000;
    background: transparent;
    spacing: 6px;
}
QToolTip {
    background-color: #FFFFE1;
    color: #000000;
    border: 1px solid #000000;
    border-radius: 0px;
    padding: 3px 6px;
}

/* Barra superior clásica Win32 azul ventana activa */
#AppBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #000080, stop:0.48 #0A246A, stop:1 #1084D0);
    border-bottom: 1px solid #404040;
}
#AppBar QLabel {
    color: #FFFFFF;
    background: transparent;
}
#AppBar #BrandBadge,
#BrandBadge {
    color: #FDE68A;
    font-size: 7.2pt;
    font-weight: 800;
    letter-spacing: 0.9px;
}
#AppBar #WorkbookTitle,
#WorkbookTitle {
    font-size: 10pt;
    font-weight: 700;
    letter-spacing: 0.3px;
    color: #FFFFFF;
}
#AppBar #WorkbookSubtitle,
#WorkbookSubtitle {
    font-size: 7.9pt;
    font-weight: 500;
    color: #E2E8F0;
}
#ConstanciaBox {
    background: #081C4A;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #7EB4EA;
    border-bottom: 1px solid #7EB4EA;
    border-radius: 0px;
    padding: 2px 10px;
}
#AppBar #ConstanciaReloj,
#ConstanciaReloj {
    color: #FFFFFF;
    font-family: "Consolas", "Segoe UI", monospace;
    font-size: 9pt;
    font-weight: 700;
}
#AppBar #ConstanciaPeriodo,
#ConstanciaPeriodo {
    color: #FDE68A;
    font-size: 7.3pt;
    font-weight: 700;
    letter-spacing: 0.3px;
}
#AppBar .PillInfo,
.PillInfo {
    background: #081C4A;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #7EB4EA;
    border-bottom: 1px solid #7EB4EA;
    color: #FFFFFF;
    font-size: 7.1pt;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 0px;
}
#AppBar .PillOk,
.PillOk {
    background: #107C41;
    border-top: 1px solid #064E3B;
    border-left: 1px solid #064E3B;
    border-right: 1px solid #86EFAC;
    border-bottom: 1px solid #86EFAC;
    color: #FFFFFF;
    font-size: 7.1pt;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 0px;
}
#AppBar .PillErr,
.PillErr {
    background: #B91C1C;
    border-top: 1px solid #450A0A;
    border-left: 1px solid #450A0A;
    border-right: 1px solid #FCA5A5;
    border-bottom: 1px solid #FCA5A5;
    color: #FFFFFF;
    font-size: 7.1pt;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 0px;
}
QPushButton#BtnQuick {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    color: #000000;
    font-size: 7.9pt;
    font-weight: 600;
    padding: 3px 8px;
    min-height: 20px;
    border-radius: 0px;
}
QPushButton#BtnQuick:hover:enabled {
    background-color: #E2DFD7;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    color: #000080;
}
QPushButton#BtnQuick:pressed:enabled {
    background-color: #C8C4BC;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
}
QPushButton#BtnQuickExcel {
    background-color: #107C41;
    border-top: 1px solid #86EFAC;
    border-left: 1px solid #86EFAC;
    border-right: 1px solid #064E3B;
    border-bottom: 1px solid #064E3B;
    color: #FFFFFF;
    font-size: 7.9pt;
    font-weight: 700;
    padding: 3px 8px;
    min-height: 20px;
    border-radius: 0px;
}
QPushButton#BtnQuickExcel:hover:enabled {
    background-color: #14914D;
    border-top: 1px solid #BBF7D0;
    border-left: 1px solid #BBF7D0;
    border-right: 1px solid #064E3B;
    border-bottom: 1px solid #064E3B;
    color: #FFFFFF;
}
QPushButton#BtnQuickExcel:pressed:enabled {
    background-color: #0D6A37;
    border-top: 1px solid #064E3B;
    border-left: 1px solid #064E3B;
    border-right: 1px solid #86EFAC;
    border-bottom: 1px solid #86EFAC;
}
QPushButton#BtnQuickExcel:disabled {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    color: #808080;
}

/* Franja de pestañas y barras acopladas clásicas estilo Excel 97 / Win32 */
#RibbonTabs {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-bottom: 1px solid #808080;
}
QPushButton.RibbonTab {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: none;
    color: #111111;
    font-size: 8pt;
    font-weight: 600;
    letter-spacing: 0.3px;
    padding: 4px 12px;
    margin-top: 3px;
    margin-right: 2px;
    border-radius: 0px;
    min-height: 20px;
}
QPushButton.RibbonTab:hover {
    background-color: #E2DFD7;
    color: #000080;
}
QPushButton.RibbonTab[active="true"] {
    background-color: #ECE9D8;
    color: #000000;
    font-weight: 700;
    border-top: 2px solid #000080;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #ECE9D8;
    margin-top: 1px;
    padding: 5px 12px 4px 12px;
}
#RibbonRight {
    color: #222222;
    font-size: 7.8pt;
    font-weight: 600;
    padding-right: 12px;
    background: transparent;
}

/* Cuerpo de barra de herramientas acoplada Excel 97 */
#RibbonBody {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-bottom: 1px solid #808080;
}
.ToolbarGrip {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    min-width: 2px;
    max-width: 2px;
    margin: 4px 0px;
    border-radius: 0px;
}
QToolButton.RibbonBtn {
    background-color: #D4D0C8;
    border: 1px solid #C8C4BC;
    border-radius: 0px;
    color: #111111;
    font-size: 7.8pt;
    font-weight: 600;
    padding: 5px 5px 4px 5px;
    min-width: 82px;
}
QToolButton.RibbonBtn:hover {
    background-color: #DEDAD2;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    color: #000000;
}
QToolButton.RibbonBtn:pressed {
    background-color: #ECE9D8;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
}
QToolButton.RibbonBtn:checked {
    background-color: #ECE9D8;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #FFFFFF;
    border-bottom: 2px solid #000080;
    color: #000080;
    font-weight: 700;
}
QToolButton.RibbonActionRun {
    background-color: #000080;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    border-radius: 0px;
    color: #FFFFFF;
    font-size: 7.8pt;
    font-weight: 700;
    padding: 5px 6px 4px 6px;
    min-width: 82px;
}
QToolButton.RibbonActionRun:hover:enabled {
    background-color: #0A246A;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #000000;
    border-bottom: 1px solid #000000;
}
QToolButton.RibbonActionRun:pressed:enabled {
    background-color: #000066;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
}
QToolButton.RibbonActionRun:disabled {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    color: #808080;
}
QToolButton.RibbonActionExcel {
    background-color: #107C41;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    border-radius: 0px;
    color: #FFFFFF;
    font-size: 7.8pt;
    font-weight: 700;
    padding: 5px 6px 4px 6px;
    min-width: 82px;
}
QToolButton.RibbonActionExcel:hover:enabled {
    background-color: #14914D;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #064E3B;
    border-bottom: 1px solid #064E3B;
}
QToolButton.RibbonActionExcel:pressed:enabled {
    background-color: #0D6A37;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
}
QToolButton.RibbonActionExcel:disabled {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    color: #808080;
}
.RibbonGroupLbl {
    color: #222222;
    font-size: 7pt;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding-top: 2px;
    background: transparent;
}
.RibbonSep {
    background-color: transparent;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    min-width: 2px;
    max-width: 2px;
    margin-top: 4px;
    margin-bottom: 4px;
}

/* Barra de fórmulas fx clásica Excel 97 */
#FormulaBar {
    background-color: #D4D0C8;
    border-bottom: 1px solid #808080;
    border-radius: 0px;
}
#NameBox {
    background-color: #FFFFFF;
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    border-radius: 0px;
    color: #000080;
    font-family: "Consolas", monospace;
    font-size: 8.5pt;
    font-weight: 700;
    padding: 2px 10px;
    min-width: 108px;
}
#FxIcon {
    background-color: #D4D0C8;
    color: #000080;
    font-family: "Georgia", serif;
    font-style: italic;
    font-weight: 700;
    font-size: 10pt;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    border-radius: 0px;
    padding: 2px 8px;
}
#FormulaText {
    background-color: #FFFFFF;
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    border-radius: 0px;
    color: #000000;
    font-family: "Consolas", "Segoe UI", monospace;
    font-size: 8.4pt;
    padding: 2px 8px;
}
.NiaTag {
    background-color: #ECE9D8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    color: #000080;
    font-size: 7.1pt;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 0px;
}

/* Tarjetas, paneles e inputs biselados Win32 */
.PanelCard {
    background-color: #ECE9D8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    border-radius: 0px;
}
.SectionHdr {
    color: #000080;
    font-size: 7.8pt;
    font-weight: 700;
    letter-spacing: 0.6px;
    border-bottom: 1px solid #808080;
    padding-bottom: 4px;
    margin-bottom: 4px;
    background: transparent;
}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QPlainTextEdit {
    background-color: #FFFFFF;
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    border-radius: 0px;
    padding: 3px 6px;
    color: #000000;
    min-height: 22px;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #000080;
}
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled, QDateEdit:disabled, QPlainTextEdit:disabled {
    background-color: #D4D0C8;
    color: #808080;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #404040;
    border-radius: 0px;
    selection-background-color: #000080;
    selection-color: #FFFFFF;
}
QPushButton {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    border-radius: 0px;
    color: #000000;
    font-weight: 600;
    padding: 4px 12px;
    min-height: 24px;
}
QPushButton:hover:enabled {
    background-color: #E2DFD7;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    color: #000080;
}
QPushButton:pressed:enabled {
    background-color: #C8C4BC;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
}
QPushButton:disabled {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    color: #808080;
}
QPushButton#BtnPrimary {
    background-color: #000080;
    border-top: 1px solid #7EB4EA;
    border-left: 1px solid #7EB4EA;
    border-right: 1px solid #000033;
    border-bottom: 1px solid #000033;
    border-radius: 0px;
    color: #FFFFFF;
    font-weight: 700;
    min-height: 32px;
}
QPushButton#BtnPrimary:hover:enabled {
    background-color: #0A246A;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #000033;
    border-bottom: 1px solid #000033;
    color: #FFFFFF;
}
QPushButton#BtnPrimary:pressed:enabled {
    background-color: #000066;
    border-top: 1px solid #000033;
    border-left: 1px solid #000033;
    border-right: 1px solid #7EB4EA;
    border-bottom: 1px solid #7EB4EA;
}
QPushButton#BtnPrimary:disabled {
    background-color: #D4D0C8;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    color: #808080;
}

/* Pestañas tipo hojas de Excel 97 (Sheet1 / Sheet2) */
QTabWidget::pane {
    background-color: #FFFFFF;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    border-radius: 0px;
}
QTabBar {
    background-color: #D4D0C8;
}
QTabBar::tab {
    background-color: #D4D0C8;
    color: #111111;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #404040;
    padding: 5px 12px;
    margin-right: 2px;
    font-size: 8.3pt;
    font-weight: 600;
    border-radius: 0px;
}
QTabBar::tab:hover {
    background-color: #E2DFD7;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #000080;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #808080;
    border-right: 1px solid #404040;
    border-bottom: 2px solid #000080;
    font-weight: 700;
}
QTabBar::tab:top:selected {
    border-top: 2px solid #000080;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #FFFFFF;
}

/* Tablas empresariales estilo hoja Excel 97 */
QTableView {
    background-color: #FFFFFF;
    alternate-background-color: #F7F6F2;
    gridline-color: #C0C0C0;
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    border-radius: 0px;
    selection-background-color: #CFE2F7;
    selection-color: #000000;
    font-size: 8.8pt;
}
QHeaderView::section {
    background-color: #D4D0C8;
    color: #000000;
    font-weight: 700;
    font-size: 8.1pt;
    padding: 4px 8px;
    border-top: 1px solid #FFFFFF;
    border-left: 1px solid #FFFFFF;
    border-right: 1px solid #808080;
    border-bottom: 1px solid #808080;
    border-radius: 0px;
}

/* Barra de estado inferior Win32 con paneles hundidos */
QStatusBar {
    background-color: #D4D0C8;
    color: #000000;
    font-size: 8pt;
    font-weight: 600;
    border-top: 1px solid #808080;
}
QStatusBar::item {
    border: none;
}
QStatusBar QLabel {
    background-color: #D4D0C8;
    color: #111111;
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    border-radius: 0px;
    padding: 2px 8px;
    margin: 2px 2px;
}

/* Indicadores cuadrados estilo Win32 en lugar de círculos modernos */
QRadioButton::indicator, QCheckBox::indicator {
    width: 12px;
    height: 12px;
    border-radius: 0px;
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-right: 1px solid #FFFFFF;
    border-bottom: 1px solid #FFFFFF;
    background-color: #FFFFFF;
}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    background-color: #000080;
    border: 2px solid #FFFFFF;
    outline: 1px solid #404040;
}
"""


def _grad(x1: float, y1: float, x2: float, y2: float, c1: str, c2: str, cmid: str | None = None) -> QLinearGradient:
    g = QLinearGradient(x1, y1, x2, y2)
    g.setColorAt(0.0, QColor(c1))
    if cmid:
        g.setColorAt(0.5, QColor(cmid))
    g.setColorAt(1.0, QColor(c2))
    return g


def _pintar_bloque_3d(
    p: QPainter,
    x: float,
    y: float,
    w: float,
    h: float,
    prof: float,
    c_frente_top: str,
    c_frente_bot: str,
    c_top: str,
    c_lado: str,
    borde: str,
) -> None:
    """Dibuja un prisma/barra 3D isométrica con caras iluminadas (frente, tapa y lateral)."""
    dx = prof * 0.72
    dy = prof * 0.55

    # Cara lateral derecha (sombra)
    lado = QPolygonF([
        QPointF(x + w, y),
        QPointF(x + w + dx, y - dy),
        QPointF(x + w + dx, y + h - dy),
        QPointF(x + w, y + h),
    ])
    p.setPen(QPen(QColor(borde), 0.7))
    p.setBrush(QColor(c_lado))
    p.drawPolygon(lado)

    # Cara superior (iluminada)
    tapa = QPolygonF([
        QPointF(x, y),
        QPointF(x + dx, y - dy),
        QPointF(x + w + dx, y - dy),
        QPointF(x + w, y),
    ])
    p.setBrush(QColor(c_top))
    p.drawPolygon(tapa)

    # Cara frontal con degradado + brillo especular
    p.setBrush(_grad(x, y, x, y + h, c_frente_top, c_frente_bot))
    p.drawRect(QRectF(x, y, w, h))
    p.setPen(QPen(QColor(255, 255, 255, 135), 0.7))
    p.drawLine(QPointF(x + 0.8, y + 0.8), QPointF(x + w - 0.8, y + 0.8))


def icono_cuadra(nombre: str, tam: int = 34) -> QIcon:
    """Genera iconos vectoriales 3D estilo Excel ejecutivo (vintage-moderno) en memoria, 100 % sin internet."""
    pm = QPixmap(tam, tam)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(tam / 36.0, tam / 36.0)

    if nombre == "logo":
        # Ícono de ventana clásico: hoja contable blanca con encabezado azul marino y renglones
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#808080"))
        p.drawRect(QRectF(7, 5, 23, 27))

        p.setBrush(QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#404040"), 1.2))
        p.drawRect(QRectF(5, 3, 23, 27))

        p.setBrush(QColor("#000080"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(6, 4, 21, 6))

        p.setPen(QPen(QColor("#64748B"), 1.6))
        p.drawLine(QPointF(9, 14), QPointF(24, 14))
        p.drawLine(QPointF(9, 19), QPointF(24, 19))
        p.drawLine(QPointF(9, 24), QPointF(21, 24))

    elif nombre == "asientos-nia240":
        # Sombra y hoja trasera 3D
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 42))
        p.drawRoundedRect(QRectF(7, 6, 22, 27), 1.5, 1.5)
        p.setBrush(_grad(8, 3, 29, 28, "#E2E8F0", "#94A3B8"))
        p.setPen(QPen(QColor("#64748B"), 0.8))
        p.drawRect(QRectF(8, 3, 21, 25))

        # Hoja frontal de diario contable 3D
        p.setBrush(_grad(4, 6, 25, 31, "#FFFFFF", "#E6EEF8"))
        p.setPen(QPen(QColor("#1B3A5C"), 1.2))
        p.drawRect(QRectF(4, 6, 21, 25))

        # Encabezado azul zafiro biselado
        p.setBrush(_grad(4, 6, 25, 12, "#3B82F6", "#1E3A8A"))
        p.setPen(QPen(QColor("#1E3A8A"), 0.8))
        p.drawRect(QRectF(4, 6, 21, 5.5))
        p.setPen(QPen(QColor(255, 255, 255, 160), 0.8))
        p.drawLine(QPointF(5, 7), QPointF(24, 7))

        # Rejilla contable y líneas
        p.setPen(QPen(QColor("#94A3B8"), 0.9))
        p.drawLine(QPointF(10.5, 12), QPointF(10.5, 30.5))
        p.drawLine(QPointF(4.5, 17.5), QPointF(24, 17.5))
        p.drawLine(QPointF(4.5, 23), QPointF(24, 23))
        p.setPen(QPen(QColor("#107C41"), 1.4))
        p.drawLine(QPointF(12.5, 15), QPointF(22, 15))
        p.setPen(QPen(QColor("#2563EB"), 1.4))
        p.drawLine(QPointF(12.5, 20.5), QPointF(20, 20.5))

        # Lupa 3D ejecutiva (mango dorado/caoba + aro metálico + lente cristal)
        p.setPen(QPen(QColor("#78350F"), 1.0))
        p.setBrush(_grad(25, 24, 33, 33, "#F59E0B", "#78350F"))
        mango = QPolygonF([
            QPointF(25.5, 23.0), QPointF(32.5, 30.0), QPointF(30.3, 32.3), QPointF(23.2, 25.2)
        ])
        p.drawPolygon(mango)

        lente = QRadialGradient(20.5, 20.5, 7.2, 18.8, 18.8)
        lente.setColorAt(0.0, QColor("#FFFFFF"))
        lente.setColorAt(0.45, QColor("#BAE6FD"))
        lente.setColorAt(1.0, QColor("#38BDF8"))
        p.setBrush(lente)
        p.setPen(QPen(QColor("#0F2744"), 2.1))
        p.drawEllipse(QRectF(15, 15, 12, 12))
        p.setPen(QPen(QColor("#FBBF24"), 1.1))
        p.drawEllipse(QRectF(15.2, 15.2, 11.6, 11.6))

    elif nombre == "excepciones-basicas":
        # Base 3D de perspectiva
        base = QPolygonF([
            QPointF(2.5, 31.5), QPointF(7.5, 27.5), QPointF(33.5, 27.5), QPointF(29.0, 31.5)
        ])
        p.setPen(QPen(QColor("#94A3B8"), 0.9))
        p.setBrush(_grad(3, 27, 30, 32, "#E2E8F0", "#CBD5E1"))
        p.drawPolygon(base)

        # 3 columnas 3D con caras superiores y laterales iluminadas (Benford)
        _pintar_bloque_3d(p, 5.0, 10.5, 5.2, 19.5, 3.8, "#60A5FA", "#1D4ED8", "#93C5FD", "#1E3A8A", "#0F2744")
        _pintar_bloque_3d(p, 13.5, 15.5, 5.2, 14.5, 3.8, "#38BDF8", "#0284C7", "#BAE6FD", "#0369A1", "#0C4A6E")
        _pintar_bloque_3d(p, 22.0, 20.5, 5.2, 9.5, 3.8, "#4ADE80", "#15803D", "#BBF7D0", "#166534", "#064E3B")

        # Curva Benford carmesí 3D con nodos esféricos brillantes
        p.setPen(QPen(QColor(0, 0, 0, 55), 2.5))
        p.drawPolyline(QPolygonF([QPointF(7.8, 7.6), QPointF(16.2, 12.6), QPointF(24.8, 17.6)]))
        p.setPen(QPen(QColor("#DC2626"), 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPolyline(QPolygonF([QPointF(7.5, 6.8), QPointF(16.0, 11.8), QPointF(24.5, 16.8)]))

        for px, py in ((7.5, 6.8), (16.0, 11.8), (24.5, 16.8)):
            g = QRadialGradient(px - 0.6, py - 0.6, 3.0)
            g.setColorAt(0.0, QColor("#FFFFFF"))
            g.setColorAt(0.5, QColor("#EF4444"))
            g.setColorAt(1.0, QColor("#991B1B"))
            p.setBrush(g)
            p.setPen(QPen(QColor("#FFFFFF"), 0.8))
            p.drawEllipse(QPointF(px, py), 2.2, 2.2)

    elif nombre == "ventas-fe":
        # Sombra y hoja de factura electrónica DGI con esquina doblada 3D
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 42))
        p.drawRect(QRectF(6.5, 5.5, 20, 26))

        hoja = QPolygonF([
            QPointF(5, 4), QPointF(19, 4), QPointF(25, 10), QPointF(25, 30), QPointF(5, 30)
        ])
        p.setBrush(_grad(5, 4, 25, 30, "#FFFFFF", "#E8EEF6"))
        p.setPen(QPen(QColor("#1B3A5C"), 1.2))
        p.drawPolygon(hoja)

        # Pliegue 3D superior derecho
        pliegue = QPolygonF([QPointF(19, 4), QPointF(19, 10), QPointF(25, 10)])
        p.setBrush(_grad(19, 4, 25, 10, "#F1F5F9", "#94A3B8"))
        p.drawPolygon(pliegue)

        # Banda dorada DGI / encabezado fiscal + renglones
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_grad(7.5, 7.5, 17, 10, "#FBBF24", "#D97706"))
        p.drawRoundedRect(QRectF(7.5, 7.5, 9.5, 2.8), 0.8, 0.8)
        p.setPen(QPen(QColor("#64748B"), 1.3))
        p.drawLine(QPointF(8, 14), QPointF(19, 14))
        p.drawLine(QPointF(8, 18.5), QPointF(17, 18.5))
        p.drawLine(QPointF(8, 23), QPointF(15, 23))

        # Sello circular esmeralda 3D con tilde blanco
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QPointF(24.5, 24.5), 7.8, 7.8)

        med = QRadialGradient(21.5, 21.0, 9.5)
        med.setColorAt(0.0, QColor("#6EE7B7"))
        med.setColorAt(0.45, QColor("#107C41"))
        med.setColorAt(1.0, QColor("#064E3B"))
        p.setBrush(med)
        p.setPen(QPen(QColor("#065F46"), 1.1))
        p.drawEllipse(QPointF(23.5, 23.5), 7.6, 7.6)

        p.setPen(QPen(QColor("#FFFFFF"), 2.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(19.6, 23.8), QPointF(22.4, 26.6), QPointF(27.6, 20.6)]))

    elif nombre == "bancos-conciliacion":
        # Documento PDF bancario 3D con franja carmesí + templo bancario clásico zafiro/oro
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 42))
        p.drawRoundedRect(QRectF(5, 5, 19, 25), 1.5, 1.5)
        p.setBrush(_grad(4, 3.5, 22, 28, "#FFFFFF", "#E2E8F0"))
        p.setPen(QPen(QColor("#1B3A5C"), 1.1))
        p.drawRoundedRect(QRectF(4, 3.5, 18.5, 24.5), 1.5, 1.5)

        # Banda PDF carmesí 3D superior
        p.setBrush(_grad(4, 3.5, 22.5, 9.5, "#EF4444", "#991B1B"))
        p.setPen(QPen(QColor("#7F1D1D"), 0.8))
        p.drawRect(QRectF(4, 3.5, 18.5, 6.0))
        p.setPen(QColor("#FFFFFF"))
        f_pdf = QFont("Arial", 5)
        f_pdf.setBold(True)
        p.setFont(f_pdf)
        p.drawText(QRectF(4, 3.5, 18.5, 6.0), Qt.AlignmentFlag.AlignCenter, "PDF")

        p.setPen(QPen(QColor("#64748B"), 1.1))
        p.drawLine(QPointF(7, 13.5), QPointF(17, 13.5))
        p.drawLine(QPointF(7, 17.5), QPointF(15, 17.5))
        p.drawLine(QPointF(7, 21.5), QPointF(14, 21.5))

        # Banco clásico 3D dorado/azul en esquina inferior derecha
        fronton = QPolygonF([QPointF(15, 20.5), QPointF(24, 15.0), QPointF(33, 20.5)])
        p.setBrush(_grad(15, 15, 33, 21, "#FDE68A", "#B45309"))
        p.setPen(QPen(QColor("#78350F"), 1.0))
        p.drawPolygon(fronton)

        p.setBrush(_grad(16.5, 20.5, 31.5, 31, "#3B82F6", "#0F2744"))
        p.setPen(QPen(QColor("#0F2744"), 0.9))
        p.drawRect(QRectF(16.5, 20.5, 15.0, 9.5))
        p.setPen(QPen(QColor("#FFFFFF"), 1.6))
        for cx in (19.5, 24.0, 28.5):
            p.drawLine(QPointF(cx, 21.8), QPointF(cx, 28.5))
        p.setBrush(_grad(14.5, 29.5, 33.5, 32, "#107C41", "#064E3B"))
        p.setPen(QPen(QColor("#064E3B"), 0.8))
        p.drawRect(QRectF(14.5, 29.5, 19.0, 2.8))

    elif nombre == "copiloto":
        # Consola analítica 3D zafiro metálico + destello dorado de copiloto
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 48))
        p.drawRoundedRect(QRectF(5, 8, 27, 23), 3, 3)

        p.setBrush(_grad(4, 6, 30, 30, "#1E4E8C", "#09192D", "#122B4A"))
        p.setPen(QPen(QColor("#60A5FA"), 1.2))
        p.drawRoundedRect(QRectF(4, 6, 26, 23.5), 3, 3)

        # Barra superior biselada estilo terminal
        p.setBrush(_grad(4, 6, 30, 11, "#3B82F6", "#1D4ED8"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(4.6, 6.6, 24.8, 4.6), 2, 2)

        # Texto SQL + líneas luminosas esmeralda/cian
        p.setPen(QColor("#6EE7B7"))
        f_sql = QFont("Consolas", 6)
        f_sql.setBold(True)
        p.setFont(f_sql)
        p.drawText(QRectF(6.5, 12.2, 21, 8), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "SQL>")
        p.setPen(QPen(QColor("#93C5FD"), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(7.5, 21.5), QPointF(21.5, 21.5))
        p.setPen(QPen(QColor("#38BDF8"), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(7.5, 25.0), QPointF(16.5, 25.0))

        # Destello/estrella ejecutiva dorada 3D
        estrella = QPolygonF([
            QPointF(27.0, 2.5), QPointF(28.8, 7.6), QPointF(34.0, 9.4), QPointF(28.8, 11.2),
            QPointF(27.0, 16.3), QPointF(25.2, 11.2), QPointF(20.0, 9.4), QPointF(25.2, 7.6),
        ])
        p.setBrush(_grad(20, 3, 34, 16, "#FEF3C7", "#D97706", "#FBBF24"))
        p.setPen(QPen(QColor("#78350F"), 0.9))
        p.drawPolygon(estrella)

    elif nombre == "muestreo-mus":
        # Marco biselado de población
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 42))
        p.drawRoundedRect(QRectF(4, 7, 29, 24), 2, 2)
        p.setBrush(_grad(3, 5, 31, 29, "#FFFFFF", "#DCE5F0"))
        p.setPen(QPen(QColor("#1B3A5C"), 1.2))
        p.drawRoundedRect(QRectF(3, 5, 28, 24), 2, 2)

        # Celdas de muestreo en relieve + cubos monetarios 3D seleccionados
        _pintar_bloque_3d(p, 5.5, 11.5, 7.5, 5.5, 2.4, "#34D399", "#107C41", "#A7F3D0", "#065F46", "#064E3B")
        _pintar_bloque_3d(p, 16.5, 11.5, 10.5, 5.5, 2.4, "#E2E8F0", "#94A3B8", "#F8FAFC", "#64748B", "#475569")
        _pintar_bloque_3d(p, 5.5, 21.0, 9.5, 5.5, 2.4, "#FDE68A", "#D97706", "#FEF3C7", "#B45309", "#78350F")
        _pintar_bloque_3d(p, 18.5, 21.0, 8.5, 5.5, 2.4, "#60A5FA", "#1D4ED8", "#DBEAFE", "#1E3A8A", "#0F2744")

    elif nombre == "conectores":
        # Base de sombra del cilindro SQL
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 45))
        p.drawEllipse(QRectF(6.5, 27.5, 23, 6))

        # 3 niveles de cilindro 3D metálico-zafiro
        for idx, y0 in enumerate((20.0, 13.5, 7.0)):
            grad_cyl = QLinearGradient(7, y0, 29, y0)
            grad_cyl.setColorAt(0.0, QColor("#172554"))
            grad_cyl.setColorAt(0.30, QColor("#60A5FA"))
            grad_cyl.setColorAt(0.55, QColor("#2563EB"))
            grad_cyl.setColorAt(0.85, QColor("#1E3A8A"))
            grad_cyl.setColorAt(1.0, QColor("#0F172A"))

            cuerpo = QPainterPath()
            cuerpo.moveTo(7, y0)
            cuerpo.lineTo(7, y0 + 6.5)
            cuerpo.arcTo(QRectF(7, y0 + 3.8, 22, 5.4), 180, 180)
            cuerpo.lineTo(29, y0)
            cuerpo.closeSubpath()

            p.setBrush(grad_cyl)
            p.setPen(QPen(QColor("#0F2744"), 1.0))
            p.drawPath(cuerpo)

            # Luz LED verde esmeralda en cada disco
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#4ADE80"))
            p.drawEllipse(QPointF(10.5, y0 + 4.3), 1.1, 1.1)

        # Tapa elíptica brillante superior
        p.setBrush(_grad(7, 4, 29, 10, "#EFF6FF", "#60A5FA", "#BAE6FD"))
        p.setPen(QPen(QColor("#1E3A8A"), 1.1))
        p.drawEllipse(QRectF(7, 4.2, 22, 5.6))

        # Conector dorado lateral (enchufe ERP)
        p.setBrush(_grad(23, 21, 33, 30, "#FDE68A", "#B45309"))
        p.setPen(QPen(QColor("#78350F"), 0.9))
        p.drawRoundedRect(QRectF(23.5, 22.0, 9.0, 7.0), 1.5, 1.5)
        p.setPen(QPen(QColor("#FFFFFF"), 1.5))
        p.drawLine(QPointF(26.0, 25.5), QPointF(30.0, 25.5))

    elif nombre == "bitacora":
        # Hojas blancas apiladas del libro mayor
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 48))
        p.drawRoundedRect(QRectF(5.5, 5.5, 21, 26), 2, 2)
        p.setBrush(_grad(7, 3, 27, 29, "#FFFFFF", "#CBD5E1"))
        p.setPen(QPen(QColor("#64748B"), 0.9))
        p.drawRoundedRect(QRectF(7, 3, 19.5, 25.5), 1.5, 1.5)

        # Portada 3D verde Excel clásico al frente
        p.setBrush(_grad(4, 5, 22, 29, "#21A366", "#0B532C", "#107C41"))
        p.setPen(QPen(QColor("#064E3B"), 1.1))
        p.drawRoundedRect(QRectF(4, 5, 19, 24.5), 2, 2)
        p.setPen(QPen(QColor("#FFFFFF"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(9.5, 13), QPointF(16.5, 21.5))
        p.drawLine(QPointF(16.5, 13), QPointF(9.5, 21.5))

        # Escudo 3D azul marino/oro SHA-256 al frente derecha
        escudo = QPainterPath()
        escudo.moveTo(25.5, 16.0)
        escudo.lineTo(32.5, 18.2)
        escudo.lineTo(32.0, 24.5)
        escudo.quadTo(30.0, 29.8, 25.5, 32.0)
        escudo.quadTo(21.0, 29.8, 19.0, 24.5)
        escudo.lineTo(18.5, 18.2)
        escudo.closeSubpath()

        p.setBrush(_grad(18, 16, 33, 32, "#2563EB", "#0F2744", "#1B3A5C"))
        p.setPen(QPen(QColor("#FBBF24"), 1.4))
        p.drawPath(escudo)
        p.setPen(QPen(QColor("#FDE68A"), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(22.2, 24.0), QPointF(24.8, 26.5), QPointF(29.2, 21.5)]))

    elif nombre == "encargos":
        # Carpeta ejecutiva 3D azul/dorada con sello de firma por roles
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 45))
        p.drawRoundedRect(QRectF(4.5, 8.5, 26, 22), 2, 2)

        # Pestaña trasera de la carpeta
        solapa = QPolygonF([
            QPointF(4, 6), QPointF(14.5, 6), QPointF(17.5, 9.5),
            QPointF(29.5, 9.5), QPointF(29.5, 28.5), QPointF(4, 28.5),
        ])
        p.setBrush(_grad(4, 6, 30, 29, "#FBBF24", "#B45309"))
        p.setPen(QPen(QColor("#78350F"), 1.0))
        p.drawPolygon(solapa)

        # Portada azul marino biselada con documento blanco asomando
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#94A3B8"), 0.8))
        p.drawRect(QRectF(6.5, 10.5, 20.5, 10.0))

        frente = QPolygonF([
            QPointF(3.5, 13.5), QPointF(30.0, 13.5), QPointF(29.0, 29.0), QPointF(4.5, 29.0)
        ])
        p.setBrush(_grad(4, 13, 30, 29, "#3B82F6", "#0F2744", "#1E4E8C"))
        p.setPen(QPen(QColor("#0F2744"), 1.1))
        p.drawPolygon(frente)

        # Medallón 3D dorado de firma de Socio / Revisor
        med = QRadialGradient(25.0, 23.0, 7.5)
        med.setColorAt(0.0, QColor("#FEF3C7"))
        med.setColorAt(0.5, QColor("#F59E0B"))
        med.setColorAt(1.0, QColor("#92400E"))
        p.setBrush(med)
        p.setPen(QPen(QColor("#78350F"), 1.0))
        p.drawEllipse(QPointF(26.0, 24.5), 6.2, 6.2)
        p.setPen(QPen(QColor("#FFFFFF"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(23.2, 24.6), QPointF(25.2, 26.8), QPointF(29.0, 22.4)]))

    elif nombre == "correr":
        # Medallón circular 3D biselado esmeralda con triángulo Play
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QPointF(18.8, 19.2), 13.2, 13.2)

        med = QRadialGradient(14.5, 13.0, 16.0)
        med.setColorAt(0.0, QColor("#6EE7B7"))
        med.setColorAt(0.45, QColor("#107C41"))
        med.setColorAt(1.0, QColor("#064E3B"))
        p.setBrush(med)
        p.setPen(QPen(QColor("#064E3B"), 1.2))
        p.drawEllipse(QPointF(18.0, 18.0), 13.0, 13.0)

        p.setBrush(_grad(13, 10, 26, 25, "#FFFFFF", "#DCFCE7"))
        p.setPen(QPen(QColor("#065F46"), 0.8))
        p.drawPolygon(QPolygonF([QPointF(14.0, 10.8), QPointF(26.2, 18.0), QPointF(14.0, 25.2)]))

    elif nombre == "excel":
        # Libro Excel 3D vintage-moderno con lomo y X blanca en relieve
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 48))
        p.drawRoundedRect(QRectF(7, 6, 24, 27), 2, 2)

        p.setBrush(_grad(12, 4, 31, 30, "#FFFFFF", "#CBD5E1"))
        p.setPen(QPen(QColor("#475569"), 1.0))
        p.drawRoundedRect(QRectF(12, 4.5, 18.5, 25.5), 1.5, 1.5)
        p.setPen(QPen(QColor("#94A3B8"), 1.0))
        for ry in (10, 15, 20, 25):
            p.drawLine(QPointF(21, ry), QPointF(28, ry))

        p.setBrush(_grad(4, 6, 23, 31, "#33C481", "#0B532C", "#107C41"))
        p.setPen(QPen(QColor("#064E3B"), 1.1))
        p.drawRoundedRect(QRectF(4, 6, 19, 25), 2, 2)
        p.setPen(QPen(QColor("#FFFFFF"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(9.5, 13.5), QPointF(17.5, 23.5))
        p.drawLine(QPointF(17.5, 13.5), QPointF(9.5, 23.5))

    p.end()
    return QIcon(pm)


class TarjetaKPI(QFrame):
    """Tarjeta KPI corporativa recta con barra lateral de color por severidad."""

    COLORES = {
        "alto": "#B91C1C",
        "medio": "#B45309",
        "bajo": "#000080",
        "ok": "#107C41",
        "neutro": "#000080",
    }

    def __init__(self, titulo: str, valor: str = "—", subtitulo: str = "", variante: str = "neutro", parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(84)
        self._aplicar_estilo(variante)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)

        self.lbl_titulo = QLabel(titulo.upper())
        self.lbl_titulo.setStyleSheet("color: #333333; font-size: 7.4pt; font-weight: 700; letter-spacing: 0.6px; border: none; background: transparent;")
        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setStyleSheet("color: #000000; font-size: 14pt; font-weight: 700; border: none; background: transparent;")
        self.lbl_sub = QLabel(subtitulo)
        self.lbl_sub.setStyleSheet("color: #404040; font-size: 7.5pt; border: none; background: transparent;")

        lay.addWidget(self.lbl_titulo)
        lay.addWidget(self.lbl_valor)
        lay.addWidget(self.lbl_sub)

    def _aplicar_estilo(self, variante: str) -> None:
        """Aplica el bisel Win32 elevado con franja lateral de severidad."""
        borde = self.COLORES.get(variante, "#000080")
        self.setStyleSheet(
            "TarjetaKPI { background-color: #ECE9D8; "
            "border-top: 1px solid #FFFFFF; border-right: 1px solid #808080; "
            f"border-bottom: 1px solid #808080; border-left: 4px solid {borde}; border-radius: 0px; }}"
        )

    def actualizar(self, valor: str, subtitulo: str = "", variante: str | None = None) -> None:
        self.lbl_valor.setText(str(valor))
        self.lbl_sub.setText(subtitulo)
        if variante:
            self._aplicar_estilo(variante)


class ModeloTablaPandas(QAbstractTableModel):
    """Modelo de tabla virtualizado para mostrar cientos de miles de filas sin demoras."""

    def __init__(
        self,
        df: pd.DataFrame | None = None,
        nombres_columnas: dict[str, str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._df = df.copy() if df is not None else pd.DataFrame()
        self._nombres = nombres_columnas or {}
        self._col_lower = [str(c).lower() for c in self._df.columns]

    def actualizar_df(self, df: pd.DataFrame, nombres_columnas: dict[str, str] | None = None) -> None:
        self.beginResetModel()
        self._df = df.copy() if df is not None else pd.DataFrame()
        if nombres_columnas is not None:
            self._nombres = nombres_columnas
        self._col_lower = [str(c).lower() for c in self._df.columns]
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self._df.columns):
            col = str(self._df.columns[section])
            return self._nombres.get(col, col)
        return str(section + 1)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        fila, col = index.row(), index.column()
        col_nombre = self._col_lower[col]
        val = self._df.iat[fila, col]

        if role == Qt.ItemDataRole.UserRole:
            return val

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col_nombre in COLUMNAS_MONETARIAS or col_nombre in ("puntaje", "lineas", "filas", "hallazgos", "criterios", "tamano"):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if col_nombre in ("nivel", "fecha", "dia"):
                return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.BackgroundRole and col_nombre == "nivel":
            txt = str(val).lower()
            if txt == "alto":
                return QColor("#FEE2E2")
            if txt == "medio":
                return QColor("#FEF3C7")
            if txt == "bajo":
                return QColor("#DBEAFE")

        if role == Qt.ItemDataRole.ForegroundRole and col_nombre == "nivel":
            txt = str(val).lower()
            if txt == "alto":
                return QColor("#991B1B")
            if txt == "medio":
                return QColor("#92400E")
            if txt == "bajo":
                return QColor("#1E40AF")

        if role == Qt.ItemDataRole.FontRole and col_nombre == "nivel":
            f = QFont("Segoe UI", 8)
            f.setBold(True)
            return f

        if role == Qt.ItemDataRole.DisplayRole:
            if pd.isna(val):
                return ""
            if isinstance(val, bool):
                return "Sí" if val else "—"
            if isinstance(val, (pd.Timestamp, datetime, date)):
                return val.strftime("%Y-%m-%d")
            if col_nombre in COLUMNAS_MONETARIAS and isinstance(val, (int, float)):
                return f"{float(val):,.2f}"
            if isinstance(val, float) and val.is_integer():
                return f"{int(val):,}"
            return str(val)

        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if self._df.empty or not (0 <= column < len(self._df.columns)):
            return
        col = self._df.columns[column]
        self.layoutAboutToBeChanged.emit()
        self._df = self._df.sort_values(
            by=col,
            ascending=(order == Qt.SortOrder.AscendingOrder),
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)
        self.layoutChanged.emit()


class DelegadoBarraPuntaje(QStyledItemDelegate):
    """Dibuja barra horizontal estilo Data Bars de Excel para la columna Puntaje."""

    def __init__(self, puntaje_maximo: int = 100, col_nivel: int | None = None, parent=None) -> None:
        super().__init__(parent)
        self.puntaje_maximo = max(int(puntaje_maximo or 100), 1)
        self.col_nivel = col_nivel

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#DBEAFE"))
        else:
            painter.fillRect(option.rect, QColor("#FFFFFF"))

        raw = index.data(Qt.ItemDataRole.UserRole)
        try:
            valor = float(raw)
        except (TypeError, ValueError):
            valor = 0.0

        nivel = ""
        if self.col_nivel is not None:
            idx_n = index.sibling(index.row(), self.col_nivel)
            nivel = str(idx_n.data(Qt.ItemDataRole.DisplayRole) or "").lower()

        color_barra = QColor("#B91C1C") if nivel == "alto" else (QColor("#D97706") if nivel == "medio" else QColor("#2563EB"))

        caja = option.rect.adjusted(6, 5, -6, -5)
        painter.fillRect(caja, QColor("#E2E8F0"))
        frac = min(max(valor / float(self.puntaje_maximo), 0.0), 1.0)
        ancho = int(caja.width() * frac)
        if ancho > 0:
            g = _grad(caja.left(), caja.top(), caja.left(), caja.bottom(), color_barra.lighter(120).name(), color_barra.name())
            painter.fillRect(QRect(caja.left(), caja.top(), ancho, caja.height()), g)

        texto = str(int(valor)) if valor.is_integer() else f"{valor:g}"
        painter.setPen(QColor("#FFFFFF") if frac > 0.45 else QColor("#0F172A"))
        font = QFont("Consolas", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(caja.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, texto)
        painter.restore()
