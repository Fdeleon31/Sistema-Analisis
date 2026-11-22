# Fases y puertas

Cada fase cierra con una puerta medible. Al cerrar una fase: actualiza este
archivo y `CHANGELOG.md`, crea la etiqueta `fase-N` y haz push (ver `GIT.md`).

## Fase 0 · semanas 1 a 4 · Sala limpia y validación (en curso)

- [x] Estructura del repositorio y flujo de git
- [x] Fichas 00 a 03 escritas en el cuaderno de sala limpia
- [x] Prototipo con DuckDB: Benford, duplicados y gaps, con casos que pasan
- [x] Ciclo de estrés: 8 de 8 variantes de exportación y 9 de 9 casos borde (34 pruebas)
- [x] Pruebas pasan en tu computador (python -m pytest)
- [ ] Layouts de 3 exportaciones reales (solo encabezados y formatos, sin datos de clientes)
- [x] Feriados 2025 verificados (solo feriados nacionales; los días no hábiles bancarios como el lunes de Carnaval quedan fuera)
- [ ] Contrato revisado (cláusulas de propiedad intelectual, confidencialidad, conflicto de interés)
- [ ] Dos semanas de registro de tiempos y dolores con IDEA
- [ ] Cinco entrevistas con auditores de otras firmas

**Puerta:** contrato revisado y 3 dolores confirmados en entrevistas.

## Fase 1 · meses 2 a 4 · MVP de asientos de diario (técnica lista)

- [x] Paquete asientos-nia240: integridad, estratificación, rubros, 10 criterios, selección y muestra impredecible
- [x] Archivo de encargo con materialidad y fecha de cierre
- [x] Muestreo MUS y aleatorio simple
- [x] Cédula con hoja del encargo y columna de conclusión
- [x] Puerta técnica: 3 datasets con resultados idénticos a los esperados (tests/test_fase1.py)
- [ ] Probar con la estructura de 3 exportaciones reales (encabezados y formato, sin datos de clientes)
- [x] Evaluación de muestras MUS con límite superior de error (Ficha 05b)
- [x] Interfaz para el auditor: app local en el navegador (`iniciar.bat`), con columnas sugeridas y confirmadas

**Puerta:** resultados idénticos a los esperados en 3 datasets de prueba. Cumplida en el entorno de desarrollo;
falta confirmarla en tu computador con `python -m pytest`.

## Fase 2 · meses 5 a 8 · Piloto pagado (técnicamente completa · 0.7.0)

- [x] Lector de XML de factura electrónica de la DGI y paquete `ventas-fe` (Ficha 10)
- [x] PDF de estados de cuenta bancarios y conciliación (`conectores/estado_cuenta_pdf.py` y paquete `bancos-conciliacion`, Ficha 13)
- [x] Copiloto en lenguaje natural (propone SQL visible, el auditor aprueba) (`ia/copiloto.py`, Ficha 14)
- [x] Puntaje de riesgo explicable por transacción (Ficha 11)
- [x] Conectores ERP del mercado panameño y fuentes SQL/multiformato (Ficha 12)
- [x] Programa nativo de escritorio (`app/escritorio.py`, 100 % sin internet) + interfaz Cinta 3D estilo Excel
- [ ] Piloto en un encargo real con horas medidas

PDF y XML de factura electrónica de la DGI, copiloto en lenguaje natural,
puntaje de riesgo, piloto en un encargo real con horas medidas.

**Puerta:** una firma pagando y horas ahorradas documentadas.

## Fase 3 · meses 9 a 15 · Escala regional y confiabilidad operativa (0.8.0)

- [x] Flujo de revisión y firmas por roles (**Preparador → Revisor → Socio**) bajo NIA 220/230 (`motor/revision.py`)
- [x] Portafolio de encargos guardados (`.yaml`), historial de corridas auditadas y reapertura trazada SHA-256 (`motor/portafolio.py`)
- [x] Empaquetador portátil `.exe` para Windows sin requerir Python (`motor/rutas.py`, `cuadra.spec`, `empaquetar_exe.bat`)
- [x] Conectores ERP regionales adicionales (Latam: `siigo-colombia`, `contpaqi-aspel-mx`, `softland-cr-latam`)
- [x] Semáforo previo de confiabilidad e integridad contable (`motor/diagnostico.py`), lector PDF bancario multipárrafo/saldos, validación estricta Debe/Haber y cédula Excel ejecutiva (`motor/formato_excel.py`)
- [ ] Instalador firmado con certificado corporativo para despliegue centralizado y validación de campo en encargo piloto real

## Ciberseguridad y Control de Acceso (Oleadas 0–5 · Fichas 19–23)

- [x] **Oleada 0 (Ficha 19):** Modelo de amenazas STRIDE y matriz de marcos OWASP ASVS/CWE, NIST SSDF/CSF 2.0, ISO 27001/27037/27701, NIA 220/230, NIGC 1 y Ley 81 (`docs/seguridad/MATRIZ_MARCOS.md`)
- [x] **Oleada 1 (Ficha 20):** Hardening técnico crítico (`motor/seguridad.py`), sandbox DuckDB (`enable_external_access = false`), `sqlite3.set_authorizer`, anti-XXE/ZIP/zlib bombs, neutralización CWE-1236 en Excel/CSV y aislamiento web `127.0.0.1`
- [x] **Oleada 2 (Ficha 21):** Criptografía Ed25519 (RFC 8032), `scrypt`, AES-256-GCM CNG, DPAPI, login dual **Administrador / Preparador** (`app/login_qt.py` y web), segregación NIA 220, sellado cruzado `sello.json` (`cuadra.py verificar`) y control de 60 días NIA 230
- [x] **Oleada 3 (Ficha 22):** Bóveda cifrada `.folioenc`, alerta de sincronización OneDrive/nube, ACLs NTFS (`icacls`), anonimización PII Ley 81, diagnóstico de soporte anonimizado y prueba de cero sockets salientes (`motor/privacidad.py`)
- [x] **Oleada 4 (Ficha 23):** Escáner estático AST/secretos, SBOM CycloneDX 1.5, `requirements.lock`, `SHA256SUMS.txt`, puerta DevSecOps (`verificar_seguridad.ps1`) y `cuadra.spec` / `empaquetar_exe.bat` con PyInstaller `6.22.3`
- [x] **Oleada 5:** Paquete de confianza TI y cumplimiento regional (`ARQUITECTURA_SEGURIDAD.md`, `CUMPLIMIENTO_LEY81_LATAM.md`, `GUIA_DESPLIEGUE_CORPORATIVO.md`, `SECURITY.md`)
- [ ] Proveer certificado corporativo externo (OV/EV) en `FOLIO_CERT_PFX` o `FOLIO_CERT_THUMBPRINT` al ejecutar `empaquetar_exe.bat` para estampar la firma Authenticode en producción
