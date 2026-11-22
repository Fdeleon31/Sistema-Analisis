# Ficha 12 · Conectores ERP del mercado panameño y fuentes SQL/multiformato

**Fecha:** noviembre 2026  
**Módulos:** `conectores/`, `motor/importador.py`, `motor/sugerencias.py`, `motor/servicio.py`, `cuadra.py`, `app/inicio.py`  
**Principio rector:** *Nada se corrige en silencio.* Toda normalización, limpieza de formato SAP, aplicación de indicador D/H, generación de consecutivo de línea o asignación de usuario por defecto queda explícitamente registrada en `control["transformaciones"]` y en la bitácora encadenada.

---

## 1. Objetivo

Permitir que Cuadra ingeste de forma uniforme, reproducible y auditada datos contables (Mayor General / Libro Diario y Balanza) provenientes tanto de los 10 sistemas contables/ERP más utilizados en Panamá como de bases de datos SQL y formatos analíticos modernos, sin romper el principio de control ni requerir scripts ad-hoc por cliente.

---

## 2. Formatos y fuentes soportados

### 2.1 Archivos tabulares y reportes ERP
- **Texto delimitado:** `.csv`, `.tsv`, `.tab`, `.dat`, `.txt` (coma, punto y coma, tabulador, barra vertical `|`).
- **Hojas de cálculo:** `.xlsx`, `.xlsm`, `.xls` (selección de hoja y filas de título previas al encabezado).
- **SAP ALV (`|`):** archivos de texto exportados desde transacciones SAP (`FBL3N`, `FAGLL03`, `SE16N`) con bordes `|col1|col2|` y filas separadoras `---+---`.
- **Codificaciones detectadas:** `UTF-8`, `UTF-8 con BOM`, `UTF-16 LE/BE` (con BOM), y `Windows-1252` (`cp1252`).

### 2.2 Formatos analíticos modernos
- **Apache Parquet:** `.parquet` (lectura directa vía DuckDB `read_parquet`).
- **JSON / JSON Lines:** `.json`, `.jsonl`, `.ndjson` (lectura directa vía DuckDB `read_json_auto`).

### 2.3 Fuentes SQL (solo lectura garantizada)
- **Archivos de base de datos:** `.sqlite`, `.sqlite3`, `.db` (SQLite abierto en modo `ro`), `.duckdb` (DuckDB en `read_only=True`).
- **Volcados SQL (`.sql`):** cargados en una instancia `sqlite3` en memoria tras sanitización estricta de dialectos (solo `CREATE TABLE` e `INSERT INTO`, rechazando instrucciones de sistema o destructivas).
- **Conexiones SQL directas (URI):** `sqlite:///...` nativo (sin dependencias extras), y `postgresql://`, `mssql+pyodbc://`, `mysql+pymysql://`, `oracle+...://` vía SQLAlchemy cuando el driver esté instalado.
  - **Seguridad:** `validar_consulta_solo_lectura` exige consultas que inicien en `SELECT` o `WITH`, rechaza múltiples sentencias (`;`) y bloquea palabras clave de escritura/administración (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `REPLACE`, `MERGE`, `EXEC`, `EXECUTE`, `GRANT`, `REVOKE`, `ATTACH`, `DETACH`, `PRAGMA`, `COPY`, `CALL`, `VACUUM`, `LOAD`, `INSTALL`).
  - **Privacidad en bitácora:** cualquier credencial en la URI se enmascara (`usuario:***@host`) antes de registrarse en `control["archivo"]` y en `bitacora.jsonl`.

---

## 3. Reglas de normalización explícita

1. **Limpieza SAP ALV:** Si las primeras líneas no vacías empiezan y terminan con `|`, el importador limpia la estructura pipe en un archivo temporal UTF-8, omite líneas decorativas (`^[\|\-\+\=\s]+$`) y registra en `transformaciones` la limpieza y el conteo de líneas separadoras omitidas.
2. **Indicador Debe/Haber (`indicador_dc`):**
   - Incompatible con `debito_credito` (si se pasan ambos, falla con `ErrorImportacion`).
   - Normaliza primero la columna `monto`.
   - Valida que todo valor no vacío en la columna indicadora pertenezca a débito (`S`, `D`, `DR`, `DEBE`, `DEBITO`, `DEBIT`, `+`) o crédito (por defecto `H`, `C`, `CR`, `HABER`, `CREDITO`, `CREDIT`, `-` o los definidos en el perfil). Ante cualquier valor desconocido, se detiene y lanza `ErrorImportacion`.
   - Aplica signo negativo a los créditos y positivo a los débitos, registrando el cambio en `transformaciones`.
3. **Montos ya numéricos:** Cuando el origen es Parquet, SQLite, DuckDB o JSON con tipos numéricos nativos (`INT`, `BIGINT`, `DECIMAL`, `DOUBLE`, `FLOAT`), se realiza conversión directa a `DECIMAL(18, 2)` sin aplicar expresiones de texto sobre separadores decimales.
4. **Fechas extendidas:** Se agregan a `FORMATOS_FECHA`: `%Y%m%d`, `%m/%d/%y`, `%Y.%m.%d`, `%m-%d-%Y`. Se conserva la detección de ambigüedad entre pares día/mes y mes/día (`%d/%m/%Y` vs `%m/%d/%Y`, `%d/%m/%y` vs `%m/%d/%y`, `%d-%m-%Y` vs `%m-%d-%Y`).
5. **Síntesis explícita de `linea` y `usuario`:**
   - Si `generar_linea=True` y falta la columna `linea`, se genera mediante `ROW_NUMBER() OVER (PARTITION BY "asiento")` y se registra `"linea: generada secuencialmente por asiento"` en `transformaciones`.
   - Si `usuario_por_defecto` se indica y falta la columna `usuario`, se crea con ese valor literal y se registra en `transformaciones`.
   - Si no se activan explícitamente, el importador mantiene el rechazo cuando falte alguna columna requerida.

