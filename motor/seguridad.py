"""Primitivas centralizadas de ciberseguridad y hardening (Ficha 20 · Oleada 1)."""
from __future__ import annotations

import atexit
import codecs
import os
import re
import shutil
import tempfile
import zipfile
import zlib
from pathlib import Path
from typing import Any, Iterator

import duckdb
import pandas as pd

MAX_BYTES_XML = 10 * 1024 * 1024  # 10 MB por documento XML
MAX_BYTES_ZIP_TOTAL = 200 * 1024 * 1024  # 200 MB descomprimidos totales por archivo ZIP
MAX_ARCHIVOS_ZIP = 10_000
MAX_RATIO_ZIP = 100.0
UMBRAL_RATIO_ZIP_BYTES = 1 * 1024 * 1024  # 1 MB para evitar falsos positivos en archivos sintéticos pequeños
MAX_BYTES_PDF_FLUJO = 50 * 1024 * 1024  # 50 MB por flujo FlateDecode
MAX_BYTES_PDF_TOTAL = 200 * 1024 * 1024  # 200 MB acumulados en lectura PDF
MAX_BYTES_SQL_DUMP = 200 * 1024 * 1024  # 200 MB por volcado .sql en memoria

_TAMANO_BLOQUE_ZIP = 65_536
_PREFIJOS_FORMULA_EXCEL = ("=", "+", "-", "@", "\t", "\r")
_RE_NUMERO_PURO = re.compile(r"^[-+]\d+(?:[.,]\d+)?$")
_RE_FORMATO_FECHA_SQL = re.compile(r"^[A-Za-z0-9%/:.,_\-\s]{1,64}$")
_RE_DTD_XML = re.compile(r"<!\s*(?:DOCTYPE|ENTITY|ELEMENT|ATTLIST)\b", re.IGNORECASE)


class ErrorSeguridad(ValueError):
    """Error lanzado al detectar una entrada, consulta o archivo potencialmente peligroso."""


def bloquear_duckdb_externo(con: duckdb.DuckDBPyConnection) -> None:
    """Deshabilita el acceso externo a archivos/red y bloquea la configuración de DuckDB (idempotente)."""
    ext, bloqueada = con.execute(
        "SELECT current_setting('enable_external_access'), current_setting('lock_configuration')"
    ).fetchone()
    if bool(bloqueada):
        if bool(ext):
            raise ErrorSeguridad("La conexión DuckDB está bloqueada con acceso externo habilitado.")
        return
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")


def citar_identificador_sql(nombre: str) -> str:
    """Cita un identificador SQL escapando comillas dobles internas."""
    if not isinstance(nombre, str) or not nombre or "\x00" in nombre:
        raise ErrorSeguridad(f"Identificador SQL inválido: {nombre!r}")
    return '"' + nombre.replace('"', '""') + '"'


def validar_formato_fecha_sql(formato: str) -> str:
    """Valida que un patrón strftime no contenga caracteres peligrosos para SQL."""
    if not isinstance(formato, str) or not _RE_FORMATO_FECHA_SQL.fullmatch(formato):
        raise ErrorSeguridad(f"Formato de fecha inválido o con caracteres no permitidos: {formato!r}")
    return formato


def sanitizar_valor_excel(valor: Any) -> Any:
    """Neutraliza cadenas susceptibles de interpretación como fórmula en Excel/CSV (CWE-1236)."""
    if not isinstance(valor, str) or not valor:
        return valor
    limpio_borde = valor.strip()
    if valor[0] not in ("\t", "\r") and (limpio_borde == "-" or _RE_NUMERO_PURO.fullmatch(limpio_borde)):
        return valor
    limpio_izq = valor.lstrip(" \t\r\n")
    if valor[0] in _PREFIJOS_FORMULA_EXCEL or limpio_izq.startswith(("=", "+", "-", "@")):
        return f"'{valor}"
    return valor


