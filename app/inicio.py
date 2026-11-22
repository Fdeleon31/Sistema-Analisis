"""Cuadra · interfaz empresarial para el auditor.

Abre con iniciar.bat (doble clic) o con:  streamlit run app/inicio.py
Todo corre en tu computador: los archivos no salen de él.
"""
from __future__ import annotations

import html
import os
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.comun import (  # noqa: E402
    EXTENSIONES_SOPORTADAS as EXTENSIONES_SUBIDA,
    FORMATOS_FECHA,
    HERRAMIENTAS,
    LEMA_MARCA,
    NOMBRE_MARCA,
    SEPARADORES_DECIMALES,
    calcular_periodo_inicio,
    cargar_dataframe_muestreo,
    constancia_tiempo_real,
    filas_crudas as _filas_crudas,
    formatear_fechas_df as _formatear_fechas_df,
    formatear_periodo_auditado,
    formatear_tamano as _formatear_tamano,
    formula_contextual as _formula_contextual_datos,
    hojas_excel as _hojas,
    pesos_defecto_puntaje as _pesos_defecto_puntaje,
    vista_previa as _vista_previa,
)
from conectores.catalogo import detectar_perfil, perfiles_disponibles, proponer_opciones_perfil  # noqa: E402
from conectores.sql_fuente import leer_conexion_sql, listar_tablas_archivo_sql  # noqa: E402
from ia.copiloto import (  # noqa: E402
    CONSULTAS_SUGERIDAS,
    ejecutar_propuesta_aprobada,
    preparar_conexion_copiloto,
    proponer_consulta_sql,
)
from motor.bitacora import Bitacora, _usuario_actual  # noqa: E402
from motor.cripto import verificar_sello_corrida  # noqa: E402
from motor.ejecutor import CRITERIOS_ASIENTO, NOMBRES_CRITERIOS  # noqa: E402
from motor.diagnostico import diagnostico_a_dataframe  # noqa: E402
from motor.privacidad import detectar_carpeta_sincronizada  # noqa: E402
from motor.seguridad import (  # noqa: E402
    ErrorSeguridad,
    crear_directorio_temporal_seguro,
    nombre_archivo_seguro,
)
from motor.usuarios import (  # noqa: E402
    PERFIL_ADMIN,
    PERFIL_PREPARADOR,
    PERFILES_VALIDOS,
    GestorUsuarios,
    SesionAutenticada,
)
from motor.exportador import detalle_resultado  # noqa: E402
from motor.importador import (  # noqa: E402
    EXTENSIONES_EXCEL,
    EXTENSIONES_SQL,
    EXTENSIONES_TEXTO,
    ErrorImportacion,
    _parece_sap_alv,
    detectar_codificacion,
)
from motor.muestreo import ErrorMuestreo, evaluar_mus, seleccionar_mus  # noqa: E402
from motor.portafolio import guardar_encargo_yaml, listar_corridas_recientes, listar_encargos, resumen_corrida_carpeta  # noqa: E402
from motor.revision import (  # noqa: E402
    ESTADOS_REVISION,
    ROLES_FIRMA,
    cargar_revisiones,
    firmar_papel_trabajo,
    reabrir_papel_trabajo,
    registrar_revision_prueba,
)
from motor.servicio import actualizar_cedula_corrida, ejecutar_encargo, paquetes_disponibles  # noqa: E402
from motor.sintetico import generar_diario_asientos  # noqa: E402
from motor.sugerencias import detectar_fila_encabezado, normalizar, sugerir_mapeo  # noqa: E402

st.set_page_config(page_title=f"{NOMBRE_MARCA.title()} · Analítica Determinista", page_icon="▪", layout="wide")

LOGO_SVG = (
    '<svg width="30" height="30" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">'
    "<defs>"
    '<linearGradient id="emb_g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#34D399"/><stop offset="0.5" stop-color="#107C41"/><stop offset="1" stop-color="#064E3B"/>'
    "</linearGradient>"
    '<linearGradient id="emb_b" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#2563EB"/><stop offset="0.5" stop-color="#1B3A5C"/><stop offset="1" stop-color="#0F2744"/>'
    "</linearGradient>"
    '<linearGradient id="emb_o" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#FDE68A"/><stop offset="1" stop-color="#B45309"/>'
    "</linearGradient>"
    "</defs>"
    '<rect x="8" y="3" width="24" height="24" rx="2.5" fill="url(#emb_g)" stroke="#064E3B" stroke-width="1"/>'
    '<rect x="4" y="7" width="5" height="25" rx="1.5" fill="url(#emb_o)" stroke="#92400E" stroke-width="0.8"/>'
    '<rect x="6" y="7" width="23" height="25" rx="2.5" fill="url(#emb_b)" stroke="#93C5FD" stroke-width="1.1"/>'
    '<rect x="9.5" y="11" width="7" height="7" rx="1" fill="#FFFFFF"/>'
    '<rect x="18.5" y="11" width="7" height="7" rx="1" fill="url(#emb_o)"/>'
    '<rect x="9.5" y="20.5" width="7" height="7" rx="1" fill="#93C5FD"/>'
    '<rect x="18.5" y="20.5" width="7" height="7" rx="1" fill="#34D399"/>'
    '<path d="M6.5 8 H28.5 V14 Q17 18 6.5 15 Z" fill="#FFFFFF" fill-opacity="0.16"/>'
    "</svg>"
)


def _inyectar_estilos() -> None:
    ruta_css = Path(__file__).with_name("estilos.css")
    if ruta_css.exists():
        css = ruta_css.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _inicializar_estado() -> None:
    defaults = {
        "herramienta": "asientos-nia240",
        "carpeta": crear_directorio_temporal_seguro(prefijo="folio_web_"),
        "corridas": {},
        "ultima_corrida": None,
        "archivos_subidos": {},
        "sesion_web": None,
        "auditor": _usuario_actual(),
        "rol": "Preparador",
        "encargo_datos": {
            "cliente": "Cliente Demo, S.A.",
            "periodo_inicio": date(2025, 1, 1),
            "fecha_cierre": date(2025, 12, 31),
            "marco": "NIIF",
            "materialidad": 150000.0,
            "materialidad_ejecucion": 112500.0,
            "umbral_trivial": 7500.0,
            "umbral_aprobacion": 10000.0,
        },
    }
    for clave, valor in defaults.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor
    if "periodo_inicio" not in st.session_state.encargo_datos:
        st.session_state.encargo_datos["periodo_inicio"] = calcular_periodo_inicio(
            st.session_state.encargo_datos.get("fecha_cierre")
        )


def _sync_encargo(campo: str, widget_key: str) -> None:
    valor = st.session_state.get(widget_key)
    if campo in ("fecha_cierre", "periodo_inicio") and not isinstance(valor, date):
        return
    st.session_state.encargo_datos[campo] = valor


def _guardar(subido, carpeta: Path) -> Path:
    carpeta_res = carpeta.resolve()
    nombre_seg = nombre_archivo_seguro(subido.name)
    ruta = (carpeta_res / nombre_seg).resolve()
    if carpeta_res not in ruta.parents:
        raise ErrorSeguridad(f"Ruta destino no permitida para el archivo subido: {subido.name!r}")
    if ruta.exists() and ruta.stat().st_size == subido.size:
        return ruta
    subido.seek(0)
    with ruta.open("wb") as destino:
        shutil.copyfileobj(subido, destino, length=8 * 1024 * 1024)
    return ruta


def _kpi_html(etiqueta: str, valor: str, subtitulo: str = "", variante: str = "") -> str:
    cls = f"cuadra-kpi {variante}".strip()
    sub = f'<div class="cuadra-kpi-sub">{html.escape(subtitulo)}</div>' if subtitulo else ""
    return (
        f'<div class="{cls}">'
        f'<div class="cuadra-kpi-label">{html.escape(etiqueta)}</div>'
        f'<div class="cuadra-kpi-value">{html.escape(str(valor))}</div>'
        f"{sub}</div>"
    )


def _formula_contextual(hid: str) -> tuple[str, str]:
    datos = st.session_state.encargo_datos
    ultima = st.session_state.get("ultima_corrida")
    estado_bit = "INTEGRA" if (ultima and ultima.bitacora.verificar()) else ("ALTERADA" if ultima else "SIN_EJECUCION")
    return _formula_contextual_datos(
        hid,
        str(datos["cliente"] or "Sin cliente"),
        datos["fecha_cierre"],
        float(datos["materialidad"] or 0.0),
        estado_bit,
        periodo_inicio=datos.get("periodo_inicio"),
    )


