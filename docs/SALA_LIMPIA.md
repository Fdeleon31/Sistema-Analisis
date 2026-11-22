# Reglas de sala limpia

Cuadra se desarrolla de forma independiente. Las especificaciones viven en el
cuaderno de sala limpia (documento aparte, con fecha por ficha).

1. Cada función parte de una ficha escrita con palabras propias desde fuentes públicas.
2. No se copia nada de la ayuda, pantallas, scripts ni archivos de otros productos.
3. No se descompila ni se inspecciona el formato interno de ningún software comercial.
4. Se programa desde la ficha, nunca mirando otro producto al mismo tiempo.
5. Cada ficha tiene casos de prueba con resultado esperado calculado a mano.
6. Solo datos sintéticos. Nada de datos de clientes ni archivos de empleadores.
7. Desarrollo en tiempo, equipo y cuentas personales.
8. El historial de git es parte de la evidencia: commits frecuentes y con mensajes claros.

## Fuentes públicas usadas

- Nigrini, M. J. (2012). *Benford's Law: Applications for Forensic Accounting,
  Auditing, and Fraud Detection*. Wiley. Tabla 7.1 (umbrales MAD) y estadístico Z.
- Documentación de DuckDB: lectura de CSV, funciones de ventana, `generate_series`.
- Documentación de Python: `hashlib` (SHA-256).
- Calendario de feriados de Panamá: Código de Trabajo, art. 46; calendario oficial 2026 publicado en prensa
  (La Estrella de Panamá, 11/12/2025; Telemetro, 2026). Ver `paquetes/excepciones-basicas/calendario/feriados_pa.csv`.
- NIA 240 (revisada), apéndice sobre selección de asientos y otros ajustes (texto publicado por el MIA, 2025).
- PCAOB AU 316.61: características de asientos inapropiados (sin descripción, sin número de cuenta, montos redondos).
- AICPA Audit Sampling Guide, apéndice C: factores de confianza de MUS para cero errores (3.00 con 95 %, 2.31 con 90 %).
- Factura electrónica de Panamá: ficha técnica publicada por la DGI (portal de factura electrónica);
  nombres de campos en ejemplos públicos de XML (Siteck); tipos de documento en Microsoft Learn (localización de Panamá).
