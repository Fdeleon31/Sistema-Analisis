"""Ficha 13 · Lectura sin internet de estados de cuenta bancarios (PDF, ZIP, carpeta o tabular).

Extrae movimientos bancarios de extractos locales (Panamá y formatos estándar) usando
el motor integrado en Python puro (PDF 1.4/FlateDecode) con respaldo en QtPdf (`QPdfDocument`).
"""
from __future__ import annotations

import hashlib
import re
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from motor.seguridad import (
    MAX_ARCHIVOS_ZIP,
    MAX_BYTES_PDF_FLUJO,
    MAX_BYTES_PDF_TOTAL,
    ErrorSeguridad,
    descomprimir_zlib_seguro,
    leer_miembros_zip_seguros,
    nombre_archivo_seguro,
)

COLUMNAS_EXTRACTO = [
    "archivo",
    "banco",
    "cuenta_bancaria",
    "linea",
    "fecha",
    "referencia",
    "descripcion",
    "debito",
    "credito",
    "monto",
    "saldo",
]

BANCOS_PANAMA = [
    ("Banco General", re.compile(r"banco\s+general", re.IGNORECASE)),
    ("Banistmo", re.compile(r"banistmo", re.IGNORECASE)),
    ("BAC Credomatic", re.compile(r"bac\s+credomatic|\bbac\b", re.IGNORECASE)),
    ("Global Bank", re.compile(r"global\s+bank", re.IGNORECASE)),
    ("Banco Nacional de Panamá", re.compile(r"banco\s+nacional|bnp", re.IGNORECASE)),
    ("Caja de Ahorros", re.compile(r"caja\s+de\s+ahorros", re.IGNORECASE)),
    ("Multibank", re.compile(r"multibank", re.IGNORECASE)),
    ("Credicorp Bank", re.compile(r"credicorp", re.IGNORECASE)),
]

MESES_CORTO = {
    "ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "ago": 8, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12,
}

RE_FECHA_INICIO = re.compile(
    r"^\s*(?P<fecha>"
    r"\d{4}[-/.]\d{2}[-/.]\d{2}"
    r"|\d{2}[/-]\d{2}[/-]\d{2,4}"
    r"|\d{1,2}[\s/-][A-Za-zÁÉÍÓÚáéíóú]{3}[\s/-]\d{2,4}"
    r"|[A-Za-zÁÉÍÓÚáéíóú]{3}\s+\d{1,2},?\s+\d{4}"
    r")\b\s*(?P<resto>.*)$"
)
RE_CUENTA = re.compile(
    r"(?:cuenta|cta\.?|account|n[uú]mero\s+de\s+cuenta)\s*[:#-]?\s*([A-Za-z0-9X*-]{5,24})",
    re.IGNORECASE,
)
RE_TOKEN_NUM = re.compile(
    r"^(?:\$?\s*|B/\.?\s*|USD\s*)?\(?[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}\)?-?(?:CR|DB|DR)?$"
    r"|^(?:\$?\s*|B/\.?\s*|USD\s*)?\(?[-+]?(?:\d{1,3}(?:,\d{3})+|\d+),\d{2}\)?-?(?:CR|DB|DR)?$"
    r"|^(?:-|—|--)$",
    re.IGNORECASE,
)
RE_LINEA_IGNORA_EXACTA = re.compile(
    r"^\s*(?:banco|estado\s+de\s+cuenta|cuenta|moneda|fecha\s+de|p[áa]gina|pag\.?\s+\d|"
    r"saldo\s+(?:inicial|anterior|de\s+apertura|final|actual|al\s+corte|de\s+cierre)|"
    r"totales|subtotal|total\s+d[ée]bitos|total\s+cr[ée]ditos|periodo\s*:|sucursal\s*:|"
    r"fecha\s+ref|fecha\s+descripci[óo]n|---\s*$|===+\s*$)",
    re.IGNORECASE,
)
RE_PIE_O_RESUMEN = re.compile(
    r"^\s*(?:fin\s+del\s+estado|nota\s*:|atentamente|este\s+estado|cualquier\s+reclamo|"
    r"generado\s+(?:el|autom)|consultas\s*:|resumen\s+de\s+cuenta|centro\s+de\s+atenci|"
    r"estimado\s+cliente|cantidad\s+de\s+movimientos)",
    re.IGNORECASE,
)
_PREF_MONTO = r"(?:[$B/.\sUSD(+-]*(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.,]\d{2})?\)?(?:\s*(?:CR|DB|DR|-))?)"
RE_SALDO_INICIAL = re.compile(
    rf"saldo\s+(?:inicial|anterior|de\s+apertura)\s*[:=]?\s*(?P<monto>{_PREF_MONTO})",
    re.IGNORECASE,
)
RE_SALDO_FINAL = re.compile(
    rf"saldo\s+(?:final|actual|al\s+corte|de\s+cierre)\s*[:=]?\s*(?P<monto>{_PREF_MONTO})",
    re.IGNORECASE,
)