def sanitizar_dataframe_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve una copia del DataFrame con columnas textuales neutralizadas frente a CWE-1236."""
    copia = df.copy()
    nuevas_cols = [sanitizar_valor_excel(c) if isinstance(c, str) else c for c in copia.columns]
    if list(copia.columns) != nuevas_cols:
        copia.columns = nuevas_cols
    for idx in range(len(copia.columns)):
        serie = copia.iloc[:, idx]
        if pd.api.types.is_object_dtype(serie.dtype) or pd.api.types.is_string_dtype(serie.dtype):
            copia.iloc[:, idx] = serie.map(
                lambda v: sanitizar_valor_excel(v) if isinstance(v, str) else v,
                na_action="ignore",
            )
    return copia


def _decodificar_cabecera_xml(contenido: bytes) -> str:
    if contenido.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return contenido.decode("utf-16", errors="ignore")
    if b"\x00" in contenido[:256]:
        # Tolera UTF-16 sin BOM eliminando bytes nulos para inspeccionar directivas DTD.
        return contenido.replace(b"\x00", b"").decode("latin-1", errors="ignore")
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("latin-1", errors="ignore")


def validar_xml_seguro(contenido: bytes, max_bytes: int = MAX_BYTES_XML) -> None:
    """Rechaza documentos XML que superen el límite de tamaño o contengan DTD/ENTITY (XXE/Billion Laughs)."""
    if not isinstance(contenido, (bytes, bytearray)):
        raise ErrorSeguridad("El contenido XML debe entregarse en bytes.")
    if len(contenido) > max_bytes:
        raise ErrorSeguridad(
            f"Documento XML excede el tamaño máximo permitido ({len(contenido):,} > {max_bytes:,} bytes)."
        )
    texto = _decodificar_cabecera_xml(bytes(contenido))
    if _RE_DTD_XML.search(texto):
        raise ErrorSeguridad("XML rechazado por seguridad: contiene declaración DTD/ENTITY no permitida.")


def validar_ruta_miembro_zip(nombre: str) -> str:
    """Valida que la ruta de un miembro dentro de un archivo ZIP no intente path traversal."""
    if not isinstance(nombre, str) or not nombre or "\x00" in nombre:
        raise ErrorSeguridad(f"Nombre de entrada ZIP inválido: {nombre!r}")
    if nombre.startswith(("/", "\\")):
        raise ErrorSeguridad(f"Ruta absoluta no permitida dentro del ZIP: {nombre!r}")
    segmentos = [s for s in re.split(r"[/\\]+", nombre) if s]
    if not segmentos:
        raise ErrorSeguridad(f"Nombre de entrada ZIP vacío: {nombre!r}")
    if ":" in segmentos[0]:
        raise ErrorSeguridad(f"Unidad de disco no permitida dentro del ZIP: {nombre!r}")
    if any(seg == ".." for seg in segmentos):
        raise ErrorSeguridad(f"Path traversal detectado dentro del ZIP: {nombre!r}")
    return nombre


def _validar_ratio_zip(descomprimido: int, comprimido: int, max_ratio: float, nombre: str) -> None:
    if descomprimido < UMBRAL_RATIO_ZIP_BYTES:
        return
    base = max(comprimido, 1)
    ratio = descomprimido / base
    if ratio > max_ratio:
        raise ErrorSeguridad(
            f"Archivo sospechoso en ZIP ({nombre!r}): ratio de compresión {ratio:.1f}x supera el límite {max_ratio:.1f}x."
        )


def leer_miembros_zip_seguros(
    ruta_zip: str | Path,
    extensiones: tuple[str, ...],
    max_archivos: int = MAX_ARCHIVOS_ZIP,
    max_bytes_archivo: int = MAX_BYTES_XML,
    max_bytes_total: int = MAX_BYTES_ZIP_TOTAL,
    max_ratio: float = MAX_RATIO_ZIP,
) -> Iterator[tuple[str, bytes]]:
    """Lee entradas seleccionadas de un ZIP con límites estrictos anti ZIP-bomb y anti path traversal."""
    exts = tuple(e.lower() for e in extensiones)
    total_bytes = 0
    conteo = 0
    with zipfile.ZipFile(ruta_zip) as z:
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            validar_ruta_miembro_zip(info.filename)
            if not info.filename.lower().endswith(exts):
                continue

            conteo += 1
            if conteo > max_archivos:
                raise ErrorSeguridad(
                    f"El archivo ZIP supera el límite máximo permitido de {max_archivos:,} archivos."
                )
            if info.file_size > max_bytes_archivo:
                raise ErrorSeguridad(
                    f"La entrada {info.filename!r} excede el límite por archivo ({info.file_size:,} > {max_bytes_archivo:,} bytes)."
                )
            _validar_ratio_zip(info.file_size, info.compress_size, max_ratio, info.filename)

            buf = bytearray()
            bytes_archivo = 0
            with z.open(info, "r") as entrada:
                while True:
                    trozo = entrada.read(_TAMANO_BLOQUE_ZIP)
                    if not trozo:
                        break
                    bytes_archivo += len(trozo)
                    total_bytes += len(trozo)
                    if bytes_archivo > max_bytes_archivo:
                        raise ErrorSeguridad(
                            f"La entrada {info.filename!r} excede el límite real de {max_bytes_archivo:,} bytes."
                        )
                    if total_bytes > max_bytes_total:
                        raise ErrorSeguridad(
                            f"El ZIP excede el límite acumulado de {max_bytes_total:,} bytes descomprimidos."
                        )
                    buf.extend(trozo)
            _validar_ratio_zip(bytes_archivo, info.compress_size, max_ratio, info.filename)
            yield info.filename, bytes(buf)


def descomprimir_zlib_seguro(datos: bytes, max_bytes: int = MAX_BYTES_PDF_FLUJO) -> bytes:
    """Descomprime un flujo zlib aplicando un límite estricto de bytes de salida."""
    dec = zlib.decompressobj()
    salida = dec.decompress(datos, max_bytes + 1)
    if len(salida) > max_bytes or dec.unconsumed_tail:
        raise ErrorSeguridad(
            f"Flujo comprimido excede el límite de seguridad de {max_bytes:,} bytes (posible bomba de descompresión)."
        )
    cola = dec.flush(max_bytes + 1 - len(salida))
    resultado = salida + cola
    if len(resultado) > max_bytes:
        raise ErrorSeguridad(
            f"Flujo comprimido excede el límite de seguridad de {max_bytes:,} bytes tras flush."
        )
    return resultado


def nombre_archivo_seguro(nombre: str, defecto: str = "archivo") -> str:
    """Valida que un nombre de archivo recibido no contenga traversal y devuelve un nombre base seguro."""
    if not isinstance(nombre, str) or not nombre.strip() or "\x00" in nombre:
        raise ErrorSeguridad(f"Nombre de archivo inválido: {nombre!r}")
    if nombre.startswith(("/", "\\")):
        raise ErrorSeguridad(f"Ruta absoluta no permitida en nombre de archivo: {nombre!r}")
    segmentos = [s for s in re.split(r"[/\\]+", nombre) if s]
    if not segmentos or ":" in segmentos[0] or any(seg == ".." for seg in segmentos):
        raise ErrorSeguridad(f"Nombre de archivo con ruta no permitida: {nombre!r}")
    base = "".join(ch for ch in segmentos[-1] if ord(ch) >= 32).strip()
    if not base or base in (".", ".."):
        return defecto
    return base


def _limpiar_directorio_temporal(ruta: Path) -> None:
    shutil.rmtree(ruta, ignore_errors=True)


def crear_directorio_temporal_seguro(prefijo: str = "folio_auditor_") -> Path:
    """Crea un directorio temporal aislado y programa su eliminación automática al salir del proceso."""
    ruta = Path(tempfile.mkdtemp(prefix=prefijo))
    if os.name != "nt":
        try:
            os.chmod(ruta, 0o700)
        except OSError:
            pass
    atexit.register(_limpiar_directorio_temporal, ruta)
    return ruta
