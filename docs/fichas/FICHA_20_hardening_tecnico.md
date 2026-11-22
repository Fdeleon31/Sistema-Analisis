# Ficha 20 · Hardening Técnico Crítico (Oleada 1)

**Fecha:** noviembre 2026  
**Módulos:** `motor/seguridad.py`, `motor/importador.py`, `motor/exportador.py`, `motor/factura_electronica.py`, `conectores/sql_fuente.py`, `conectores/estado_cuenta_pdf.py`, `conectores/__init__.py`, `ia/copiloto.py`, `app/inicio.py`, `.streamlit/config.toml`, `iniciar.bat`, `cuadra.py`  
**Referencias públicas:**
- **OWASP ASVS v4.0.3** (V1, V5, V12, V13) y **OWASP CWE Top 25** (`CWE-22`, `CWE-89`, `CWE-409`, `CWE-522`, `CWE-532`, `CWE-611`, `CWE-776`, `CWE-1236`).
- **OWASP CSV Injection** (Formula Injection): neutralización preventiva con apóstrofo literal `'` en cadenas iniciadas por `=`, `+`, `-`, `@`, tabulador o retorno de carro.
- **DuckDB Security Documentation**: configuración `enable_external_access = false` y `lock_configuration = true`.
- **Python Software Foundation**: módulo estándar `sqlite3` (`Connection.set_authorizer`), `zipfile`, `zlib` (`decompressobj().decompress(data, max_length)`), `tempfile`.
- **ISO/IEC 27001:2022** (Anexo A.8.28 — Codificación segura) y **NIST SSDF** (PW.4, PW.8).

**Principio rector:** *Defensa en profundidad en cada frontera de entrada y salida de datos, fallando de forma explícita con `ErrorSeguridad` (subclase de `ValueError`) antes de procesar o exportar contenido potencialmente peligroso.*

---

## 1. Primitivas centralizadas (`motor/seguridad.py`)

Se define la excepción `ErrorSeguridad(ValueError)` para mantener compatibilidad con los manejadores de validación existentes y distinguir bloqueos de seguridad en pruebas.

### 1.1 Límites numéricos de seguridad por defecto

| Constante | Valor | Propósito |
| :--- | :--- | :--- |
| `MAX_BYTES_XML` | `10 * 1024 * 1024` (10 MB) | Tamaño máximo de cada XML de factura electrónica |
| `MAX_BYTES_ZIP_TOTAL` | `200 * 1024 * 1024` (200 MB) | Tamaño total descomprimido permitido en un archivo ZIP |
| `MAX_ARCHIVOS_ZIP` | `10_000` | Número máximo de entradas procesables en un ZIP |
| `MAX_RATIO_ZIP` | `100.0` | Razón máxima descomprimido/comprimido (aplicada cuando `tamaño >= UMBRAL_RATIO_ZIP_BYTES`) |
| `UMBRAL_RATIO_ZIP_BYTES` | `1 * 1024 * 1024` (1 MB) | Umbral mínimo para evaluar ratio ZIP y evitar falsos positivos en XML/PDF sintéticos pequeños |
| `MAX_BYTES_PDF_FLUJO` | `50 * 1024 * 1024` (50 MB) | Tamaño máximo descomprimido de un flujo `FlateDecode` PDF |
| `MAX_BYTES_PDF_TOTAL` | `200 * 1024 * 1024` (200 MB) | Tamaño máximo acumulado de flujos o archivo PDF bancario |
| `MAX_BYTES_SQL_DUMP` | `200 * 1024 * 1024` (200 MB) | Tamaño máximo de un volcado `.sql` cargado en memoria |

### 1.2 Bloqueo e idempotencia en DuckDB
- `bloquear_duckdb_externo(con)`:
  1. Consulta `SELECT current_setting('enable_external_access'), current_setting('lock_configuration')`.
  2. Si `lock_configuration` ya es `True`: si `enable_external_access` sigue `True` lanza `ErrorSeguridad`; en caso contrario retorna sin volver a ejecutar `SET` (evita `InvalidInputException` en DuckDB 2.x).
  3. Si no está bloqueada, ejecuta `SET enable_external_access = false` y `SET lock_configuration = true`.