@dataclass
class LecturaExtracto:
    movimientos: pd.DataFrame
    errores: list[dict] = field(default_factory=list)
    lineas_omitidas: int = 0
    archivos: int = 0
    sha256: str = ""
    metodo: str = "pdf"
    resumen_saldos: list[dict] = field(default_factory=list)


def _parsear_fecha_banco(texto: str) -> date | None:
    t = texto.strip()
    if re.match(r"^\d{4}[-/.]\d{2}[-/.]\d{2}$", t):
        t_iso = t.replace("/", "-").replace(".", "-")
        try:
            return date.fromisoformat(t_iso)
        except ValueError:
            return None
    m_txt = re.match(r"^(\d{1,2})[\s/-]([A-Za-zÁÉÍÓÚáéíóú]{3})[\s/-](\d{2,4})$", t)
    if m_txt:
        dia, mes_s, anio_s = int(m_txt.group(1)), m_txt.group(2).lower(), int(m_txt.group(3))
        anio = 2000 + anio_s if anio_s < 100 else anio_s
        mes = MESES_CORTO.get(mes_s)
        if mes:
            try:
                return date(anio, mes, dia)
            except ValueError:
                return None
    m_mdy = re.match(r"^([A-Za-zÁÉÍÓÚáéíóú]{3})\s+(\d{1,2}),?\s+(\d{4})$", t)
    if m_mdy:
        mes_s, dia, anio = m_mdy.group(1).lower(), int(m_mdy.group(2)), int(m_mdy.group(3))
        mes = MESES_CORTO.get(mes_s)
        if mes:
            try:
                return date(anio, mes, dia)
            except ValueError:
                return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _parsear_monto_banco(token: str) -> tuple[float | None, str]:
    """Convierte un token monetario de extracto a (valor, etiqueta CR/DB/'')."""
    t = token.strip().upper()
    if t in ("-", "—", "--"):
        return 0.0, ""
    etiqueta = ""
    if t.endswith("CR"):
        etiqueta, t = "CR", t[:-2].strip()
    elif t.endswith(("DB", "DR")):
        etiqueta, t = "DB", t[:-2].strip()
    neg = False
    if t.endswith("-"):
        neg = True
        t = t[:-1].strip()
    t = t.replace("B/.", "").replace("B/", "").replace("$", "").replace("USD", "").strip()
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1].strip()
    elif t.startswith("-"):
        neg = True
        t = t[1:].strip()
    elif t.startswith("+"):
        t = t[1:].strip()
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        parte_dec = t.rsplit(",", 1)[1]
        t = t.replace(",", ".") if len(parte_dec) == 2 else t.replace(",", "")
    val = round(float(t), 2)
    return (-val if neg else val), etiqueta


def _desescapar_pdf_literal(raw: bytes) -> str:
    out = bytearray()
    i, n = 0, len(raw)
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while i < n:
        ch = raw[i]
        if ch == 92 and i + 1 < n:  # '\'
            nxt = raw[i + 1]
            if nxt in escapes:
                out.append(escapes[nxt])
                i += 2
                continue
            if nxt in (92, 40, 41):  # \, (, )
                out.append(nxt)
                i += 2
                continue
            if nxt in (10, 13):
                i += 3 if (nxt == 13 and i + 2 < n and raw[i + 2] == 10) else 2
                continue
            if 48 <= nxt <= 55:  # octal \ddd
                fin = i + 2
                while fin < min(i + 4, n) and 48 <= raw[fin] <= 55:
                    fin += 1
                out.append(int(raw[i + 1 : fin], 8) & 0xFF)
                i = fin
                continue
        out.append(ch)
        i += 1
    return out.decode("cp1252", errors="replace")


def _decodificar_pdf_hex(raw: bytes) -> str:
    limpio = re.sub(rb"\s+", b"", raw)
    if len(limpio) % 2:
        limpio += b"0"
    try:
        datos = bytes.fromhex(limpio.decode("ascii"))
    except ValueError:
        return ""
    if datos.startswith(b"\xfe\xff"):
        return datos[2:].decode("utf-16-be", errors="replace")
    if len(datos) >= 4 and len(datos) % 2 == 0 and datos[0] == 0:
        return datos.decode("utf-16-be", errors="replace")
    return datos.decode("cp1252", errors="replace")


