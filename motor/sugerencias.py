"""Sugerencia de mapeo de columnas por reglas (sin IA).

Propone, para cada columna estándar, la columna del archivo del cliente que más
se le parece. El auditor siempre confirma; nada se aplica sin su aprobación.
La sugerencia con IA (Fase 2) se apoyará en la misma interfaz.
"""
from __future__ import annotations

import re
import unicodedata

SINONIMOS: dict[str, list[str]] = {
    "asiento": ["asiento", "no asiento", "numero asiento", "num asiento", "comprobante", "no comprobante",
                "poliza", "partida", "je", "journal", "voucher", "documento", "no documento", "transaccion"],
    "linea": ["linea", "renglon", "item", "secuencia", "line", "no linea"],
    "fecha": ["fecha", "fecha contable", "fecha asiento", "fecha registro", "date", "posting date", "fecha documento"],
    "cuenta": ["cuenta", "codigo cuenta", "cod cuenta", "no cuenta", "account", "cuenta contable", "codigo"],
    "descripcion": ["descripcion", "concepto", "detalle", "glosa", "referencia", "description", "memo", "nombre"],
    "monto": ["monto", "importe", "valor", "amount", "saldo movimiento", "neto"],
    "usuario": ["usuario", "user", "creado por", "registrado por", "elaborado por", "capturista"],
    "saldo_inicial": ["saldo inicial", "saldo anterior", "opening balance", "balance inicial", "inicial"],
    "saldo_final": ["saldo final", "saldo actual", "closing balance", "balance final", "final"],
}
DEBITO = ["debe", "debito", "debitos", "cargo", "cargos", "debit"]
CREDITO = ["haber", "credito", "creditos", "abono", "abonos", "credit"]


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def _puntaje(columna: str, sinonimos: list[str]) -> int:
    c = normalizar(columna)
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


def sugerir_mapeo(columnas: list[str], requeridas: list[str]) -> dict[str, str | None]:
    """{columna_estándar: columna_del_archivo o None}. Una columna del archivo se usa una sola vez."""
    usadas: set[str] = set()
    salida: dict[str, str | None] = {}
    # Primero las coincidencias exactas por nombre estándar
    for req in requeridas:
        if req in columnas:
            salida[req] = req
            usadas.add(req)
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
    deb = [c for c in columnas if normalizar(c) in DEBITO]
    cre = [c for c in columnas if normalizar(c) in CREDITO]
    return (deb[0], cre[0]) if deb and cre else None


def detectar_fila_encabezado(filas: list[list[str]], requeridas: list[str], maximo: int = 15) -> int:
    """Índice de la fila que mejor parece un encabezado (más columnas estándar reconocidas).

    Sirve para archivos con títulos arriba ("EMPRESA DEMO, S.A.", "Balanza 2025"). Si ninguna fila
    reconoce al menos dos columnas, devuelve 0 y el auditor decide.
    """
    mejor, mejor_puntos = 0, 1
    for i, fila in enumerate(filas[:maximo]):
        celdas = [str(c) for c in fila if c is not None and str(c).strip() and str(c).lower() != "nan"]
        if not celdas:
            continue
        sugerido = sugerir_mapeo(celdas, requeridas)
        puntos = sum(1 for v in sugerido.values() if v is not None)
        if sugerir_debito_credito(celdas):
            puntos += 1
        if puntos > mejor_puntos:
            mejor, mejor_puntos = i, puntos
    return mejor
