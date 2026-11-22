# Cambios

## 0.9.0 · Ciberseguridad Integral y Control de Acceso Dual (noviembre 2026)

- **Gobierno, modelo de amenazas y marcos (Oleada 0, Ficha 19):**
  - Modelo STRIDE sobre 6 vectores críticos y matriz viva de trazabilidad ([MATRIZ_MARCOS.md](docs/seguridad/MATRIZ_MARCOS.md)) mapeada a OWASP ASVS/CWE, NIST SSDF/CSF 2.0, ISO/IEC 27001/27037/27701, RFC 8032/3161, CycloneDX/SLSA, NIGC 1, NIA 220/230/500 y Ley 81 de Panamá.
- **Hardening técnico crítico (Oleada 1, Ficha 20 · `motor/seguridad.py`):**
  - Bloqueo e idempotencia en DuckDB (`enable_external_access = false`, `lock_configuration = true`), validador SQL ampliado con soporte de comentarios anidados y bloqueo de funciones externas, `sqlite3.set_authorizer` en lectura y dumps `.sql`, credenciales `env:VAR` + TLS/timeout + sesión `READ ONLY`, escape de identificadores SQL y formatos de fecha (`motor/importador.py`), neutralización CWE-1236 en cédulas Excel/CSV (`motor/exportador.py`), protección anti-XXE/DTD y anti-bombas ZIP/zlib (`motor/factura_electronica.py`, `conectores/estado_cuenta_pdf.py`), y aislamiento web local `127.0.0.1` + XSRF + temporales con limpieza `atexit`.
- **Criptografía Ed25519, RBAC, Login Dual y Sellado NIA 220/230 (Oleada 2, Ficha 21 · `motor/cripto.py`, `motor/usuarios.py`, `app/login_qt.py`):**
  - Ed25519 (RFC 8032) en Python puro, `hashlib.scrypt`, AES-256-GCM vía Windows CNG (`bcrypt.dll`) y Windows DPAPI (`crypt32.dll`).
  - Pantalla de inicio de sesión clásica Win32 `FOLIO AUDITOR` y login web con acceso diferenciado para **Administrador** (panel de usuarios, políticas y bitácora de accesos) y **Preparador / Auditor** (`Preparador`, `Revisor`, `Socio`), segregación estricta `Preparador ≠ Revisor ≠ Socio`, sellado cruzado `sello.json`, ventana de compilación NIA 230 de 60 días y comando `python cuadra.py verificar <carpeta>`.
- **Privacidad, bóveda cifrada y Ley 81 (Oleada 3, Ficha 22 · `motor/privacidad.py`):**
  - Bóveda cifrada `.folioenc` (`AES-256-GCM` + `scrypt`/DPAPI + AAD + borrado limpio), detección de carpetas en la nube (OneDrive/Dropbox/Drive), ACLs NTFS (`icacls`), anonimización PII panameña/LatAm, exportación de diagnóstico técnico sin datos confidenciales, retención programada y verificación de cero sockets salientes.
- **Cadena de suministro y confianza corporativa TI (Oleadas 4 y 5, Ficha 23 · `herramientas/seguridad_build.py`, `verificar_seguridad.ps1`, `docs/seguridad/`, `SECURITY.md`):**
  - Generador offline de SBOM **CycloneDX 1.5** (`docs/seguridad/sbom.cdx.json`), `requirements.lock`, `SHA256SUMS.txt`, analizador estático AST anti-código-inseguro/secretos, `empaquetar_exe.bat` con `pyinstaller==6.22.3` y flujo Authenticode SHA-256 + RFC 3161, más paquete documental corporativo TI y análisis de cumplimiento Ley 81 / LatAm.

## 0.8.0 · Fase 3: Revisión por roles (NIA 220/230), portafolio y empaquetador `.exe` (noviembre 2026)

- **Flujo de revisión y firmas por roles (`motor/revision.py`, Ficha 15):**
  - Roles `Preparador`, `Revisor` y `Socio`, estados por prueba (`Pendiente`, `En revisión`, `Aclarado con evidencia`, `Hallazgo confirmado`), registro de conclusiones de auditoría en `revisiones.json` + bitácora SHA-256, bloqueo definitivo al firmar el Socio, reapertura con motivo obligatorio y actualización automática de `cedula.xlsx` (columnas `Estado revisión`/`Revisado por` en `Resumen` y hoja `Revisiones y Firmas`).