def _leer_literal_pdf(buf: bytes, idx: int) -> tuple[bytes, int]:
    """Lee un literal PDF `(...)` respetando paréntesis balanceados y escapes."""
    assert buf[idx : idx + 1] == b"("
    i, n, prof = idx + 1, len(buf), 1
    inicio = i
    while i < n and prof > 0:
        c = buf[i]
        if c == 92:  # '\'
            i += 2
            continue
        if c == 40:  # '('
            prof += 1
        elif c == 41:  # ')'
            prof -= 1
            if prof == 0:
                return buf[inicio:i], i + 1
        i += 1
    return buf[inicio:n], n


def _extraer_chunks_bt(bloque: bytes) -> list[tuple[float, float, str]]:
    """Extrae fragmentos `(y, x, texto)` desde un bloque `BT ... ET`."""
    chunks: list[tuple[float, float, str]] = []
    n = len(bloque)
    i = 0
    x, y, leading = 0.0, 0.0, 12.0
    nums: list[float] = []
    ultimo_array: list[str] = []
    ultimo_str: str | None = None

    while i < n:
        c = bloque[i]
        if c in (9, 10, 12, 13, 32):
            i += 1
            continue
        if c == 37:  # '%' comentario
            fin = bloque.find(b"\n", i)
            i = n if fin < 0 else fin + 1
            continue
        if c == 40:  # '(' literal string
            raw, i = _leer_literal_pdf(bloque, i)
            ultimo_str = _desescapar_pdf_literal(raw)
            continue
        if c == 60 and bloque[i : i + 2] != b"<<":  # '<...>' hex string
            fin = bloque.find(b">", i + 1)
            fin = n if fin < 0 else fin
            ultimo_str = _decodificar_pdf_hex(bloque[i + 1 : fin])
            i = fin + 1
            continue
        if c == 91:  # '[' array TJ
            i += 1
            partes: list[str] = []
            while i < n and bloque[i] != 93:
                bc = bloque[i]
                if bc == 40:
                    raw, i = _leer_literal_pdf(bloque, i)
                    partes.append(_desescapar_pdf_literal(raw))
                elif bc == 60:
                    fin = bloque.find(b">", i + 1)
                    fin = n if fin < 0 else fin
                    partes.append(_decodificar_pdf_hex(bloque[i + 1 : fin]))
                    i = fin + 1
                else:
                    i += 1
            ultimo_array = partes
            i += 1
            continue
        if c == 47:  # '/Name'
            m_nom = re.match(rb"/[^\s\[\]()<>/{}]+", bloque[i:])
            i += len(m_nom.group(0)) if m_nom else 1
            nums.clear()
            continue

        m_num = re.match(rb"[-+]?(?:\d+\.?\d*|\.\d+)(?=[\s\[\]()<>/{}]|$)", bloque[i:])
        if m_num:
            nums.append(float(m_num.group(0)))
            i += len(m_num.group(0))
            continue

        m_op = re.match(rb"[A-Za-z*'\"]+", bloque[i:])
        if m_op:
            op = m_op.group(0).decode("ascii", errors="ignore")
            i += len(m_op.group(0))
            if op in ("Td", "TD") and len(nums) >= 2:
                tx, ty = nums[-2], nums[-1]
                x += tx
                y += ty
                if op == "TD":
                    leading = -ty
            elif op == "Tm" and len(nums) >= 6:
                x, y = nums[-2], nums[-1]
            elif op == "TL" and nums:
                leading = nums[-1]
            elif op == "T*":
                y -= leading
            elif op == "Tj" and ultimo_str is not None:
                if ultimo_str.strip():
                    chunks.append((y, x, ultimo_str))
                ultimo_str = None
            elif op == "TJ":
                unido = "".join(ultimo_array)
                if unido.strip():
                    chunks.append((y, x, unido))
                ultimo_array = []
            elif op in ("'", '"') and ultimo_str is not None:
                y -= leading
                if ultimo_str.strip():
                    chunks.append((y, x, ultimo_str))
                ultimo_str = None
            nums.clear()
            continue
        i += 1
    return chunks


