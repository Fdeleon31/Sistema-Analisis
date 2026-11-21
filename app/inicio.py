"""Cuadra · interfaz para el auditor.

Abre con iniciar.bat (doble clic) o con:  streamlit run app/inicio.py
Todo corre en tu computador: los archivos no salen de él.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from motor import __version__  # noqa: E402
from motor.importador import ErrorImportacion, detectar_codificacion  # noqa: E402
from motor.muestreo import ErrorMuestreo, evaluar_mus, seleccionar_mus  # noqa: E402
from motor.servicio import ejecutar_encargo, paquetes_disponibles  # noqa: E402
from motor.sugerencias import detectar_fila_encabezado, sugerir_debito_credito, sugerir_mapeo  # noqa: E402

st.set_page_config(page_title="Cuadra", page_icon="📊", layout="wide")

FORMATOS_FECHA = {"Detectar automáticamente": None, "día/mes/año (31/12/2025)": "%d/%m/%Y",
                  "mes/día/año (12/31/2025)": "%m/%d/%Y", "año-mes-día (2025-12-31)": "%Y-%m-%d"}


def _guardar(subido, carpeta: Path) -> Path:
    ruta = carpeta / subido.name
    ruta.write_bytes(subido.getvalue())
    return ruta


def _vista_previa(ruta: Path, hoja: str | None, saltar: int) -> pd.DataFrame:
    if ruta.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(ruta, sheet_name=hoja or 0, skiprows=saltar or None, nrows=20, dtype=str)
    return pd.read_csv(ruta, sep=None, engine="python", skiprows=saltar or None, nrows=20, dtype=str,
                       encoding=detectar_codificacion(ruta))


def _filas_crudas(ruta: Path, hoja: str | None) -> list[list[str]]:
    """Primeras filas sin interpretar encabezados, para detectar dónde empieza la tabla."""
    if ruta.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(ruta, sheet_name=hoja or 0, header=None, nrows=15, dtype=str).values.tolist()
    import csv
    with ruta.open(encoding=detectar_codificacion(ruta), newline="") as f:
        texto = f.read(20000)
    lineas = texto.splitlines()[:15]
    try:
        dialecto = csv.Sniffer().sniff("\n".join(lineas[-5:]), delimiters=",;\t|")
    except csv.Error:
        dialecto = csv.excel
    return list(csv.reader(lineas, dialecto))


def _hojas(ruta: Path) -> list[str]:
    if ruta.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.ExcelFile(ruta).sheet_names
    return []


# --- Encabezado -------------------------------------------------------------------------
st.title("Cuadra")
st.caption(f"Analítica de auditoría · versión {__version__} · los datos se procesan solo en este computador")

pestana_encargo, pestana_muestreo = st.tabs(["Encargo y pruebas", "Muestreo MUS"])

# --- Encargo y pruebas -------------------------------------------------------------------
with pestana_encargo:
    paquetes = paquetes_disponibles()
    nombres = {m["nombre"]: pid for pid, m in paquetes.items()}
    elegido = st.selectbox("Paquete de pruebas", list(nombres), index=list(nombres.values()).index("asientos-nia240")
                           if "asientos-nia240" in nombres.values() else 0)
    manifiesto = paquetes[nombres[elegido]]
    st.caption(manifiesto.get("descripcion", ""))

    st.subheader("1. Datos del encargo")
    c1, c2, c3 = st.columns(3)
    cliente = c1.text_input("Cliente", "Cliente Demo, S.A.")
    fecha_cierre = c2.date_input("Fecha de cierre", date(2025, 12, 31))
    marco = c3.selectbox("Marco contable", ["NIIF", "NIIF para PYMES"])
    c4, c5, c6, c7 = st.columns(4)
    materialidad = c4.number_input("Materialidad", min_value=0.0, value=150000.0, step=1000.0)
    materialidad_ejecucion = c5.number_input("Materialidad de ejecución", min_value=0.0, value=materialidad * 0.75, step=1000.0)
    umbral_trivial = c6.number_input("Umbral trivial", min_value=0.0, value=materialidad * 0.05, step=500.0)
    umbral_aprobacion = c7.number_input("Umbral de aprobación (0 si no aplica)", min_value=0.0, value=10000.0, step=500.0)
    periodo_inicio = date(fecha_cierre.year, 1, 1) if fecha_cierre.month == 12 else date(fecha_cierre.year - 1, fecha_cierre.month + 1, 1)
    encargo = {
        "cliente": cliente, "periodo_inicio": periodo_inicio.isoformat(), "fecha_cierre": fecha_cierre.isoformat(), "marco": marco,
        "prefijo_ingresos": "4",
        "materialidad": materialidad, "materialidad_ejecucion": materialidad_ejecucion,
        "umbral_trivial": umbral_trivial, "umbral_aprobacion": umbral_aprobacion,
    }

    st.subheader("2. Archivos del cliente")
    if "carpeta" not in st.session_state:
        st.session_state.carpeta = Path(tempfile.mkdtemp(prefix="cuadra_"))
    carpeta = st.session_state.carpeta

    archivos: dict[str, Path | None] = {}
    opciones: dict[str, dict] = {}
    listo = True
    for definicion in manifiesto["archivos"]:
        tabla = definicion["tabla"]
        etiqueta = f"{tabla.capitalize()}{' (opcional)' if definicion.get('opcional') else ''}"
        with st.expander(f"{etiqueta}: {definicion.get('descripcion', '')}", expanded=not definicion.get("opcional")):
            if definicion.get("tipo") == "factura_electronica":
                subidos = st.file_uploader("ZIP o archivos XML de factura electrónica", type=["zip", "xml"],
                                           accept_multiple_files=True, key=f"archivo_{tabla}")
                if not subidos:
                    archivos[tabla] = None
                    listo = listo and bool(definicion.get("opcional"))
                    continue
                destino = carpeta / f"fe_{tabla}"
                destino.mkdir(exist_ok=True)
                for s_ in subidos:
                    _guardar(s_, destino)
                archivos[tabla] = destino
                st.caption(f"{len(subidos)} archivo(s) cargado(s); los XML ilegibles se reportarán sin detener la lectura.")
                continue
            subido = st.file_uploader("Archivo CSV o Excel", type=["csv", "txt", "xlsx", "xlsm", "xls"], key=f"archivo_{tabla}")
            if not subido:
                archivos[tabla] = None
                listo = listo and bool(definicion.get("opcional"))
                continue
            ruta = _guardar(subido, carpeta)
            hojas = _hojas(ruta)
            a1, a2, a3 = st.columns(3)
            hoja = a1.selectbox("Hoja", hojas, index=len(hojas) - 1, key=f"hoja_{tabla}") if hojas else None
            detectada = detectar_fila_encabezado(_filas_crudas(ruta, hoja), list(definicion["columnas_requeridas"]))
            saltar = a2.number_input("Filas de título antes del encabezado", 0, 50, detectada, key=f"saltar_{tabla}_{hoja}",
                                     help="Detectado automáticamente; corrígelo si la vista previa no muestra los encabezados.")
            formato = a3.selectbox("Formato de fecha", list(FORMATOS_FECHA), key=f"fecha_{tabla}") if definicion.get("columnas_fecha") else None
            try:
                previa = _vista_previa(ruta, hoja, saltar)
            except Exception as e:  # noqa: BLE001
                st.error(f"No pude leer el archivo: {e}")
                listo = False
                continue
            st.dataframe(previa.head(5), width="stretch")

            columnas = [str(c) for c in previa.columns]
            requeridas = list(definicion["columnas_requeridas"])
            dc = sugerir_debito_credito(columnas) if "monto" in requeridas else None
            usar_dc = False
            if dc:
                usar_dc = st.checkbox(f"El monto viene en dos columnas: {dc[0]} (débito) y {dc[1]} (crédito)", value=True, key=f"dc_{tabla}")
            pedir = [r for r in requeridas if not (usar_dc and r == "monto")]
            sugerido = sugerir_mapeo(columnas, pedir)
            st.markdown("**Confirma las columnas** (sugeridas automáticamente):")
            mapeo, cols = {}, st.columns(4)
            for i, req in enumerate(pedir):
                opciones_col = ["(falta)"] + columnas
                valor = sugerido.get(req)
                elegida = cols[i % 4].selectbox(req, opciones_col, index=opciones_col.index(valor) if valor in columnas else 0,
                                                key=f"map_{tabla}_{req}")
                if elegida == "(falta)":
                    listo = False
                elif elegida != req:
                    mapeo[elegida] = req
            archivos[tabla] = ruta
            opciones[tabla] = {
                "mapeo": mapeo, "hoja": hoja, "saltar_filas": saltar or None,
                "formato_fecha": FORMATOS_FECHA.get(formato) if formato else None,
                "debito_credito": dc if usar_dc else None,
            }

    st.subheader("3. Correr")
    if st.button("Correr pruebas", type="primary", disabled=not listo):
        try:
            with st.spinner("Importando y corriendo pruebas…"):
                corrida = ejecutar_encargo(manifiesto["id"], archivos, encargo, opciones=opciones)
            st.session_state.corrida = corrida
        except (ErrorImportacion, ValueError) as e:
            st.error(str(e))
    if not listo:
        st.info("Sube los archivos obligatorios y confirma todas sus columnas para habilitar el botón.")

    corrida = st.session_state.get("corrida")
    if corrida:
        st.success(f"Listo. Bitácora íntegra: {'sí' if corrida.bitacora.verificar() else 'NO'}")
        for control in corrida.controles:
            texto = f"{control['archivo']}: {control['filas']:,} filas"
            if control.get("filas_excluidas"):
                motivo = "XML ilegibles" if "archivos_xml" in control else "filas excluidas (totales o en blanco)"
                texto += f" · {control['filas_excluidas']} {motivo}"
            st.caption(texto)
        resumen = pd.DataFrame([
            {"Ficha": r.ficha, "Prueba": r.nombre, "Resultado": r.omitida or r.excepciones} for r in corrida.resultados
        ])
        st.dataframe(resumen, width="stretch", hide_index=True)
        for r in corrida.resultados:
            if r.omitida:
                continue
            with st.expander(f"[{r.ficha}] {r.nombre} · {r.excepciones}"):
                if r.resumen.get("advertencia"):
                    st.warning(r.resumen["advertencia"])
                st.dataframe(r.tabla, width="stretch", hide_index=True)
        st.download_button("Descargar cédula en Excel", corrida.cedula.read_bytes(), file_name=f"cedula_{manifiesto['id']}.xlsx")

# --- Muestreo MUS ------------------------------------------------------------------------
with pestana_muestreo:
    st.subheader("Selección")
    poblacion = st.file_uploader("Población (CSV o Excel con identificador y valor)", type=["csv", "xlsx"], key="poblacion")
    if poblacion:
        ruta = _guardar(poblacion, st.session_state.carpeta)
        df = pd.read_excel(ruta) if ruta.suffix.lower() == ".xlsx" else pd.read_csv(ruta, sep=None, engine="python")
        m1, m2, m3, m4, m5 = st.columns(5)
        col_id = m1.selectbox("Identificador", list(df.columns))
        col_valor = m2.selectbox("Valor", list(df.columns), index=min(1, len(df.columns) - 1))
        tolerable = m3.number_input("Error tolerable", min_value=1.0, value=45000.0, step=1000.0)
        confianza = m4.selectbox("Confianza", [95, 90])
        semilla = m5.number_input("Semilla", value=2025, step=1)
        try:
            seleccion, plan = seleccionar_mus(df, col_id, col_valor, tolerable, int(confianza), semilla=int(semilla))
            st.session_state.plan_mus = plan
            st.write(f"Valor en libros **{plan.valor_libros:,.2f}** · n = **{plan.tamano}** · intervalo **{plan.intervalo:,.2f}** · inicio {plan.inicio:,.2f}")
            st.dataframe(seleccion, width="stretch", hide_index=True)
        except ErrorMuestreo as e:
            st.error(str(e))

    st.subheader("Evaluación")
    errores = st.file_uploader("Errores encontrados (id, valor_libros, valor_auditado)", type=["csv", "xlsx"], key="errores")
    plan = st.session_state.get("plan_mus")
    e1, e2, e3 = st.columns(3)
    intervalo = e1.number_input("Intervalo", min_value=1.0, value=float(plan.intervalo) if plan else 15000.0)
    tolerable_ev = e2.number_input("Error tolerable ", min_value=1.0, value=float(plan.error_tolerable) if plan else 45000.0)
    confianza_ev = e3.selectbox("Confianza ", [95, 90])
    if errores:
        ruta = _guardar(errores, st.session_state.carpeta)
        df_err = pd.read_excel(ruta) if ruta.suffix.lower() == ".xlsx" else pd.read_csv(ruta)
        try:
            ev = evaluar_mus(df_err, intervalo, tolerable_ev, int(confianza_ev))
            (st.error if ev.limite_superior > tolerable_ev else st.success)(ev.conclusion)
            st.dataframe(ev.detalle, width="stretch", hide_index=True)
        except ErrorMuestreo as e:
            st.error(str(e))