- **Portafolio de encargos e historial (`motor/portafolio.py`):**
  - Carga y guardado de plantillas `encargos/*.yaml` desde UI, exploración de corridas históricas en `salidas/` con verificación SHA-256 en vivo y pestaña **Encargos y Firmas** integrada en Escritorio (`VistaPortafolioWidget`) y Web (`_render_portafolio_y_roles`).
- **Rutas portátiles y empaquetado Windows `.exe` (`motor/rutas.py`, `cuadra.spec`, `empaquetar_exe.bat`):**
  - Separación `raiz_recursos()` (`_MEIPASS`) y `raiz_trabajo()` para distribuir `dist\LibroAuditoria\LibroAuditoria.exe` en equipos Windows 100 % sin internet ni instalación previa de Python.
- **Confiabilidad contable, lector PDF multipárrafo y cédula Excel ejecutiva (`motor/diagnostico.py`, `motor/formato_excel.py`, Ficha 16):**
  - Eliminación de coerción silenciosa en `debito`/`credito` (`motor/importador.py`), guarda numérica en Benford (`motor/estadistica.py`), semáforo previo de integridad (`cuadre_diario`, `cuadre_balanza`, `claves_mayor`, `fechas_*`, `integridad_extracto`), unión de descripciones envueltas y cuadre `Saldo Inicial + Créditos - Débitos == Saldo Final` en `conectores/estado_cuenta_pdf.py`, estilización ejecutiva en `cedula.xlsx`, cierre seguro `closeEvent` en escritorio y 3 perfiles ERP Latam (`siigo-colombia`, `contpaqi-aspel-mx`, `softland-cr-latam`).
- **Identidad ejecutiva `Folio Auditor` y constancia en tiempo real (Ficha 17):**
  - Banda superior ejecutiva en Escritorio y Web con cliente activo, período auditado editable (`periodo_inicio` – `fecha_cierre`) y reloj en tiempo real local + UTC (`QTimer` / `@st.fragment(run_every="1s")`), además de sellos de emisión y encabezados/pies de impresión OOXML en `cedula.xlsx`.
- **Sistema visual de estación contable clásica Win32 y hoja de cálculo biselada (`app/componentes_qt.py`, `app/estilos.css`, Ficha 18):**
  - Adopción del sistema visual clásico Win32 / hoja de cálculo biselada en Escritorio (PySide6) y Web (Streamlit): superficie neutra `#D4D0C8`, biseles 3D elevado (`#FFFFFF`/`#404040`) y hundido (`#808080`/`#FFFFFF`), barra de título con gradiente clásico `#000080 -> #1084D0`, barra de fórmula y cuadro de nombres en pozos hundidos, rejilla ortogonal tipo libro `#C0C0C0` y paneles de barra de estado segmentados, conservando intactos los íconos 3D SVG/`QPainter`, la identidad `Folio Auditor` y la constancia en tiempo real.

## 0.7.0 · Cierre técnico de Fase 2: Bancos PDF y Copiloto SQL sin internet (noviembre 2026)

- **Estados de cuenta bancarios en PDF y paquete `bancos-conciliacion` (Ficha 13):**
  - Lector local 100 % sin internet en `conectores/estado_cuenta_pdf.py` (motor FlateDecode/PDF 1.4 en Python puro + respaldo `PySide6.QtPdf`) capaz de leer PDFs individuales, multipágina, carpetas, ZIP o archivos tabulares de bancos de Panamá (*Banco General, Banistmo, BAC Credomatic, Global Bank, Banco Nacional*).
  - 5 pruebas NIA 500/330 en `paquetes/bancos-conciliacion/`: continuidad aritmética de saldos corridos, duplicados en extracto, movimientos fuera de periodo, cargos/abonos bancarios no registrados en el mayor y partidas del mayor en tránsito (conciliación 1 a 1 determinista por monto y ventana temporal).
  - Generador sintético `generar_estado_cuenta_bancos()` y comando CLI `python cuadra.py ejemplo-bancos`.
