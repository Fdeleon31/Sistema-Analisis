# Política de Seguridad · Folio Auditor

**Folio Auditor** es una estación determinista de analítica y documentación de auditoría diseñada para operar **100 % en local sin conexión a internet**, sin telemetría y con integridad criptográfica verificable de sus papeles de trabajo.

---

## 1. Alcance soportado

Esta política cubre los componentes actuales de la rama principal (`0.8.x`):
- Motor analítico, importación, bitácora, criptografía, RBAC, privacidad y exportación (`motor/`).
- Conectores ERP y lectura segura de fuentes SQL y extractos PDF (`conectores/`).
- Copiloto SQL local sin internet (`ia/copiloto.py`).
- Aplicaciones de escritorio PySide6 (`app/escritorio.py`, `app/login_qt.py`) y respaldo web local en `127.0.0.1` (`app/inicio.py`, `.streamlit/config.toml`).
- Herramientas de compilación segura, verificación y empaquetado (`herramientas/seguridad_build.py`, `verificar_seguridad.ps1`, `empaquetar_exe.bat`) y distribución portátil Windows (`LibroAuditoria.exe`).

**Fuera de alcance:**
- Compromiso físico de estaciones de trabajo sin cifrado de disco de sistema operativo (BitLocker) o con cuentas Windows comprometidas con privilegios administrativos.
- Configuraciones inseguras o credenciales débiles en servidores SQL externos administrados por terceros.
- Modificaciones locales de archivos binarios o scripts posteriores a la entrega que invaliden el manifiesto `SHA256SUMS.txt` o la firma Authenticode.

---

## 2. Protocolo y canal de reporte de vulnerabilidades

Si descubres una vulnerabilidad de seguridad, un fallo criptográfico o una brecha potencial en controles de aislamiento o privacidad:

1. **No publiques detalles ni *exploits* en *issues* públicos** mientras no exista mitigación disponible.
2. **No utilices ni adjuntes datos reales de clientes o terceros:** reproduce y documenta el problema exclusivamente mediante **datos sintéticos**.
3. **Canal de reporte privado:**
   - Reporta el hallazgo mediante el canal privado de **Security Advisories** del repositorio o a través del contacto de seguridad institucional entregado en el paquete corporativo de despliegue de la firma.
4. **Información recomendada en el reporte:**
   - Componente o módulo afectado (ej. `motor/cripto.py`, `conectores/sql_fuente.py`, `LibroAuditoria.exe`).
   - Versión o resumen SHA-256 del artefacto (`SHA256SUMS.txt` / `sbom.cdx.json`).
   - Pasos reproducibles paso a paso con entradas sintéticas y resultado observado frente al esperado.
   - Clasificación preliminar estimada (STRIDE / CWE) e impacto potencial.

Se garantiza evaluación de buena fe y coordinación transparente con quien reporte hallazgos siguiendo estas pautas.

---

## 3. Niveles de severidad y SLA objetivo de respuesta

Los tiempos objetivo de atención se cuentan a partir de la recepción confirmada del reporte en el canal privado:

| Severidad | Criterio técnico representativo | Acuse de recibo | Triaje inicial | Parche / mitigación objetivo |
| :--- | :--- | :---: | :---: | :---: |
| **Crítica** | Ejecución arbitraria de código desde archivo de cliente (XML/Excel/PDF/SQL), falsificación o evasión de firma Ed25519 (`sello.json`), fuga de red en modo offline o exposición masiva de secretos/PII | **≤ 24 h** | **≤ 48 h** | **≤ 7 días** |
| **Alta** | Evasión de restricción SQL de solo lectura, fallo en cifrado autenticado `.folioenc`, escalación de privilegios entre `Preparador`/`Revisor`/`Socio`/`Administrador` o elusión de segregación NIA 220 | **≤ 48 h** | **≤ 72 h** | **≤ 15 días** |
| **Media** | Denegación de servicio local ante archivo malformado controlado, debilidad parcial en políticas locales o endurecimiento de interfaz `127.0.0.1` | **≤ 72 h** | **≤ 5 días** | **≤ 30 días** |
| **Baja / Informativa** | Mejoras de higiene de código, advertencias no explotables o actualización preventiva de dependencias en SBOM | **≤ 5 días** | **≤ 10 días** | Siguiente ciclo planificado |

