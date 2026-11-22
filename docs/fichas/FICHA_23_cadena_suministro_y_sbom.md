# Ficha 23 · Cadena de Suministro, SBOM CycloneDX 1.5, Análisis Estático y Empaquetado Firmado (Oleada 4)

**Fecha:** noviembre 2026  
**Módulos y artefactos:** `herramientas/__init__.py`, `herramientas/seguridad_build.py`, `verificar_seguridad.ps1`, `empaquetar_exe.bat`, `cuadra.spec`, `requirements.lock`  
**Pruebas asociadas:** `tests/test_seguridad_supply_chain.py`  
**Referencias públicas:**
- **OWASP CycloneDX Specification v1.5** (*Software Bill of Materials — JSON Schema*, metadatos de componente y *Package URL* `pkg:pypi/...`).
- **SLSA** (*Supply-chain Levels for Software Artifacts* — procedencia reproducible, fijación de dependencias y generación verificable de manifiestos de integridad).
- **NIST SP 800-218** (*Secure Software Development Framework — SSDF*: prácticas **PS** *Protect the Software*, **PW** *Produce Well-Secured Software* y **RV** *Respond to Vulnerabilities*).
- **ISO/IEC 27001:2022** (Anexo A.8.8 — Gestión de vulnerabilidades técnicas; A.8.25 — Ciclo de vida de desarrollo seguro; A.8.29 — Pruebas de seguridad en desarrollo y aceptación).
- **CIS Controls v8** (Control 16 — Seguridad del Software de Aplicación).
- **RFC 3161** (*Internet X.509 Public Key Infrastructure Time-Stamp Protocol — TSP*) y documentación pública de **Microsoft Authenticode** (`signtool.exe` y `Get-AuthenticodeSignature`).
- **Python 3.12 Standard Library** (`ast`, `hashlib`, `importlib.metadata`, `json`, `re`, `uuid`, `pathlib`, `argparse`, `datetime`).

**Principio rector:** *Integridad verificable de extremo a extremo desde el código fuente hasta el ejecutable Windows entregado al departamento de TI.* Todo artefacto compilado debe acompañar inventario completo de dependencias (**SBOM CycloneDX 1.5**), versión fija de empaquetador, manifiesto criptográfico (`SHA256SUMS.txt`), compuerta automática libre de patrones inseguros o secretos y soporte estándar de firma digital corporativa **Authenticode**.

---

## 1. Herramientas de seguridad de compilación sin internet (`herramientas/seguridad_build.py`)

Diseñado en **Python 3.12 puro (cero dependencias externas)** para ejecutarse incluso en entornos corporativos totalmente desconectados de internet (*air-gapped*).

### 1.1 Generación de SBOM CycloneDX 1.5 (`generar_sbom_cyclonedx`)

- Firma: `generar_sbom_cyclonedx(salida: str | Path | None = None) -> dict`.
- Inspecciona las distribuciones instaladas en el entorno activo mediante `importlib.metadata.distributions()`, sin realizar peticiones HTTP ni consultar registros remotos.
- Construye un objeto JSON conforme a **CycloneDX 1.5**:
  - `bomFormat`: `"CycloneDX"`
  - `specVersion`: `"1.5"`
  - `serialNumber`: `"urn:uuid:<uuid4>"`
  - `version`: `1`
  - `metadata`: marca temporal `timestamp` (UTC ISO 8601) y componente raíz `{"type": "application", "name": "Folio Auditor", "version": <motor.__version__>}`.
  - `components`: lista determinista ordenada por `(name.lower(), version)`, donde cada librería incluye `type="library"`, `name`, `version` y `purl` normalizado (`pkg:pypi/<nombre_normalizado>@<version>`).
- Si se especifica `salida`, crea los directorios padres necesarios y serializa el documento en UTF-8 indentado (p. ej. `docs/seguridad/sbom.cdx.json` y `dist/LibroAuditoria/sbom.cdx.json`).

### 1.2 Lockfile de dependencias activas (`generar_lockfile_entorno`)

- Firma: `generar_lockfile_entorno(salida: str | Path) -> Path`.
- Genera un archivo `requirements.lock` ordenado alfabéticamente con líneas fijadas `Nombre==Version` correspondientes a las distribuciones instaladas en `.venv`, incluyendo un comentario de cabecera con fecha y constancia de generación offline para evitar derivas por rangos abiertos (`>=`).

### 1.3 Manifiesto de integridad `SHA256SUMS.txt` (`generar_sha256sums`)

- Firma: `generar_sha256sums(carpeta: str | Path, salida: str | Path | None = None) -> Path`.
- Recorre todos los archivos regulares contenidos bajo `carpeta` (por defecto `dist\LibroAuditoria`), ordenados de forma determinista por ruta relativa en estilo POSIX.
- Excluye el propio archivo de salida (`SHA256SUMS.txt`) para evitar autorreferencia circular.
- Escribe líneas estándar `<sha256_hex>  <ruta_relativa_posix>\n` (con dos espacios entre resumen y ruta, compatible con `Get-FileHash` y verificadores estándar de integridad).

### 1.4 Analizador estático AST y detector de secretos/entorno (`escanear_seguridad_estatico`)

- Firma: `escanear_seguridad_estatico(raiz: str | Path) -> list[dict]`.
- Recorre archivos `.py` bajo `raiz` excluyendo directorios de entorno y salida (`.venv`, `venv`, `build`, `dist`, `__pycache__`, `.pytest_cache`, `salidas`).
- **Reglas AST sobre código fuente de producción** (excluyendo `tests/` para evitar falsos positivos con vectores adversarios sintéticos):
  - Llamadas dinámicas inseguras: `eval(...)`, `exec(...)`.
  - Deserialización insegura: `pickle.load(...)`, `pickle.loads(...)`, `yaml.load(...)` sin `Loader=yaml.SafeLoader` explícito.
  - Ejecución de subprocesos o shell insegura: `subprocess.*(..., shell=True)`, `os.system(...)`, `os.popen(...)`.