- **Copiloto analítico en lenguaje natural y redactor NIA (Ficha 14):**
  - Nuevo módulo `ia/copiloto.py` (`proponer_consulta_sql`, `ejecutar_propuesta_aprobada`, `redactar_borrador_hallazgo`): traduce consultas en español a `SELECT`/`WITH` visible 100 % offline, exige validación de solo lectura y aprobación explícita del auditor antes de ejecutar en DuckDB y registra cada consulta aprobada en la bitácora encadenada SHA-256.
  - Nuevo comando `python cuadra.py copiloto --pregunta "..." --aprobar`.
- **Escritorio y Web:** nuevos módulos **Bancos PDF** y **Copiloto SQL** con iconografía 3D estilo Excel en la Cinta de Opciones (`app/escritorio.py`, `app/componentes_qt.py`, `app/inicio.py`, `app/estilos.css`).

## 0.6.0 · Fase 2, puntaje de riesgo y conectores del mercado de Panamá (noviembre 2026)

- **Puntaje de riesgo explicable por asiento (Ficha 11):** suma ponderada de los 10 criterios
  en `asientos-nia240` (`asientos-puntaje`), clasificación en niveles `alto`/`medio`/`bajo`,
  explicación legible por asiento y personalización de pesos/umbrales desde el encargo o la interfaz.
- **Estudio del mercado de Panamá (`docs/ESTUDIO_MERCADO_PANAMA.md`) y Ficha 12:** 10 perfiles ERP en
  `conectores/perfiles/` (`sap-ecc-s4`, `sap-b1`, `softland-exactus`, `sage50-peachtree`, `quickbooks`,
  `odoo`, `dynamics`, `netsuite`, `alegra-interfuerza`, `monica-saint`) con autodetección y consultas SQL.
- **Ingesta multiformato y SQL de solo lectura (`conectores/sql_fuente.py`, `motor/importador.py`):**
  SAP ALV (`|`), indicador Debe/Haber (`SHKZG` `S`/`H` y equivalentes), fechas `YYYYMMDD` / `MM/DD/YY`,
  `UTF-16`, `.tsv`, `.parquet`, `.json`/`.jsonl`, `.sqlite`/`.duckdb`/`.sql` y conexiones SQL (`SELECT`/`WITH`)
  con enmascaramiento de credenciales y generación explícita opcional de `linea` y `usuario`.
- **Programa nativo de escritorio (PySide6, 100 % sin internet):** `app/escritorio.py` y `app/componentes_qt.py` con Cinta de Opciones e iconos 3D estilo Excel ejecutivo, lectura directa de archivos pesados desde disco sin copia en red, tablas virtualizadas (`QAbstractTableModel`) con barra de datos en puntaje de riesgo, diálogo de vista previa/mapeo ERP, extractor SQL y exportación directa de cédula Excel. `iniciar.bat` abre por defecto la aplicación de escritorio (`iniciar.bat web` conserva la interfaz Streamlit) y se agrega `python cuadra.py escritorio`.
- **Interfaz Web y CLI:** pestaña **Conectores ERP / SQL**, Cinta de Opciones con iconografía 3D ejecutiva, soporte de carga pesada (hasta 4 GB y lectura directa sin copia), configuración opcional de pesos, tabla de puntaje con barra de progreso y comando `python cuadra.py conectores`.
- 89 pruebas pasando en Windows (Python 3.12).

## 0.5.0 · Fase 2, factura electrónica de la DGI (noviembre 2026)

- Lector de XML de factura electrónica (`motor/factura_electronica.py`): carpeta, ZIP o XML suelto;
  ignora espacios de nombres; los XML ilegibles se reportan sin detener la lectura.
- Paquete `ventas-fe` 0.1.0 (Ficha 10): resumen por tipo de documento, totales inconsistentes,
  CUFE repetido, huecos de numeración por tipo y punto de facturación, documentos fuera del periodo,
  ambiente de pruebas y conciliación mensual de ventas del mayor contra lo facturado
  (sin repetir CUFE, notas de crédito restando).
- Dataset sintético de 300 facturas con 7 anomalías sembradas; comando `ejemplo-fe`; carga de ZIP o XML en la interfaz.
- 64 pruebas.

