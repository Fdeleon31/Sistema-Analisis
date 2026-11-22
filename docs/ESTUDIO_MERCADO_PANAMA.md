# Estudio del mercado contable y de sistemas ERP en Panamá (2025–2026)

**Proyecto:** Cuadra — Analítica de auditoría  
**Propósito:** Adaptar la capa de ingesta, mapeo y conectores SQL/multiformato de Cuadra a la realidad operativa de las firmas de auditoría y empresas en Panamá (regla de sala limpia: basado únicamente en documentación pública y estándares abiertos).

---

## 1. Contexto contable, fiscal y tecnológico de Panamá

El mercado panameño presenta particularidades únicas en Latinoamérica que impactan directamente la forma en que los sistemas contables exportan su Libro Diario, Mayor General y Balanza de Comprobación:

1. **Economía dolarizada y bimonetaria (USD / PAB 1:1):** Aunque la moneda de curso legal y funcional suele ser el dólar estadounidense (`USD`) en paridad 1:1 con el balboa (`PAB`, abreviado `B/.`), los ERP locales y regionales (como Softland/Exactus o SAP Business One) almacenan con frecuencia columnas duales (`LOCAL` vs. `DOLAR` o `DMBTR` vs. `WRBTR`), y las exportaciones de Excel/CSV mezclan prefijos como `B/.`, `US$`, `$` o `USD`.
2. **Cumplimiento fiscal ante la DGI (SFEP / PAC e ITBMS):** La adopción del Sistema de Factura Electrónica de Panamá (SFEP) a través de Proveedores Autorizados Calificados (PAC) o el Facturador Gratuito ha impulsado una ola de modernización hacia ERP en la nube (Alegra, InterFuerza, Odoo) y conectores locales en ERP globales (SAP, Dynamics, NetSuite), manteniendo el control de ITBMS (7 % general y tasas especiales) y formularios DGI (430/4331).
3. **Planilla local (CSS / SIPE y Código de Trabajo):** Las empresas medianas y grandes suelen preferir ERP con localización de planilla panameña (Softland, InterFuerza) o mantener sistemas de contabilidad tradicionales conectados a módulos locales de nómina.
4. **Hibridación regional de formatos de fecha y decimales:**
   - Software de origen estadounidense muy arraigado en Panamá (Sage 50/Peachtree, QuickBooks, Dynamics GP) exporta fechas en `MM/DD/YYYY` o `MM/DD/YY` con punto decimal.
   - Software latinoamericano o europeo localizado (Softland, Alegra, InterFuerza, Odoo, Mónica, Saint) exporta `DD/MM/YYYY` (a veces con coma decimal y `;` como delimitador en configuraciones regionales en español).
   - SAP ECC / S/4HANA exporta `YYYYMMDD` o `DD.MM.YYYY`, montos con signo negativo al final (`1,500.00-`) y reportes ALV delimitados por barras verticales (`|`) en codificación `UTF-16` o `Windows-1252` (`cp1252`).
5. **Restricciones de datos incompletos en PYMES:** Muchos reportes estándar exportados desde Sage 50, QuickBooks, Alegra, InterFuerza o Mónica omiten un número consecutivo de línea (`linea`) y, en planes básicos o reportes resumidos, omiten la columna de usuario (`usuario`). Para no bloquear al auditor ni corregir en silencio, Cuadra debe permitir sintetizar explícitamente estos campos con registro completo en la bitácora y en la hoja `Control de archivos`.

---

## 2. Segmentación del mercado en Panamá

### 2.1 Segmento Corporativo, Multinacionales, Banca y Zona Libre de Colón

