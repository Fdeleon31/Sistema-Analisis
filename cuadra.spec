# -*- mode: python ; coding: utf-8 -*-
"""Especificación PyInstaller para generar el programa portátil offline de Windows (LibroAuditoria)."""

from pathlib import Path

RAIZ = Path(SPECPATH)

datas = [
    (str(RAIZ / "paquetes"), "paquetes"),
    (str(RAIZ / "conectores" / "perfiles"), "conectores/perfiles"),
    (str(RAIZ / "app" / "estilos.css"), "app"),
    (str(RAIZ / "docs" / "seguridad"), "docs/seguridad"),
]

hiddenimports = [
    "duckdb",
    "pandas",
    "openpyxl",
    "yaml",
    "sqlite3",
    "PySide6.QtPdf",
    "motor",
    "motor.bitacora",
    "motor.cripto",
    "motor.diagnostico",
    "motor.ejecutor",
    "motor.estadistica",
    "motor.exportador",
    "motor.factura_electronica",
    "motor.formato_excel",
    "motor.importador",
    "motor.muestreo",
    "motor.portafolio",
    "motor.privacidad",
    "motor.revision",
    "motor.rutas",
    "motor.seguridad",
    "motor.servicio",
    "motor.sintetico",
    "motor.sugerencias",
    "motor.usuarios",
    "conectores",
    "conectores.catalogo",
    "conectores.estado_cuenta_pdf",
    "conectores.sql_fuente",
    "ia",
    "ia.copiloto",
    "app",
    "app.comun",
    "app.componentes_qt",
    "app.login_qt",
    "herramientas",
    "herramientas.seguridad_build",
]

a = Analysis(
    [str(RAIZ / "app" / "escritorio.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "streamlit",
        "pytest",
        "tornado",
        "altair",
        "pydeck",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.QtDesigner",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LibroAuditoria",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LibroAuditoria",
)