- Ficha 11 (puntaje de riesgo explicable): NIA 240 (revisada) y PCAOB AU 316.61 como base de los criterios de riesgo; ponderación por defecto y umbrales definidos por juicio profesional propio y configurables por encargo. Ver `docs/fichas/FICHA_11_puntaje_riesgo.md`.
- Ficha 12 (conectores ERP del mercado panameño y fuentes SQL/multiformato): documentación pública de SAP (`BKPF`/`BSEG`/`ACDOCA` y SAP B1 `OJDT`/`JDT1`), Microsoft Learn (Dynamics BC `G/L Entry` y GP `GL20000`), Odoo (`account.move.line`), QuickBooks, Sage 50, NetSuite, Softland/Exactus, DuckDB y SQLite. Ver `docs/ESTUDIO_MERCADO_PANAMA.md` y `docs/fichas/FICHA_12_conectores_panama.md`.
- Ficha 13 (estados de cuenta bancarios en PDF y conciliación): NIA 500, NIA 330, NIA 240 y especificación pública ISO 32000-1 (PDF FlateDecode y operadores de texto) para lectura local offline de extractos bancarios de Panamá. Ver `docs/fichas/FICHA_13_bancos_conciliacion.md`.
- Ficha 14 (copiloto en lenguaje natural y redactor NIA): NIA 230, NIA 240, NIA 500 y NIA 520 con separación estricta entre propuesta SQL visible, cálculo determinista en DuckDB y aprobación del auditor. Ver `docs/fichas/FICHA_14_copiloto_sql.md`.
- Ficha 15 (flujo de revisión por roles NIA 220/230, portafolio de encargos y empaquetado portátil `.exe`): identificación de preparador, revisor y socio en bitácora encadenada SHA-256 y separación de rutas de recursos/trabajo. Ver `docs/fichas/FICHA_15_roles_revision_y_portafolio.md`.
- Ficha 16 (endurecimiento de confiabilidad contable, lectura bancaria multipárrafo/saldos, formato ejecutivo de cédula Excel y cobertura Latam): NIA 500, NIA 330, NIA 320, NIA 230 y validación estricta sin coerción silenciosa. Ver `docs/fichas/FICHA_16_confiabilidad_y_diagnostico.md`.
- Ficha 17 (identidad ejecutiva `Folio Auditor`, banda de constancia en tiempo real y encabezados/pies de impresión en cédulas Excel): NIA 230 (párrs. 8, 9 y 14–16 sobre identificación de cliente, período auditado, fecha/hora y compilación de papeles de trabajo), NIA 220, estándar ISO 8601 (marcas local/UTC) y especificación OOXML/`openpyxl` para encabezados y pies de página de impresión. Ver `docs/fichas/FICHA_17_identidad_y_constancia.md`.
- Ficha 18 (sistema visual de estación contable clásica Win32 y hoja de cálculo biselada): convenciones públicas de escritorio IBM SAA CUA (*Common User Access*), *The Windows Interface Guidelines for Software Design* (Microsoft Press, 1995), documentación pública Win32 de `GetSysColor`/`DrawEdge` (`#D4D0C8`, biseles elevado `#FFFFFF`/`#404040` y hundido `#808080`/`#FFFFFF`, barra de título `#000080 -> #1084D0`), convenciones abiertas de interfaz de hoja de cálculo de dos dimensiones (barra de fórmula en pozos hundidos y rejilla tipo libro `#C0C0C0`) y NIA 230 (párrs. 8, 9 y 14–16 sobre legibilidad e identificación de papeles de trabajo), conservando los íconos 3D SVG/`QPainter`, la identidad `Folio Auditor` y la constancia en tiempo real. Ver `docs/fichas/FICHA_18_interfaz_clasica_win32.md`.
- Ficha 19 (arquitectura de ciberseguridad, modelo de amenazas STRIDE y marcos aplicables): estándares y guías públicas OWASP ASVS v4.0.3, OWASP CWE Top 25, NIST SP 800-218 (SSDF), NIST CSF 2.0, NIST SP 800-57, RFC 8032 (Ed25519), RFC 3161, ISO/IEC 27001:2022 (Anexo A.8), ISO/IEC 27037, ISO/IEC 27701, CycloneDX, SLSA, CIS Controls v8, OWASP Top 10 for LLM Applications, NIGC 1 / NIA 220 / NIA 230 / NIA 500 y leyes públicas de protección de datos personales (Ley 81 de 2019 de Panamá y Decreto Ejecutivo 285 de 2021, Ley 1581 de Colombia, LFPDPPP de México y Ley 8968 de Costa Rica). Ver `docs/fichas/FICHA_19_ciberseguridad_y_marcos.md` y `docs/seguridad/MATRIZ_MARCOS.md`.
- Ficha 20 (hardening técnico crítico · Oleada 1): OWASP CSV/Formula Injection (`CWE-1236`), protección anti-XXE/DTD (`CWE-611`, `CWE-776`), defensa contra bombas de compresión y *path traversal* en ZIP y flujos `zlib` PDF (`CWE-22`, `CWE-409`), aislamiento de DuckDB (`enable_external_access = false` y `lock_configuration = true`), `sqlite3.Connection.set_authorizer` de la biblioteca estándar de Python, neutralización SQL de identificadores/formatos (`CWE-89`), manejo seguro de credenciales por entorno (`CWE-522`, `CWE-532`) y aislamiento local `127.0.0.1` en Streamlit. Ver `docs/fichas/FICHA_20_hardening_tecnico.md`.
- Ficha 21 (criptografía Ed25519, control de acceso RBAC, login dual Administrador/Preparador y sellado NIA 220/230 · Oleada 2): RFC 8032 (Ed25519 en Python puro con vectores §7.1), NIST SP 800-57, `hashlib.scrypt`, Windows CNG `AES-256-GCM` (`bcrypt.dll`), Windows DPAPI (`crypt32.dll`), ISO/IEC 27037, NIGC 1 y NIA 220/230 (segregación `Preparador ≠ Revisor ≠ Socio`, sellado cruzado `sello.json` y ventana de archivo de 60 días), con interfaz Win32 clásica `FOLIO AUDITOR`. Ver `docs/fichas/FICHA_21_cripto_roles_y_login.md`.
- Ficha 22 (privacidad, bóveda cifrada y cumplimiento Ley 81/LatAm · Oleada 3): Ley 81 de 2019 y Decreto Ejecutivo 285 de 2021 (Panamá), Ley 1581 (Colombia), LFPDPPP (México), Ley 8968 (Costa Rica), ISO/IEC 27701, CIS Controls v8 Control 3, bóveda `.folioenc` (`AES-256-GCM` + `scrypt`/DPAPI + AAD), detección de carpetas en la nube (OneDrive/Dropbox/Drive), ACLs NTFS (`icacls`), anonimización PII y prueba de cero sockets salientes. Ver `docs/fichas/FICHA_22_privacidad_y_boveda.md`.
- Ficha 23 (cadena de suministro, SBOM CycloneDX, SAST y empaquetado firmado · Oleada 4): CycloneDX 1.5, NIST SP 800-218 (SSDF), SLSA Nivel 2, ISO/IEC 27001 Anexo A.8, RFC 3161 (marcas de tiempo Authenticode), analizador estático AST de Python, `SHA256SUMS.txt` y documentación de confianza TI en `docs/seguridad/` y `SECURITY.md`. Ver `docs/fichas/FICHA_23_cadena_suministro_y_sbom.md`.
