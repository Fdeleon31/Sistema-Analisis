"""Estilos ejecutivos offline para las cédulas Excel de auditoría."""
from __future__ import annotations

from datetime import date, datetime
from itertools import islice

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


FILL_ENCABEZADO = PatternFill("solid", fgColor="0F2744")
FONT_ENCABEZADO = Font(name="Calibri", size=10.5, bold=True, color="FFFFFF")
FONT_DATOS = Font(name="Calibri", size=10, color="111827")

BORDE_DATO = Border(bottom=Side(style="thin", color="E2E8F0"))
BORDE_ENCABEZADO = Border(bottom=Side(style="medium", color="1E3A5F"))

ESTILOS_ESTADO = {
    "ALERTA": (PatternFill("solid", fgColor="FEE2E2"), Font(name="Calibri", size=10, bold=True, color="991B1B")),
    "ALTO": (PatternFill("solid", fgColor="FEE2E2"), Font(name="Calibri", size=10, bold=True, color="991B1B")),
    "HALLAZGO CONFIRMADO": (PatternFill("solid", fgColor="FEE2E2"), Font(name="Calibri", size=10, bold=True, color="991B1B")),
    "NO CONFORME": (PatternFill("solid", fgColor="FEE2E2"), Font(name="Calibri", size=10, bold=True, color="991B1B")),
    "ADVERTENCIA": (PatternFill("solid", fgColor="FEF3C7"), Font(name="Calibri", size=10, bold=True, color="92400E")),
    "MEDIO": (PatternFill("solid", fgColor="FEF3C7"), Font(name="Calibri", size=10, bold=True, color="92400E")),
    "EN REVISIÓN": (PatternFill("solid", fgColor="FEF3C7"), Font(name="Calibri", size=10, bold=True, color="92400E")),
    "PENDIENTE": (PatternFill("solid", fgColor="F1F5F9"), Font(name="Calibri", size=10, color="475569")),
    "OK": (PatternFill("solid", fgColor="DCFCE7"), Font(name="Calibri", size=10, bold=True, color="166534")),
    "FIRMADO": (PatternFill("solid", fgColor="DCFCE7"), Font(name="Calibri", size=10, bold=True, color="166534")),
    "ACLARADO CON EVIDENCIA": (PatternFill("solid", fgColor="DCFCE7"), Font(name="Calibri", size=10, bold=True, color="166534")),
    "BAJO": (PatternFill("solid", fgColor="DCFCE7"), Font(name="Calibri", size=10, bold=True, color="166534")),
}

COLS_MONEDA = {
    "monto", "debito", "credito", "saldo", "saldo_inicial", "saldo_final",
    "monto excluido", "total_asiento", "total_debito", "total_credito",
    "total_bruto", "total_neto", "subtotal", "itbms", "total",
    "saldo_libro", "saldo_calculado", "debe", "haber", "variacion",
    "diferencia_neta", "diferencia_abs", "materialidad",
}
COLS_ENVOLVER = {
    "detalle", "explicacion", "transformaciones", "conclusión del auditor",
    "observación", "accion_sugerida", "descripcion", "razon_social",
}


def estilizar_libro(xls, max_filas_estilo: int = 2500, encabezado_impresion: str = "") -> None:
    """Aplica formato de papel de trabajo ejecutivo a todas las hojas del libro openpyxl."""
    for hoja in xls.sheets.values():
        if encabezado_impresion:
            hoja.oddHeader.left.text = encabezado_impresion[:140]
            hoja.oddHeader.left.size = 8
            hoja.oddHeader.right.text = "&D &T"
            hoja.oddHeader.right.size = 8
            hoja.oddFooter.left.text = "Folio Auditor · Evidencia determinista SHA-256"
            hoja.oddFooter.left.size = 8
            hoja.oddFooter.right.text = "Página &P de &N"
            hoja.oddFooter.right.size = 8

        max_row = hoja.max_row or 0
        max_col = hoja.max_column or 0
        if max_row < 1 or max_col < 1:
            continue

        hoja.views.sheetView[0].showGridLines = True
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = f"A1:{get_column_letter(max_col)}{max_row}"
        hoja.row_dimensions[1].height = 24

        encabezados: dict[int, str] = {}
        for col_idx in range(1, max_col + 1):
            celda = hoja.cell(row=1, column=col_idx)
            nombre = str(celda.value or "").strip().lower()
            encabezados[col_idx] = nombre
            celda.fill = FILL_ENCABEZADO
            celda.font = FONT_ENCABEZADO
            celda.border = BORDE_ENCABEZADO
            celda.alignment = Alignment(vertical="center", horizontal="left", wrap_text=True)

        limite = min(max_row, max_filas_estilo + 1)
        for row_idx in range(2, limite + 1):
            for col_idx in range(1, max_col + 1):
                celda = hoja.cell(row=row_idx, column=col_idx)
                col_nombre = encabezados[col_idx]
                celda.font = FONT_DATOS
                celda.border = BORDE_DATO

                val = celda.value
                clave_est = str(val).strip().upper() if val is not None else ""
                if clave_est in ESTILOS_ESTADO and col_nombre in (
                    "estado", "nivel", "riesgo", "estado revisión", "resultado", ""
                ):
                    fill_e, font_e = ESTILOS_ESTADO[clave_est]
                    celda.fill = fill_e
                    celda.font = font_e
                    celda.alignment = Alignment(vertical="center", horizontal="center")
                elif isinstance(val, (int, float)) and not isinstance(val, bool) and col_nombre in COLS_MONEDA:
                    celda.number_format = '#,##0.00;(#,##0.00);"-"'
                    celda.alignment = Alignment(vertical="center", horizontal="right")
                elif isinstance(val, (date, datetime)):
                    celda.number_format = "yyyy-mm-dd"
                    celda.alignment = Alignment(vertical="center", horizontal="center")
                else:
                    envolver = col_nombre in COLS_ENVOLVER
                    celda.alignment = Alignment(vertical="top" if envolver else "center", wrap_text=envolver)

        for columna in hoja.columns:
            largo = max(len(str(c.value)) if c.value is not None else 0 for c in islice(columna, 200))
            col_letra = columna[0].column_letter
            col_nombre = str(columna[0].value or "").strip().lower()
            tope = 56 if col_nombre in COLS_ENVOLVER else 46
            hoja.column_dimensions[col_letra].width = min(max(12, largo + 3), tope)
