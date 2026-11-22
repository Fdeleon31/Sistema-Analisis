# Folio Auditor · contexto para Claude Code y agentes IA

Mesa de analítica y documentación determinista de auditoría para firmas latinoamericanas (Panamá primero).
Proyecto personal de Felipe, desarrollado fuera de su empleo bajo reglas de sala limpia.
Estado actual: **Fase 3 (`0.8.0` · `Folio Auditor`)**, programa nativo de escritorio (`.exe` sin internet), interfaz Web secundaria, confiabilidad contable (Ficha 16) e identidad ejecutiva con constancia en tiempo real (Ficha 17).
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

- `cuadra.py`: CLI principal (`escritorio`, `ejemplo`, `ejemplo-asientos`, `ejemplo-fe`, `ejemplo-bancos`, `conectores`, `copiloto`, `correr`, `muestra`, `evaluar`).
- `app/`:
  - `escritorio.py` + `componentes_qt.py` + `comun.py`: **programa nativo de escritorio (PySide6, 100 % sin internet)** con Cinta de Opciones e iconos 3D estilo Excel, barra de constancia en tiempo real (cliente, período auditado y reloj local + UTC por `QTimer`), cierre seguro de hilos (`closeEvent`) y respaldo en navegador (`inicio.py` + `estilos.css`, con `@st.fragment(run_every="1s")`).
  - `iniciar.bat`: abre escritorio por defecto (`iniciar.bat web` inicia Streamlit en puerto `8501`).
  - `cuadra.spec` + `empaquetar_exe.bat`: compila `dist\LibroAuditoria\LibroAuditoria.exe` (soporta `--autoprueba`).
- `conectores/`:
  - `catalogo.py` + `perfiles/*.yaml`: **13 perfiles ERP** (10 Panamá + 3 regionales Latam: `siigo-colombia`, `contpaqi-aspel-mx`, `softland-cr-latam`).
  - `sql_fuente.py`: SQLite, DuckDB, volcados `.sql` y conexiones SQL solo lectura.
  - `estado_cuenta_pdf.py`: lector offline de extractos PDF multipágina/ZIP con descripciones envueltas, signos al final y cuadre `Saldo Inicial + Créditos - Débitos == Saldo Final`.
- `ia/`: `copiloto.py` (traducción offline español → `SELECT`/`WITH` visible, ejecución aprobada en DuckDB y redacción NIA).
- `motor/`:
  - `importador.py` (normalización multiformato, validación estricta de `monto` y `--debito-credito`, SAP ALV, indicador D/H),
  - `diagnostico.py` (semáforo previo NIA 500/320: cuadre diario/balanza, claves duplicadas, cobertura de fechas e integridad de extractos),
  - `ejecutor.py` (manifiestos, parámetros del encargo, puntaje explicable Ficha 11 y conciliación 1 a 1),
  - `revision.py` (roles `Preparador -> Revisor -> Socio`, conclusiones, bloqueo y reapertura trazada NIA 220/230),
  - `portafolio.py` (encargos YAML e historial de corridas en `salidas/`),
  - `formato_excel.py` + `exportador.py` (cédula Excel ejecutiva con hoja `Diagnostico`, encabezados/pies OOXML de impresión e inmovilización `A2`),
  - `estadistica.py` (Benford), `muestreo.py` (MUS y aleatorio), `bitacora.py` (JSONL SHA-256), `rutas.py`, `servicio.py`, `sintetico.py`.
- `paquetes/<id>/`: `excepciones-basicas`, `asientos-nia240`, `ventas-fe`, `bancos-conciliacion`.
- `tests/`: suite automatizada completa (`136+` pruebas).

## Comandos

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
python cuadra.py ejemplo-asientos
python cuadra.py escritorio --autoprueba
.\iniciar.bat web
.\empaquetar_exe.bat
```

## Pendientes vigentes

1. Piloto con exportaciones reales anonimizadas (encabezados/PDF de clientes de firma, agregando variantes sintéticas en `tests/archivos_realistas.py`).
2. Confirmar el feriado del 10 de noviembre de 2025 (fuente oficial en `feriados_pa.csv`).
3. Instalar `git` en Windows, inicializar `.git` y configurar repositorio privado en GitHub para `git push` (ver `docs/GIT.md`).
4. Firma digital de código del instalador Windows para despliegue en red corporativa.