def _descomprimir_flujos_pdf(
    data: bytes,
    max_bytes_flujo: int = MAX_BYTES_PDF_FLUJO,
    max_bytes_total: int = MAX_BYTES_PDF_TOTAL,
) -> list[bytes]:
    """Extrae y descomprime flujos de contenido de un PDF con límites anti-bombas de compresión."""
    flujos: list[bytes] = []
    pos = 0
    total_bytes = 0
    for m in re.finditer(rb"(?<!end)stream(?:\r\n|\n|\r)", data):
        enc_ini = max(0, m.start() - 256)
        dic = data[enc_ini : m.start()]
        fin = data.find(b"endstream", m.end())
        if fin < pos or fin < 0:
            continue
        cuerpo = data[m.end() : fin]
        if cuerpo.endswith(b"\r\n"):
            cuerpo = cuerpo[:-2]
        elif cuerpo.endswith((b"\n", b"\r")):
            cuerpo = cuerpo[:-1]
        pos = fin + len(b"endstream")
        if b"/FlateDecode" in dic:
            try:
                cuerpo = descomprimir_zlib_seguro(cuerpo, max_bytes=max_bytes_flujo)
            except zlib.error:
                continue
        total_bytes += len(cuerpo)
        if total_bytes > max_bytes_total:
            raise ErrorSeguridad(
                f"Los flujos descomprimidos del PDF superan el límite máximo de {max_bytes_total:,} bytes."
            )
        if b"BT" in cuerpo and (b"Tj" in cuerpo or b"TJ" in cuerpo):
            flujos.append(cuerpo)
    return flujos


def _extraer_lineas_pdf_puro(data: bytes) -> list[str]:
    lineas: list[str] = []
    for flujo in _descomprimir_flujos_pdf(data):
        chunks_pagina: list[tuple[float, float, str]] = []
        for m_bt in re.finditer(rb"\bBT\b(.*?)\bET\b", flujo, re.DOTALL):
            chunks_pagina.extend(_extraer_chunks_bt(m_bt.group(1)))
        if not chunks_pagina:
            continue
        filas_y: dict[float, list[tuple[float, str]]] = {}
        for cy, cx, txt in chunks_pagina:
            clave_y = round(cy / 2.0) * 2.0
            filas_y.setdefault(clave_y, []).append((cx, txt.strip()))
        for clave_y in sorted(filas_y.keys(), reverse=True):
            partes = [txt for _, txt in sorted(filas_y[clave_y], key=lambda item: item[0]) if txt]
            if partes:
                lineas.append("  ".join(partes))
    return lineas


def _extraer_lineas_qtpdf(ruta: Path) -> list[str]:
    try:
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtPdf import QPdfDocument
    except Exception:  # noqa: BLE001
        return []
    app = QCoreApplication.instance()
    creada = False
    if app is None:
        app = QCoreApplication([])
        creada = True
    try:
        doc = QPdfDocument()
        err = doc.load(str(ruta))
        if err != QPdfDocument.Error.None_:
            return []
        lineas: list[str] = []
        for pag in range(doc.pageCount()):
            txt = doc.getAllText(pag).text()
            for ln in txt.splitlines():
                if ln.strip():
                    lineas.append(ln.strip())
        return lineas
    finally:
        if creada:
            app.quit()


def extraer_lineas_pdf(ruta: Path) -> list[str]:
    """Extrae líneas de texto de un PDF usando el parser Flate/Tj local y QtPdf como respaldo."""
    return _extraer_lineas_pdf_con_metodo(ruta)[0]


def _proporcion_legible(lineas: list[str]) -> float:
    """Fracción de caracteres imprimibles. Un PDF con fuentes incrustadas (CID/Identity-H) leído sin su
    tabla ToUnicode produce códigos de glifo como \x16\x14…, que no son texto."""
    texto = "".join(lineas)
    if not texto:
        return 0.0
    legibles = sum(1 for c in texto if c.isprintable() and not ("\x00" <= c <= "\x1f"))
    return legibles / len(texto)


def _lineas_con_fecha(lineas: list[str]) -> int:
    return sum(1 for ln in lineas if RE_FECHA_INICIO.match(ln.strip()))


def _extraer_lineas_pdf_con_metodo(ruta: Path) -> tuple[list[str], str]:
    """Devuelve (líneas, método). Usa el parser local si su texto es legible; si no, QtPdf (PDFium),
    que sí interpreta fuentes incrustadas. Si ninguno sirve, devuelve lo mejor que haya y el lector lo
    reportará como error (nunca se descarta en silencio)."""
    tamano = ruta.stat().st_size
    if tamano > MAX_BYTES_PDF_TOTAL:
        raise ErrorSeguridad(
            f"El archivo PDF {ruta.name!r} excede el límite máximo permitido ({tamano:,} > {MAX_BYTES_PDF_TOTAL:,} bytes)."
        )
    lineas = _extraer_lineas_pdf_puro(ruta.read_bytes())
    if lineas and _proporcion_legible(lineas) >= 0.98 and _lineas_con_fecha(lineas) > 0:
        return lineas, "pdf"
    lineas_qt = _extraer_lineas_qtpdf(ruta)
    if lineas_qt and _lineas_con_fecha(lineas_qt) >= _lineas_con_fecha(lineas):
        return lineas_qt, "pdf (QtPdf)"
    return lineas, "pdf"


