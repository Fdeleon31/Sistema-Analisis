"""Genera un mayor sintético con anomalías sembradas a propósito.

Sirve para demos y para la prueba de integración. Nunca uses datos de
clientes reales en este repositorio.

Anomalías sembradas (y lo que el paquete debe encontrar):
- Asientos 1500 a 1502 y 2200 eliminados: gaps en la numeración.
- Asiento 2501 copia exacta del asiento 100: duplicados.
- Línea 2 del asiento 777 con un día de diferencia: mismo-mismo-distinto.
- 15 de julio de 2025 sin registros: gap de fecha hábil.
- 60 asientos entre 9,900 y 9,999 (justo bajo un límite de 10,000): pico en el par 99 de Benford.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ASIENTOS = 2500
ELIMINADOS = {1500, 1501, 1502, 2200}
DIA_SIN_REGISTROS = date(2025, 7, 15)
ASIENTO_DUPLICADO_ORIGEN, ASIENTO_DUPLICADO_COPIA = 100, 2501
ASIENTO_FECHAS_DISTINTAS = 777

CUENTAS = [
    ("5101", "Compra de mercancía"),
    ("5201", "Honorarios profesionales"),
    ("5202", "Alquiler de oficina"),
    ("5203", "Servicios públicos"),
    ("5204", "Mantenimiento"),
    ("5301", "Publicidad"),
    ("1501", "Compra de equipo"),
]
USUARIOS = ["ana.gomez", "luis.perez", "maria.rios", "jose.vega"]


def dias_habiles(anio: int = 2025) -> list[date]:
    dia, fin, dias = date(anio, 1, 2), date(anio, 12, 31), []
    while dia <= fin:
        if dia.weekday() < 5 and dia != DIA_SIN_REGISTROS:
            dias.append(dia)
        dia += timedelta(days=1)
    return dias


def generar(ruta: str | Path, semilla: int = 42) -> Path:
    rnd = random.Random(semilla)
    dias = dias_habiles()
    picos = set(rnd.sample([n for n in range(1, ASIENTOS + 1) if n not in ELIMINADOS | {ASIENTO_DUPLICADO_ORIGEN, ASIENTO_FECHAS_DISTINTAS}], 60))

    filas = []
    for n in range(1, ASIENTOS + 1):
        if n in ELIMINADOS:
            continue
        fecha = dias[int((n - 1) * len(dias) / ASIENTOS)]
        cuenta, descripcion = rnd.choice(CUENTAS)
        if n in picos:
            monto = round(rnd.uniform(9900, 9999.99), 2)
        else:
            monto = round(rnd.lognormvariate(6.5, 1.6), 2)
            monto = max(monto, 1.00)
        usuario = rnd.choice(USUARIOS)
        fecha_credito = fecha + timedelta(days=1) if n == ASIENTO_FECHAS_DISTINTAS else fecha
        filas.append([n, 1, fecha.isoformat(), cuenta, descripcion, f"{monto:.2f}", usuario])
        filas.append([n, 2, fecha_credito.isoformat(), "1101", descripcion, f"{-monto:.2f}", usuario])

    origen = [f for f in filas if f[0] == ASIENTO_DUPLICADO_ORIGEN]
    filas.extend([[ASIENTO_DUPLICADO_COPIA, *f[1:]] for f in origen])

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["asiento", "linea", "fecha", "cuenta", "descripcion", "monto", "usuario"])
        escritor.writerows(filas)
    return ruta


# --- Fase 1 · Diario y balanza con anomalías de asientos sembradas ---------------------

FERIADOS_2025 = {
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 3, 4), date(2025, 4, 18), date(2025, 5, 1),
    date(2025, 11, 3), date(2025, 11, 5), date(2025, 11, 10), date(2025, 11, 28),
    date(2025, 12, 8), date(2025, 12, 20), date(2025, 12, 25),
}
CUENTAS_BASE = [c for c in CUENTAS if c[0] != "1501"] + [("1501", "Compra de equipo")]
USUARIOS_BASE = ["ana.gomez", "luis.perez", "maria.rios", "jose.vega"]

# Asientos sembrados y lo que cada uno debe disparar (criterios de la Ficha 04).
SEMBRADOS_ASIENTOS = {
    101: {"fecha": date(2025, 3, 9)},                       # domingo
    202: {"fecha": date(2025, 5, 1)},                       # feriado
    303: {"monto": 25000.00},                               # redondo
    404: {"usuario": "admin.temporal"},                     # usuario poco frecuente
    505: {"cuenta": "6999", "descripcion": "Gasto extraordinario"},  # cuenta poco usada
    606: {"descripcion": "Ajuste varios"},                  # descripción genérica
    707: {"descuadre": 50.00},                              # descuadrado
    808: {"fecha": date(2025, 12, 30)},                     # cerca del cierre
    909: {"monto": 9876.54},                                # justo bajo el umbral de 10,000
    1001: {"monto": 150000.37},                             # sobre materialidad de ejecución
    1111: {"fecha": date(2025, 11, 30), "monto": 50000.00,  # domingo + redondo + usuario + descripción
           "usuario": "admin.temporal", "descripcion": "Reclasificación"},
}


def _dias_base_2025() -> list[date]:
    dia, fin, dias = date(2025, 1, 2), date(2025, 12, 23), []
    while dia <= fin:
        if dia.weekday() < 5 and dia not in FERIADOS_2025:
            dias.append(dia)
        dia += timedelta(days=1)
    return dias


def _monto_base(rnd: random.Random) -> float:
    """Montos con centavos, menores a 9,000: nunca redondos, nunca cerca del umbral ni de la materialidad."""
    while True:
        monto = round(rnd.lognormvariate(6.5, 1.4), 2)
        if 1 <= monto < 9000:
            if round(monto * 100) % 100 == 0:
                monto = round(monto + 0.37, 2)
            return monto


def generar_diario_asientos(carpeta: str | Path, semilla: int = 7, formato: str = "estandar", asientos: int = 1200) -> tuple[Path, Path]:
    """Genera diario y balanza 2025. formato="dificil" exporta como lo haría un ERP poco amable."""
    rnd = random.Random(semilla)
    dias = _dias_base_2025()
    filas = []
    for n in range(1, asientos + 1):
        semilla_asiento = SEMBRADOS_ASIENTOS.get(n, {})
        fecha = semilla_asiento.get("fecha", dias[int((n - 1) * len(dias) / asientos)])
        cuenta, descripcion = rnd.choice(CUENTAS_BASE)
        monto = _monto_base(rnd)
        usuario = rnd.choice(USUARIOS_BASE)
        cuenta = semilla_asiento.get("cuenta", cuenta)
        descripcion = semilla_asiento.get("descripcion", descripcion)
        monto = semilla_asiento.get("monto", monto)
        usuario = semilla_asiento.get("usuario", usuario)
        credito = -(monto - semilla_asiento.get("descuadre", 0.0))
        filas.append([n, 1, fecha, cuenta, descripcion, round(monto, 2), usuario])
        filas.append([n, 2, fecha, "1101", descripcion, round(credito, 2), usuario])

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    import pandas as pd  # import local: el resto del módulo no depende de pandas

    diario = pd.DataFrame(filas, columns=["asiento", "linea", "fecha", "cuenta", "descripcion", "monto", "usuario"])

    movimientos = diario.groupby("cuenta")["monto"].sum().round(2)
    rnd_saldos = random.Random(semilla + 1000)
    balanza = []
    for cuenta, mov in movimientos.items():
        if cuenta == "6999":
            continue  # sembrado: cuenta del mayor que falta en la balanza
        inicial = round(rnd_saldos.uniform(1000, 90000), 2)
        final = round(inicial + mov, 2)
        if cuenta == "5204":
            final = round(final + 1234.56, 2)  # sembrado: diferencia entre balanza y mayor
        balanza.append([cuenta, f"Cuenta {cuenta}", inicial, final])
    balanza.append(["1999", "Cuenta sin movimiento", 500.00, 500.00])
    balanza.append(["2999", "Cuenta que cambia sin movimientos", 100.00, 300.00])  # sembrado
    balanza = pd.DataFrame(balanza, columns=["cuenta", "descripcion", "saldo_inicial", "saldo_final"]).sort_values("cuenta")

    if formato == "estandar":
        ruta_diario, ruta_balanza = carpeta / "diario_2025.csv", carpeta / "balanza_2025.csv"
        diario.assign(fecha=diario["fecha"].map(date.isoformat)).to_csv(ruta_diario, index=False)
        balanza.to_csv(ruta_balanza, index=False)
        return ruta_diario, ruta_balanza

    if formato == "dificil":
        ruta_diario, ruta_balanza = carpeta / "diario_2025_erp.xlsx", carpeta / "balanza_2025_erp.csv"
        erp = pd.DataFrame({
            "No. Asiento": diario["asiento"].map(lambda a: f"JE-{a:06d}"),
            "Línea": diario["linea"],
            "Fecha": diario["fecha"].map(lambda d: d.strftime("%d/%m/%Y")),
            "Cuenta": diario["cuenta"],
            "Descripción": diario["descripcion"],
            "Debe": diario["monto"].clip(lower=0),
            "Haber": (-diario["monto"]).clip(lower=0),
            "Usuario": diario["usuario"],
        })
        with pd.ExcelWriter(ruta_diario) as xls:
            pd.DataFrame({"Reporte": ["Libro diario 2025"]}).to_excel(xls, sheet_name="Portada", index=False)
            erp.to_excel(xls, sheet_name="Diario", index=False)
        with ruta_balanza.open("w", newline="", encoding="cp1252") as f:
            escritor = csv.writer(f)
            escritor.writerow(["CLIENTE DEMO, S.A. - Balanza de comprobación 2025"])
            escritor.writerow(["cuenta", "descripcion", "saldo_inicial", "saldo_final"])
            for c, d, si, sf in balanza.itertuples(index=False):
                escritor.writerow([c, d.replace("Cuenta", "Cuenta contable año"), f"{si:,.2f}", f"{sf:,.2f}"])
            escritor.writerow(["", "Total", "", ""])
        return ruta_diario, ruta_balanza

    raise ValueError(f"Formato desconocido: {formato}")


# --- Fase 2 · Facturas electrónicas de la DGI con anomalías sembradas -------------------

NS_FE = "http://dgi-fep.mef.gob.pa"
RUC_EMISOR = "155000001-2-2020"  # ficticio

SEMBRADOS_FE = {
    "falta": 150,            # hueco en la numeración
    "duplicada": 77,         # mismo CUFE en dos archivos
    "inconsistente": 120,    # total inflado en 10.00
    "fuera_periodo": 300,    # emitida en enero de 2026
    "ambiente_pruebas": 250,  # iAmb = 2
    "diferencia_junio": -1500.00,  # ventas del mayor de junio menores que lo facturado
}


def _xml_factura(tipo: str, punto: str, numero: int, fecha: date, neto: float, receptor: str,
                 ambiente: str = "1", ajuste_total: float = 0.0) -> tuple[str, str]:
    itbms = round(neto * 0.07, 2)
    total = round(neto + itbms, 2)
    cufe = f"FE{tipo}{ambiente}00000{RUC_EMISOR.replace('-', '')}{punto}{numero:010d}{fecha:%Y%m%d}"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rFE xmlns="{NS_FE}">
  <dVerForm>1.00</dVerForm>
  <dId>{cufe}</dId>
  <gDGen>
    <iAmb>{ambiente}</iAmb>
    <iTpEmis>01</iTpEmis>
    <dFechaEm>{fecha.isoformat()}T10:00:00-05:00</dFechaEm>
    <iDoc>{tipo}</iDoc>
    <dPtoFacDF>{punto}</dPtoFacDF>
    <dNroDF>{numero:010d}</dNroDF>
    <gEmis>
      <gRucEmi><dTipoRuc>2</dTipoRuc><dRuc>{RUC_EMISOR}</dRuc><dDV>00</dDV></gRucEmi>
      <dNombEm>Cliente Demo, S.A. (sintético)</dNombEm>
    </gEmis>
    <gDatRec>
      <iTipoRec>01</iTipoRec>
      <gRucRec><dTipoRuc>2</dTipoRuc><dRuc>{receptor}</dRuc><dDV>00</dDV></gRucRec>
      <dNombRec>Comprador {receptor}</dNombRec>
    </gDatRec>
  </gDGen>
  <gItem>
    <dSecItem>0001</dSecItem>
    <dDescProd>Servicio</dDescProd>
    <gPrecios><dPrItem>{neto:.2f}</dPrItem><dValTotItem>{total:.2f}</dValTotItem></gPrecios>
    <gITBMSItem><dTasaITBMS>01</dTasaITBMS><dValITBMS>{itbms:.2f}</dValITBMS></gITBMSItem>
  </gItem>
  <gTot>
    <dTotNeto>{neto:.2f}</dTotNeto>
    <dTotITBMS>{itbms:.2f}</dTotITBMS>
    <dVTot>{total + ajuste_total:.2f}</dVTot>
    <dVTotItems>{total:.2f}</dVTotItems>
  </gTot>
</rFE>
"""
    return cufe, xml