## 0.4.0 · Fase 1 completa en lo técnico (noviembre 2026)

- Interfaz para el auditor (`iniciar.bat` o `streamlit run app/inicio.py`): datos del encargo,
  carga de archivos con vista previa, detección de hoja, fila de encabezado y Debe/Haber,
  columnas sugeridas que el auditor confirma, resultados en pantalla y descarga de la cédula.
  Pestaña de muestreo MUS: selección y evaluación.
- Evaluación de muestras MUS (Ficha 05b) y comando `evaluar`.
- Servicio único (`motor/servicio.py`) que usan la línea de comandos y la interfaz.
- Sugerencia de columnas por reglas (`motor/sugerencias.py`), sin IA; la IA llegará en la Fase 2.
- Feriados 2025 con fuente por fecha. 58 pruebas.

## 0.3.0 · Fase 1, MVP de asientos de diario (noviembre 2026)

- Paquete `asientos-nia240` 0.1.0: mayor contra balanza (Ficha 07), estratificación por materialidad (Ficha 06),
  sumarización por rubro con regla por prefijo y mapeo del cliente (Ficha 09), diez criterios de riesgo por asiento,
  selección sugerida y muestra impredecible con semilla (Ficha 04).
- Archivo de encargo (`encargos/*.yaml`): materialidad, materialidad de ejecución, umbral trivial, fecha de cierre,
  umbral de aprobación y demás parámetros, aplicados a todas las pruebas.
- Varios archivos por encargo: `--archivo mayor=... --archivo balanza=...`; pruebas que se omiten con aviso si falta un archivo opcional.
- Muestreo (Ficha 05): MUS con factores de confianza 3.00 (95 %) y 2.31 (90 %), selección sistemática con inicio
  aleatorio o explícito, y aleatorio simple repetible. Comando `muestra`.
- Cédula: hoja del encargo, columna de conclusión del auditor y detalle por criterio.
- Puerta de Fase 1: 3 datasets con resultados idénticos a los esperados (estándar, exportación de ERP difícil y MUS a mano). 48 pruebas.

## 0.2.0 · Fase 0, ciclo de estrés (noviembre 2026)

Tres rondas contra archivos realistas; de 3 de 8 variantes correctas a 8 de 8, más 9 de 9 casos borde.

- Importación: detecta UTF-8 o Windows-1252; quita BOM y espacios de encabezados; lee todo como texto y normaliza.
- Montos: separador de miles, coma decimal, símbolos de moneda, negativos entre paréntesis o con signo al final (SAP).
- Fechas: ISO, con hora, dd/mm/aaaa y otros; si son ambiguas (día y mes menores o iguales a 12) detiene la importación y pide el formato.
- Excluye filas sin fecha ni asiento (totales, líneas en blanco) y las reporta con su monto.
- Débito y crédito en columnas separadas (--debito-credito); hoja de Excel (--hoja); filas de título (--saltar-filas).
- Asientos alfanuméricos: gaps por prefijo (AS-, NC-).
- Calendario de feriados de Panamá 2025 y 2026 como tabla auxiliar del paquete; la prueba de días sin registros los excluye.
- Benford avisa cuando la muestra es menor al mínimo configurado (1,000 por defecto, criterio ajustable).
- Hoja "Control de archivos" con filas excluidas, codificación, formato de fecha y transformaciones.
- 34 pruebas automáticas; 500 mil líneas se importan y analizan en unos 2.4 segundos (medido en el entorno de desarrollo).

## 0.1.0 · Fase 0 (noviembre 2026)

- Estructura del repositorio: motor, paquetes, conectores, ia, app, docs y tests.
- Motor: importación de CSV y Excel con SHA-256 y totales de control (Ficha 00).
- Bitácora de evidencia JSONL con cadena de hashes que detecta alteraciones.
- Paquete `excepciones-basicas` 0.1.0: Benford 1 y 2 dígitos (Ficha 01),
  duplicados exactos y mismo-mismo-distinto (Ficha 02), gaps en asientos y fechas (Ficha 03).
- Exportación de la cédula a Excel con resumen, control de archivos y bitácora.
- Generador de mayor sintético con anomalías sembradas.
- 14 pruebas automáticas contra resultados calculados a mano.
