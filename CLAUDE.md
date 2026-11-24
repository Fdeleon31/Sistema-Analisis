# Folio Auditor · contexto para Claude Code y agentes IA

Mesa de analítica y documentación determinista de auditoría para firmas latinoamericanas (Panamá primero).
Proyecto personal de Felipe, desarrollado fuera de su empleo bajo reglas de sala limpia.
Estado actual: **Fase 3 (`0.9.0` · `Folio Auditor`)**, programa nativo de escritorio (`.exe` sin internet), interfaz Web secundaria, confiabilidad contable (Ficha 16), identidad ejecutiva con constancia en tiempo real (Ficha 17) y suite integral de ciberseguridad + pantalla dual de inicio de sesión (`Administrador` / `Preparador`) conforme a OWASP ASVS, NIST SSDF/CSF 2.0, Ed25519 RFC 8032, AES-256-GCM/DPAPI, Ley 81, CycloneDX 1.5 y SLSA L2 (Fichas 19–23).
Responde y documenta siempre en **español**.

## Reglas que no se rompen

1. **Sala limpia.** Nada se copia, descompila ni inspecciona de software comercial (en particular Caseware IDEA).
   Cada función nueva parte de una ficha escrita con fuentes públicas (`docs/fichas/` y `docs/SALA_LIMPIA.md`) antes del código.
2. **Solo datos sintéticos.** Nunca datos de clientes ni archivos del empleador. `datos/clientes/` está en `.gitignore`.
3. **Nada se corrige en silencio.** Toda transformación o exclusión queda en el control de importación y en la bitácora.
   Si algo es ambiguo (fechas, montos, Debe/Haber), el importador se detiene y pide el dato (`ErrorImportacion`).
4. **La IA propone y redacta; el motor determinista calcula; el auditor aprueba.** Ningún número de la cédula sale de un LLM.
5. **Resultados esperados primero.** Cada prueba nueva trae casos en `paquetes/<paquete>/casos/` con resultados
   calculados a mano o fijados por diseño antes de correr el motor. `pytest` debe pasar siempre al 100 %.
6. **Sin marcas heredadas ni versión visible en UI.** Los títulos de ventana y barras muestran **`FOLIO AUDITOR`** y jamás exponen `"cuadra"` en texto visible ni cadenas de versión.
7. **Trampas técnicas conocidas (no regresar):**
   - PySide6 Fusion: **nunca** llamar `setButtonSymbols(NoButtons)` en `QDoubleSpinBox` (borra el texto numérico).
   - Estilos Qt: acotar marcos contenedores con `#Id { ... }` para no pisar botones hijos (`#BtnPrimary`).
   - Windows PowerShell: usar `;` en lugar de `&&`.
8. **Git solo por consola** (comandos `git`), nunca GitHub Desktop. Commits pequeños con mensajes claros en español (`docs/GIT.md`). Nota: verifica si `git` y `.git` están inicializados antes de intentar `push`.

## Estructura del proyecto

- `cuadra.py`: CLI principal (`escritorio`, `ejemplo`, `ejemplo-asientos`, `ejemplo-fe`, `ejemplo-bancos`, `conectores`, `copiloto`, `correr`, `muestra`, `evaluar`, `verificar`, `seguridad`, `usuarios`).
- `app/`:
  - `escritorio.py` + `login_qt.py` + `componentes_qt.py` + `comun.py`: **programa nativo de escritorio (PySide6, 100 % sin internet)** con pantalla dual de inicio de sesión (`DialogoLoginFolio`, `DialogoAdminSeguridad`, `DialogoCambiarContrasena`), Cinta de Opciones e iconos 3D estilo Excel, barra de constancia en tiempo real (cliente, período auditado y reloj local + UTC por `QTimer`), cierre seguro de hilos (`closeEvent`) y respaldo en navegador (`inicio.py` + `estilos.css`, con `@st.fragment(run_every="1s")`).
  - `iniciar.bat`: abre escritorio por defecto (`iniciar.bat web` inicia Streamlit en puerto `8501`).
  - `cuadra.spec` + `empaquetar_exe.bat`: compila `dist\LibroAuditoria\LibroAuditoria.exe` (soporta `--autoprueba` y `--sin-login`) y genera `sbom.cdx.json` + `SHA256SUMS.txt`.
