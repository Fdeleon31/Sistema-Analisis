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
POSPROCESOS = {"benford", "criterios", "seleccion", "aleatoria", "informativo", "conciliacion"}
CRITERIOS_ASIENTO = [
    "fin_semana_feriado", "posterior_cierre", "cerca_cierre", "monto_redondo", "bajo_umbral",
    "descripcion_sospechosa", "usuario_poco_frecuente", "cuenta_poco_usada", "descuadrado", "sobre_materialidad",
]


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