| Sistema / ERP | Presencia y uso en Panamá | Arquitectura / Fuente de datos | Particularidades técnicas de exportación |
| --- | --- | --- | --- |
| **SAP S/4HANA y SAP ECC (FI-GL)** | Estándar dominante en multinacionales (SEM), banca, telecomunicaciones, energía, Canal/logística y grandes grupos económicos. | Tablas `BKPF` (encabezado), `BSEG` (segmentos) y `ACDOCA` (Universal Journal en S/4HANA). Exportaciones vía transacciones `FBL3N`, `FAGLL03` o `SE16N`. | Columnas técnicas (`BELNR`, `BUZEI`, `BUDAT`, `HKONT`/`RACCT`, `SGTXT`, `DMBTR`/`HSL`, `USNAM`). Indicador Debe/Haber `SHKZG` (`S`=Debe, `H`=Haber) o `DRCRK` con monto sin signo o signo al final (`1,500.00-`). Archivos `.txt` ALV con delimitador `\|`, bordes `---+---` y a menudo codificación `UTF-16`. Fechas `YYYYMMDD` o `DD.MM.YYYY`. |
| **SAP Business One (SAP B1)** | Muy fuerte en empresas medianas-altas, distribuidoras, importadoras de Zona Libre y grupos comerciales en expansión. | SQL Server o SAP HANA. Tablas `OJDT` (encabezado de asiento), `JDT1` (líneas), `OACT` (plan de cuentas), `OUSR` (usuarios). | Campos `TransId`, `Line_ID`, `RefDate`, `Account`, `LineMemo`, `Debit`, `Credit`, `UserSign`/`U_NAME`. Distingue `Debit`/`Credit` en moneda local frente a `FCDebit`/`FCCredit` (moneda extranjera). |
| **Softland ERP / Exactus** | Uno de los líderes indiscutibles en empresa mediana y corporativo local centroamericano/panameño por su localización nativa (DGI, ITBMS, CSS/SIPE). | SQL Server (`dbo.DIARIO` / `ASIENTO_DE_DIARIO`, `CUENTA_CONTABLE`). También exportación a Excel/CSV con encabezados en español. | Campos `ASIENTO`/`NUMERO_COMPROBANTE`, `CONSECUTIVO`/`LINEA`, `FECHA`, `CUENTA_CONTABLE`, `REFERENCIA`/`CONCEPTO`/`GLOSA`, columnas duales `DEBITO_LOCAL`/`CREDITO_LOCAL` y `DEBITO_DOLAR`/`CREDITO_DOLAR`. |
| **Microsoft Dynamics (GP y D365 Business Central)** | Dynamics GP tiene amplia base instalada en empresas tradicionales medianas y financieras; Business Central crece en adopción cloud. | GP sobre SQL Server (`GL20000` año abierto, `GL30000` histórico, `GL00105` índice de cuenta). Business Central vía OData/Excel (`Table 17 G/L Entry`). | GP: `JRNENTRY`, `SEQNUMBR`, `TRXDATE`, `ACTNUMST`/`ACTINDX`, `REFRENCE`, `DEBITAMT`, `CRDTAMNT`, `USWHPSTD`. BC: `Document No.`, `Entry No.`, `Posting Date`, `G/L Account No.`, `Description`, `Debit Amount`, `Credit Amount`, `User ID`. |
| **Oracle NetSuite** | Corporativos multilatinos, tecnología, servicios y empresas regionales 100 % en la nube. | Exportación CSV/Excel desde *General Ledger Detail* o *Saved Searches* (Tipo Transaction). | Columnas `Document Number`/`Internal ID`, `Line ID`, `Date`, `Account`, `Memo`, `Amount (Debit)`/`Amount (Credit)` o `Amount`, `Created By`. A menudo omite el número de línea si no se incluye en el *Saved Search*. |

### 2.2 Segmento PYME, Comercios y Contadores Independientes

| Sistema / ERP | Presencia y uso en Panamá | Arquitectura / Fuente de datos | Particularidades técnicas de exportación |
| --- | --- | --- | --- |
| **Sage 50 / Peachtree** | Históricamente el software de escritorio más difundido entre PYMES panameñas, comercios e importadores y despachos contables tradicionales. | Base propietaria Btrieve/Pervasive; entrega al auditor mediante CSV o Excel del *General Ledger* / *General Journal*. | Columnas `Reference`/`Trans No`/`Journal Reference`, `Date` (frecuentemente `MM/DD/YY` o `MM/DD/YYYY`), `Account ID`/`General Ledger ID`, `Description`/`Trans Description`, `Debit Amt`/`Credit Amt` o `Amount`. Frecuentemente sin columna `linea` ni `usuario`. |
| **QuickBooks (Desktop y Online)** | Muy usado en PYMES de servicios, empresas con matriz/clientes en EE. UU., zonas francas y profesionales independientes. | Exportación CSV/Excel de *Journal* o *General Ledger* (`.iif` / `.csv` / `.xlsx`). | Columnas `DOCNUM`/`Num`/`Trans #`, `DATE`, `ACCNT`/`Account`, `MEMO`/`Memo/Description`, `DEBIT`/`CREDIT` o `AMOUNT`, `CREATED BY`/`User`. Suele carecer de consecutivo de línea (`linea`). |
| **Odoo** | Crecimiento acelerado en PYMES modernas y distribuidoras gracias a partners locales con módulos PAC de DGI. | PostgreSQL (`account_move`, `account_move_line`, `account_account`, `res_users`) o exportación directa CSV/Excel de apuntes contables. | Nombres técnicos (`move_id/name`, `date`, `account_id/code`, `name`, `debit`, `credit`, `create_uid`) o traducidos al español (`Asiento contable`, `Fecha`, `Cuenta`, `Etiqueta`, `Debe`, `Haber`, `Creado por`). No expone `linea` explícita en la vista estándar de exportación. |
| **Alegra e InterFuerza** | Líderes nativos en la nube para PYMES en Panamá por su integración directa con PAC/DGI y (en InterFuerza) planilla local. | SaaS en la nube; exportación a Excel/CSV de libro diario y movimientos contables. | Encabezados en español (`Comprobante`/`No. Asiento`, `Fecha`, `Código cuenta`/`Cuenta Contable`, `Observaciones`/`Detalle`, `Débito`, `Crédito`, `Usuario`/`Creado por`). Suelen omitir `linea` y, en exportaciones resumidas, `usuario`. |
| **Mónica y Saint** | Comercios minoristas, ferreterías, distribuidoras locales tradicionales y contadores de pequeña empresa. | Aplicaciones de escritorio/red local; exportación a Excel/CSV/TXT. | Codificación frecuente `Windows-1252` (`cp1252`), fechas `DD/MM/YYYY`, columnas `Debe`/`Haber` o `Débito`/`Crédito`, frecuentemente sin `linea` y sin `usuario`. |

