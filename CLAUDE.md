# Cuadra · contexto para Claude Code

Herramienta de analítica de auditoría con IA para firmas latinoamericanas (Panamá primero).
Proyecto personal de Felipe, desarrollado fuera de su empleo. Estado: Fase 1 técnica completa (0.4.0); Fase 2 en curso.
Responde y documenta en español.

## Reglas que no se rompen

1. **Sala limpia.** Nada se copia, descompila ni inspecciona de software comercial (en particular Caseware IDEA).
   Cada función nueva parte de una ficha escrita con fuentes públicas (ver `docs/SALA_LIMPIA.md`) antes del código.
2. **Solo datos sintéticos.** Nunca datos de clientes ni archivos del empleador. `datos/clientes/` está en `.gitignore`.
3. **Nada se corrige en silencio.** Toda transformación o exclusión queda en el control de importación y en la bitácora.
   Si algo es ambiguo (fechas, montos), el importador se detiene y pide el dato.
4. **La IA propone y redacta; el motor determinista calcula; el auditor aprueba.** Ningún número de la cédula sale de un LLM.
5. **Resultados esperados primero.** Cada prueba nueva trae casos en `paquetes/<paquete>/casos/` con resultados
   calculados a mano o fijados por diseño antes de correr el motor. `python -m pytest` debe pasar siempre.
6. **Git solo por consola** (comandos `git`), nunca GitHub Desktop. Commits pequeños con mensajes claros en español.
   Al cerrar una fase: actualizar `docs/FASES.md` y `CHANGELOG.md`, etiqueta `fase-N` y push (ver `docs/GIT.md`).

## Estructura

- `cuadra.py`: línea de comandos (`ejemplo`, `ejemplo-asientos`, `correr`, `muestra`, `evaluar`).
- `app/inicio.py` + `iniciar.bat`: interfaz del auditor (Streamlit, local). Usa `motor/servicio.py` y `motor/sugerencias.py`.
- `motor/`: `importador.py` (normalización y control), `ejecutor.py` (manifiestos, parámetros del encargo, posprocesos),
  `estadistica.py` (Benford), `muestreo.py` (MUS y aleatorio), `exportador.py` (cédula Excel), `bitacora.py` (JSONL encadenado),
  `sintetico.py` (datasets con anomalías sembradas).
- `paquetes/<id>/`: `manifiesto.yaml` + `pruebas/*.sql` + `casos/` (+ tablas auxiliares). Agregar un paquete no debe tocar el motor.
  - `excepciones-basicas`: Benford, duplicados, mismo-mismo-distinto, gaps de asientos y fechas (con feriados de Panamá).
  - `asientos-nia240`: mayor vs balanza, estratificación, rubros, 10 criterios por asiento, selección y muestra impredecible.
- `encargos/*.yaml`: materialidad, materialidad de ejecución, umbral trivial, fecha de cierre, umbral de aprobación.
- `tests/`: unitarias, ciclo de estrés con formatos de ERP (`archivos_realistas.py`), casos borde y puerta de Fase 1 (`test_fase1.py`).
- SQL con placeholders: `{identificador}` (validado y entre comillas) y `$parametro` (parámetro de DuckDB).

## Comandos

```powershell
.venv\Scripts\Activate.ps1
python -m pytest
python cuadra.py ejemplo-asientos
python cuadra.py correr --paquete asientos-nia240 --encargo encargos\ejemplo-2025.yaml --archivo mayor=... --archivo balanza=...
python cuadra.py muestra --archivo ... --id cliente --valor saldo --tolerable 45000
```

## Pendientes (en orden)

1. Confirmar que `python -m pytest` pasa 48 de 48 en Windows; corregir lo que falle.
2. Probar con la estructura de 3 exportaciones reales (Felipe trae encabezados y formato, sin datos);
   agregarlas como variantes en `tests/archivos_realistas.py` y repetir el ciclo hasta que pasen.
3. Fase 2: lector de XML de factura electrónica de la DGI (CUFE), PDF de estados bancarios, copiloto en lenguaje natural, puntaje de riesgo.
4. Confirmar el feriado del 10 de noviembre de 2025 (único sin fuente en `feriados_pa.csv`).

Plan completo, fichas y criterios de cada fase: cuaderno de sala limpia (https://claude.ai/artifact/VVB2FfSa5sQFY9ibuDzUzz)
y plano de producto (https://claude.ai/artifact/CYvnqev8ukQABGew8uvooj).
