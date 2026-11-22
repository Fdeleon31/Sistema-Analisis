# Ficha 19 · Arquitectura de Ciberseguridad, Modelo de Amenazas y Marcos Aplicables

**Fecha:** noviembre 2026  
**Módulos transversales:** `motor/`, `conectores/`, `ia/`, `app/`, `cuadra.py`, `docs/seguridad/`  
**Referencias públicas:**
- **OWASP ASVS v4.0.3** (*Application Security Verification Standard* — V1 Arquitectura/Modelado de Amenazas, V2 Autenticación, V4 Control de Acceso, V5 Validación y Sanitización, V6 Criptografía, V8 Protección de Datos, V12 Archivos/Recursos, V13 API/Consultas).
- **OWASP CWE Top 25** (en particular CWE-22 *Path Traversal*, CWE-89 *SQL Injection*, CWE-409 *Improper Handling of Highly Compressed Data*, CWE-522 *Insufficiently Protected Credentials*, CWE-532 *Insertion of Sensitive Information into Log File*, CWE-611 *Improper Restriction of XML External Entity Reference*, CWE-776 *Improper Restriction of Recursive Entity References in DTDs*, CWE-1236 *Improper Neutralization of Formula Elements in a CSV/Spreadsheet File*).
- **NIST SP 800-218** (*Secure Software Development Framework — SSDF*: prácticas PO, PS, PW y RV).
- **NIST Cybersecurity Framework (CSF) 2.0** (*Govern, Identify, Protect, Detect, Respond, Recover*).
- **NIST SP 800-57** (*Recommendation for Key Management*) y **RFC 8032** (*Edwards-Curve Digital Signature Algorithm — Ed25519*) y **RFC 3161** (*Time-Stamp Protocol*).
- **ISO/IEC 27001:2022** (Anexo A.8 — controles tecnológicos, criptografía, registro de eventos, desarrollo seguro) e **ISO/IEC 27002:2022**.
- **ISO/IEC 27037** (*Guidelines for identification, collection, acquisition and preservation of digital evidence*).
- **ISO/IEC 27701** (*Privacy Information Management*).
- **NIGC 1 / ISQM 1** (*Norma Internacional de Gestión de la Calidad 1*), **NIA 220**, **NIA 230** (*Documentación de auditoría*) y **NIA 500** (*Evidencia de auditoría*).
- **Legislación de privacidad regional:** **Ley 81 de 2019 de Panamá** y **Decreto Ejecutivo 285 de 2021** (Protección de Datos Personales), **Ley 1581 de 2012** (Colombia), **LFPDPPP** (México) y **Ley 8968** (Costa Rica).
- **Supply Chain y Gobierno TI:** **CycloneDX** (SBOM), **SLSA** (*Supply-chain Levels for Software Artifacts*), **CIS Controls v8** (especialmente Control 3 — Protección de Datos y Control 16 — Seguridad de Aplicaciones) y **OWASP Top 10 for LLM Applications** (evolutivo de IA).

**Principio rector:** *Cero confianza en entradas de terceros, ejecución determinista 100 % local sin telemetría, evidencia probatoria verificable criptográficamente y protección estricta de los datos del cliente en reposo.*

---

## 1. Contexto arquitectónico y perfil de amenazas

**Folio Auditor** es una estación de analítica y documentación determinista de auditoría para firmas latinoamericanas (Panamá primero) que opera **100 % sin conexión a internet**:
- No transmite archivos contables, cédulas ni métricas hacia servicios en la nube.
- No integra aún modelos de lenguaje remotos (el Copiloto actual traduce patrones en español a SQL visible determinista).
- Consume archivos potencialmente no confiables generados por terceros (clientes auditados, PACs de facturación electrónica, bancos, exportaciones ERP y volcados SQL).
- Produce papeles de trabajo (`cedula.xlsx`), bitácoras (`bitacora.jsonl`) y registros de revisión/firma (`revisiones.json`) sujetos a exigencias legales y normativas (NIA 220/230, NIGC 1, Ley 81).

La ausencia de internet elimina vectores clásicos de exposición SaaS pública, pero concentra el riesgo en **6 vectores locales y de cadena de suministro**.

---

## 2. Modelo de amenazas STRIDE (6 vectores críticos)