### 1.3 Neutralización de inyección de fórmulas Excel/CSV (`CWE-1236`)
- `sanitizar_valor_excel(valor)` y `sanitizar_dataframe_excel(df)`:
  - Conserva intactos los valores no textuales (`int`, `float`, `Decimal`, `bool`, `date`, `datetime`, `None`), el guion simple `"-"`, y números con signo puro (`re.fullmatch(r"[-+]\d+(?:[.,]\d+)?", valor.strip())`).
  - Si una cadena comienza con `=`, `+`, `-`, `@`, `\t`, `\r` o su texto tras `lstrip(" \t\r\n")` comienza con `=`, `+`, `-`, `@`, antepone un apóstrofo literal `'` para impedir su evaluación como fórmula en Excel o hojas de cálculo compatibles.
  - `sanitizar_dataframe_excel` aplica la neutralización únicamente sobre columnas de tipo texto (`object` o `string`) y encabezados textuales, sin alterar columnas numéricas, booleanas ni de fecha.

### 1.4 Escape de identificadores y formatos en DuckDB
- `citar_identificador_sql(nombre)`: rechaza nulos/vacíos/`\x00` y escapa comillas dobles internas duplicándolas (`"` → `""`).
- `validar_formato_fecha_sql(formato)`: exige longitud `<= 64` y coincidencia estricta con `^[A-Za-z0-9%/:.,_\-\s]+$`, impidiendo inyección SQL en `TRY_STRPTIME`.