- `conectores/`:
  - `catalogo.py` + `perfiles/*.yaml`: **13 perfiles ERP** (10 Panamá + 3 regionales Latam: `siigo-colombia`, `contpaqi-aspel-mx`, `softland-cr-latam`).
  - `sql_fuente.py`: SQLite, DuckDB, volcados `.sql` y conexiones SQL solo lectura endurecidas contra SQLi/RCE (`sqlite3.set_authorizer`, bloqueo DuckDB externo).
  - `estado_cuenta_pdf.py`: lector offline de extractos PDF multipágina/ZIP con descripciones envueltas, signos al final y cuadre `Saldo Inicial + Créditos - Débitos == Saldo Final`.
- `ia/`: `copiloto.py` (traducción offline español → `SELECT`/`WITH` visible, ejecución aprobada en DuckDB con bloqueo externo y redacción NIA).
- `motor/`:
  - `seguridad.py` (guardas compartidas: SQLi/identificadores, anti-CWE-1236 Excel, anti-XXE, anti-Zip Slip/Zip Bomb, DuckDB locked),
  - `cripto.py` (Ed25519 RFC 8032 puro, `scrypt`, AES-256-GCM vía Windows CNG `bcrypt.dll`, DPAPI vía `crypt32.dll`, sellado `sello.json`),
  - `usuarios.py` (`GestorUsuarios`, perfiles `Administrador`, `Preparador`, `Revisor`, `Socio`, bloqueo fuerza bruta 5/15 min, `bitacora_accesos.jsonl`),
  - `privacidad.py` (bóveda cifrada `.folioenc`, detección de nube OneDrive/Dropbox, ACLs NTFS `icacls`, anonimización soporte Ley 81, retención),
  - `importador.py` (normalización multiformato, validación estricta de `monto` y `--debito-credito`, SAP ALV, indicador D/H),
  - `diagnostico.py` (semáforo previo NIA 500/320: cuadre diario/balanza, claves duplicadas, cobertura de fechas e integridad de extractos),
  - `ejecutor.py` (manifiestos, parámetros del encargo, puntaje explicable Ficha 11 y conciliación 1 a 1),
  - `revision.py` (roles `Preparador -> Revisor -> Socio`, segregación estricta, firma Ed25519 por rol, sellado `sello.json` y archivo NIA 230 de 60 días),
  - `portafolio.py` (encargos YAML e historial de corridas en `salidas/`),
  - `formato_excel.py` + `exportador.py` (cédula Excel ejecutiva con hoja `Diagnostico`, sanitización contra inyección de fórmulas, encabezados/pies OOXML de impresión e inmovilización `A2`),
  - `estadistica.py` (Benford), `muestreo.py` (MUS y aleatorio), `bitacora.py` (JSONL SHA-256), `rutas.py`, `servicio.py`, `sintetico.py`.
- `herramientas/seguridad_build.py` + `verificar_seguridad.ps1`: escáner SAST/secretos AST offline, SBOM CycloneDX 1.5, `requirements.lock` y `SHA256SUMS.txt`.
- `paquetes/<id>/`: `excepciones-basicas`, `asientos-nia240`, `ventas-fe`, `bancos-conciliacion`.
- `tests/`: suite automatizada completa (`210+` pruebas, incluyendo 77+ pruebas de ciberseguridad).

## Comandos

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
powershell -ExecutionPolicy Bypass -File .\verificar_seguridad.ps1
python cuadra.py ejemplo-asientos
python cuadra.py escritorio --autoprueba
python cuadra.py usuarios --listar
python cuadra.py seguridad --escanear
.\iniciar.bat web
.\empaquetar_exe.bat
```

## Pendientes vigentes

1. Piloto con exportaciones reales anonimizadas (encabezados/PDF de clientes de firma, agregando variantes sintéticas en `tests/archivos_realistas.py`).
2. Confirmar el feriado del 10 de noviembre de 2025 (fuente oficial en `feriados_pa.csv`).
3. Instalar `git` en Windows, inicializar `.git` y configurar repositorio privado en GitHub para `git push` (ver `docs/GIT.md`).
4. Firma digital de código del instalador Windows para despliegue en red corporativa.