def _detectar_banco_y_cuenta(lineas: list[str]) -> tuple[str, str]:
    encabezado = "\n".join(lineas[:20])
    banco = "Banco Genérico"
    for nombre, patron in BANCOS_PANAMA:
        if patron.search(encabezado):
            banco = nombre
            break
    cuenta = ""
    for ln in lineas[:20]:
        m = RE_CUENTA.search(ln)
        if m:
            cuenta = m.group(1).strip()
            break
    return banco, cuenta


def _separar_montos_finales(resto: str) -> tuple[str, list[tuple[float, str]]] | None:
    tokens = re.split(r"\s{2,}|\t+|\s+", resto.strip())
    montos_rev: list[tuple[float, str]] = []
    idx = len(tokens) - 1
    while idx >= 0 and len(montos_rev) < 3:
        tok = tokens[idx].strip()
        if RE_TOKEN_NUM.match(tok):
            try:
                val, etq = _parsear_monto_banco(tok)
            except ValueError:
                break
            if val is not None:
                montos_rev.append((val, etq))
                idx -= 1
                continue
        break
    if len(montos_rev) < 2:
        return None
    montos = list(reversed(montos_rev))
    texto_izq = " ".join(tokens[: idx + 1]).strip()
    return texto_izq, montos


def _es_linea_movimiento_roto(ln: str) -> bool:
    if RE_LINEA_IGNORA_EXACTA.match(ln) or RE_PIE_O_RESUMEN.match(ln):
        return False
    if _separar_montos_finales(ln) is not None:
        return True
    if re.match(r"^\d{1,4}[/-]\d{1,2}[/-]", ln):
        return True
    return bool(re.search(r"\b(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?:\s*(?:CR|DB|DR|-))?\s*$", ln, re.IGNORECASE))


def _resumen_saldo_extracto(lineas: list[str], filas: list[dict], nombre_archivo: str) -> dict:
    saldo_inicial = None
    saldo_final_rep = None
    for ln in lineas:
        if saldo_inicial is None:
            m_ini = RE_SALDO_INICIAL.search(ln)
            if m_ini:
                try:
                    val, etq = _parsear_monto_banco(m_ini.group("monto"))
                    if val is not None:
                        saldo_inicial = -abs(val) if etq == "DB" else val
                except ValueError:
                    pass
        m_fin = RE_SALDO_FINAL.search(ln)
        if m_fin:
            try:
                val, etq = _parsear_monto_banco(m_fin.group("monto"))
                if val is not None:
                    saldo_final_rep = -abs(val) if etq == "DB" else val
            except ValueError:
                pass

    total_deb = round(sum(float(f["debito"]) for f in filas), 2)
    total_cred = round(sum(float(f["credito"]) for f in filas), 2)
    saldo_obj = saldo_final_rep if saldo_final_rep is not None else (filas[-1]["saldo"] if filas else None)
    saldo_calc = round(saldo_inicial + total_cred - total_deb, 2) if saldo_inicial is not None else None
    diferencia = round(saldo_calc - saldo_obj, 2) if (saldo_calc is not None and saldo_obj is not None) else None
    cuadra = (abs(diferencia) <= 0.01) if diferencia is not None else None
    return {
        "archivo": nombre_archivo,
        "movimientos": len(filas),
        "saldo_inicial": saldo_inicial,
        "saldo_final_reportado": saldo_final_rep,
        "saldo_final_objetivo": saldo_obj,
        "total_debitos": total_deb,
        "total_creditos": total_cred,
        "saldo_calculado": saldo_calc,
        "diferencia": diferencia,
        "cuadra": cuadra,
    }


