"""Pruebas automatizadas de cadena de suministro, SBOM, SAST/secretos y build seguro (Ficha 23)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

from herramientas.seguridad_build import (
    escanear_seguridad_estatico,
    generar_lockfile_entorno,
    generar_sbom_cyclonedx,
    generar_sha256sums,
)

RAIZ = Path(__file__).resolve().parents[1]


def test_generar_sbom_cyclonedx_valido_y_componentes_clave(tmp_path):
    ruta_sbom = tmp_path / "salida" / "sbom.cdx.json"
    sbom = generar_sbom_cyclonedx(ruta_sbom)

    assert ruta_sbom.is_file()
    cargado = json.loads(ruta_sbom.read_text(encoding="utf-8"))
    assert cargado == sbom

    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["version"] == 1
    assert sbom["serialNumber"].startswith("urn:uuid:")
    uuid.UUID(sbom["serialNumber"].removeprefix("urn:uuid:"))

    meta = sbom["metadata"]
    assert meta["timestamp"].endswith("Z")
    assert meta["component"]["type"] == "application"
    assert meta["component"]["name"] == "Folio Auditor"
    assert meta["component"]["version"]

    componentes = sbom["components"]
    assert len(componentes) > 10
    claves_orden = [(c["name"].lower(), c["version"]) for c in componentes]
    assert claves_orden == sorted(claves_orden)

    por_nombre = {c["name"].lower(): c for c in componentes}
    for clave in ("duckdb", "pandas", "pyside6"):
        assert clave in por_nombre
        comp = por_nombre[clave]
        assert comp["type"] == "library"
        assert comp["version"]
        assert comp["purl"].startswith("pkg:pypi/")
        assert f"@{comp['version']}" in comp["purl"]


def test_generar_lockfile_entorno_ordenado_y_offline(tmp_path):
    ruta_lock = tmp_path / "sub" / "requirements.lock"
    retorno = generar_lockfile_entorno(ruta_lock)

    assert retorno == ruta_lock
    assert ruta_lock.is_file()
    lineas = ruta_lock.read_text(encoding="utf-8").splitlines()
    cabeceras = [l for l in lineas if l.startswith("#")]
    paquetes = [l for l in lineas if l and not l.startswith("#")]

    assert any("offline" in h.lower() for h in cabeceras)
    assert len(paquetes) > 10
    assert all("==" in p for p in paquetes)
    nombres_ord = [(p.split("==", 1)[0].lower(), p.split("==", 1)[1]) for p in paquetes]
    assert nombres_ord == sorted(nombres_ord)

    nombres_presentes = {p.split("==", 1)[0].lower() for p in paquetes}
    assert {"duckdb", "pandas", "pyside6"}.issubset(nombres_presentes)


def test_generar_sha256sums_posix_y_coincidencia(tmp_path):
    carpeta = tmp_path / "entrega"
    (carpeta / "sub" / "nivel").mkdir(parents=True)
    archivo_a = carpeta / "app.exe"
    archivo_b = carpeta / "sub" / "nivel" / "config.yaml"
    archivo_a.write_bytes(b"binario-sintetico-folio-auditor")
    archivo_b.write_text("clave: valor\n", encoding="utf-8")

    # Pre-crear SHA256SUMS.txt antiguo para comprobar que se excluye a sí mismo
    sums = carpeta / "SHA256SUMS.txt"
    sums.write_text("obsoleto", encoding="utf-8")

    salida = generar_sha256sums(carpeta)
    assert salida == sums

    lineas = sums.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2

    rutas_rel = []
    for linea in lineas:
        digest, rel = linea.split("  ", 1)
        assert len(digest) == 64
        assert "\\" not in rel
        rutas_rel.append(rel)
        esperado = hashlib.sha256((carpeta / rel).read_bytes()).hexdigest()
        assert digest == esperado

    assert rutas_rel == ["app.exe", "sub/nivel/config.yaml"]


def test_escanear_seguridad_estatico_detecta_riesgos_en_tmp_path(tmp_path):
    (tmp_path / "codigo_riesgoso.py").write_text(
        "\n".join(
            [
                "import os",
                "import pickle",
                "import subprocess",
                "import yaml",
                "",
                'eval("1")',
                'exec("x = 1")',
                'pickle.loads(b"data")',
                'yaml.load("a: 1")',
                'subprocess.run("dir", shell=True)',
                'os.system("echo hola")',
                'CLAVE = "-----BEGIN RSA PRIVATE KEY-----"',
                'URI = "postgresql://auditor:ClaveSuperSecreta99@db.local:5432/erp"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "datos" / "clientes").mkdir(parents=True)
    (tmp_path / "datos" / "clientes" / "secreto_cliente.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    (tmp_path / ".streamlit").mkdir(parents=True)
    (tmp_path / ".streamlit" / "config.toml").write_text(
        '[server]\naddress = "0.0.0.0"\nenableXsrfProtection = false\nenableCORS = true\n'
        "[browser]\ngatherUsageStats = true\n",
        encoding="utf-8",
    )

    # Archivos seguros y carpetas omitidas (tests/, docs/) no deben generar ruido extra
    (tmp_path / "codigo_limpio.py").write_text(
        "\n".join(
            [
                "import subprocess",
                "import yaml",
                "",
                "class Dialogo:",
                "    def exec(self):",
                "        return 1",
                "",
                "dlg = Dialogo()",
                "dlg.exec()",
                'yaml.load("a: 1", Loader=yaml.SafeLoader)',
                'yaml.safe_load("a: 1")',
                'subprocess.run(["echo", "ok"], shell=False)',
                'URI_OK = "env:FOLIO_SQL_URI"',
                'URI_MASK = "postgresql://auditor:***@db.local:5432/erp"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_adversario.py").write_text('eval("1")\n', encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ejemplo.md").write_text("-----BEGIN RSA PRIVATE KEY-----\n", encoding="utf-8")

    hallazgos = escanear_seguridad_estatico(tmp_path)
    reglas = {h["regla"] for h in hallazgos}
    archivos = {h["archivo"] for h in hallazgos}

    assert "LLAMADA_DINAMICA_INSEGURA" in reglas
    assert "DESERIALIZACION_PICKLE" in reglas
    assert "YAML_LOAD_INSEGURO" in reglas
    assert "SUBPROCESS_SHELL_TRUE" in reglas
    assert "EJECUCION_COMANDO_OS" in reglas
    assert "CLAVE_PRIVADA_EXPUESTA" in reglas
    assert "SECRETO_URI_SQL" in reglas
    assert "DATOS_CLIENTES_EN_REPO" in reglas
    assert "STREAMLIT_HARDENING" in reglas

    assert "codigo_riesgoso.py" in archivos
    assert "codigo_limpio.py" not in archivos
    assert "tests/test_adversario.py" not in archivos
    assert "docs/ejemplo.md" not in archivos

    detalles_eval = [h for h in hallazgos if h["archivo"] == "codigo_riesgoso.py"]
    assert any("eval(" in h["detalle"] for h in detalles_eval)
    assert any("shell=True" in h["detalle"] for h in detalles_eval)
    assert any(h["regla"] == "CLAVE_PRIVADA_EXPUESTA" for h in detalles_eval)


def test_escanear_seguridad_estatico_raiz_real_limpia():
    hallazgos = escanear_seguridad_estatico(RAIZ)
    assert hallazgos == [], f"Se encontraron hallazgos inesperados: {hallazgos}"


def test_cli_seguridad_build_escanear_y_artefactos(tmp_path):
    res_ok = subprocess.run(
        [sys.executable, str(RAIZ / "herramientas" / "seguridad_build.py"), "--escanear"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    assert res_ok.returncode == 0
    assert "Escaneo estático limpio: 0 hallazgos." in res_ok.stdout

    (tmp_path / "malo.py").write_text('eval("1")\n', encoding="utf-8")
    res_fail = subprocess.run(
        [
            sys.executable,
            str(RAIZ / "herramientas" / "seguridad_build.py"),
            "--escanear",
            "--raiz",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    assert res_fail.returncode == 1
    assert "LLAMADA_DINAMICA_INSEGURA" in res_fail.stdout

    carpeta_dist = tmp_path / "dist_sim"
    carpeta_dist.mkdir()
    (carpeta_dist / "LibroAuditoria.exe").write_bytes(b"MZ-sintetico")
    res_art = subprocess.run(
        [
            sys.executable,
            str(RAIZ / "herramientas" / "seguridad_build.py"),
            "--sbom",
            str(carpeta_dist / "sbom.cdx.json"),
            "--sha256sums",
            str(carpeta_dist),
        ],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    assert res_art.returncode == 0
    assert (carpeta_dist / "sbom.cdx.json").is_file()
    texto_sums = (carpeta_dist / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert "LibroAuditoria.exe" in texto_sums
    assert "sbom.cdx.json" in texto_sums


def test_empaquetar_exe_y_verificar_seguridad_contienen_controles():
    bat = (RAIZ / "empaquetar_exe.bat").read_text(encoding="utf-8")
    assert "pyinstaller==6.22.3" in bat
    assert "herramientas\\seguridad_build.py" in bat
    assert "sbom.cdx.json" in bat
    assert "SHA256SUMS.txt" in bat or "--sha256sums" in bat
    assert "signtool" in bat
    assert "http://timestamp.digicert.com" in bat
    assert "/fd SHA256" in bat
    assert "/td SHA256" in bat
    assert "FOLIO_CERT_PFX" in bat
    assert "FOLIO_CERT_THUMBPRINT" in bat

    ps1 = (RAIZ / "verificar_seguridad.ps1").read_text(encoding="utf-8")
    assert '$ErrorActionPreference = "Stop"' in ps1
    assert "herramientas\\seguridad_build.py --escanear" in ps1
    assert "test_seguridad_supply_chain.py" in ps1
    assert "docs\\seguridad\\sbom.cdx.json" in ps1
    assert "requirements.lock" in ps1
    assert "bandit" in ps1
    assert "pip-audit" in ps1


def test_hashes_lockfile_sin_red_y_conservados_al_regenerar(tmp_path, monkeypatch):
    """Esperado por diseño: --hash por versión fijada, sin cambiar versiones; regenerar conserva los hashes."""
    from herramientas import seguridad_build as sb

    lock = tmp_path / "requirements.lock"
    lock.write_text("# cabecera\nduckdb==2.0.1\npandas==3.1.1\n", encoding="utf-8")
    falsos = {("duckdb", "2.0.1"): ["b" * 64, "a" * 64], ("pandas", "3.1.1"): ["c" * 64]}
    sb.agregar_hashes_lockfile(lock, obtener_hashes=lambda n, v: falsos[(n, v)])
    texto = lock.read_text(encoding="utf-8")
    assert "duckdb==2.0.1 \\\n    --hash=sha256:" + "a" * 64 + " \\\n    --hash=sha256:" + "b" * 64 + "\n" in texto
    assert "pandas==3.1.1 \\\n    --hash=sha256:" + "c" * 64 + "\n" in texto

    # Regenerar desde el entorno conserva hashes de versiones iguales y avisa las nuevas
    monkeypatch.setattr(sb, "_distribuciones_entorno", lambda: [("duckdb", "2.0.1"), ("pandas", "3.2.0")])
    sb.generar_lockfile_entorno(lock)
    texto = lock.read_text(encoding="utf-8")
    assert "--hash=sha256:" + "a" * 64 in texto
    assert "pandas==3.2.0\n" in texto
    assert "FALTAN HASHES para 1" in texto