### 1.5 Validación anti-XXE / anti-bombas XML, ZIP y PDF
- `validar_xml_seguro(contenido, max_bytes=MAX_BYTES_XML)`: verifica tamaño y rechaza cualquier declaración DTD/entidad (`<!DOCTYPE`, `<!ENTITY`, `<!ELEMENT`, `<!ATTLIST`, sin distinguir mayúsculas/minúsculas).
- `validar_ruta_miembro_zip(nombre)`: rechaza `\x00`, rutas absolutas (`/`, `\`), letras de unidad (`C:`) y segmentos `..`.
- `leer_miembros_zip_seguros(ruta_zip, extensiones, ...)`: lee por streaming en bloques de 64 KiB verificando tamaño real descomprimido (contra encabezados ZIP manipulados), límite por archivo, límite acumulado, conteo máximo y ratio en entradas `>= 1 MB`.
- `descomprimir_zlib_seguro(datos, max_bytes=MAX_BYTES_PDF_FLUJO)`: descomprime mediante `zlib.decompressobj().decompress(datos, max_bytes + 1)` abortando de inmediato si supera `max_bytes`.

### 1.6 Saneamiento de nombres y temporales
- `nombre_archivo_seguro(nombre, defecto="archivo")`: rechaza `\x00`, rutas absolutas y segmentos `..`; elimina caracteres de control y conserva solo el nombre base seguro.
- `crear_directorio_temporal_seguro(prefijo="folio_auditor_")`: crea directorio temporal con permisos `0o700` cuando aplica y registra limpieza en `atexit`.

---

## 2. Controles por subsistema

1. **SQL y Copiloto (`conectores/sql_fuente.py`, `ia/copiloto.py`, `motor/importador.py`, `cuadra.py`):**
   - `preparar_conexion_copiloto` y `ejecutar_propuesta_aprobada` aplican `bloquear_duckdb_externo(con)` tras la carga de tablas.
   - `validar_consulta_solo_lectura` soporta comentarios de bloque anidados `/* ... */`, rechaza comentarios/literales sin cerrar y `$$...$$`, amplía `PALABRAS_PROHIBIDAS` (`INTO`, `SET`, `RESET`, `EXPORT`, `IMPORT`, `CHECKPOINT`, `PREPARE`, `DEALLOCATE`, `USE`) y bloquea `FUNCIONES_PROHIBIDAS_SQL` (`read_csv*`, `read_parquet`, `read_json*`, `read_ndjson*`, `read_text`, `read_blob`, `glob`, `getenv`, `current_setting`, `duckdb_*`, `sqlite_scan`, `postgres_scan`, `pg_read_file`, `xp_cmdshell`, `load_extension`, etc.).
   - Soporte de `env:NOMBRE_VAR` en `es_uri_sql` / `resolver_uri_sql` / `enmascarar_uri` (incluyendo enmascaramiento de parámetros sensibles en query strings como `password=`, `pwd=`, `secret=`, `token=`).
   - `sqlite3.Connection.set_authorizer` obligatorio tanto en archivos `.sqlite` como en carga y consulta de volcados `.sql` (con límite `MAX_BYTES_SQL_DUMP`).
   - `leer_archivo_sql` aplica `bloquear_duckdb_externo` al abrir `.duckdb`.
   - `leer_conexion_sql` añade parámetros opcionales retrocompatibles `timeout_segundos=30`, `requerir_tls=False`, `forzar_solo_lectura=True` y `rollback()` explícito al cerrar la conexión SQLAlchemy.
2. **Exportación y lectores de documentos (`motor/exportador.py`, `motor/factura_electronica.py`, `conectores/estado_cuenta_pdf.py`, `cuadra.py`):**
   - `exportar_excel`, `muestra` y `evaluar` sanitizan todos los DataFrames exportados a `.xlsx` y `.csv`.
   - `factura_electronica.py` valida XML y ZIP contra XXE, path traversal y bombas de compresión.
   - `estado_cuenta_pdf.py` valida tamaño total de PDF, descomprime flujos con `descomprimir_zlib_seguro`, usa `leer_miembros_zip_seguros` y evita colisiones/traversal con prefijo secuencial + `nombre_archivo_seguro`.
3. **Interfaz web local (`.streamlit/config.toml`, `iniciar.bat`, `app/inicio.py`):**
   - `address = "127.0.0.1"`, `enableCORS = false`, `enableXsrfProtection = true`, `gatherUsageStats = false`.
   - `_guardar` valida `nombre_archivo_seguro` y confirma que la ruta resuelta permanece dentro del directorio temporal seguro de la sesión.

---

## 3. Casos adversarios esperados (`tests/test_seguridad_hardening.py`)

| Vector probado | Entrada adversaria | Resultado esperado |
| :--- | :--- | :--- |
| Escape DuckDB Copiloto | `SELECT * FROM read_text('README.md')` directo en conexión | Rechazado por `PermissionException` en DuckDB y bloqueado antes por `validar_consulta_solo_lectura` (`ErrorSeguridad`) |
| Evasión SQL | Comentarios anidados `/* /* */ */ DROP TABLE mayor`, `$$a$$`, `getenv('PATH')`, `SELECT * INTO t` | Rechazado con `ErrorSeguridad` |
| SQLite dump hostil | `.sql` con `ATTACH DATABASE` o `CREATE TRIGGER` | Rechazado en `_cargar_dump_sql_en_memoria` |
| Credencial en URI | `env:TEST_FOLIO_SQL_URI` + URI con `user:pass@` y `?password=abc` | `enmascarar_uri` oculta secreto y preserva `env:...` |
| Comillas en columna CSV | Encabezado `nota"mal` importado | Se importa sin error SQL gracias a `citar_identificador_sql` |
| Fórmula Excel (CWE-1236) | `=1+1`, `+CMD\|' /C calc'!A0`, `-2+3`, `@SUM(1+1)`, `\t=1+1` | Celda en `.xlsx` queda como tipo texto `"s"` con prefijo `'` |
| XML XXE / Billion Laughs | XML con `<!DOCTYPE foo [<!ENTITY ...>]>` | `ErrorSeguridad` en `leer_xml`; documentado en `lectura.errores` en `leer_facturas` |
| ZIP traversal / bomba | Miembro `../../evil.xml` o bomba > límite/ratio | `ErrorSeguridad` inmediato |
| PDF zlib bomb | Flujo `FlateDecode` que expande sobre el límite configurado | `ErrorSeguridad` |
| Colisión en ZIP PDF | `ene/estado.pdf` y `feb/estado.pdf` en un mismo ZIP | Se procesan ambos PDFs sin sobrescribirse |
| Configuración Web | Lectura de `.streamlit/config.toml`, `iniciar.bat` y `nombre_archivo_seguro("../x")` | Binding `127.0.0.1`, XSRF/CORS seguros, traversal rechazado |