def _parsear_lineas_extracto(lineas: list[str], nombre_archivo: str) -> tuple[list[dict], list[dict], int]:
    banco, cuenta = _detectar_banco_y_cuenta(lineas)
    filas: list[dict] = []
    errores: list[dict] = []
    omitidas = 0
    linea_n = 0
    ultima_fila: dict | None = None
    continuaciones = 0
    saldo_previo: float | None = None

    for idx_raw, ln_raw in enumerate(lineas, start=1):
        ln = ln_raw.strip()
        if not ln:
            continue
        m_si = RE_SALDO_INICIAL.search(ln)
        if m_si and saldo_previo is None and not filas:
            try:
                val_si, etq_si = _parsear_monto_banco(m_si.group("monto"))
            except ValueError:
                val_si = None
            if val_si is not None:
                saldo_previo = -abs(val_si) if etq_si == "DB" else val_si
                ultima_fila = None
                continue
        if RE_SALDO_FINAL.search(ln):
            ultima_fila = None
            continue  # lo usa _resumen_saldo_extracto para el cuadre
        m_f = RE_FECHA_INICIO.match(ln)
        if not m_f:
            if _es_linea_movimiento_roto(ln):
                ultima_fila = None
                omitidas += 1
                errores.append({"archivo": nombre_archivo, "linea": idx_raw, "error": f"Línea sin fecha reconocida: {ln[:80]}"})
                continue
            if (
                ultima_fila is not None
                and continuaciones < 2
                and not RE_LINEA_IGNORA_EXACTA.match(ln)
                and not RE_PIE_O_RESUMEN.match(ln)
                and len(ln) <= 120
            ):
                extra = re.sub(r"\s+", " ", ln).strip()
                if ultima_fila["descripcion"] == "(sin descripción)":
                    ultima_fila["descripcion"] = extra
                else:
                    ultima_fila["descripcion"] = f"{ultima_fila['descripcion']} {extra}"
                continuaciones += 1
                continue
            ultima_fila = None
            omitidas += 1
            continue

        fecha = _parsear_fecha_banco(m_f.group("fecha"))
        if fecha is None:
            ultima_fila = None
            omitidas += 1
            errores.append({"archivo": nombre_archivo, "linea": idx_raw, "error": f"Fecha inválida: {ln[:80]}"})
            continue

        separado = _separar_montos_finales(m_f.group("resto"))
        if not separado:
            ultima_fila = None
            omitidas += 1
            errores.append({"archivo": nombre_archivo, "linea": idx_raw, "error": f"Sin columnas de monto y saldo: {ln[:80]}"})
            continue

        texto_izq, montos = separado
        if len(montos) == 3:
            deb = abs(montos[0][0])
            cred = abs(montos[1][0])
            saldo = round(montos[2][0], 2)
            monto = round(cred - deb, 2)
        else:
            val_mov, etq = montos[0]
            saldo = round(montos[1][0], 2)
            if etq == "DB":
                deb, cred = abs(val_mov), 0.0
            elif etq == "CR":
                deb, cred = 0.0, abs(val_mov)
            elif val_mov < 0:
                deb, cred = abs(val_mov), 0.0
            elif saldo_previo is not None and abs(round(saldo_previo - abs(val_mov), 2) - saldo) <= 0.005:
                # Una sola columna de monto sin signo: la dirección sale del saldo corrido.
                deb, cred = abs(val_mov), 0.0
            else:
                deb, cred = 0.0, abs(val_mov)
            monto = round(cred - deb, 2)

        referencia = ""
        descripcion = texto_izq
        m_ref = re.match(r"^([A-Z]{0,5}-?\d{3,12}|(?:ACH|CHQ|ND|NC|TRF|DEP)-[A-Za-z0-9-]+)\s+(.+)$", texto_izq)
        if m_ref:
            referencia = m_ref.group(1).strip()
            descripcion = m_ref.group(2).strip()

        linea_n += 1
        fila = {
            "archivo": nombre_archivo,
            "banco": banco,
            "cuenta_bancaria": cuenta,
            "linea": linea_n,
            "fecha": fecha,
            "referencia": referencia,
            "descripcion": descripcion or "(sin descripción)",
            "debito": round(deb, 2),
            "credito": round(cred, 2),
            "monto": monto,
            "saldo": saldo,
        }
        filas.append(fila)
        ultima_fila = fila
        continuaciones = 0
        saldo_previo = saldo
    return filas, errores, omitidas