- **Detección de secretos reales** (excluyendo `tests/` y `docs/`):
  - Bloques PEM de claves privadas (`-----BEGIN ... PRIVATE KEY-----`).
  - Cadenas URI SQL con credenciales literales embebidas (`://usuario:clave@`), ignorando referencias seguras `env:VAR` y valores enmascarados (`***`).
- **Guardarraíles de privacidad y configuración local:**
  - Verifica que `datos/clientes/` (si existe) no contenga archivos distintos de `.gitkeep` o `README.md` (prevención de fuga accidental de datos reales en el repositorio).
  - Verifica que `.streamlit/config.toml` (si existe) declare obligatoriamente `address = "127.0.0.1"`, `enableXsrfProtection = true`, `enableCORS = false` y `gatherUsageStats = false`.
- Cada hallazgo se reporta como `{"severidad": "ALTA" | "MEDIA", "regla": str, "archivo": str, "linea": int, "detalle": str}`.

### 1.5 Interfaz de línea de comandos (`__main__`)

Soporta las banderas:
- `--escanear` (junto con `--raiz <ruta>` opcional): imprime resumen en español y termina con código `0` (`"Escaneo estático limpio: 0 hallazgos."`) o código `1` ante incidencias.
- `--sbom <ruta>`
- `--lockfile <ruta>`
- `--sha256sums <carpeta>`

---

## 2. Puerta automatizada de verificación pre-entrega (`verificar_seguridad.ps1`)

Script PowerShell con tolerancia cero a fallos (`$ErrorActionPreference = "Stop"`):

1. Ejecuta `.\\.venv\\Scripts\\python.exe herramientas\\seguridad_build.py --escanear`.
2. Ejecuta todas las suites automatizadas de seguridad con `pytest`:
   - `tests/test_seguridad_hardening.py` (Oleada 1)
   - `tests/test_seguridad_cripto_roles.py` (Oleada 2)
   - `tests/test_login_pantalla.py` (Login dual y panel Admin)
   - `tests/test_seguridad_privacidad.py` (Oleada 3 y cero sockets salientes)
   - `tests/test_seguridad_supply_chain.py` (Oleada 4)
3. Genera los artefactos actualizados `docs\seguridad\sbom.cdx.json` y `requirements.lock` mediante `herramientas\seguridad_build.py`.
4. Comprueba opcionalmente si `bandit` o `pip-audit` están instalados dentro de `.venv`; si existen los ejecuta como refuerzo adicional y, si no están presentes en entornos sin conexión, concluye limpiamente sin interrumpir la compuerta offline.

---

## 3. Empaquetado reproducible y firma Authenticode (`empaquetar_exe.bat`)

1. **Versión fija de PyInstaller:** reemplaza la instalación sin versión por `pyinstaller==6.22.3`, asegurando reproducibilidad al compilar la especificación técnica `cuadra.spec` hacia `dist\LibroAuditoria\LibroAuditoria.exe`.
2. **Emisión de SBOM y hashes en la entrega:** tras copiar `encargos\*.yaml`, invoca `herramientas\seguridad_build.py --sbom "dist\LibroAuditoria\sbom.cdx.json" --sha256sums "dist\LibroAuditoria"`.
3. **Flujo estándar de firma digital Authenticode con sello de tiempo RFC 3161:**
   - Si el entorno de compilación define `FOLIO_CERT_PFX` (con contraseña opcional en `FOLIO_CERT_PASS`) o `FOLIO_CERT_THUMBPRINT`, invoca:
     `signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ... "dist\LibroAuditoria\LibroAuditoria.exe"`
   - Inmediatamente después regenera `--sha256sums "dist\LibroAuditoria"` para que `SHA256SUMS.txt` refleje el hash exacto del binario ya firmado.
   - Si no hay certificado corporativo ni `signtool` disponible en una compilación local de desarrollo, imprime un aviso explícito indicando que el binario queda sin firma Authenticode sin abortar el empaquetado local.

---

## 4. Casos esperados (`tests/test_seguridad_supply_chain.py`)

| Caso de prueba | Entrada / Objeto evaluado | Resultado esperado |
| :--- | :--- | :--- |
| **SBOM CycloneDX 1.5** | `generar_sbom_cyclonedx` | `bomFormat == "CycloneDX"`, `specVersion == "1.5"`, componentes ordenados con `purl` válidos incluyendo `duckdb`, `pandas` y `PySide6` |
| **Lockfile y SHA256SUMS** | `generar_lockfile_entorno` y `generar_sha256sums` sobre carpeta sintética | Archivo con pines `==`; archivo `SHA256SUMS.txt` sin autorreferencia y con hashes SHA-256 coincidentes bit a bit |
| **Detección AST y secretos** | Archivo temporal en `tmp_path` con `eval("1")`, `subprocess.run("dir", shell=True)` y encabezado `-----BEGIN RSA PRIVATE KEY-----` | El escáner reporta las 3 incidencias con archivo y número de línea exactos |
| **Repositorio limpio** | `escanear_seguridad_estatico` sobre la raíz real del proyecto | **0 hallazgos** en producción y guardarraíles de `.streamlit/config.toml` y `datos/clientes/` satisfechos |
| **Contrato `empaquetar_exe.bat`** | Inspección del script de empaquetado | Fija `pyinstaller==6.22.3`, genera `sbom.cdx.json` y `SHA256SUMS.txt`, e incluye flujo `signtool` con `/fd SHA256` y sello RFC 3161 |