### 2.3 Fuentes de datos modernas y extracción directa por TI

En auditorías con equipos de TI o extracciones directas del departamento de sistemas (Especialistas de Datos / IT Audit), es común recibir:
- **Bases de datos portables:** SQLite (`.sqlite`, `.sqlite3`, `.db`), DuckDB (`.duckdb`) y volcados SQL (`.sql`) generados desde MySQL/MariaDB, PostgreSQL o SQL Server.
- **Conexiones SQL de solo lectura:** Consultas `SELECT` directas contra SQL Server (Softland, SAP B1, Dynamics GP), PostgreSQL (Odoo) o MySQL/MariaDB mediante cadena de conexión estándar.
- **Formatos analíticos e intercambio:** Apache Parquet (`.parquet`), JSON / JSON Lines (`.json`, `.jsonl`, `.ndjson`), TSV / archivos separados por tabulador en `UTF-16` (`.tsv`, `.tab`, `.dat`).

---

## 3. Matriz de brechas técnicas y soluciones en Cuadra

| Brecha detectada en el mercado de Panamá | Solución implementada en Cuadra (Fase 2 · Ficha 12) |
| --- | --- |
| Reportes SAP ALV en `.txt` delimitados por `\|`, con líneas separadoras `---+---` y espacios alrededor de celdas | Preprocesamiento explícito `_limpiar_sap_alv` en `motor/importador.py` con registro en `control["transformaciones"]` y `detectar_fila_encabezado` adaptado a pipes. |
| Indicador Debe/Haber (`SHKZG`: `S`/`H` o `DRCRK` o `D/C`) en lugar de monto con signo o dos columnas | Nuevo parámetro `indicador_dc` en `importar` + `sugerir_indicador_dc` en `motor/sugerencias.py`. Valida todos los valores y se detiene ante códigos desconocidos. |
| Fechas SAP (`YYYYMMDD`), US corto (`MM/DD/YY`), punto europeo (`YYYY.MM.DD`) y guion US (`MM-DD-YYYY`) | Ampliación de `FORMATOS_FECHA` en `motor/importador.py`, preservando la regla estricta de detención ante fechas ambiguas (`dd/mm` vs `mm/dd`). |
| Exportaciones Unicode de Excel / SAP / SQL BCP en `UTF-16` | Detección de BOM `UTF-16 LE/BE` y `UTF-8 BOM` en `detectar_codificacion`. |
| Pares de columnas débito/crédito complejos (`Debit Amt`/`Credit Amt`, `DEBITO_LOCAL`/`CREDITO_LOCAL`, `DEBITAMT`/`CRDTAMNT`, `Amount (Debit)`/`Amount (Credit)`) | `sugerir_debito_credito` mejorado para distinguir moneda local vs extranjera (`FCDebit`) y emparejar alias de cada ERP. |
| Ausencia de `linea` o `usuario` en exportes de Sage 50, QuickBooks, Odoo, Alegra, InterFuerza, Mónica y Saint | Parámetros explícitos `generar_linea=True` (`ROW_NUMBER() OVER (PARTITION BY asiento)`) y `usuario_por_defecto` con confirmación del auditor y registro obligatorio en `control["transformaciones"]` y bitácora. Nunca se inventa ni se rellena en silencio. |
| Entrega de extracciones SQL (`.sqlite`, `.duckdb`, `.sql`) o conexiones directas a BD del ERP | Módulo `conectores/sql_fuente.py` con validación estricta de **solo lectura** (`SELECT`/`WITH`), enmascaramiento de contraseñas en URIs y huella SHA-256 determinista. |
| Archivos grandes analíticos (`.parquet`, `.json`, `.jsonl`, `.tsv`) | Lectura directa en DuckDB manteniendo normalización de montos ya numéricos, fechas y totales de control. |
| Conocimiento disperso de nombres de columnas por ERP | Catálogo de 10 perfiles YAML en `conectores/perfiles/` + autodetección automática (`detectar_perfil`) + consultas SQL de extracción listas en `cuadra.py conectores` y en la pestaña UI **"Conectores Panamá y SQL"**. |
