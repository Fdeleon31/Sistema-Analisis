"""Sugerencia de mapeo de columnas por reglas y perfiles ERP (sin IA).

Propone, para cada columna estándar, la columna del archivo del cliente que más
se le parece. El auditor siempre confirma; nada se aplica sin su aprobación.
La sugerencia con IA (Fase 2) se apoyará en la misma interfaz.
"""
from __future__ import annotations

import re
import unicodedata

SINONIMOS: dict[str, list[str]] = {
    "asiento": [
        "asiento", "no asiento", "numero asiento", "num asiento", "nro asiento",
        "comprobante", "no comprobante", "numero comprobante", "poliza", "partida",
        "je", "journal", "journal entry", "asiento contable", "voucher",
        "documento", "no documento", "documento contable", "doc contable",
        "belnr", "transid", "jrnentry", "docnum", "transaccion", "transaction id",
        "document number", "document no", "tran id", "internal id", "reference",
        "trans no", "journal reference", "move id name", "move name", "numero", "num",
    ],
    "linea": [
        "linea", "renglon", "item", "secuencia", "line", "no linea", "line no",
        "buzei", "docln", "line id", "consecutivo", "seqnumbr", "entry no",
        "posicion", "pos", "visorder", "sequence",
    ],
    "fecha": [
        "fecha", "fecha contable", "fecha contabilizacion", "fe contabilizacion",
        "fecha asiento", "fecha registro", "fecha de creacion", "fec asiento",
        "date", "posting date", "fecha documento", "budat", "refdate", "taxdate", "trxdate",
    ],
    "cuenta": [
        "cuenta", "codigo cuenta", "cod cuenta", "no cuenta", "account", "cuenta contable",
        "codigo", "codigo de cuenta", "hkont", "racct", "cuenta mayor", "cuenta de mayor",
        "g l account", "gl account", "g l account no", "account id", "general ledger id",
        "accnt", "actnumst", "actindx", "account id code", "account code",
    ],
    "descripcion": [
        "descripcion", "concepto", "detalle", "glosa", "referencia", "description",
        "memo", "nombre", "observaciones", "etiqueta", "label", "notas",
        "sgtxt", "bktxt", "linememo", "refrence", "dscriptn", "memo description",
        "trans description", "line description", "texto posicion", "texto",
    ],
    "monto": [
        "monto", "importe", "valor", "amount", "saldo movimiento", "neto",
        "dmbtr", "hsl", "wrbtr", "wsl", "importe ml", "monto local", "monto dolar",
        "amount net",
    ],
    "usuario": [
        "usuario", "user", "user id", "creado por", "registrado por", "elaborado por",
        "capturista", "usnam", "nombre del usuario", "u name", "usersign", "user code",
        "usuario creacion", "created by", "create uid", "create uid name",
        "uswhpstd", "operador",
    ],
    "saldo_inicial": ["saldo inicial", "saldo anterior", "opening balance", "balance inicial", "inicial"],
    "saldo_final": ["saldo final", "saldo actual", "closing balance", "balance final", "final"],
}

DEBITO = {"debe", "debito", "debitos", "cargo", "cargos", "debit", "debit amt", "debit amount", "debitamt", "amount debit", "debito local", "debito dolar", "importe debe", "sysdeb"}
CREDITO = {"haber", "credito", "creditos", "abono", "abonos", "credit", "credit amt", "credit amount", "crdtamnt", "amount credit", "credito local", "credito dolar", "importe haber", "syscred"}

PARES_DC_PRIORIDAD: list[tuple[str, str]] = [
    ("debito local", "credito local"),
    ("debito dolar", "credito dolar"),
    ("debit amt", "credit amt"),
    ("debit amount", "credit amount"),
    ("amount debit", "amount credit"),
    ("debitamt", "crdtamnt"),
    ("importe debe", "importe haber"),
    ("debe", "haber"),
    ("debito", "credito"),
    ("debitos", "creditos"),
    ("debit", "credit"),
    ("sysdeb", "syscred"),
    ("cargo", "abono"),
    ("fcdebit", "fccredit"),
]

INDICADORES_DC = [
    "shkzg", "drcrk", "d c", "ind d h", "ind debe haber", "indicador d h",
    "indicador dc", "debe haber", "tipo movimiento", "naturaleza",
]


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def _puntaje(columna: str, sinonimos: list[str]) -> int:
    c = normalizar(columna)
    if not c:
        return 0
    mejor = 0
    for s in sinonimos:
        if c == s:
            mejor = max(mejor, 100)
        elif c.startswith(s) or c.endswith(s):
            mejor = max(mejor, 80)
        elif s in c.split():
            mejor = max(mejor, 70)
        elif s in c:
            mejor = max(mejor, 50)
    return mejor