def _leer_extracto_tabular(ruta: Path) -> LecturaExtracto:
    df = pd.read_excel(ruta) if ruta.suffix.lower() in (".xlsx", ".xlsm", ".xls") else pd.read_csv(ruta, sep=None, engine="python")
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    col_fecha = next((cols_lower[k] for k in ("fecha", "date", "fecha_movimiento") if k in cols_lower), None)
    if col_fecha is None:
        raise ValueError(f"El extracto tabular {ruta.name} requiere al menos columna 'fecha'.")

    filas: list[dict] = []
    for idx, row in df.iterrows():
        f_val = _parsear_fecha_banco(str(row[col_fecha])) if not isinstance(row[col_fecha], (date, pd.Timestamp)) else pd.Timestamp(row[col_fecha]).date()
        if f_val is None:
            continue
        if "debito" in cols_lower and "credito" in cols_lower:
            deb = abs(_parsear_monto_banco(str(row[cols_lower["debito"]]))[0] or 0.0)
            cred = abs(_parsear_monto_banco(str(row[cols_lower["credito"]]))[0] or 0.0)
            monto = round(cred - deb, 2)
        elif "monto" in cols_lower:
            monto = _parsear_monto_banco(str(row[cols_lower["monto"]]))[0] or 0.0
            deb = abs(monto) if monto < 0 else 0.0
            cred = monto if monto > 0 else 0.0
        else:
            raise ValueError(f"El extracto tabular {ruta.name} debe tener 'monto' o 'debito'/'credito'.")

        saldo = None
        if "saldo" in cols_lower and pd.notna(row[cols_lower["saldo"]]):
            saldo = _parsear_monto_banco(str(row[cols_lower["saldo"]]))[0]

        filas.append({
            "archivo": ruta.name,
            "banco": str(row[cols_lower["banco"]]) if "banco" in cols_lower else "Banco Genérico",
            "cuenta_bancaria": str(row[cols_lower["cuenta_bancaria"]]) if "cuenta_bancaria" in cols_lower else "",
            "linea": int(row[cols_lower["linea"]]) if "linea" in cols_lower and pd.notna(row[cols_lower["linea"]]) else idx + 1,
            "fecha": f_val,
            "referencia": str(row[cols_lower["referencia"]]) if "referencia" in cols_lower and pd.notna(row[cols_lower["referencia"]]) else "",
            "descripcion": str(row[cols_lower["descripcion"]]) if "descripcion" in cols_lower and pd.notna(row[cols_lower["descripcion"]]) else "",
            "debito": round(deb, 2),
            "credito": round(cred, 2),
            "monto": round(monto, 2),
            "saldo": saldo,
        })
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    return LecturaExtracto(
        movimientos=pd.DataFrame(filas, columns=COLUMNAS_EXTRACTO),
        archivos=1,
        sha256=sha,
        metodo=ruta.suffix.lower().lstrip("."),
    )


def _fuentes_pdf(ruta: Path) -> Iterable[tuple[str, Path]]:
    if ruta.is_dir():
        for p in sorted(ruta.rglob("*.pdf")):
            yield str(p.relative_to(ruta)), p
    elif ruta.suffix.lower() == ".pdf":
        yield ruta.name, ruta
    else:
        raise ValueError(f"Formato no soportado para extracto bancario: {ruta.name}")


def _procesar_pdf_en_lote(
    lineas: list[str],
    nombre: str,
    filas_totales: list[dict],
    errores_totales: list[dict],
    resumenes_saldos: list[dict],
) -> int:
    f_pdf, err_pdf, om = _parsear_lineas_extracto(lineas, nombre)
    if not f_pdf:
        err_pdf.append({
            "archivo": nombre,
            "linea": 0,
            "error": (
                "No se reconoció ningún movimiento en este PDF (texto ilegible, escaneado o formato no soportado). "
                f"Legibilidad del texto extraído: {_proporcion_legible(lineas):.0%}."
            ),
        })
    filas_totales.extend(f_pdf)
    errores_totales.extend(err_pdf)
    resumenes_saldos.append(_resumen_saldo_extracto(lineas, f_pdf, nombre))
    return om