---

## 4. Flujo obligatorio de verificación pre-entrega

Antes de emitir cualquier paquete ejecutable o actualización hacia una firma auditora, debe superarse íntegramente la compuerta automatizada definida en `verificar_seguridad.ps1`:

```powershell
.\verificar_seguridad.ps1
```

Este flujo ejecuta en secuencia:
1. **Análisis estático AST, secretos y guardarraíles** (`.\.venv\Scripts\python.exe herramientas\seguridad_build.py --escanear`):
   - Verifica ausencia de llamadas inseguras (`eval`, `exec`, `pickle`, `yaml.load` sin `SafeLoader`, `shell=True`, `os.system`).
   - Verifica ausencia de llaves privadas o URIs con contraseñas literales en código fuente.
   - Confirma que `datos/clientes/` no contenga archivos reales y que `.streamlit/config.toml` conserve `127.0.0.1`, XSRF activo, CORS desactivado y cero telemetría.
2. **Suite completa de pruebas adversarias y funcionales de seguridad (`pytest`):**
   - `tests/test_seguridad_hardening.py` (DuckDB bloqueado, SQL solo lectura, XML/ZIP/PDF/Excel).
   - `tests/test_seguridad_cripto_roles.py` (vectores RFC 8032 Ed25519, AES-256-GCM, DPAPI, `sello.json`, RBAC y NIA 230).
   - `tests/test_login_pantalla.py` (login dual Administrador/Preparador y panel de seguridad Qt).
   - `tests/test_seguridad_privacidad.py` (bóveda `.folioenc`, detector de nube, anonimización PII, retención y **cero sockets salientes**).
   - `tests/test_seguridad_supply_chain.py` (SBOM CycloneDX 1.5, lockfile, `SHA256SUMS.txt` y escáner estático).
3. **Generación de inventario y bloqueo offline:**
   - Emite `docs/seguridad/sbom.cdx.json` (**CycloneDX 1.5**) y `requirements.lock`.
4. **Refuerzo SAST/SCA opcional:**
   - Ejecuta `bandit` y `pip-audit` cuando están instalados en `.venv`, manteniendo compatibilidad con compilaciones 100 % sin conexión.
5. **Empaquetado y firma (`empaquetar_exe.bat`):**
   - Compila con versión fija de PyInstaller (`6.22.3`), emite `dist\LibroAuditoria\sbom.cdx.json` y `SHA256SUMS.txt`, y aplica firma digital **Authenticode** con sello de tiempo **RFC 3161** cuando se configura el certificado corporativo.

---

## 5. Alineamiento con marcos internacionales

| Marco / Norma | Contribución principal en Folio Auditor |
| :--- | :--- |
| **NIST CSF 2.0** | Gobierno de amenazas y matriz de trazabilidad (`GV`/`ID`), defensa en profundidad (`PR`), bitácoras SHA-256 y detección de anomalías (`DE`), protocolo de reporte y SLA (`RS`/`RC`). |
| **NIST SP 800-218 (SSDF)** | Reglas de sala limpia y requisitos de seguridad previos al código (`PO`), protección de binarios y cadena de suministro (`PS`), pruebas adversarias continuas y análisis AST (`PW`), y gestión estructurada de vulnerabilidades (`RV`). |
| **ISO/IEC 27001:2022 y SOC 2** | Alineamiento técnico con controles de acceso (`A.8.3`), gestión de vulnerabilidades técnicas (`A.8.8`), eliminación y enmascaramiento (`A.8.10`/`A.8.11`), criptografía (`A.8.24`), desarrollo seguro (`A.8.25`/`A.8.28`/`A.8.29`), y criterios SOC 2 de Seguridad, Confidencialidad e Integridad de Procesamiento. |
| **OWASP ASVS v4.0.3 y SLSA** | Verificación sobre entradas hostiles, autenticación local `scrypt`, SBOM CycloneDX 1.5 y manifiestos `SHA256SUMS.txt`. |
| **NIGC 1, NIA 220/230/500 y Ley 81 (Panamá)** | Segregación obligatoria `Preparador ≠ Revisor ≠ Socio`, cierre no repudiable `sello.json`, ventana de 60 días, bóveda `.folioenc` y procesamiento 100 % local sin transferencia internacional de datos. |