def sugerir_mapeo(
    columnas: list[str],
    requeridas: list[str],
    sinonimos_extra: dict[str, list[str]] | None = None,
) -> dict[str, str | None]:
    """{columna_estándar: columna_del_archivo o None}. Una columna del archivo se usa una sola vez."""
    usadas: set[str] = set()
    salida: dict[str, str | None] = {}
    # 1. Coincidencias exactas por nombre estándar
    for req in requeridas:
        if req in columnas:
            salida[req] = req
            usadas.add(req)

    # 2. Alias prioritarios del perfil ERP si se proporcionaron
    if sinonimos_extra:
        por_norm = {}
        for c in columnas:
            if c not in usadas:
                por_norm.setdefault(normalizar(c), c)
        for req in requeridas:
            if req in salida:
                continue
            for alias in sinonimos_extra.get(req, []):
                encontrada = por_norm.get(normalizar(alias))
                if encontrada and encontrada not in usadas:
                    salida[req] = encontrada
                    usadas.add(encontrada)
                    break

    # 3. Coincidencias por sinónimos generales
    for req in requeridas:
        if req in salida:
            continue
        candidatos = sorted(
            ((_puntaje(c, SINONIMOS.get(req, [req])), c) for c in columnas if c not in usadas),
            key=lambda x: -x[0],
        )
        if candidatos and candidatos[0][0] >= 50:
            salida[req] = candidatos[0][1]
            usadas.add(candidatos[0][1])
        else:
            salida[req] = None
    return salida


def sugerir_debito_credito(columnas: list[str]) -> tuple[str, str] | None:
    """Si el archivo trae débito y crédito en columnas separadas, las propone."""
    por_norm: dict[str, str] = {}
    for c in columnas:
        por_norm.setdefault(normalizar(c), c)

    for deb_norm, cre_norm in PARES_DC_PRIORIDAD:
        if deb_norm in por_norm and cre_norm in por_norm:
            return (por_norm[deb_norm], por_norm[cre_norm])

    deb = [c for c in columnas if normalizar(c) in DEBITO]
    cre = [c for c in columnas if normalizar(c) in CREDITO]
    if deb and cre:
        return (deb[0], cre[0])

    # Búsqueda flexible excluyendo columnas de indicador o moneda extranjera si hay mejores
    deb_flex = [c for c in columnas if any(p in normalizar(c).split() for p in ("debe", "debito", "debit")) and "ind" not in normalizar(c)]
    cre_flex = [c for c in columnas if any(p in normalizar(c).split() for p in ("haber", "credito", "credit")) and "ind" not in normalizar(c)]
    return (deb_flex[0], cre_flex[0]) if deb_flex and cre_flex else None


def sugerir_indicador_dc(columnas: list[str]) -> str | None:
    """Detecta una columna indicadora de Debe/Haber (ej. SHKZG, DRCRK, D/C)."""
    por_norm = {normalizar(c): c for c in columnas}
    for candidato in INDICADORES_DC:
        if candidato in por_norm:
            return por_norm[candidato]
    return None


def _celdas_fila_cruda(fila: list[str]) -> list[str]:
    limpias = [str(c).strip() for c in fila if c is not None and str(c).strip() and str(c).lower() != "nan"]
    if not limpias:
        return []
    unida = " ".join(limpias)
    if re.match(r"^[\|\-\+\=\s]+$", unida):
        return []
    if len(limpias) == 1 and limpias[0].startswith("|") and limpias[0].endswith("|"):
        return [p.strip() for p in limpias[0].strip("|").split("|") if p.strip()]
    return limpias


def detectar_fila_encabezado(filas: list[list[str]], requeridas: list[str], maximo: int = 20) -> int:
    """Índice de la fila que mejor parece un encabezado (más columnas estándar reconocidas).

    Soporta filas con títulos arriba y reportes SAP ALV delimitados por '|'.
    """
    mejor, mejor_puntos = 0, 1
    for i, fila in enumerate(filas[:maximo]):
        celdas = _celdas_fila_cruda(fila)
        if not celdas:
            continue
        sugerido = sugerir_mapeo(celdas, requeridas)
        puntos = sum(1 for v in sugerido.values() if v is not None)
        if sugerir_debito_credito(celdas) or sugerir_indicador_dc(celdas):
            puntos += 1
        if puntos > mejor_puntos:
            mejor, mejor_puntos = i, puntos
    return mejor