def leer_estado_cuenta(ruta: str | Path) -> LecturaExtracto:
    """Lee un PDF bancario, carpeta/ZIP de PDFs o archivo tabular (.csv/.xlsx) sin conexión a internet."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe: {ruta}")

    if ruta.is_file() and ruta.suffix.lower() in (".csv", ".tsv", ".xlsx", ".xlsm", ".xls"):
        return _leer_extracto_tabular(ruta)

    filas_totales: list[dict] = []
    errores_totales: list[dict] = []
    resumenes_saldos: list[dict] = []
    omitidas_tot = 0
    huella = hashlib.sha256()
    n_archivos = 0
    metodos: set[str] = set()

    if ruta.is_file() and ruta.suffix.lower() == ".zip":
        import tempfile
        with tempfile.TemporaryDirectory(prefix="folio_pdf_") as tmp:
            for nombre, raw in leer_miembros_zip_seguros(
                ruta,
                extensiones=(".pdf",),
                max_archivos=MAX_ARCHIVOS_ZIP,
                max_bytes_archivo=MAX_BYTES_PDF_TOTAL,
                max_bytes_total=MAX_BYTES_PDF_TOTAL,
            ):
                n_archivos += 1
                huella.update(hashlib.sha256(raw).digest())
                tmp_pdf = Path(tmp) / f"{n_archivos:05d}_{nombre_archivo_seguro(nombre, 'extracto.pdf')}"
                tmp_pdf.write_bytes(raw)
                lineas_pdf, metodo_pdf = _extraer_lineas_pdf_con_metodo(tmp_pdf)
                metodos.add(metodo_pdf)
                omitidas_tot += _procesar_pdf_en_lote(
                    lineas_pdf, nombre, filas_totales, errores_totales, resumenes_saldos
                )
    else:
        for nombre, p_pdf in _fuentes_pdf(ruta):
            n_archivos += 1
            huella.update(hashlib.sha256(p_pdf.read_bytes()).digest())
            lineas_pdf, metodo_pdf = _extraer_lineas_pdf_con_metodo(p_pdf)
            metodos.add(metodo_pdf)
            omitidas_tot += _procesar_pdf_en_lote(
                lineas_pdf, nombre, filas_totales, errores_totales, resumenes_saldos
            )

    df = pd.DataFrame(filas_totales, columns=COLUMNAS_EXTRACTO)
    if n_archivos and df.empty:
        raise ValueError(
            f"No se reconoció ningún movimiento bancario en {ruta.name}: "
            + "; ".join(e["error"] for e in errores_totales if e.get("linea") == 0)[:400]
            + " Exporta el estado de cuenta en CSV/Excel desde la banca en línea o revisa que el PDF no sea escaneado."
        )
    return LecturaExtracto(
        movimientos=df,
        errores=errores_totales,
        lineas_omitidas=omitidas_tot,
        archivos=n_archivos,
        sha256=huella.hexdigest(),
        metodo=", ".join(sorted(metodos)) or "pdf",
        resumen_saldos=resumenes_saldos,
    )


def _escapar_pdf(texto: str) -> bytes:
    """Escapa texto ASCII/WinAnsi para cadenas literales `(...)` en PDF 1.4."""
    raw = texto.encode("cp1252", errors="replace")
    salida = bytearray()
    for b in raw:
        if b in (40, 41, 92):  # (, ), \
            salida.append(92)
        salida.append(b)
    return bytes(salida)


def generar_pdf_estado_cuenta(
    ruta: str | Path,
    encabezado: list[str],
    filas: list[dict],
    compresion: bool = True,
) -> Path:
    """Genera un documento PDF 1.4 válido y multipágina de estado de cuenta bancario sintético."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    lineas_tabla = [
        f"{f['fecha']}  {f.get('referencia', ''):<10}  {f['descripcion'][:32]:<32}  "
        f"{f['debito']:>10,.2f}  {f['credito']:>10,.2f}  {f['saldo']:>11,.2f}"
        for f in filas
    ]

    filas_por_pagina = 40
    paginas_texto: list[list[str]] = []
    if not lineas_tabla:
        paginas_texto.append(encabezado)
    else:
        for idx in range(0, len(lineas_tabla), filas_por_pagina):
            bloques_pag = list(encabezado) + [
                "Fecha       Ref.        Descripción                       Débito     Crédito       Saldo",
                "-" * 92,
                *lineas_tabla[idx : idx + filas_por_pagina],
            ]
            paginas_texto.append(bloques_pag)

    objetos: dict[int, bytes] = {}
    font_id = 3
    objetos[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"

    page_ids: list[int] = []
    next_id = 4
    for lineas_pag in paginas_texto:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)

        ops: list[bytes] = [b"BT", b"/F1 8.5 Tf"]
        y = 760.0
        for ln in lineas_pag:
            ops.append(f"1 0 0 1 28 {y:.1f} Tm (".encode("ascii") + _escapar_pdf(ln) + b") Tj")
            y -= 13.5
        ops.append(b"ET")
        stream_raw = b"\n".join(ops)
        if compresion:
            cuerpo = zlib.compress(stream_raw)
            objetos[content_id] = (
                f"<< /Length {len(cuerpo)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
                + cuerpo
                + b"\nendstream"
            )
        else:
            objetos[content_id] = (
                f"<< /Length {len(stream_raw)} >>\nstream\n".encode("ascii")
                + stream_raw
                + b"\nendstream"
            )
        objetos[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objetos[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objetos[2] = f"<< /Type /Pages /Kids [ {kids} ] /Count {len(page_ids)} >>".encode("ascii")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    max_id = max(objetos)
    for oid in range(1, max_id + 1):
        offsets[oid] = len(out)
        out.extend(f"{oid} 0 obj\n".encode("ascii"))
        out.extend(objetos[oid])
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {max_id + 1}\n0000000000 65535 f \n".encode("ascii"))
    for oid in range(1, max_id + 1):
        out.extend(f"{offsets[oid]:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    ruta.write_bytes(bytes(out))
    return ruta