| Vector | Amenaza STRIDE | Superficie en Folio Auditor | Impacto | Mitigación principal |
| :--- | :--- | :--- | :--- | :--- |
| **V1 · Archivos hostiles de clientes/terceros** | *Tampering*, *Elevation of Privilege* (en cliente del auditor), *Denial of Service* | `motor/exportador.py`, `motor/factura_electronica.py`, `conectores/estado_cuenta_pdf.py`, `motor/importador.py` | Ejecución de fórmulas en Excel (`CWE-1236`), expansión XXE/Billion Laughs (`CWE-611`/`776`), agotamiento de RAM/disco por ZIP/zlib bombs (`CWE-409`), *path traversal* (`CWE-22`), ruptura de SQL por comillas en encabezados | Sanitización de celdas Excel/CSV, bloqueo de `<!DOCTYPE`/`<!ENTITY`, límites estrictos de tamaño/conteo/ratio en ZIP y zlib, validación de rutas de miembros, escape de identificadores SQL (`citar_identificador_sql`) |
| **V2 · Motor SQL y Copiloto** | *Information Disclosure*, *Tampering*, *Elevation of Privilege* | `ia/copiloto.py`, `conectores/sql_fuente.py`, `motor/importador.py`, `cuadra.py` | Lectura de archivos del host vía funciones de DuckDB (`read_text`, `read_csv`, `glob`, `getenv`), escape de comentarios/literales SQL, mutación en ERP o `.sql` dump, exposición de credenciales en CLI/procesos | `SET enable_external_access = false` + `SET lock_configuration = true`, lista de bloqueo de funciones y sentencias peligrosas, parser de comentarios anidados, `sqlite3.set_authorizer`, sesiones SQL `READ ONLY` + TLS/timeout, `env:VAR` para URIs y enmascaramiento ampliado |
| **V3 · Interfaz web local y temporales** | *Information Disclosure*, *CSRF*, *Tampering* | `app/inicio.py`, `.streamlit/config.toml`, `iniciar.bat` | Acceso desde terceros en la misma LAN Wi-Fi si Streamlit escucha en `0.0.0.0`, escritura arbitraria por nombre de archivo subido, residuos de datos de clientes en `%TEMP%` | Binding estricto a `127.0.0.1`, XSRF activo y CORS deshabilitado, saneamiento de nombres de archivo (`nombre_archivo_seguro`), directorio temporal con permisos acotados y limpieza automática `atexit` |
| **V4 · Integridad probatoria y roles NIA 220/230** | *Repudiation*, *Tampering*, *Spoofing* | `motor/bitacora.py`, `motor/revision.py`, `motor/exportador.py` | Recálculo silencioso de `bitacora.jsonl`, alteración posterior de `cedula.xlsx`/`revisiones.json`, auto-aprobación sin segregación (`Preparador == Socio`) | Segregación de funciones obligatoria, autenticación local (`scrypt`), firma asimétrica **Ed25519 (RFC 8032)** y `sello.json` de cierre verificable vía CLI/UI (**Oleada 2**) |
| **V5 · Confidencialidad en reposo (Ley 81)** | *Information Disclosure* | `encargos/`, `salidas/`, carpetas temporales y soporte técnico | Exposición de datos contables si el portátil carece de cifrado o sincroniza con OneDrive/Dropbox, fuga en reportes de soporte | Cifrado `AES-256-GCM` / DPAPI, alerta por carpetas sincronizadas en la nube, ACLs NTFS restrictivas, borrado seguro y exportador de diagnóstico anonimizado (**Oleada 3**) |
| **V6 · Cadena de suministro y distribución** | *Tampering*, *Supply Chain Compromise* | `requirements.txt`, `empaquetar_exe.bat`, `cuadra.spec` | Dependencias comprometidas por rangos abiertos, ausencia de verificación de integridad o bloqueo por EDR corporativo | `requirements.lock` con hashes SHA-256, SAST/SCA (`bandit`, `pip-audit`, escaneo de secretos), SBOM **CycloneDX**, `SHA256SUMS.txt` y firma **Authenticode** (**Oleada 4**) |

---

## 3. Hoja de ruta estructurada en 6 oleadas

1. **Oleada 0 (Ficha 19 · Gobierno y Sala Limpia):** modelo de amenazas STRIDE, catálogo de marcos y matriz de trazabilidad viva (`docs/seguridad/MATRIZ_MARCOS.md`).
2. **Oleada 1 (Ficha 20 · Hardening técnico crítico):** módulo central `motor/seguridad.py`, aislamiento DuckDB/SQL/Copiloto, defensa ante archivos hostiles (Excel, XML, ZIP, PDF, `.sql`), aislamiento de interfaz web local (`127.0.0.1`) y limpieza de temporales, verificado con `tests/test_seguridad_hardening.py`.
3. **Oleada 2 (Ficha 21 · Integridad probatoria y roles NIA 220/230):** autenticación local, segregación `Preparador ≠ Revisor ≠ Socio`, firmas digitales Ed25519 (`sello.json`), comando `verificar` y control de ventana de archivo de 60 días.
4. **Oleada 3 (Ficha 22 · Privacidad y datos en reposo — Ley 81):** bóveda cifrada `AES-256-GCM` / DPAPI, alerta OneDrive/nube, permisos NTFS restrictivos, retención y diagnóstico anonimizado, prueba de cero sockets salientes.
5. **Oleada 4 (Ficha 23 · Cadena de suministro y distribución segura):** lockfile con hashes, verificación SAST/SCA automática, SBOM CycloneDX y firma digital Authenticode de `LibroAuditoria.exe`.
6. **Oleada 5 (Paquete de confianza corporativa para firmas):** documentación técnica y legal para departamentos de TI y socios (`ARQUITECTURA_SEGURIDAD.md`, `CUMPLIMIENTO_LEY81_LATAM.md`, `GUIA_DESPLIEGUE_CORPORATIVO.md`, `SECURITY.md`).