---

## 4. Perfiles ERP en `conectores/perfiles/*.yaml`

Cada perfil YAML documenta:
- `id`, `nombre`, `segmento_panama`, `descripcion`, `motor_origen`, `formatos_frecuentes`.
- `aliases`: diccionario `{columna_estandar: [alias_erp...]}`.
- `debito_credito_pares`: lista ordenada de pares `[col_debito, col_credito]` priorizando moneda local antes que extranjera.
- `indicador_dc`: `{columnas: [...], valores_credito: [...]}` cuando aplica (ej. SAP `SHKZG`).
- `separador_decimal`, `formato_fecha`, `generar_linea_si_falta`, `usuario_defecto_si_falta`.
- `consultas_sql`: plantillas `SELECT` de solo lectura documentadas desde esquemas públicos.

### Perfiles incluidos
1. `sap-ecc-s4` — SAP ECC / S/4HANA (`BKPF`/`BSEG`/`ACDOCA`, `FBL3N`)
2. `sap-b1` — SAP Business One (`OJDT`/`JDT1`)
3. `softland-exactus` — Softland ERP / Exactus (`DIARIO`/`CUENTA_CONTABLE`)
4. `sage50-peachtree` — Sage 50 / Peachtree
5. `quickbooks` — Intuit QuickBooks (Desktop / Online)
6. `odoo` — Odoo (`account.move.line`)
7. `dynamics` — Microsoft Dynamics (GP `GL20000` y Business Central `G/L Entry`)
8. `netsuite` — Oracle NetSuite (GL Detail / Saved Search)
9. `alegra-interfuerza` — Alegra e InterFuerza (Cloud Panamá)
10. `monica-saint` — Mónica y Saint (Comercios tradicionales)

### Algoritmo de autodetección (`detectar_perfil`)
Compara las columnas del archivo contra los alias normalizados de cada perfil (priorizando coincidencia exacta normalizada y pares D/C o indicadores D/H específicos). Devuelve el perfil con mayor puntaje si alcanza al menos 3 columnas reconocidas (o un indicador/par específico del ERP más al menos 2 columnas); en caso contrario devuelve `(None, 0)` para archivos genéricos.

---

## 5. Casos esperados de verificación

Partiendo del mayor sintético de `tests/archivos_realistas.py` (4,994 líneas, suma neta `0.0`, gaps de asientos `[[1500, 1502], [2200, 2200]]`, 4 filas en `duplicados-exactos`, 2 filas en `mismo-mismo-distinto` y gap de fecha `2025-07-15`), todas las variantes deben arrojar exactamente los mismos resultados al correr `excepciones-basicas`:
1. SAP ECC / FBL3N ALV pipe `.txt` con `SHKZG` (`S`/`H`) y `BUDAT` `YYYYMMDD`.
2. SAP Business One `.sqlite` con `OJDT` + `JDT1` consultado vía `SELECT ... JOIN`.
3. Softland / Exactus `.sql` dump con `DIARIO` y `DEBITO_LOCAL`/`CREDITO_LOCAL`.
4. Sage 50 / Peachtree `.csv` (`MM/DD/YY`, `Debit Amt`/`Credit Amt`, sin `linea` ni `usuario`).
5. QuickBooks `.csv` (`DOCNUM`, `MM/DD/YYYY`, `AMOUNT`, sin `linea`).
6. Odoo `.parquet` (`debit`/`credit`, sin `linea`).
7. Microsoft Dynamics GP `.duckdb` (`GL20000` con `DEBITAMT`/`CRDTAMNT`).
8. Alegra / InterFuerza `.jsonl` (`Débito`/`Crédito`, sin `linea` ni `usuario`).
9. Exportación `UTF-16` delimitada por tabuladores (`.tsv`).
10. Rechazo seguro ante indicador D/H desconocido, bloqueo de sentencias SQL de escritura/sistema y enmascaramiento de credenciales en URIs SQL.

---

## 6. Fuentes públicas consultadas (Sala limpia)

- **SAP Help Portal & SAP Community:** estructuras públicas de `BKPF`, `BSEG`, `ACDOCA` (`SHKZG`, `DRCRK`, `BELNR`, `BUZEI`, `BUDAT`, `HKONT`, `DMBTR`, `USNAM`) y `OJDT`/`JDT1` en SAP Business One (`TransId`, `Line_ID`, `RefDate`, `Account`, `Debit`, `Credit`).
- **Microsoft Learn:** documentación pública de Microsoft Dynamics 365 Business Central (`Table 17 G/L Entry`) y Microsoft Dynamics GP (`GL20000` Year-to-Date Transaction Open).
- **Odoo Documentation & OCA:** esquema público del modelo `account.move.line` y nombres de exportación estándar.
- **Intuit QuickBooks Public Docs:** especificaciones públicas de exportación/importación de asientos de diario (`.IIF`/CSV).
- **Sage 50 (Peachtree) Public Support & Accountant's Guides:** columnas estándar de exportación del Libro Mayor.
- **Oracle NetSuite Public Help:** columnas estándar de *General Ledger Detail* y *Saved Searches*.
- **Softland / Exactus:** diccionario de datos y consultas públicas del módulo de Contabilidad General (`DIARIO`, `CUENTA_CONTABLE`).
- **DuckDB & Python SQLite3 Documentation:** lectura de Parquet, JSON, DuckDB read-only y SQLite URI mode `ro`.
