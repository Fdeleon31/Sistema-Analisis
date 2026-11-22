"""Ejecuta un paquete de pruebas descrito por su manifiesto.yaml."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from .bitacora import Bitacora
from .estadistica import analizar_benford
from .importador import validar_identificador
from .muestreo import muestra_aleatoria

PARAMETRO = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
POSPROCESOS = {
    "benford", "criterios", "puntaje", "seleccion", "aleatoria",
    "informativo", "conciliacion", "conciliacion_1a1",
}
CRITERIOS_ASIENTO = [
    "fin_semana_feriado", "posterior_cierre", "cerca_cierre", "monto_redondo", "bajo_umbral",
    "descripcion_sospechosa", "usuario_poco_frecuente", "cuenta_poco_usada", "descuadrado", "sobre_materialidad",
]
NOMBRES_CRITERIOS = {
    "fin_semana_feriado": "Fin de semana o feriado",
    "posterior_cierre": "Posterior al cierre",
    "cerca_cierre": "Cerca del cierre",
    "monto_redondo": "Monto redondo",
    "bajo_umbral": "Justo bajo el umbral de aprobación",
    "descripcion_sospechosa": "Descripción vacía o genérica",
    "usuario_poco_frecuente": "Usuario poco frecuente",
    "cuenta_poco_usada": "Cuenta poco usada",
    "descuadrado": "Asiento descuadrado",
    "sobre_materialidad": "Sobre materialidad de ejecución",
}


@dataclass
class ResultadoPrueba:
    id: str
    nombre: str
    ficha: str
    nia: list[str]
    tabla: pd.DataFrame
    resumen: dict = field(default_factory=dict)
    sql_sha256: str = ""
    omitida: str | None = None

    @property
    def excepciones(self) -> int:
        if "excepciones" in self.resumen:
            return int(self.resumen["excepciones"])
        return len(self.tabla)


def cargar_manifiesto(carpeta: str | Path) -> dict:
    carpeta = Path(carpeta)
    with (carpeta / "manifiesto.yaml").open(encoding="utf-8") as f:
        manifiesto = yaml.safe_load(f)
    manifiesto["_carpeta"] = carpeta
    return manifiesto


def cargar_encargo(ruta: str | Path | None) -> dict:
    if not ruta:
        return {}
    with Path(ruta).open(encoding="utf-8") as f:
        encargo = yaml.safe_load(f) or {}
    encargo["_carpeta"] = Path(ruta).resolve().parent
    return encargo


def resolver_parametros(parametros: dict, encargo: dict) -> dict:
    """Un valor "encargo.x" toma el valor x del archivo del encargo; "encargo.x|y" usa y si x falta."""
    salida = {}
    for clave, valor in parametros.items():
        if isinstance(valor, str) and valor.startswith("encargo."):
            nombre, _, defecto = valor[len("encargo."):].partition("|")
            if nombre in encargo and encargo[nombre] is not None:
                valor = encargo[nombre]
            elif defecto != "":
                valor = yaml.safe_load(defecto)
            elif not encargo:
                raise ValueError("Este paquete necesita un archivo de encargo con materialidad y fecha de cierre. "
                                 "Pásalo con --encargo (hay un ejemplo en encargos/ejemplo-2025.yaml).")
            else:
                raise ValueError(f"Falta {nombre!r} en el archivo del encargo (lo usa el parámetro {clave!r}).")
        if isinstance(valor, date):
            valor = valor.isoformat()
        salida[clave] = valor
    return salida


def _identificadores(valores: dict) -> dict[str, str]:
    salida = {}
    for clave, valor in valores.items():
        nombres = valor if isinstance(valor, list) else [valor]
        salida[clave] = ", ".join(f'"{validar_identificador(n)}"' for n in nombres)
    return salida


def _numero_compacto(valor: float) -> int | float:
    return int(valor) if float(valor).is_integer() else round(float(valor), 2)


def _aplicar_posproceso_puntaje(tabla: pd.DataFrame, parametros: dict) -> tuple[pd.DataFrame, dict]:
    """Calcula el puntaje de riesgo explicable por asiento (Ficha 11)."""
    pesos_encargo = parametros.get("pesos_encargo") or {}
    if not isinstance(pesos_encargo, dict):
        raise ValueError("pesos_riesgo debe ser un diccionario {criterio: peso}.")
    pesos_brutos = {**parametros["pesos"], **pesos_encargo}

    invalidos = [k for k in pesos_brutos if k not in CRITERIOS_ASIENTO]
    if invalidos:
        raise ValueError(
            f"Criterio(s) de riesgo inválido(s): {', '.join(invalidos)}. "
            f"Válidos: {', '.join(CRITERIOS_ASIENTO)}"
        )
    for k, v in pesos_brutos.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or float(v) < 0:
            raise ValueError(f"El peso del criterio {k!r} debe ser un número mayor o igual a 0 (recibido: {v!r}).")

    alto = float(parametros["nivel_alto"])
    medio = float(parametros["nivel_medio"])
    if medio < 0 or alto < 0 or medio > alto:
        raise ValueError(
            f"Umbrales de riesgo inválidos: nivel_riesgo_medio ({medio}) no puede superar a nivel_riesgo_alto ({alto})."
        )

    todos_enteros = all(float(v).is_integer() for v in pesos_brutos.values())
    pesos = {k: (int(v) if todos_enteros else round(float(v), 2)) for k, v in pesos_brutos.items()}

    presentes = [c for c in CRITERIOS_ASIENTO if c in tabla.columns]
    asientos_analizados = len(tabla)

    salida = tabla.copy()
    puntaje_serie = pd.Series(0.0, index=salida.index)
    for c in presentes:
        puntaje_serie = puntaje_serie + salida[c].astype(bool).astype(int) * float(pesos.get(c, 0))
    puntaje_serie = puntaje_serie.round(2)
    salida["puntaje"] = puntaje_serie.astype(int) if todos_enteros else puntaje_serie

    def _nivel(p: float) -> str:
        if p >= alto:
            return "alto"
        if p >= medio:
            return "medio"
        if p > 0:
            return "bajo"
        return ""

    def _explicar(fila: pd.Series) -> str:
        marcados = [c for c in presentes if bool(fila[c])]
        ordenados = sorted(marcados, key=lambda c: -float(pesos.get(c, 0)))
        partes = []
        for c in ordenados:
            w = pesos.get(c, 0)
            w_txt = str(int(w)) if float(w).is_integer() else f"{float(w):g}"
            partes.append(f"{NOMBRES_CRITERIOS.get(c, c)} (+{w_txt})")
        return "; ".join(partes)

    salida["nivel"] = salida["puntaje"].map(_nivel)
    salida = salida[salida["puntaje"] > 0].copy()
    salida["explicacion"] = [_explicar(fila) for _, fila in salida.iterrows()]
    salida = salida.sort_values(by=["puntaje", "total_debito", "asiento"], ascending=[False, False, True]).reset_index(drop=True)

    prioridad = ["asiento", "fecha", "usuario", "descripcion", "total_debito", "puntaje", "nivel", "explicacion"]
    columnas = [c for c in prioridad if c in salida.columns] + [c for c in salida.columns if c not in prioridad]
    salida = salida[columnas]

    por_nivel = {
        "alto": int((salida["nivel"] == "alto").sum()),
        "medio": int((salida["nivel"] == "medio").sum()),
        "bajo": int((salida["nivel"] == "bajo").sum()),
    }
    puntaje_maximo = sum(pesos.values()) if todos_enteros else round(sum(float(v) for v in pesos.values()), 2)
    resumen = {
        "excepciones": len(salida),
        "por_nivel": por_nivel,
        "pesos": pesos,
        "puntaje_maximo": puntaje_maximo,
        "umbrales": {"alto": _numero_compacto(alto), "medio": _numero_compacto(medio)},
        "asientos_analizados": asientos_analizados,
    }
    return salida, resumen


def _aplicar_posproceso_conciliacion_1a1(tabla: pd.DataFrame, parametros: dict) -> tuple[pd.DataFrame, dict]:
    """Emparejamiento determinista 1 a 1 por monto y proximidad temporal (Ficha 13)."""
    ventana = int(parametros.get("ventana_dias", 5))
    devolver = str(parametros.get("devolver", "origen"))
    if tabla.empty:
        return tabla.drop(columns=["_lado"], errors="ignore"), {"excepciones": 0, "emparejados": 0, "ventana_dias": ventana}

    origen = tabla[tabla["_lado"] == "origen"].reset_index(drop=True)
    contra = tabla[tabla["_lado"] == "contraparte"].reset_index(drop=True)
    fechas_o = pd.to_datetime(origen["fecha"]).dt.date
    fechas_c = pd.to_datetime(contra["fecha"]).dt.date
    montos_o = pd.to_numeric(origen["monto"]).round(2)
    montos_c = pd.to_numeric(contra["monto"]).round(2)

    candidatos: list[tuple[int, int, int, int]] = []
    por_monto_c: dict[float, list[int]] = {}
    for j, m_c in enumerate(montos_c):
        por_monto_c.setdefault(float(m_c), []).append(j)

    for i, m_o in enumerate(montos_o):
        f_o = fechas_o.iloc[i]
        ref_o = str(origen["referencia"].iloc[i] or "").strip().upper()
        for j in por_monto_c.get(float(m_o), []):
            diff = abs((f_o - fechas_c.iloc[j]).days)
            if diff <= ventana:
                desc_c = str(contra["descripcion"].iloc[j] or "").upper()
                penal_ref = 0 if (ref_o and ref_o in desc_c) else 1
                candidatos.append((diff, penal_ref, i, j))

    candidatos.sort()
    usados_o: set[int] = set()
    usados_c: set[int] = set()
    for _, _, i, j in candidatos:
        if i not in usados_o and j not in usados_c:
            usados_o.add(i)
            usados_c.add(j)

    if devolver == "contraparte":
        libres = contra.loc[~contra.index.isin(usados_c)].copy()
        cols = [c for c in ["asiento", "linea", "fecha", "cuenta", "descripcion", "monto"] if c in libres.columns]
    else:
        libres = origen.loc[~origen.index.isin(usados_o)].copy()
        cols = [c for c in ["archivo", "banco", "cuenta_bancaria", "linea", "fecha", "referencia", "descripcion", "monto"] if c in libres.columns]

    salida = libres[cols].sort_values(by=[c for c in ("fecha", "linea") if c in cols]).reset_index(drop=True)
    resumen = {
        "excepciones": len(salida),
        "emparejados": len(usados_o),
        "ventana_dias": ventana,
        "monto_no_conciliado": round(float(salida["monto"].sum()), 2) if not salida.empty else 0.0,
    }
    return salida, resumen


def _tablas_existentes(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def correr_prueba(
    con: duckdb.DuckDBPyConnection,
    carpeta: Path,
    prueba: dict,
    bitacora: Bitacora | None = None,
    encargo: dict | None = None,
) -> ResultadoPrueba:
    faltan_tablas = [t for t in prueba.get("requiere", []) if t not in _tablas_existentes(con)]
    if faltan_tablas:
        motivo = f"Omitida: falta el archivo {', '.join(faltan_tablas)}"
        return ResultadoPrueba(prueba["id"], prueba["nombre"], str(prueba.get("ficha", "")), prueba.get("nia", []),
                               pd.DataFrame(), {"excepciones": 0}, omitida=motivo)

    parametros_prueba = resolver_parametros(prueba.get("parametros", {}), encargo or {})
    plantilla = (carpeta / prueba["sql"]).read_text(encoding="utf-8")
    sql = plantilla.format(**_identificadores(prueba.get("identificadores", {})))
    usados = set(PARAMETRO.findall(sql))
    parametros = {k: v for k, v in parametros_prueba.items() if k in usados}
    faltan = usados - parametros.keys()
    if faltan:
        raise ValueError(f"Prueba {prueba['id']}: faltan parámetros {sorted(faltan)}")

    tabla = con.execute(sql, parametros).df()
    resumen: dict = {}

    posproceso = prueba.get("posproceso")
    if posproceso == "benford":
        tabla, resumen = analizar_benford(tabla, int(parametros_prueba["digitos"]))
        resumen["excepciones"] = len(resumen["digitos_significativos"])
        n_minimo = int(parametros_prueba.get("n_minimo", 0))
        if resumen["n"] < n_minimo:
            resumen["advertencia"] = (
                f"Muestra pequeña: {resumen['n']} montos, menos que el mínimo configurado de {n_minimo}. "
                "La conformidad es poco confiable; úsala solo como indicio."
            )
    elif posproceso == "criterios":
        presentes = [c for c in CRITERIOS_ASIENTO if c in tabla.columns]
        resumen["por_criterio"] = {c: int(tabla[c].sum()) for c in presentes}
        resumen["asientos_analizados"] = len(tabla)
        tabla = tabla[tabla["criterios"] > 0].reset_index(drop=True)
        resumen["excepciones"] = len(tabla)
    elif posproceso == "puntaje":
        tabla, resumen = _aplicar_posproceso_puntaje(tabla, parametros_prueba)
    elif posproceso == "seleccion":
        minimo = int(parametros_prueba.get("minimo_criterios", 2))
        regla = (tabla["criterios"] >= minimo) | tabla["descuadrado"] | tabla["sobre_materialidad"]
        tabla = tabla[regla].reset_index(drop=True)
        resumen["excepciones"] = len(tabla)
        resumen["regla"] = f"{minimo} o más criterios, descuadrados o sobre materialidad de ejecución"
    elif posproceso == "aleatoria":
        sin_criterios = tabla[tabla["criterios"] == 0]
        n = min(int(parametros_prueba["tamano_aleatoria"]), len(sin_criterios))
        tabla = muestra_aleatoria(sin_criterios, "asiento", n, int(parametros_prueba["semilla"]))
        resumen["excepciones"] = len(tabla)
        resumen["semilla"] = int(parametros_prueba["semilla"])
        resumen["poblacion_sin_criterios"] = len(sin_criterios)
    elif posproceso == "informativo":
        resumen["excepciones"] = 0
        resumen["informativo"] = True
    elif posproceso == "conciliacion":
        diferencias = tabla[tabla["diferencia"].abs() > 0.005]
        resumen["excepciones"] = len(diferencias)
        resumen["diferencia_total"] = round(float(tabla["diferencia"].sum()), 2)
        resumen["periodos"] = len(tabla)
    elif posproceso == "conciliacion_1a1":
        tabla, resumen = _aplicar_posproceso_conciliacion_1a1(tabla, parametros_prueba)
    elif posproceso is not None:
        raise ValueError(f"Posproceso desconocido: {posproceso}. Válidos: {sorted(POSPROCESOS)}")
    else:
        resumen["excepciones"] = len(tabla)

    resultado = ResultadoPrueba(
        id=prueba["id"],
        nombre=prueba["nombre"],
        ficha=str(prueba.get("ficha", "")),
        nia=prueba.get("nia", []),
        tabla=tabla,
        resumen=resumen,
        sql_sha256=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
    )
    if bitacora:
        bitacora.registrar(
            "prueba",
            prueba=resultado.id,
            version_paquete=prueba.get("_version"),
            parametros=parametros_prueba,
            identificadores=prueba.get("identificadores", {}),
            sql_sha256=resultado.sql_sha256,
            filas_resultado=len(tabla),
            resumen=resumen,
        )
    return resultado


def cargar_auxiliares(con: duckdb.DuckDBPyConnection, manifiesto: dict, bitacora: Bitacora | None = None, encargo: dict | None = None) -> None:
    """Carga las tablas de referencia del paquete. Si el encargo trae su propio archivo, ese manda."""
    carpeta = manifiesto["_carpeta"]
    encargo = encargo or {}
    for aux in manifiesto.get("auxiliares", []):
        tabla = validar_identificador(aux["tabla"])
        ruta = None
        clave_encargo = aux.get("desde_encargo")
        if clave_encargo and encargo.get(clave_encargo):
            ruta = Path(encargo[clave_encargo])
            if not ruta.is_absolute():
                ruta = encargo["_carpeta"] / ruta
        elif aux.get("archivo"):
            ruta = (carpeta / aux["archivo"]).resolve()
        if ruta is None:
            columnas = ", ".join(f'"{validar_identificador(c)}" VARCHAR' for c in aux["columnas"])
            con.execute(f'CREATE OR REPLACE TABLE "{tabla}" ({columnas})')
            continue
        con.execute(f'CREATE OR REPLACE TABLE "{tabla}" AS SELECT * FROM read_csv(?, header = true, all_varchar = true)', [str(ruta)])
        if bitacora:
            filas = con.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0]
            bitacora.registrar("tabla_auxiliar", tabla=tabla, archivo=str(ruta.name), filas=filas,
                               sha256=hashlib.sha256(ruta.read_bytes()).hexdigest())


def correr_paquete(
    con: duckdb.DuckDBPyConnection,
    manifiesto: dict,
    bitacora: Bitacora | None = None,
    encargo: dict | None = None,
) -> list[ResultadoPrueba]:
    carpeta = manifiesto["_carpeta"]
    cargar_auxiliares(con, manifiesto, bitacora, encargo)
    resultados = []
    for prueba in manifiesto["pruebas"]:
        prueba = {**prueba, "_version": manifiesto.get("version")}
        resultados.append(correr_prueba(con, carpeta, prueba, bitacora, encargo))
    return resultados