def generar_facturas_fe(carpeta: str | Path, semilla: int = 21) -> tuple[Path, Path]:
    """Genera los XML de 2025 (carpeta y ZIP) y un mayor de ventas coherente salvo lo sembrado.

    Devuelve (zip_de_facturas, mayor_csv).
    """
    import zipfile

    import pandas as pd

    rnd = random.Random(semilla)
    carpeta = Path(carpeta)
    xmls = carpeta / "facturas_xml"
    xmls.mkdir(parents=True, exist_ok=True)
    dias = _dias_base_2025()
    ventas_mes: dict[str, float] = {}

    def registrar(fecha: date, neto: float, signo: int = 1):
        mes = fecha.strftime("%Y-%m")
        ventas_mes[mes] = round(ventas_mes.get(mes, 0.0) + signo * neto, 2)

    for n in range(1, 301):
        if n == SEMBRADOS_FE["falta"]:
            continue
        fecha = dias[int((n - 1) * len(dias) / 300)]
        if n == SEMBRADOS_FE["fuera_periodo"]:
            fecha = date(2026, 1, 3)
        neto = _monto_base(rnd)
        ambiente = "2" if n == SEMBRADOS_FE["ambiente_pruebas"] else "1"
        ajuste = 10.0 if n == SEMBRADOS_FE["inconsistente"] else 0.0
        cufe, xml = _xml_factura("01", "001", n, fecha, neto, f"8-{100 + n % 40}-{n:04d}", ambiente, ajuste)
        (xmls / f"FE_001_{n:010d}.xml").write_text(xml, encoding="utf-8")
        if n == SEMBRADOS_FE["duplicada"]:
            (xmls / f"FE_001_{n:010d}_copia.xml").write_text(xml, encoding="utf-8")
        if ambiente == "1" and fecha.year == 2025:
            registrar(fecha, neto)

    for n in range(1, 6):  # notas de crédito
        fecha = dias[40 * n]
        neto = round(rnd.uniform(50, 400), 2)
        cufe, xml = _xml_factura("04", "001", n, fecha, neto, "8-120-0001")
        (xmls / f"NC_001_{n:010d}.xml").write_text(xml, encoding="utf-8")
        registrar(fecha, neto, -1)

    (xmls / "archivo_danado.xml").write_text("<rFE><gDGen>sin cerrar", encoding="utf-8")

    ruta_zip = carpeta / "facturas_2025.zip"
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(xmls.glob("*.xml")):
            z.write(p, p.name)

    filas, asiento = [], 1
    for mes, total in sorted(ventas_mes.items()):
        if mes == "2025-06":
            total = round(total + SEMBRADOS_FE["diferencia_junio"], 2)
        fecha = date.fromisoformat(f"{mes}-28")
        filas.append([asiento, 1, fecha.isoformat(), "1201", f"Ventas de {mes}", total, "ana.gomez"])
        filas.append([asiento, 2, fecha.isoformat(), "4101", f"Ventas de {mes}", -total, "ana.gomez"])
        asiento += 1
    ruta_mayor = carpeta / "mayor_ventas_2025.csv"
    pd.DataFrame(filas, columns=["asiento", "linea", "fecha", "cuenta", "descripcion", "monto", "usuario"]).to_csv(ruta_mayor, index=False)
    return ruta_zip, ruta_mayor