@st.fragment(run_every="1s")
def _render_appbar_tiempo_real() -> None:
    """Renderiza la barra superior ejecutiva con reloj y período auditado en tiempo real."""
    datos = st.session_state.encargo_datos
    cliente_txt = html.escape(str(datos["cliente"] or "Sin cliente"))
    cierre = datos["fecha_cierre"]
    periodo_txt = formatear_periodo_auditado(datos.get("periodo_inicio"), cierre)
    marco_txt = html.escape(str(datos["marco"]))
    mat_val = float(datos.get("materialidad") or 0.0)
    auditor_txt = html.escape(str(st.session_state.get("auditor") or _usuario_actual()))
    rol_txt = html.escape(str(st.session_state.get("rol") or "Preparador"))
    eyebrow_txt = html.escape(f"{NOMBRE_MARCA} · {LEMA_MARCA.split(' · ', 1)[0].upper()}")
    hora_local, hora_utc = constancia_tiempo_real()
    hora_utc_corta = hora_utc.split(" ", 1)[1] if " " in hora_utc else hora_utc

    ultima = st.session_state.get("ultima_corrida")
    if ultima is None:
        bitacora_pill = '<span class="cuadra-pill cuadra-pill-muted">BITÁCORA SIN EJECUCIÓN</span>'
    elif ultima.bitacora.verificar():
        bitacora_pill = '<span class="cuadra-pill cuadra-pill-ok">BITÁCORA ÍNTEGRA · SHA-256</span>'
    else:
        bitacora_pill = '<span class="cuadra-pill cuadra-pill-err">BITÁCORA ALTERADA</span>'

    st.markdown(
        "\n".join([
            '<div class="cuadra-appbar">',
            '  <div class="cuadra-brand">',
            '    <div>',
            f'      <div class="cuadra-brand-eyebrow" title="{html.escape(LEMA_MARCA)}">{eyebrow_txt}</div>',
            f'      <div class="cuadra-brand-title">Cliente: {cliente_txt}</div>',
            '    </div>',
            '  </div>',
            f'  <div class="cuadra-doc-title">Marco {marco_txt} · Mat. B/. {mat_val:,.0f} · Auditor: {auditor_txt} ({rol_txt})</div>',
            f'  <div class="cuadra-constancia-box" title="{html.escape(hora_local)} | {html.escape(hora_utc)}">',
            f'    <div class="cuadra-clock-val">{html.escape(hora_local)} · {html.escape(hora_utc_corta)}</div>',
            f'    <div class="cuadra-period-val">PERÍODO AUDITADO: {html.escape(periodo_txt)}</div>',
            '  </div>',
            '  <div class="cuadra-status-group">',
            '    <span class="cuadra-pill">SIN INTERNET</span>',
            f'    {bitacora_pill}',
            '  </div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )


def _render_barra_superior() -> None:
    _render_appbar_tiempo_real()
    st.markdown(
        "\n".join([
            '<div class="cuadra-ribbon-tabs">',
            '  <div class="cuadra-ribbon-tab-list">',
            '    <span class="win97-grip" aria-hidden="true"></span>',
            '    <div class="cuadra-ribbon-tab-active">Auditoría y Datos</div>',
            '    <div class="cuadra-ribbon-tab-info">Normativa NIA · DGI Panamá</div>',
            '  </div>',
            '  <div class="cuadra-ribbon-right">Motor DuckDB Determinista · Trazabilidad SHA-256</div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )

    with st.container(key="cuadra_ribbon_box", border=False):
        st.markdown('<div class="cuadra-toolbar-marker"></div>', unsafe_allow_html=True)
        cols = st.columns(len(HERRAMIENTAS), gap="small")
        for idx, (hid, nombre, _, _) in enumerate(HERRAMIENTAS):
            activo = st.session_state.herramienta == hid
            if cols[idx].button(
                nombre,
                key=f"tb_{hid}",
                type="primary" if activo else "secondary",
                use_container_width=True,
            ):
                st.session_state.herramienta = hid
                st.rerun()
        st.markdown(
            """
            <div class="cuadra-ribbon-groups">
                <div class="cuadra-ribbon-group-lbl" title="Pruebas deterministas por paquete (NIA 240, Benford, Factura DGI y Bancos)">Pruebas de Auditoría (NIA)</div>
                <div class="cuadra-ribbon-group-lbl" title="Muestreo Estadístico Monetario (NIA 530)">Muestreo</div>
                <div class="cuadra-ribbon-group-lbl" title="Conectores ERP/SQL y Copiloto Offline">ERP, SQL y Copiloto</div>
                <div class="cuadra-ribbon-group-lbl" title="Bitácora SHA-256, Roles NIA 220 y Cédulas Excel">Evidencia, Roles y Excel</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    meta = next(h for h in HERRAMIENTAS if h[0] == st.session_state.herramienta)
    cuadro_nombre, formula = _formula_contextual(meta[0])
    nias = "".join(f'<span class="cuadra-nia-tag">{html.escape(n)}</span>' for n in meta[3])
    st.markdown(
        f"""
        <div class="cuadra-formulabar">
            <div class="cuadra-namebox">{html.escape(cuadro_nombre)}</div>
            <div class="cuadra-fx">fx</div>
            <div class="cuadra-formula-text" title="{html.escape(meta[2])}">{html.escape(formula)}</div>
            <div class="cuadra-nia-group">{nias}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pesos_encargo(manifiesto: dict, encargo: dict) -> None:
    pesos_def, alto_def, medio_def = _pesos_defecto_puntaje(manifiesto)
    if not pesos_def:
        return
    with st.expander("Pesos del puntaje de riesgo (opcional)"):
        st.caption("Ajusta los pesos por criterio o los umbrales de clasificación solo si el encargo lo requiere.")
        cols = st.columns(2)
        nuevos_pesos: dict[str, int] = {}
        for idx, (clave, valor_def) in enumerate(pesos_def.items()):
            etiqueta = NOMBRES_CRITERIOS.get(clave, clave)
            nuevos_pesos[clave] = int(
                cols[idx % 2].number_input(
                    etiqueta, min_value=0, max_value=100, value=int(valor_def), step=1, key=f"peso_{clave}"
                )
            )
        u1, u2 = st.columns(2)
        nivel_alto = int(u1.number_input("Umbral nivel alto", min_value=1, value=alto_def, step=1, key="umbral_alto_riesgo"))
        nivel_medio = int(u2.number_input("Umbral nivel medio", min_value=1, value=medio_def, step=1, key="umbral_medio_riesgo"))
        cambiados = {k: v for k, v in nuevos_pesos.items() if v != pesos_def[k]}
        if cambiados:
            encargo["pesos_riesgo"] = cambiados
        if nivel_alto != alto_def:
            encargo["nivel_riesgo_alto"] = nivel_alto
        if nivel_medio != medio_def:
            encargo["nivel_riesgo_medio"] = nivel_medio


def _render_confirmacion_columnas(
    tabla: str,
    definicion: dict,
    previa: pd.DataFrame,
    origen_id: str,
    perfiles: dict[str, dict],
    extra_opciones: dict,
) -> tuple[bool, dict]:
    st.dataframe(previa.head(5), width="stretch", hide_index=True)
    columnas = [str(c) for c in previa.columns]
    requeridas = list(definicion["columnas_requeridas"])

    perfil_auto, _ = detectar_perfil(columnas)
    nombres_perfiles = {p["nombre"]: pid for pid, p in perfiles.items()}
    opciones_erp = ["Automático / Genérico"] + list(nombres_perfiles)
    idx_erp = opciones_erp.index(perfil_auto["nombre"]) if perfil_auto and perfil_auto["nombre"] in opciones_erp else 0

    erp_nombre = st.selectbox(
        "Sistema contable / ERP",
        opciones_erp,
        index=idx_erp,
        key=f"erp_{tabla}_{origen_id}",
    )
    if perfil_auto:
        st.caption(f"Sistema detectado automáticamente por encabezados: **{perfil_auto['nombre']}**")

    perfil_elegido = perfiles[nombres_perfiles[erp_nombre]] if erp_nombre != "Automático / Genérico" else None
    perfil_key = perfil_elegido["id"] if perfil_elegido else "generico"
    prop = proponer_opciones_perfil(perfil_elegido, columnas, requeridas)

    dc = prop["debito_credito"]
    ind = prop["indicador_dc"]
    usar_dc = False
    usar_ind = False
    if dc:
        usar_dc = st.checkbox(
            f"El monto viene en dos columnas: {dc[0]} (débito) y {dc[1]} (crédito)",
            value=True,
            key=f"dc_{tabla}_{origen_id}_{perfil_key}",
        )
    elif ind:
        usar_ind = st.checkbox(
            f"Aplicar signo Debe/Haber con la columna indicadora {ind[0]!r} (créditos: {', '.join(ind[1])})",
            value=True,
            key=f"ind_{tabla}_{origen_id}_{perfil_key}",
        )

    pedir = [r for r in requeridas if not (usar_dc and r == "monto")]
    sugerido = dict(prop["mapeo_std_a_col"])
    if "monto" in pedir and sugerido.get("monto") is None:
        sinonimos = (perfil_elegido or {}).get("aliases")
        sugerido["monto"] = sugerir_mapeo(columnas, ["monto"], sinonimos_extra=sinonimos).get("monto")

    detectadas_iniciales = sum(1 for req in pedir if sugerido.get(req) in columnas)
    todas_ok = detectadas_iniciales == len(pedir)
    titulo_mapeo = (
        f"Mapeo confirmado automáticamente ({detectadas_iniciales}/{len(pedir)} columnas) — clic para ajustar"
        if todas_ok
        else f"Confirmar mapeo de columnas ({detectadas_iniciales}/{len(pedir)} detectadas)"
    )

    mapeo: dict[str, str] = {}
    faltan_req: list[str] = []
    generar_linea = False
    usuario_por_defecto = None

    with st.expander(titulo_mapeo, expanded=not todas_ok):
        cols = st.columns(4)
        for i, req in enumerate(pedir):
            opciones_col = ["(falta)"] + columnas
            valor = sugerido.get(req)
            elegida = cols[i % 4].selectbox(
                req,
                opciones_col,
                index=opciones_col.index(valor) if valor in columnas else 0,
                key=f"map_{tabla}_{req}_{origen_id}_{perfil_key}",
            )
            if elegida == "(falta)":
                faltan_req.append(req)
            elif elegida != req:
                mapeo[elegida] = req

        if "linea" in faltan_req:
            generar_linea = st.checkbox(
                "Generar número de línea por asiento (queda registrado en la bitácora)",
                value=bool(prop["generar_linea"]),
                key=f"gen_linea_{tabla}_{origen_id}_{perfil_key}",
            )
            if generar_linea:
                faltan_req.remove("linea")

        if "usuario" in faltan_req:
            usar_usr_def = st.checkbox(
                "Continuar sin columna de usuario (usa '(sin usuario en origen)' y queda en bitácora)",
                value=bool(prop["usuario_por_defecto"]),
                key=f"usr_def_{tabla}_{origen_id}_{perfil_key}",
            )
            if usar_usr_def:
                usuario_por_defecto = prop["usuario_por_defecto"] or "(sin usuario en origen)"
                faltan_req.remove("usuario")

    opciones_tabla = {
        **extra_opciones,
        "mapeo": mapeo,
        "debito_credito": dc if usar_dc else None,
        "indicador_dc": ind if usar_ind else None,
        "generar_linea": generar_linea or None,
        "usuario_por_defecto": usuario_por_defecto,
        "perfil_erp": perfil_elegido["id"] if perfil_elegido else None,
        "_confirmado_ui": True,
    }
    return len(faltan_req) == 0, opciones_tabla


def _render_puntaje_resultados(corrida) -> None:
    r_puntaje = next((r for r in corrida.resultados if r.id == "asientos-puntaje" and not r.omitida), None)
    if not r_puntaje:
        return

    st.markdown('<div class="cuadra-section-hdr">Puntaje de riesgo por asiento</div>', unsafe_allow_html=True)
    pn = r_puntaje.resumen.get("por_nivel", {"alto": 0, "medio": 0, "bajo": 0})
    analizados = r_puntaje.resumen.get("asientos_analizados", 0)
    umbrales = r_puntaje.resumen.get("umbrales", {})

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(_kpi_html("Riesgo alto", str(pn.get("alto", 0)), f"Puntaje ≥ {umbrales.get('alto', 25)}", "cuadra-kpi-alto"), unsafe_allow_html=True)
    k2.markdown(_kpi_html("Riesgo medio", str(pn.get("medio", 0)), f"Puntaje ≥ {umbrales.get('medio', 15)}", "cuadra-kpi-medio"), unsafe_allow_html=True)
    k3.markdown(_kpi_html("Riesgo bajo", str(pn.get("bajo", 0)), "Puntaje > 0", "cuadra-kpi-bajo"), unsafe_allow_html=True)
    k4.markdown(_kpi_html("Asientos analizados", f"{analizados:,}", f"{r_puntaje.excepciones} con hallazgos"), unsafe_allow_html=True)

    pesos = r_puntaje.resumen.get("pesos", {})
    with st.expander("Ver pesos aplicados por criterio", expanded=False):
        df_pesos = pd.DataFrame([
            {"Criterio": NOMBRES_CRITERIOS.get(k, k), "Peso": v} for k, v in pesos.items()
        ])
        st.dataframe(df_pesos, width="stretch", hide_index=True)

    cols_visibles = [
        c for c in ["asiento", "fecha", "usuario", "descripcion", "total_debito", "puntaje", "nivel", "explicacion"]
        if c in r_puntaje.tabla.columns
    ]
    tabla_vista = _formatear_fechas_df(r_puntaje.tabla[cols_visibles])
    st.dataframe(
        tabla_vista,
        width="stretch",
        hide_index=True,
        column_config={
            "asiento": st.column_config.TextColumn("Asiento", width="small"),
            "fecha": st.column_config.TextColumn("Fecha", width="small"),
            "usuario": st.column_config.TextColumn("Usuario", width="small"),
            "descripcion": st.column_config.TextColumn("Descripción", width="medium"),
            "total_debito": st.column_config.NumberColumn("Total débito", format="%,.2f", width="small"),
            "puntaje": st.column_config.ProgressColumn(
                "Puntaje",
                min_value=0,
                max_value=int(r_puntaje.resumen.get("puntaje_maximo", 100) or 100),
                format="%d",
                width="small",
            ),
            "nivel": st.column_config.TextColumn("Nivel", width="small"),
            "explicacion": st.column_config.TextColumn("Explicación", width="large"),
        },
    )


def _render_origen_archivo_o_ruta(
    ruta: Path,
    origen_id: str,
    paquete_id: str,
    tabla: str,
    definicion: dict,
    perfiles_erp: dict[str, dict],
) -> tuple[bool, dict | None]:
    """Previsualiza un archivo local (subido o por ruta directa) y confirma sus columnas."""
    ext = ruta.suffix.lower()
    extra_opc: dict = {}

    if ext in EXTENSIONES_SQL:
        try:
            tablas_sql = listar_tablas_archivo_sql(ruta)
        except ValueError as e:
            st.error(f"No pude abrir el origen SQL: {e}")
            return False, None
        t_sql = st.selectbox("Tabla SQL", tablas_sql, key=f"tsql_{tabla}_{origen_id}") if tablas_sql else None
        q_sql = st.text_area(
            "Consulta SQL personalizada (opcional, solo SELECT)",
            key=f"qsql_{tabla}_{origen_id}",
            placeholder="Opcional: SELECT * FROM ...",
        )
        try:
            previa = _vista_previa(ruta, None, 0, tabla_sql=t_sql, consulta_sql=q_sql or None)
        except ValueError as e:
            st.error(str(e))
            return False, None
        extra_opc = {"tabla_origen": t_sql, "consulta_sql": q_sql or None}
    else:
        hoja = None
        saltar = 0
        formato = None
        sep_dec = "Punto (1,234.56)"
        if ext in EXTENSIONES_EXCEL or ext in EXTENSIONES_TEXTO:
            hojas = _hojas(ruta)
            a1, a2, a3, a4 = st.columns(4)
            hoja = a1.selectbox("Hoja", hojas, index=len(hojas) - 1, key=f"hoja_{tabla}_{origen_id}") if hojas else None
            es_alv = ext in EXTENSIONES_TEXTO and _parece_sap_alv(ruta, detectar_codificacion(ruta, max_bytes=262144), 0)
            if es_alv:
                a2.caption("Formato SAP ALV (`|`) detectado")
            else:
                detectada = detectar_fila_encabezado(_filas_crudas(ruta, hoja), list(definicion["columnas_requeridas"]))
                saltar = int(
                    a2.number_input(
                        "Filas antes del encabezado",
                        0, 50, detectada,
                        key=f"saltar_{tabla}_{origen_id}_{hoja}",
                        help="Detectado automáticamente; corrígelo si la vista previa no muestra los encabezados.",
                    )
                )
            if definicion.get("columnas_fecha"):
                formato = a3.selectbox("Formato de fecha", list(FORMATOS_FECHA), key=f"fecha_{tabla}_{origen_id}")
            sep_dec = a4.selectbox("Separador decimal", list(SEPARADORES_DECIMALES), key=f"dec_{tabla}_{origen_id}")
        try:
            previa = _vista_previa(ruta, hoja, saltar)
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude leer el archivo: {e}")
            return False, None
        extra_opc = {
            "hoja": hoja,
            "saltar_filas": saltar or None,
            "formato_fecha": FORMATOS_FECHA.get(formato) if formato else None,
            "separador_decimal": SEPARADORES_DECIMALES[sep_dec],
        }

    ok_tabla, opc_tabla = _render_confirmacion_columnas(tabla, definicion, previa, origen_id, perfiles_erp, extra_opc)
    return ok_tabla, opc_tabla


def _render_vista_paquete(paquete_id: str, perfiles_erp: dict[str, dict]) -> None:
    paquetes = paquetes_disponibles()
    manifiesto = paquetes[paquete_id]

    datos_enc = st.session_state.encargo_datos
    with st.container(border=True):
        st.markdown('<div class="cuadra-section-hdr">1 · Parámetros del encargo</div>', unsafe_allow_html=True)
        c1, c_ini, c2, c3 = st.columns([2, 1, 1, 1])
        k_cli = f"w_{paquete_id}_cliente"
        k_ini = f"w_{paquete_id}_inicio"
        k_cie = f"w_{paquete_id}_cierre"
        k_mar = f"w_{paquete_id}_marco"
        cliente = c1.text_input(
            "Cliente", value=datos_enc["cliente"], key=k_cli, on_change=_sync_encargo, args=("cliente", k_cli)
        )
        inicio_defecto = datos_enc.get("periodo_inicio") or calcular_periodo_inicio(datos_enc["fecha_cierre"])
        periodo_inicio = c_ini.date_input(
            "Inicio del período",
            value=inicio_defecto,
            key=k_ini,
            on_change=_sync_encargo,
            args=("periodo_inicio", k_ini),
        )
        fecha_cierre = c2.date_input(
            "Fecha de cierre", value=datos_enc["fecha_cierre"], key=k_cie, on_change=_sync_encargo, args=("fecha_cierre", k_cie)
        )
        marcos = ["NIIF", "NIIF para PYMES"]
        marco = c3.selectbox(
            "Marco contable",
            marcos,
            index=marcos.index(datos_enc["marco"]) if datos_enc["marco"] in marcos else 0,
            key=k_mar,
            on_change=_sync_encargo,
            args=("marco", k_mar),
        )

        c4, c5, c6, c7 = st.columns(4)
        k_mat = f"w_{paquete_id}_mat"
        k_mej = f"w_{paquete_id}_mej"
        k_tri = f"w_{paquete_id}_tri"
        k_apr = f"w_{paquete_id}_apr"
        materialidad = c4.number_input(
            "Materialidad", min_value=0.0, value=float(datos_enc["materialidad"]), step=1000.0,
            key=k_mat, on_change=_sync_encargo, args=("materialidad", k_mat),
        )
        materialidad_ejecucion = c5.number_input(
            "Materialidad de ejecución", min_value=0.0, value=float(datos_enc["materialidad_ejecucion"]), step=1000.0,
            key=k_mej, on_change=_sync_encargo, args=("materialidad_ejecucion", k_mej),
        )
        umbral_trivial = c6.number_input(
            "Umbral trivial", min_value=0.0, value=float(datos_enc["umbral_trivial"]), step=500.0,
            key=k_tri, on_change=_sync_encargo, args=("umbral_trivial", k_tri),
        )
        umbral_aprobacion = c7.number_input(
            "Umbral de aprobación",
            min_value=0.0,
            value=float(datos_enc["umbral_aprobacion"]),
            step=500.0,
            help="Monto desde el cual un asiento requiere aprobación; usa 0 si no aplica.",
            key=k_apr,
            on_change=_sync_encargo,
            args=("umbral_aprobacion", k_apr),
        )
        fecha_cierre_eff = fecha_cierre if isinstance(fecha_cierre, date) else datos_enc["fecha_cierre"]
        periodo_inicio_eff = (
            periodo_inicio
            if isinstance(periodo_inicio, date)
            else datos_enc.get("periodo_inicio") or calcular_periodo_inicio(fecha_cierre_eff)
        )
        if periodo_inicio_eff > fecha_cierre_eff:
            st.warning("El inicio del período no debe ser posterior a la fecha de cierre.")

        datos_enc.update({
            "cliente": cliente,
            "periodo_inicio": periodo_inicio_eff,
            "fecha_cierre": fecha_cierre_eff,
            "marco": marco,
            "materialidad": materialidad,
            "materialidad_ejecucion": materialidad_ejecucion,
            "umbral_trivial": umbral_trivial,
            "umbral_aprobacion": umbral_aprobacion,
        })

        encargo: dict = {
            "cliente": cliente,
            "periodo_inicio": periodo_inicio_eff.isoformat(),
            "fecha_cierre": fecha_cierre_eff.isoformat(),
            "marco": marco,
            "prefijo_ingresos": "4",
            "materialidad": materialidad,
            "materialidad_ejecucion": materialidad_ejecucion,
            "umbral_trivial": umbral_trivial,
            "umbral_aprobacion": umbral_aprobacion,
        }
        if paquete_id == "asientos-nia240":
            _render_pesos_encargo(manifiesto, encargo)

    with st.container(border=True):
        st.markdown('<div class="cuadra-section-hdr">2 · Fuentes de datos del cliente</div>', unsafe_allow_html=True)
        carpeta = st.session_state.carpeta
        archivos: dict[str, Path | str | None] = {}
        opciones: dict[str, dict] = {}
        listo = True

        for definicion in manifiesto["archivos"]:
            tabla = definicion["tabla"]
            etiqueta = f"{tabla.capitalize()}{' (opcional)' if definicion.get('opcional') else ''}"
            with st.expander(f"{etiqueta} — {definicion.get('descripcion', '')}", expanded=not definicion.get("opcional")):
                clave_subida = f"{paquete_id}_{tabla}"
                if definicion.get("tipo") in ("factura_electronica", "estado_cuenta_bancario"):
                    es_banco = definicion.get("tipo") == "estado_cuenta_bancario"
                    subidos = st.file_uploader(
                        "Extracto bancario (PDF, ZIP, CSV o Excel)" if es_banco else "ZIP o archivos XML de factura electrónica",
                        type=["pdf", "zip", "csv", "xlsx", "xls"] if es_banco else ["zip", "xml"],
                        accept_multiple_files=True,
                        key=f"archivo_{paquete_id}_{tabla}",
                    )
                    if subidos:
                        destino = carpeta / f"esp_{paquete_id}_{tabla}"
                        destino.mkdir(exist_ok=True)
                        for s_ in subidos:
                            _guardar(s_, destino)
                        st.session_state.archivos_subidos[clave_subida] = {
                            "ruta": destino if len(subidos) > 1 else _guardar(subidos[0], destino),
                            "nombre": f"{len(subidos)} archivo(s)" if len(subidos) > 1 else subidos[0].name,
                            "size": sum(s_.size for s_ in subidos),
                        }
                    guardado = st.session_state.archivos_subidos.get(clave_subida)
                    if not guardado or not Path(guardado["ruta"]).exists():
                        archivos[tabla] = None
                        listo = listo and bool(definicion.get("opcional"))
                        continue
                    c_info, c_quit = st.columns([4, 1])
                    nota = "líneas no transaccionales quedarán en control" if es_banco else "los XML ilegibles se reportarán sin detener la lectura"
                    c_info.caption(f"Fuente activa en sesión: **{guardado['nombre']}** ({nota}).")
                    if c_quit.button("Quitar", key=f"quitar_{clave_subida}", use_container_width=True):
                        st.session_state.archivos_subidos.pop(clave_subida, None)
                        st.rerun()
                    archivos[tabla] = Path(guardado["ruta"])
                    continue

                modo = st.radio(
                    "Origen de datos",
                    [
                        "Archivo (hasta 4 GB: Excel, CSV, SAP TXT, Parquet, JSON, SQLite, DuckDB, .sql)",
                        "Ruta local directa (archivos muy pesados en este equipo, lectura directa sin subir)",
                        "Base de datos SQL (solo lectura)",
                    ],
                    horizontal=True,
                    key=f"origen_{paquete_id}_{tabla}",
                )
                if modo.startswith("Archivo"):
                    subido = st.file_uploader(
                        "Archivo de datos",
                        type=EXTENSIONES_SUBIDA,
                        key=f"archivo_{paquete_id}_{tabla}",
                    )
                    if subido:
                        ruta_guardada = _guardar(subido, carpeta)
                        st.session_state.archivos_subidos[clave_subida] = {
                            "ruta": ruta_guardada,
                            "nombre": subido.name,
                            "size": subido.size,
                        }
                    guardado = st.session_state.archivos_subidos.get(clave_subida)
                    if not guardado or not Path(guardado["ruta"]).exists():
                        archivos[tabla] = None
                        listo = listo and bool(definicion.get("opcional"))
                        continue
                    ruta = Path(guardado["ruta"])
                    if not subido:
                        c_info, c_quit = st.columns([4, 1])
                        c_info.info(f"Archivo activo en sesión: **{guardado['nombre']}** ({_formatear_tamano(guardado['size'])})")
                        if c_quit.button("Quitar", key=f"quitar_{clave_subida}", use_container_width=True):
                            st.session_state.archivos_subidos.pop(clave_subida, None)
                            st.rerun()
                    origen_id = f"{paquete_id}_f_{guardado['nombre']}_{guardado['size']}"
                    ok_tabla, opc_tabla = _render_origen_archivo_o_ruta(ruta, origen_id, paquete_id, tabla, definicion, perfiles_erp)
                    if opc_tabla is None:
                        listo = False
                        continue
                    archivos[tabla] = ruta
                    opciones[tabla] = opc_tabla
                    listo = listo and ok_tabla
                elif modo.startswith("Ruta local"):
                    ruta_txt = st.text_input(
                        "Ruta del archivo en este computador",
                        key=f"ruta_local_{paquete_id}_{tabla}",
                        placeholder=r"C:\Datos\mayor_2025.csv  o  datos\ejemplo\diario_2025.csv",
                    ).strip().strip('"').strip("'")
                    if not ruta_txt:
                        archivos[tabla] = None
                        listo = listo and bool(definicion.get("opcional"))
                        continue
                    ruta = Path(ruta_txt)
                    if not ruta.is_absolute():
                        ruta = (RAIZ / ruta).resolve()
                    if not ruta.exists() or not ruta.is_file():
                        st.error(f"No encuentro el archivo: {ruta}")
                        archivos[tabla] = None
                        listo = False
                        continue
                    tamano = ruta.stat().st_size
                    st.caption(f"Lectura directa sin copia: **{ruta.name}** ({_formatear_tamano(tamano)})")
                    origen_id = f"{paquete_id}_loc_{ruta.name}_{tamano}"
                    ok_tabla, opc_tabla = _render_origen_archivo_o_ruta(ruta, origen_id, paquete_id, tabla, definicion, perfiles_erp)
                    if opc_tabla is None:
                        listo = False
                        continue
                    archivos[tabla] = ruta
                    opciones[tabla] = opc_tabla
                    listo = listo and ok_tabla
                else:
                    uri_sql = st.text_input(
                        "Cadena de conexión SQL (solo lectura)",
                        key=f"uri_{paquete_id}_{tabla}",
                        placeholder="sqlite:///ruta/erp.db  o  mssql+pyodbc://usuario:clave@servidor/bd",
                    )
                    plantillas = {
                        f"{p['nombre']} · {q['titulo']}": q["sql"].strip()
                        for p in perfiles_erp.values()
                        for q in (p.get("consultas_sql") or [])
                    }
                    sel_plantilla = st.selectbox(
                        "Plantilla SQL de ERP (opcional)",
                        ["(consulta manual)"] + list(plantillas),
                        key=f"plantilla_sql_{paquete_id}_{tabla}",
                    )
                    if sel_plantilla != "(consulta manual)" and st.button("Cargar plantilla SQL", key=f"cargar_pl_{paquete_id}_{tabla}"):
                        st.session_state[f"qsql_uri_{paquete_id}_{tabla}"] = plantillas[sel_plantilla]
                    t_sql_uri = st.text_input("Tabla (si no escribes consulta)", key=f"tsql_uri_{paquete_id}_{tabla}")
                    q_sql_uri = st.text_area("Consulta SQL (solo SELECT / WITH)", key=f"qsql_uri_{paquete_id}_{tabla}")
                    if st.button("Probar consulta y previsualizar", key=f"btn_sql_{paquete_id}_{tabla}"):
                        try:
                            df_p, _ = leer_conexion_sql(
                                uri_sql,
                                tabla_origen=t_sql_uri or None,
                                consulta_sql=q_sql_uri or None,
                                limite=20,
                            )
                            st.session_state[f"sql_previa_{paquete_id}_{tabla}"] = {
                                "uri": uri_sql,
                                "df": df_p,
                                "tabla_origen": t_sql_uri or None,
                                "consulta_sql": q_sql_uri or None,
                            }
                        except Exception as e:  # noqa: BLE001
                            st.error(str(e))
                    cache_sql = st.session_state.get(f"sql_previa_{paquete_id}_{tabla}")
                    if not cache_sql or cache_sql["uri"] != uri_sql:
                        archivos[tabla] = None
                        listo = listo and bool(definicion.get("opcional"))
                        continue
                    ok_tabla, opc_tabla = _render_confirmacion_columnas(
                        tabla,
                        definicion,
                        cache_sql["df"],
                        f"{paquete_id}_sql_{hash(uri_sql)}",
                        perfiles_erp,
                        {"tabla_origen": cache_sql["tabla_origen"], "consulta_sql": cache_sql["consulta_sql"]},
                    )
                    archivos[tabla] = uri_sql
                    opciones[tabla] = opc_tabla
                    listo = listo and ok_tabla

    with st.container(border=True):
        st.markdown('<div class="cuadra-section-hdr">3 · Ejecución y resultados</div>', unsafe_allow_html=True)
        b_col, info_col = st.columns([1, 3])
        if b_col.button("Correr pruebas", type="primary", disabled=not listo, use_container_width=True):
            try:
                with st.spinner("Importando datos y ejecutando pruebas deterministas…"):
                    corrida_nueva = ejecutar_encargo(manifiesto["id"], archivos, encargo, opciones=opciones)
                st.session_state.corridas[paquete_id] = corrida_nueva
                st.session_state.ultima_corrida = corrida_nueva
                st.rerun()
            except (ErrorImportacion, ValueError) as e:
                st.error(str(e))
        if not listo:
            info_col.info("Carga los archivos obligatorios y confirma las columnas para habilitar la ejecución.")

        corrida = st.session_state.corridas.get(paquete_id)
        if corrida:
            r1, r2 = st.columns([3, 1])
            integra = corrida.bitacora.verificar()
            if integra:
                r1.success("Ejecución completada · Bitácora encadenada íntegra (SHA-256 verificado).")
            else:
                r1.error("Ejecución completada · Advertencia: la verificación de integridad de la bitácora falló.")
            r2.download_button(
                "Descargar cédula en Excel",
                corrida.cedula.read_bytes(),
                file_name=f"cedula_{manifiesto['id']}.xlsx",
                use_container_width=True,
            )

            diag = corrida.diagnostico or {}
            if diag:
                est_d = diag.get("estado_general", "OK")
                msg_d = f"Diagnóstico previo de confiabilidad de datos: **{est_d}** ({diag.get('resumen', '')})"
                if est_d == "ALERTA":
                    st.error(msg_d)
                elif est_d == "ADVERTENCIA":
                    st.warning(msg_d)
                else:
                    st.info(msg_d)
                with st.expander("Detalle de diagnóstico contable e integridad fuente", expanded=(est_d == "ALERTA")):
                    st.dataframe(diagnostico_a_dataframe(diag), width="stretch", hide_index=True)

            with st.expander("Control de archivos y transformaciones registradas", expanded=False):
                df_ctrl = pd.DataFrame([
                    {
                        "Archivo": c["archivo"],
                        "Filas": c["filas"],
                        "Excluidas": c.get("filas_excluidas", 0),
                        "Codificación": c.get("codificacion", "Excel"),
                        "ERP": c.get("perfil_erp") or "Genérico",
                        "Transformaciones": " | ".join(c.get("transformaciones", [])) or "Ninguna",
                    }
                    for c in corrida.controles
                ])
                st.dataframe(df_ctrl, width="stretch", hide_index=True)

            resumen = pd.DataFrame([
                {
                    "Norma NIA": ", ".join(r.nia) if r.nia else "—",
                    "Prueba": r.nombre,
                    "Hallazgos": r.omitida or r.excepciones,
                    "Resumen": "" if r.omitida else detalle_resultado(r),
                }
                for r in corrida.resultados
            ])
            st.dataframe(resumen, width="stretch", hide_index=True)

            _render_puntaje_resultados(corrida)

            st.markdown('<div class="cuadra-section-hdr" style="margin-top:0.75rem;">Detalle por prueba</div>', unsafe_allow_html=True)
            for r in corrida.resultados:
                if r.omitida:
                    continue
                if r.id == "asientos-puntaje":
                    titulo_exp = f"Detalle técnico: matriz de criterios por asiento · {r.excepciones} asientos"
                    cols_matriz = [c for c in ["asiento", "puntaje", "nivel", *CRITERIOS_ASIENTO] if c in r.tabla.columns]
                    tabla_exp = r.tabla[cols_matriz].rename(columns=NOMBRES_CRITERIOS)
                else:
                    titulo_exp = f"{r.nombre} · {r.excepciones}"
                    tabla_exp = _formatear_fechas_df(r.tabla)
                with st.expander(titulo_exp):
                    if r.resumen.get("advertencia"):
                        st.warning(r.resumen["advertencia"])
                    st.dataframe(tabla_exp, width="stretch", hide_index=True)


def _render_muestreo_mus() -> None:
    col_sel, col_ev = st.columns(2, gap="medium")

    with col_sel:
        with st.container(border=True):
            st.markdown('<div class="cuadra-section-hdr">1 · Selección estadística MUS</div>', unsafe_allow_html=True)
            st.caption("Sube la población (identificador y saldo en libros) para calcular tamaño, intervalo J y selección.")
            plantilla_pob = "cliente,saldo\nC001,12500.00\nC002,48900.00\nC003,7200.50\n"
            st.download_button("Descargar plantilla de población (CSV)", plantilla_pob, file_name="plantilla_poblacion_mus.csv")

            poblacion = st.file_uploader("Población (CSV o Excel)", type=["csv", "xlsx"], key="poblacion")
            if poblacion:
                ruta = _guardar(poblacion, st.session_state.carpeta)
                df = cargar_dataframe_muestreo(ruta)
                m1, m2 = st.columns(2)
                col_id = m1.selectbox("Identificador", list(df.columns), key="mus_col_id")
                col_valor = m2.selectbox("Valor en libros", list(df.columns), index=min(1, len(df.columns) - 1), key="mus_col_val")
                m3, m4, m5 = st.columns(3)
                tolerable = m3.number_input("Error tolerable", min_value=1.0, value=45000.0, step=1000.0, key="mus_tol")
                confianza = m4.selectbox("Confianza (%)", [95, 90], format_func=lambda x: f"{x} %", key="mus_conf")
                semilla = m5.number_input("Semilla", value=2025, step=1, key="mus_semilla")
                try:
                    seleccion, plan = seleccionar_mus(df, col_id, col_valor, tolerable, int(confianza), semilla=int(semilla))
                    st.session_state.plan_mus = plan
                    k1, k2, k3 = st.columns(3)
                    k1.markdown(_kpi_html("Valor en libros", f"{plan.valor_libros:,.2f}"), unsafe_allow_html=True)
                    k2.markdown(_kpi_html("Tamaño muestra (n)", str(plan.tamano), f"Intervalo {plan.intervalo:,.2f}"), unsafe_allow_html=True)
                    k3.markdown(_kpi_html("Inicio aleatorio", f"{plan.inicio:,.2f}"), unsafe_allow_html=True)
                    st.dataframe(seleccion, width="stretch", hide_index=True)
                except ErrorMuestreo as e:
                    st.error(str(e))

    with col_ev:
        with st.container(border=True):
            st.markdown('<div class="cuadra-section-hdr">2 · Evaluación de muestra MUS</div>', unsafe_allow_html=True)
            st.caption("Sube la hoja con las partidas auditadas y mapea identificador, valor en libros y valor auditado.")
            plantilla_err = "id,valor_libros,valor_auditado\nC001,12500.00,12500.00\nC002,48900.00,46400.00\nC003,7200.50,7200.50\n"
            st.download_button("Descargar plantilla de errores (CSV)", plantilla_err, file_name="plantilla_errores_mus.csv")

            errores = st.file_uploader("Resultados de auditoría (CSV o Excel)", type=["csv", "xlsx"], key="errores")
            plan = st.session_state.get("plan_mus")
            e1, e2, e3 = st.columns(3)
            intervalo = e1.number_input("Intervalo (J)", min_value=1.0, value=float(plan.intervalo) if plan else 15000.0, key="ev_int")
            tolerable_ev = e2.number_input("Error tolerable", min_value=1.0, value=float(plan.error_tolerable) if plan else 45000.0, key="ev_tol")
            confianza_ev = e3.selectbox("Confianza (%)", [95, 90], format_func=lambda x: f"{x} %", key="ev_conf")

            if errores:
                ruta = _guardar(errores, st.session_state.carpeta)
                df_err = cargar_dataframe_muestreo(ruta)
                cols_err = list(df_err.columns)

                def _idx(candidatos: tuple[str, ...], fallback: int) -> int:
                    for i, c in enumerate(cols_err):
                        if normalizar(c) in candidatos:
                            return i
                    return min(fallback, max(len(cols_err) - 1, 0))

                c_id, c_lib, c_aud = st.columns(3)
                col_err_id = c_id.selectbox("Columna ID", cols_err, index=_idx(("id", "cliente", "codigo", "cuenta"), 0), key="ev_col_id")
                col_err_lib = c_lib.selectbox("Valor en libros", cols_err, index=_idx(("valor libros", "saldo", "libros"), 1), key="ev_col_lib")
                col_err_aud = c_aud.selectbox("Valor auditado", cols_err, index=_idx(("valor auditado", "auditado", "real"), 2), key="ev_col_aud")
                try:
                    ev = evaluar_mus(
                        df_err, intervalo, tolerable_ev, int(confianza_ev),
                        col_id=col_err_id, col_libros=col_err_lib, col_auditado=col_err_aud,
                    )
                    supera = ev.limite_superior > tolerable_ev
                    k1, k2, k3 = st.columns(3)
                    k1.markdown(_kpi_html("Error proyectado", f"{ev.error_proyectado:,.2f}"), unsafe_allow_html=True)
                    k2.markdown(_kpi_html("Margen incremental", f"{ev.margen_incremental:,.2f}"), unsafe_allow_html=True)
                    k3.markdown(
                        _kpi_html("Límite superior", f"{ev.limite_superior:,.2f}", "", "cuadra-kpi-alto" if supera else "cuadra-kpi-ok"),
                        unsafe_allow_html=True,
                    )
                    (st.error if supera else st.success)(ev.conclusion)
                    st.dataframe(ev.detalle, width="stretch", hide_index=True)
                except ErrorMuestreo as e:
                    st.error(str(e))


def _render_conectores(perfiles_erp: dict[str, dict]) -> None:
    with st.container(border=True):
        st.markdown('<div class="cuadra-section-hdr">Catálogo de sistemas contables del mercado panameño y formatos soportados</div>', unsafe_allow_html=True)
        st.write(
            "Formatos soportados: **Excel** (`.xlsx`, `.xlsm`, `.xls`), **CSV / TSV / TXT** (incluyendo reportes **SAP ALV `|`** "
            "y codificación **UTF-16 / Windows-1252**), **Parquet**, **JSON / JSONL**, **SQLite**, **DuckDB**, volcados **`.sql`** "
            "y conexiones **SQL de solo lectura** (`SELECT` / `WITH`)."
        )
        tabla_perfiles = pd.DataFrame([
            {
                "Sistema contable / ERP": p["nombre"],
                "Segmento en Panamá": p.get("segmento_panama", ""),
                "Formatos frecuentes": ", ".join(p.get("formatos_frecuentes", [])),
                "Soporte sin línea / usuario": "Sí (explícito en bitácora)" if p.get("generar_linea_si_falta") or p.get("usuario_defecto_si_falta") else "No requiere",
            }
            for p in perfiles_erp.values()
        ])
        st.dataframe(tabla_perfiles, width="stretch", hide_index=True)

    with st.container(border=True):
        st.markdown('<div class="cuadra-section-hdr">Inspector de mapeo y consultas SQL de extracción</div>', unsafe_allow_html=True)
        nombres_cat = {p["nombre"]: pid for pid, p in perfiles_erp.items()}
        elegido_cat = st.selectbox("Sistema contable / ERP", list(nombres_cat), key="cat_erp")
        p_sel = perfiles_erp[nombres_cat[elegido_cat]]
        st.caption(f"{p_sel.get('descripcion', '').strip()} · Motor: {p_sel.get('motor_origen', '')}")

        izq, der = st.columns([1, 1.15], gap="medium")
        with izq:
            df_alias = pd.DataFrame([
                {"Columna estándar": std, "Alias reconocidos en el ERP": ", ".join(aliases)}
                for std, aliases in (p_sel.get("aliases") or {}).items()
            ])
            st.dataframe(df_alias, width="stretch", hide_index=True)
            if p_sel.get("debito_credito_pares"):
                pares_txt = ", ".join(" / ".join(par) for par in p_sel["debito_credito_pares"])
                st.info(f"**Pares Débito / Crédito:** {pares_txt}")
            if p_sel.get("indicador_dc"):
                ind_cfg = p_sel["indicador_dc"]
                st.info(
                    f"**Indicador Debe / Haber:** {', '.join(ind_cfg.get('columnas', []))} "
                    f"(créditos: {', '.join(ind_cfg.get('valores_credito', []))})"
                )
        with der:
            consultas = p_sel.get("consultas_sql") or []
            if consultas:
                for q in consultas:
                    st.markdown(f"**{q['titulo']}**")
                    st.code(q["sql"].strip(), language="sql")
            else:
                st.info("Este sistema se audita habitualmente mediante exportación tabular (CSV o Excel) desde sus reportes de Diario o Mayor General.")


def _render_copiloto() -> None:
    with st.container(border=True):
        st.markdown(
            '<div class="cuadra-section-hdr">Copiloto SQL 100 % sin internet · La herramienta propone, DuckDB calcula y tú apruebas</div>',
            unsafe_allow_html=True,
        )
        fuentes_disp: dict[str, Path] = {}
        for k, v in st.session_state.archivos_subidos.items():
            if v and Path(v["ruta"]).exists():
                tabla_nom = k.rsplit("_", 1)[-1]
                fuentes_disp[tabla_nom] = Path(v["ruta"])
        if not fuentes_disp:
            mayor_s, balanza_s = generar_diario_asientos(st.session_state.carpeta / "demo_copiloto")
            fuentes_disp = {"mayor": mayor_s, "balanza": balanza_s}
            st.caption("Usando diario y balanza sintéticos de demostración (si cargas archivos en un paquete, el copiloto los consultará automáticamente).")
        else:
            st.caption("Tablas activas en sesión: " + ", ".join(f"**{t}** (`{p.name}`)" for t, p in fuentes_disp.items()))

        st.markdown("**Consultas frecuentes:**")
        b_cols = st.columns(len(CONSULTAS_SUGERIDAS))
        for idx, (etq, preg) in enumerate(CONSULTAS_SUGERIDAS):
            if b_cols[idx].button(etq, key=f"sug_cop_{idx}", use_container_width=True):
                st.session_state["cop_pregunta"] = preg
                prop_sug = proponer_consulta_sql(preg, {t: [] for t in fuentes_disp}, st.session_state.encargo_datos)
                st.session_state["cop_prop"] = prop_sug
                st.session_state["cop_sql"] = prop_sug.sql

        pregunta = st.text_input(
            "Pregunta en español",
            key="cop_pregunta",
            placeholder="Ej.: asientos mayores a 25,000 en noviembre  o  resumen por usuario",
        )
        if st.button("1 · Proponer consulta SQL visible", key="cop_btn_prop"):
            try:
                prop = proponer_consulta_sql(pregunta, {t: [] for t in fuentes_disp}, st.session_state.encargo_datos)
                st.session_state["cop_prop"] = prop
                st.session_state["cop_sql"] = prop.sql
            except ValueError as e:
                st.warning(str(e))

        sql_edit = st.text_area(
            "SQL SELECT propuesto (revisable y editable antes de ejecutar)",
            key="cop_sql",
            height=130,
        )
        prop_act = st.session_state.get("cop_prop")
        if prop_act:
            st.info(f"**{prop_act.titulo}** ({', '.join(prop_act.nia)}): {prop_act.explicacion}")

        if st.button("2 · Aprobar y ejecutar en motor DuckDB", type="primary", disabled=not bool(sql_edit.strip()), key="cop_btn_exec"):
            try:
                con, _ = preparar_conexion_copiloto(fuentes_disp)
                try:
                    ultima = st.session_state.get("ultima_corrida")
                    res = ejecutar_propuesta_aprobada(
                        con,
                        sql_edit,
                        pregunta=pregunta,
                        titulo=prop_act.titulo if prop_act else "Consulta ad-hoc aprobada",
                        nia=prop_act.nia if prop_act else ["NIA 500", "NIA 230"],
                        explicacion=prop_act.explicacion if prop_act else "",
                        bitacora=ultima.bitacora if ultima else None,
                        encargo=st.session_state.encargo_datos,
                    )
                    st.session_state["cop_res"] = res
                finally:
                    con.close()
            except Exception as e:  # noqa: BLE001
                st.error(str(e))

        res_act = st.session_state.get("cop_res")
        if res_act:
            c1, c2 = st.columns([1.3, 1], gap="medium")
            with c1:
                st.markdown(f"**Resultado determinista ({len(res_act.tabla):,} filas · SHA-256 `{res_act.sql_sha256[:12]}…`)**")
                st.dataframe(_formatear_fechas_df(res_act.tabla), width="stretch", hide_index=True)
            with c2:
                st.markdown("**Borrador de papel de trabajo (NIA)**")
                st.text_area("Borrador", value=res_act.borrador, height=280, key="cop_borr_txt", label_visibility="collapsed")


def _render_bitacora_y_cedula() -> None:
    corrida = st.session_state.get("ultima_corrida")
    if corrida is None:
        with st.container(border=True):
            st.markdown('<div class="cuadra-section-hdr">Bitácora de auditoría y cédula</div>', unsafe_allow_html=True)
            st.info(
                "Aún no has ejecutado un análisis en esta sesión. Selecciona **Asientos NIA 240**, **Excepciones básicas** "
                "o **Factura DGI** en la barra superior para importar datos, generar la cédula y auditar la bitácora SHA-256."
            )
        return

    integra = corrida.bitacora.verificar()
    registros = corrida.bitacora.leer()
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(_kpi_html("Último paquete", corrida.manifiesto["id"], f"v{corrida.manifiesto['version']}"), unsafe_allow_html=True)
    k2.markdown(_kpi_html("Fuentes importadas", str(len(corrida.controles))), unsafe_allow_html=True)
    k3.markdown(_kpi_html("Eventos en bitácora", str(len(registros))), unsafe_allow_html=True)
    k4.markdown(
        _kpi_html("Integridad SHA-256", "ÍNTEGRA" if integra else "ALTERADA", "", "cuadra-kpi-ok" if integra else "cuadra-kpi-alto"),
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        c_hdr, c_btn = st.columns([3, 1])
        c_hdr.markdown('<div class="cuadra-section-hdr">Control de archivos importados</div>', unsafe_allow_html=True)
        c_btn.download_button(
            "Descargar cédula en Excel",
            corrida.cedula.read_bytes(),
            file_name=f"cedula_{corrida.manifiesto['id']}.xlsx",
            use_container_width=True,
            key="dl_cedula_bitacora",
        )
        df_ctrl = pd.DataFrame([
            {
                "Archivo": c["archivo"],
                "Tabla": c["tabla"],
                "Filas": c["filas"],
                "Excluidas": c.get("filas_excluidas", 0),
                "Codificación": c.get("codificacion", "Excel"),
                "Formato fecha": c.get("formato_fecha", ""),
                "SHA-256": c["sha256"],
                "Transformaciones": " | ".join(c.get("transformaciones", [])) or "Ninguna",
            }
            for c in corrida.controles
        ])
        st.dataframe(df_ctrl, width="stretch", hide_index=True)

    with st.container(border=True):
        st.markdown('<div class="cuadra-section-hdr">Registro encadenado de bitácora</div>', unsafe_allow_html=True)
        df_reg = pd.DataFrame([
            {
                "Fecha y hora (UTC)": r["fecha_hora_utc"],
                "Usuario": r["usuario"],
                "Evento": r["evento"],
                "Detalle": r["datos"].get("prueba") or r["datos"].get("archivo") or r["datos"].get("tabla") or "",
                "Hash": r["hash"],
            }
            for r in registros
        ])
        st.dataframe(df_reg, width="stretch", hide_index=True)


def _render_login_web(gestor: GestorUsuarios) -> bool:
    """Muestra la pantalla de inicio de sesión web si la seguridad local está configurada."""
    if (
        not gestor.existe_configuracion()
        or st.session_state.get("sesion_web") is not None
        or os.environ.get("FOLIO_OMITIR_LOGIN_WEB") == "1"
    ):
        return True

    st.markdown(
        "\n".join([
            '<div class="cuadra-appbar">',
            '  <div class="cuadra-brand">',
            f'    <div>{LOGO_SVG}</div>',
            '    <div>',
            f'      <div class="cuadra-brand-eyebrow">{html.escape(NOMBRE_MARCA)} · ACCESO SEGURO</div>',
            f'      <div class="cuadra-brand-title">{html.escape(LEMA_MARCA)}</div>',
            '    </div>',
            '  </div>',
            '  <div class="cuadra-status-group"><span class="cuadra-pill">100 % SIN INTERNET</span></div>',
            '</div>',
        ]),
        unsafe_allow_html=True,
    )
    _, col_centro, _ = st.columns([1, 1.4, 1])
    with col_centro:
        with st.container(border=True):
            st.markdown("### Iniciar sesión en Folio Auditor")
            modo_lbl = st.radio(
                "Modo de acceso",
                ["Preparador / Auditor", "Administrador"],
                horizontal=True,
                key="login_web_modo",
            )
            modo_req = PERFIL_ADMIN if modo_lbl == "Administrador" else PERFIL_PREPARADOR
            if modo_req == PERFIL_ADMIN:
                st.info("Modo Administrador: gestión de usuarios, roles NIA 220, políticas de seguridad y bitácora de accesos.")
            else:
                st.info("Modo Preparador / Auditor: ejecución de paquetes NIA, muestreo, copiloto SQL y revisión/firma por rol.")
            usr_in = st.text_input("Usuario", key="login_web_usr")
            pwd_in = st.text_input("Contraseña", type="password", key="login_web_pwd")
            if st.button("Iniciar sesión", type="primary", use_container_width=True, key="login_web_btn"):
                try:
                    sesion = gestor.autenticar(usr_in, pwd_in, modo_acceso=modo_req)
                    st.session_state.sesion_web = sesion
                    st.session_state.auditor = sesion.nombre_completo
                    st.session_state.rol = sesion.rol_auditoria or sesion.perfil
                    st.rerun()
                except ErrorSeguridad as exc:
                    st.error(str(exc))
    st.stop()
    return False


def _render_portafolio_y_roles() -> None:
    gestor = GestorUsuarios(RAIZ)
    sesion_web: SesionAutenticada | None = st.session_state.get("sesion_web")
    politicas = gestor.politicas()
    izq, der = st.columns([1, 1.35], gap="medium")
    with izq:
        with st.container(border=True):
            st.markdown('<div class="cuadra-section-hdr">1 · Sesión de auditor y roles (NIA 220)</div>', unsafe_allow_html=True)
            if sesion_web is not None:
                st.success(f"Sesión autenticada: {sesion_web.etiqueta_ui} · Llave Ed25519 {sesion_web.huella_clave[:12]}…")
                auditor = sesion_web.nombre_completo
                rol = sesion_web.rol_auditoria or sesion_web.perfil
                st.session_state.auditor = auditor
                st.session_state.rol = rol
                if st.button("Cerrar sesión", key="pf_btn_logout"):
                    st.session_state.sesion_web = None
                    st.rerun()
                if sesion_web.es_admin:
                    with st.expander("Administración de Usuarios y Políticas de Seguridad"):
                        df_u = pd.DataFrame([
                            {
                                "Usuario": u["usuario"],
                                "Nombre": u["nombre_completo"],
                                "Perfil": u["perfil"],
                                "Activo": "Sí" if u["activo"] else "No",
                                "Huella Ed25519": u["huella_clave"][:14] + "…",
                            }
                            for u in gestor.listar_usuarios()
                        ])
                        st.dataframe(df_u, width="stretch", hide_index=True)
                        nu1, nu2 = st.columns(2)
                        n_usr = nu1.text_input("Nuevo usuario", key="adm_web_usr")
                        n_nom = nu2.text_input("Nombre completo", key="adm_web_nom")
                        nu3, nu4 = st.columns(2)
                        n_perf = nu3.selectbox("Perfil", list(PERFILES_VALIDOS), index=1, key="adm_web_perf")
                        n_pwd = nu4.text_input("Contraseña inicial", type="password", key="adm_web_pwd")
                        if st.button("Crear usuario", key="adm_web_crear"):
                            try:
                                gestor.crear_usuario(sesion_web, n_usr, n_nom, n_pwd, n_perf)
                                st.success(f"Usuario '{n_usr}' creado.")
                                st.rerun()
                            except ErrorSeguridad as exc:
                                st.error(str(exc))
                        seg_chk = st.checkbox("Segregación estricta Preparador ≠ Revisor ≠ Socio", value=bool(politicas.get("segregacion_estricta", True)), key="adm_web_seg")
                        if st.button("Guardar políticas", key="adm_web_pol"):
                            try:
                                gestor.actualizar_politicas(sesion_web, segregacion_estricta=seg_chk)
                                st.success("Políticas actualizadas.")
                            except ErrorSeguridad as exc:
                                st.error(str(exc))
            else:
                a1, a2 = st.columns(2)
                auditor = a1.text_input("Auditor activo", value=st.session_state.auditor, key="pf_auditor")
                rol = a2.selectbox(
                    "Rol de firma",
                    list(ROLES_FIRMA),
                    index=ROLES_FIRMA.index(st.session_state.rol) if st.session_state.rol in ROLES_FIRMA else 0,
                    key="pf_rol",
                )
                st.session_state.auditor = auditor
                st.session_state.rol = rol
                if not gestor.existe_configuracion():
                    with st.expander("Activar control de acceso (Crear Administrador y Preparador)"):
                        c1, c2 = st.columns(2)
                        adm_u = c1.text_input("Usuario Administrador", value="admin", key="init_w_au")
                        adm_n = c2.text_input("Nombre Administrador", value="Administrador de Calidad", key="init_w_an")
                        adm_p = st.text_input("Contraseña Administrador (min. 10 chars, May/Min/Núm)", type="password", key="init_w_ap")
                        prp_u = c1.text_input("Usuario Preparador", value="preparador", key="init_w_pu")
                        prp_n = c2.text_input("Nombre Preparador", value="Auditor Preparador", key="init_w_pn")
                        prp_p = st.text_input("Contraseña Preparador", type="password", key="init_w_pp")
                        if st.button("Inicializar cuentas seguras", key="init_w_btn"):
                            try:
                                prep = {"usuario": prp_u, "nombre_completo": prp_n, "contrasena": prp_p} if prp_u.strip() else None
                                gestor.inicializar_firma(adm_u, adm_n, adm_p, preparador=prep, segregacion_estricta=True)
                                st.session_state.sesion_web = gestor.autenticar(adm_u, adm_p, modo_acceso=PERFIL_ADMIN)
                                st.success("Control de acceso activado.")
                                st.rerun()
                            except ErrorSeguridad as exc:
                                st.error(str(exc))

        with st.container(border=True):
            st.markdown('<div class="cuadra-section-hdr">2 · Portafolio de encargos (encargos/*.yaml)</div>', unsafe_allow_html=True)
            encargos = listar_encargos()
            if encargos:
                df_enc = pd.DataFrame([
                    {
                        "Archivo": e["archivo"],
                        "Cliente": e["cliente"],
                        "Cierre": e["fecha_cierre"],
                        "Marco": e["marco"],
                        "Materialidad": e["materialidad"],
                    }
                    for e in encargos
                ])
                st.dataframe(df_enc, width="stretch", hide_index=True)
                sel_e = st.selectbox("Encargo a cargar", [e["archivo"] for e in encargos], key="pf_sel_enc")
                if st.button("Cargar encargo en sesión", key="pf_btn_cargar"):
                    elegido = next(e for e in encargos if e["archivo"] == sel_e)["datos"]
                    fc_raw = str(elegido.get("fecha_cierre") or "2025-12-31")[:10]
                    try:
                        fc_dt = date.fromisoformat(fc_raw)
                    except ValueError:
                        fc_dt = date(2025, 12, 31)
                    pi_raw = str(elegido.get("periodo_inicio") or "")[:10]
                    try:
                        pi_dt = date.fromisoformat(pi_raw) if pi_raw else calcular_periodo_inicio(fc_dt)
                    except ValueError:
                        pi_dt = calcular_periodo_inicio(fc_dt)
                    st.session_state.encargo_datos.update({
                        "cliente": str(elegido.get("cliente") or "Cliente Demo, S.A."),
                        "periodo_inicio": pi_dt,
                        "fecha_cierre": fc_dt,
                        "marco": str(elegido.get("marco") or "NIIF"),
                        "materialidad": float(elegido.get("materialidad") or 150000.0),
                        "materialidad_ejecucion": float(elegido.get("materialidad_ejecucion") or 112500.0),
                        "umbral_trivial": float(elegido.get("umbral_trivial") or 7500.0),
                        "umbral_aprobacion": float(elegido.get("umbral_aprobacion") or 10000.0),
                    })
                    st.success(f"Encargo `{sel_e}` cargado en sesión.")
                    st.rerun()

            nombre_yaml = st.text_input("Guardar encargo actual como (.yaml)", value="mi-encargo", key="pf_nom_yaml")
            if st.button("Guardar encargo actual como YAML", key="pf_btn_guardar"):
                ruta_g = guardar_encargo_yaml(st.session_state.encargo_datos, nombre_yaml)
                st.success(f"Guardado en `{ruta_g.name}`.")

        with st.container(border=True):
            st.markdown('<div class="cuadra-section-hdr">3 · Historial de corridas (salidas/)</div>', unsafe_allow_html=True)
            hist = listar_corridas_recientes()
            if hist:
                df_h = pd.DataFrame([
                    {
                        "Corrida": h["nombre"],
                        "Paquete": h["paquete"],
                        "Cliente": h["cliente"],
                        "Firmas": h["estado_firmas"],
                        "SHA-256": "ÍNTEGRO" if h["sha256_integro"] else "ALTERADO",
                    }
                    for h in hist
                ])
                st.dataframe(df_h, width="stretch", hide_index=True)

    with der:
        with st.container(border=True):
            st.markdown('<div class="cuadra-section-hdr">4 · Revisión por prueba y firma de papel de trabajo</div>', unsafe_allow_html=True)
            ultima = st.session_state.get("ultima_corrida")
            hist = listar_corridas_recientes()
            opciones_c = []
            if ultima:
                opciones_c.append(f"Activa: {ultima.carpeta.name} ({ultima.manifiesto['id']})")
            for h in hist:
                etq = f"{h['nombre']} ({h['paquete']})"
                if not ultima or h["carpeta"] != ultima.carpeta:
                    opciones_c.append(etq)

            if not opciones_c:
                st.info("Ejecuta un paquete o genera una corrida para revisar hallazgos y estampar firmas por rol.")
                return

            sel_c = st.selectbox("Corrida a revisar", opciones_c, key="pf_sel_corrida")
            if sel_c.startswith("Activa:") and ultima:
                carpeta_c = ultima.carpeta
                corrida_obj = ultima
            else:
                nombre_dir = sel_c.split(" (", 1)[0]
                carpeta_c = next(h["carpeta"] for h in hist if h["nombre"] == nombre_dir)
                corrida_obj = ultima if (ultima and ultima.carpeta == carpeta_c) else None

            info = resumen_corrida_carpeta(carpeta_c)
            if not info:
                st.warning("No se pudo leer la bitácora de esta corrida.")
                return

            pruebas_exec = info["pruebas_ejecutadas"]
            ids_p = [p["id"] for p in pruebas_exec if p["id"]]
            rev = cargar_revisiones(carpeta_c, ids_p)
            firmas = rev.get("firmas", {})
            bloqueado = bool(rev.get("bloqueado"))

            k_cols = st.columns(4)
            for idx, r_rol in enumerate(ROLES_FIRMA):
                f = firmas.get(r_rol)
                k_cols[idx].markdown(
                    _kpi_html(r_rol, f["auditor"] if f else "Pendiente", f["fecha_utc"] if f else "Sin firma", "cuadra-kpi-ok" if f else ""),
                    unsafe_allow_html=True,
                )
            k_cols[3].markdown(
                _kpi_html("Estado papel", "CERRADO" if bloqueado else "ABIERTO", "Bloqueado por Socio" if bloqueado else "Editable", "cuadra-kpi-ok" if bloqueado else "cuadra-kpi-bajo"),
                unsafe_allow_html=True,
            )

            df_rev = pd.DataFrame([
                {
                    "Prueba": p["id"],
                    "Hallazgos": p["filas"],
                    "Estado": rev["por_prueba"].get(p["id"], {}).get("estado", "Pendiente"),
                    "Auditor": rev["por_prueba"].get(p["id"], {}).get("auditor", ""),
                    "Conclusión": rev["por_prueba"].get(p["id"], {}).get("conclusion", ""),
                }
                for p in pruebas_exec
            ])
            st.dataframe(df_rev, width="stretch", hide_index=True)

            if ids_p and not bloqueado:
                p_sel = st.selectbox("Prueba a revisar", ids_p, key="pf_prueba_ed")
                act = rev["por_prueba"].get(p_sel, {})
                est_sel = st.selectbox(
                    "Estado de revisión",
                    list(ESTADOS_REVISION),
                    index=ESTADOS_REVISION.index(act.get("estado")) if act.get("estado") in ESTADOS_REVISION else 0,
                    key="pf_est_ed",
                )
                conc_txt = st.text_area("Conclusión del auditor", value=act.get("conclusion", ""), key="pf_conc_ed")
                b1, b2, b3 = st.columns(3)
                bit = Bitacora(carpeta_c / "bitacora.jsonl", usuario=auditor)
                if b1.button("Guardar conclusión", key="pf_btn_save_rev", use_container_width=True):
                    try:
                        registrar_revision_prueba(carpeta_c, p_sel, est_sel, conc_txt, auditor, rol, bitacora=bit)
                        if corrida_obj:
                            actualizar_cedula_corrida(corrida_obj)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                if b2.button("Aclarar sin hallazgos", key="pf_btn_clear_zero", use_container_width=True):
                    for p in pruebas_exec:
                        if int(p["filas"]) == 0:
                            registrar_revision_prueba(
                                carpeta_c, p["id"], "Aclarado con evidencia", "Sin excepciones deterministas.", auditor, rol, bitacora=bit
                            )
                    if corrida_obj:
                        actualizar_cedula_corrida(corrida_obj)
                    st.rerun()
                if b3.button(f"Firmar como {rol}", type="primary", key="pf_btn_firmar", use_container_width=True):
                    try:
                        exigir_seg = bool(politicas.get("segregacion_estricta", True)) if sesion_web is not None else False
                        ventana_dias = int(politicas.get("ventana_archivo_dias", 60))
                        firmar_papel_trabajo(
                            carpeta_c,
                            rol,
                            auditor,
                            bitacora=bit,
                            pruebas_ejecutadas=ids_p,
                            exigir_segregacion=exigir_seg,
                            sesion=sesion_web,
                            ventana_archivo_dias=ventana_dias,
                        )
                        if corrida_obj:
                            actualizar_cedula_corrida(corrida_obj)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            elif bloqueado:
                if (carpeta_c / "sello.json").exists():
                    sello_res = verificar_sello_corrida(carpeta_c)
                    if sello_res.get("valido"):
                        st.success(f"Sello Ed25519 verificado ({sello_res.get('huella_clave', '')[:12]}…).")
                    else:
                        st.error(f"Sello criptográfico inválido: {sello_res.get('motivo')}")
                motivo_r = st.text_input("Motivo para reabrir el papel cerrado", key="pf_motivo_reab")
                if st.button("Reabrir papel (registra en bitácora)", key="pf_btn_reab"):
                    try:
                        reabrir_papel_trabajo(
                            carpeta_c,
                            motivo_r,
                            auditor,
                            rol=rol,
                            bitacora=Bitacora(carpeta_c / "bitacora.jsonl", usuario=auditor),
                            sesion=sesion_web,
                        )
                        if corrida_obj:
                            actualizar_cedula_corrida(corrida_obj)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

            if info["cedula_existe"]:
                st.download_button(
                    "Descargar cédula actualizada (Excel)",
                    info["cedula"].read_bytes(),
                    file_name=f"cedula_{info['paquete']}_{info['nombre']}.xlsx",
                    use_container_width=True,
                    key="pf_dl_excel",
                )


# --- Arranque ---------------------------------------------------------------------------
_inyectar_estilos()
_inicializar_estado()
_gestor_web = GestorUsuarios(RAIZ)
_render_login_web(_gestor_web)
_render_barra_superior()
if _gestor_web.politicas().get("alerta_nube", True):
    _info_nube = detectar_carpeta_sincronizada(RAIZ)
    if _info_nube.get("en_nube"):
        st.caption(f"Aviso de privacidad (Ley 81): carpeta de trabajo en {_info_nube['proveedor']}. Se recomienda ubicación local sin sincronización automática.")

perfiles_erp = perfiles_disponibles()
herramienta_actual = st.session_state.herramienta

if herramienta_actual in ("asientos-nia240", "excepciones-basicas", "ventas-fe", "bancos-conciliacion"):
    _render_vista_paquete(herramienta_actual, perfiles_erp)
elif herramienta_actual == "muestreo-mus":
    _render_muestreo_mus()
elif herramienta_actual == "conectores":
    _render_conectores(perfiles_erp)
elif herramienta_actual == "copiloto":
    _render_copiloto()
elif herramienta_actual == "bitacora":
    _render_bitacora_y_cedula()
elif herramienta_actual == "encargos":
    _render_portafolio_y_roles()
