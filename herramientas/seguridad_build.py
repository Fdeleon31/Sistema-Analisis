"""Cadena de suministro, SBOM CycloneDX 1.5, lockfile, SHA-256 y escaneo SAST/secretos (Ficha 23)."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import re
import sys
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RAIZ_DEFECTO = Path(__file__).resolve().parents[1]

_DIRECTORIOS_EXCLUIDOS = frozenset(
    {
        ".venv",
        "venv",
        "build",
        "dist",
        "__pycache__",
        ".pytest_cache",
        "salidas",
        ".git",
    }
)

_EXTENSIONES_SECRETOS = frozenset(
    {
        ".py",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".pem",
        ".key",
        ".bat",
        ".ps1",
        ".txt",
        ".md",
        ".sql",
        ".spec",
    }
)

_MODULOS_VIGILADOS = frozenset({"pickle", "_pickle", "yaml", "subprocess", "os", "builtins"})
_SUBPROCESS_SIEMPRE_SHELL = frozenset({"getoutput", "getstatusoutput"})

_RE_CLAVE_PRIVADA = re.compile(r"-----BEGIN\s+(?:[A-Z0-9]+\s+)*PRIVATE KEY-----")
_RE_URI_SQL_SECRETO = re.compile(
    r"(?i)\b(?:sqlite|postgresql|postgres|mysql|mssql|oracle|mariadb)(?:\+[a-z0-9_]+)?://"
    r"([A-Za-z0-9_.%\-]+):([^@\s'\"`<>()]+)@([A-Za-z0-9_.\-:\[\]]+)"
)
_EJEMPLOS_GENERICOS_URI = frozenset(
    {
        ("usuario", "clave", "servidor"),
        ("usuario", "contrasena", "servidor"),
        ("user", "pass", "host"),
        ("user", "password", "host"),
    }
)


def _obtener_version_aplicacion() -> str:
    """Obtiene la versión del paquete motor sin depender de rutas externas."""
    try:
        from motor import __version__

        return str(__version__)
    except ImportError:
        init_motor = _RAIZ_DEFECTO / "motor" / "__init__.py"
        if init_motor.is_file():
            coincidencia = re.search(
                r'__version__\s*=\s*["\']([^"\']+)["\']',
                init_motor.read_text(encoding="utf-8", errors="ignore"),
            )
            if coincidencia:
                return coincidencia.group(1)
    return "0.8.0"


def _normalizar_nombre_pypi(nombre: str) -> str:
    """Normaliza un nombre de distribución PyPI según PEP 503 para PURL."""
    return re.sub(r"[-_.]+", "-", nombre).strip("-").lower()


def _distribuciones_entorno() -> list[tuple[str, str]]:
    """Devuelve pares únicos (Nombre, Version) ordenados alfabéticamente desde el entorno activo."""
    vistos: set[tuple[str, str]] = set()
    resultado: list[tuple[str, str]] = []
    for dist in importlib.metadata.distributions():
        nombre = (dist.metadata.get("Name") or getattr(dist, "name", "") or "").strip()
        version = (dist.version or "").strip()
        if not nombre:
            continue
        clave = (nombre.lower(), version)
        if clave in vistos:
            continue
        vistos.add(clave)
        resultado.append((nombre, version))
    resultado.sort(key=lambda item: (item[0].lower(), item[1]))
    return resultado


def _timestamp_utc_iso() -> str:
    """Genera marca de tiempo UTC ISO-8601 terminada en Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generar_sbom_cyclonedx(salida: str | Path | None = None) -> dict[str, Any]:
    """Genera un SBOM CycloneDX 1.5 offline a partir de las distribuciones instaladas en el entorno."""
    componentes = [
        {
            "type": "library",
            "name": nombre,
            "version": version,
            "purl": f"pkg:pypi/{_normalizar_nombre_pypi(nombre)}@{version}",
        }
        for nombre, version in _distribuciones_entorno()
    ]
    sbom: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": _timestamp_utc_iso(),
            "component": {
                "type": "application",
                "name": "Folio Auditor",
                "version": _obtener_version_aplicacion(),
            },
        },
        "components": componentes,
    }
    if salida is not None:
        destino = Path(salida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(sbom, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return sbom


def generar_lockfile_entorno(salida: str | Path) -> Path:
    """Escribe un archivo requirements.lock ordenado alfabéticamente desde las distribuciones activas."""
    destino = Path(salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    lineas = [
        "# Lockfile generado offline desde el entorno activo (.venv) de Folio Auditor",
        f"# Fecha UTC: {_timestamp_utc_iso()}",
        "# Regenerar con: .\\.venv\\Scripts\\python.exe herramientas\\seguridad_build.py --lockfile requirements.lock",
    ]
    for nombre, version in _distribuciones_entorno():
        lineas.append(f"{nombre}=={version}")
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
    return destino


def _sha256_archivo(ruta: Path) -> str:
    """Calcula el resumen hexadecimal SHA-256 leyendo por bloques."""
    with ruta.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def generar_sha256sums(carpeta: str | Path, salida: str | Path | None = None) -> Path:
    """Calcula SHA-256 de todos los archivos regulares bajo carpeta ordenados por ruta POSIX."""
    base = Path(carpeta)
    if not base.is_dir():
        raise FileNotFoundError(f"No existe la carpeta para calcular SHA256SUMS: {base}")
    destino = Path(salida) if salida is not None else base / "SHA256SUMS.txt"
    destino_resuelto = destino.resolve()

    entradas: list[tuple[str, Path]] = []
    for ruta in base.rglob("*"):
        if not ruta.is_file():
            continue
        if ruta.resolve() == destino_resuelto:
            continue
        entradas.append((ruta.relative_to(base).as_posix(), ruta))
    entradas.sort(key=lambda item: item[0])

    lineas = [f"{_sha256_archivo(ruta)}  {rel_posix}" for rel_posix, ruta in entradas]
    destino.parent.mkdir(parents=True, exist_ok=True)
    contenido = ("\n".join(lineas) + "\n") if lineas else ""
    destino.write_text(contenido, encoding="utf-8", newline="\n")
    return destino


def _es_constante_true(nodo: ast.AST) -> bool:
    return isinstance(nodo, ast.Constant) and nodo.value is True


class _VisitanteSeguridadAST(ast.NodeVisitor):
    """Inspecciona un módulo Python vía AST en busca de primitivas peligrosas."""

    def __init__(self, archivo_rel: str) -> None:
        self.archivo_rel = archivo_rel
        self.modulos: dict[str, str] = {}
        self.simbolos: dict[str, tuple[str, str]] = {}
        self.hallazgos: list[dict[str, Any]] = []

    def _registrar(self, severidad: str, regla: str, linea: int, detalle: str) -> None:
        self.hallazgos.append(
            {
                "severidad": severidad,
                "regla": regla,
                "archivo": self.archivo_rel,
                "linea": linea,
                "detalle": detalle,
            }
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            nombre_mod = alias.name.split(".", 1)[0]
            alias_local = alias.asname or nombre_mod
            if nombre_mod in _MODULOS_VIGILADOS:
                self.modulos[alias_local] = nombre_mod
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            mod_raiz = node.module.split(".", 1)[0]
            if mod_raiz in _MODULOS_VIGILADOS:
                for alias in node.names:
                    alias_local = alias.asname or alias.name
                    self.simbolos[alias_local] = (mod_raiz, alias.name)
        self.generic_visit(node)

    def _es_yaml_safe_loader(self, valor: ast.AST) -> bool:
        if isinstance(valor, ast.Name):
            if valor.id in {"SafeLoader", "CSafeLoader"}:
                return True
            simbolo = self.simbolos.get(valor.id)
            return simbolo in {("yaml", "SafeLoader"), ("yaml", "CSafeLoader")}
        if isinstance(valor, ast.Attribute) and isinstance(valor.value, ast.Name):
            mod = self.modulos.get(valor.value.id) or valor.value.id
            return mod == "yaml" and valor.attr in {"SafeLoader", "CSafeLoader"}
        return False

    def _evaluar_llamada_modulo(self, modulo: str, attr: str, node: ast.Call) -> None:
        linea = getattr(node, "lineno", 1)
        if modulo == "builtins" and attr in {"eval", "exec"}:
            self._registrar(
                "ALTA",
                "LLAMADA_DINAMICA_INSEGURA",
                linea,
                f"Uso de builtins.{attr}() prohibido en código de producción.",
            )
            return
        if modulo in {"pickle", "_pickle"} and attr in {"load", "loads"}:
            self._registrar(
                "ALTA",
                "DESERIALIZACION_PICKLE",
                linea,
                f"Uso inseguro de {modulo}.{attr}() detectado.",
            )
            return
        if modulo == "yaml" and attr == "load":
            loader_seguro = any(
                kw.arg == "Loader" and self._es_yaml_safe_loader(kw.value) for kw in node.keywords
            )
            if not loader_seguro:
                self._registrar(
                    "ALTA",
                    "YAML_LOAD_INSEGURO",
                    linea,
                    "Uso de yaml.load() sin Loader=yaml.SafeLoader.",
                )
            return
        if modulo == "yaml" and attr == "unsafe_load":
            self._registrar(
                "ALTA",
                "YAML_LOAD_INSEGURO",
                linea,
                "Uso de yaml.unsafe_load() detectado.",
            )
            return
        if modulo == "subprocess":
            usa_shell = attr in _SUBPROCESS_SIEMPRE_SHELL or any(
                kw.arg == "shell" and _es_constante_true(kw.value) for kw in node.keywords
            )
            if usa_shell:
                self._registrar(
                    "ALTA",
                    "SUBPROCESS_SHELL_TRUE",
                    linea,
                    f"Llamada a subprocess.{attr}() con shell=True prohibida.",
                )
            return
        if modulo == "os" and attr in {"system", "popen"}:
            self._registrar(
                "ALTA",
                "EJECUCION_COMANDO_OS",
                linea,
                f"Uso inseguro de os.{attr}() detectado.",
            )

    def visit_Call(self, node: ast.Call) -> None:
        linea = getattr(node, "lineno", 1)
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in {"eval", "exec"} and func.id not in self.simbolos:
                self._registrar(
                    "ALTA",
                    "LLAMADA_DINAMICA_INSEGURA",
                    linea,
                    f"Uso de {func.id}() prohibido en código de producción.",
                )
            elif func.id in self.simbolos:
                modulo, attr = self.simbolos[func.id]
                self._evaluar_llamada_modulo(modulo, attr, node)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base = func.value.id
            modulo = self.modulos.get(base)
            if modulo is None and base in _MODULOS_VIGILADOS:
                modulo = base
            if modulo is not None:
                self._evaluar_llamada_modulo(modulo, func.attr, node)
        self.generic_visit(node)


def _iterar_archivos_escaneables(raiz_path: Path) -> list[Path]:
    """Recorre archivos bajo raiz_path podando directorios de entorno y salida."""
    archivos: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(raiz_path):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in _DIRECTORIOS_EXCLUIDOS and d.lower() not in _DIRECTORIOS_EXCLUIDOS
        )
        base = Path(dirpath)
        for nombre in sorted(filenames):
            archivos.append(base / nombre)
    return archivos


def _es_ejemplo_generico_uri(usuario: str, clave: str, host: str) -> bool:
    if re.fullmatch(r"\*+", clave):
        return True
    if clave.startswith(("<", "{", "$")) or "env:" in clave.lower():
        return True
    return (usuario.lower(), clave.lower(), host.lower()) in _EJEMPLOS_GENERICOS_URI


def _escanear_secretos_archivo(ruta: Path, rel_posix: str) -> list[dict[str, Any]]:
    hallazgos: list[dict[str, Any]] = []
    texto = ruta.read_text(encoding="utf-8", errors="ignore")
    for num_linea, linea in enumerate(texto.splitlines(), start=1):
        if _RE_CLAVE_PRIVADA.search(linea):
            hallazgos.append(
                {
                    "severidad": "ALTA",
                    "regla": "CLAVE_PRIVADA_EXPUESTA",
                    "archivo": rel_posix,
                    "linea": num_linea,
                    "detalle": "Se detectó un encabezado PEM de clave privada en el repositorio.",
                }
            )
        for coincidencia in _RE_URI_SQL_SECRETO.finditer(linea):
            usuario, clave, host = coincidencia.groups()
            if _es_ejemplo_generico_uri(usuario, clave, host):
                continue
            hallazgos.append(
                {
                    "severidad": "ALTA",
                    "regla": "SECRETO_URI_SQL",
                    "archivo": rel_posix,
                    "linea": num_linea,
                    "detalle": "URI SQL con contraseña literal embebida; usar referencia env:VAR.",
                }
            )
    return hallazgos


def _buscar_linea_clave(texto: str, clave: str) -> int:
    patron = re.compile(rf"^\s*{re.escape(clave)}\s*=", re.IGNORECASE)
    for num_linea, linea in enumerate(texto.splitlines(), start=1):
        if patron.search(linea):
            return num_linea
    return 1


def _verificar_datos_clientes(raiz_path: Path) -> list[dict[str, Any]]:
    carpeta_clientes = raiz_path / "datos" / "clientes"
    if not carpeta_clientes.is_dir():
        return []
    hallazgos: list[dict[str, Any]] = []
    for archivo in sorted(carpeta_clientes.rglob("*")):
        if not archivo.is_file():
            continue
        rel_clientes = archivo.relative_to(carpeta_clientes).as_posix()
        if rel_clientes not in {".gitkeep", "README.md"}:
            hallazgos.append(
                {
                    "severidad": "ALTA",
                    "regla": "DATOS_CLIENTES_EN_REPO",
                    "archivo": archivo.relative_to(raiz_path).as_posix(),
                    "linea": 1,
                    "detalle": (
                        "Archivo detectado en datos/clientes/ fuera de .gitkeep o README.md "
                        "(regla de sala limpia: cero datos reales de clientes)."
                    ),
                }
            )
    return hallazgos


def _verificar_config_streamlit(raiz_path: Path) -> list[dict[str, Any]]:
    config_toml = raiz_path / ".streamlit" / "config.toml"
    if not config_toml.is_file():
        return []
    rel_posix = ".streamlit/config.toml"
    texto = config_toml.read_text(encoding="utf-8", errors="ignore")
    try:
        datos = tomllib.loads(texto)
    except tomllib.TOMLDecodeError as exc:
        return [
            {
                "severidad": "ALTA",
                "regla": "STREAMLIT_CONFIG_INVALIDA",
                "archivo": rel_posix,
                "linea": 1,
                "detalle": f"No se pudo interpretar .streamlit/config.toml: {exc}",
            }
        ]

    hallazgos: list[dict[str, Any]] = []
    servidor = datos.get("server") if isinstance(datos.get("server"), dict) else {}
    navegador = datos.get("browser") if isinstance(datos.get("browser"), dict) else {}
    requisitos = [
        (servidor, "address", "127.0.0.1", "ALTA", "address debe ser \"127.0.0.1\"."),
        (servidor, "enableXsrfProtection", True, "ALTA", "enableXsrfProtection debe ser true."),
        (servidor, "enableCORS", False, "ALTA", "enableCORS debe ser false."),
        (navegador, "gatherUsageStats", False, "MEDIA", "gatherUsageStats debe ser false."),
    ]
    for seccion, clave, esperado, severidad, mensaje in requisitos:
        actual = seccion.get(clave)
        cumple = (actual is esperado) if isinstance(esperado, bool) else (actual == esperado)
        if not cumple:
            hallazgos.append(
                {
                    "severidad": severidad,
                    "regla": "STREAMLIT_HARDENING",
                    "archivo": rel_posix,
                    "linea": _buscar_linea_clave(texto, clave),
                    "detalle": f"Configuración insegura en .streamlit/config.toml: {mensaje}",
                }
            )
    return hallazgos


def escanear_seguridad_estatico(raiz: str | Path) -> list[dict[str, Any]]:
    """Ejecuta escaneo SAST por AST, detección de secretos, sala limpia y hardening local."""
    raiz_path = Path(raiz).resolve()
    if not raiz_path.is_dir():
        raise FileNotFoundError(f"La raíz a escanear no existe: {raiz_path}")

    hallazgos: list[dict[str, Any]] = []

    for archivo in _iterar_archivos_escaneables(raiz_path):
        if not archivo.is_file():
            continue
        rel = archivo.relative_to(raiz_path)
        rel_posix = rel.as_posix()

        es_test = any(parte.lower() == "tests" for parte in rel.parts[:-1])
        es_doc = any(parte.lower() == "docs" for parte in rel.parts[:-1])

        if archivo.suffix.lower() == ".py" and not es_test:
            codigo = archivo.read_text(encoding="utf-8", errors="ignore")
            try:
                arbol = ast.parse(codigo, filename=rel_posix)
            except SyntaxError as exc:
                hallazgos.append(
                    {
                        "severidad": "MEDIA",
                        "regla": "AST_ERROR_SINTAXIS",
                        "archivo": rel_posix,
                        "linea": exc.lineno or 1,
                        "detalle": f"Error de sintaxis al analizar AST: {exc.msg}",
                    }
                )
            else:
                visitante = _VisitanteSeguridadAST(rel_posix)
                visitante.visit(arbol)
                hallazgos.extend(visitante.hallazgos)

        es_texto_vigilado = (
            archivo.suffix.lower() in _EXTENSIONES_SECRETOS
            or archivo.name.lower().startswith(".env")
        )
        if es_texto_vigilado and not es_test and not es_doc:
            hallazgos.extend(_escanear_secretos_archivo(archivo, rel_posix))

    hallazgos.extend(_verificar_datos_clientes(raiz_path))
    hallazgos.extend(_verificar_config_streamlit(raiz_path))

    hallazgos.sort(key=lambda h: (h["archivo"], h["linea"], h["regla"]))
    return hallazgos


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Herramienta offline de cadena de suministro, SBOM CycloneDX 1.5 y escaneo estático."
    )
    parser.add_argument(
        "--escanear",
        action="store_true",
        help="Ejecuta el escaneo SAST, secretos, datos/clientes y configuración local.",
    )
    parser.add_argument(
        "--raiz",
        type=Path,
        default=_RAIZ_DEFECTO,
        help="Carpeta raíz a analizar con --escanear (por defecto, la raíz del proyecto).",
    )
    parser.add_argument(
        "--sbom",
        type=Path,
        default=None,
        help="Ruta de salida para generar el SBOM en formato CycloneDX 1.5.",
    )
    parser.add_argument(
        "--lockfile",
        type=Path,
        default=None,
        help="Ruta de salida para generar requirements.lock desde el entorno activo.",
    )
    parser.add_argument(
        "--sha256sums",
        type=Path,
        default=None,
        help="Carpeta sobre la cual generar el manifiesto SHA256SUMS.txt.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada CLI."""
    parser = _construir_parser()
    args = parser.parse_args(argv)

    if not any([args.escanear, args.sbom, args.lockfile, args.sha256sums]):
        parser.print_help()
        return 0

    codigo_salida = 0
    if args.escanear:
        hallazgos = escanear_seguridad_estatico(args.raiz)
        if hallazgos:
            print(f"Escaneo estático encontró {len(hallazgos)} hallazgo(s):")
            for item in hallazgos:
                print(
                    f"  [{item['severidad']}] {item['regla']} "
                    f"{item['archivo']}:{item['linea']} - {item['detalle']}"
                )
            codigo_salida = 1
        else:
            print("Escaneo estático limpio: 0 hallazgos.")

    if args.sbom is not None:
        sbom = generar_sbom_cyclonedx(args.sbom)
        print(
            f"SBOM CycloneDX {sbom['specVersion']} generado en {args.sbom} "
            f"({len(sbom['components'])} componentes)."
        )

    if args.lockfile is not None:
        ruta_lock = generar_lockfile_entorno(args.lockfile)
        print(f"Lockfile generado en {ruta_lock}.")

    if args.sha256sums is not None:
        ruta_sums = generar_sha256sums(args.sha256sums)
        print(f"Manifiesto SHA-256 generado en {ruta_sums}.")

    return codigo_salida


if __name__ == "__main__":
    sys.exit(main())
