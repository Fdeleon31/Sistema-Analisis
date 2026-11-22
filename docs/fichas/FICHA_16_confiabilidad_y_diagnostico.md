# Ficha 16 · Endurecimiento de confiabilidad contable, PDF y formatos de cédula

## Objetivo
Elevar la confiabilidad operativa y metodológica del sistema antes de que el auditor emita o firme conclusiones (NIA 500, NIA 330 y NIA 230), evitando silencios en importación, fortaleciendo la lectura offline de PDFs bancarios reales, añadiendo un semáforo previo de integridad contable y formateando las cédulas Excel para revisión directa de gerencia y socios.

## Especificación técnica implementada
1. **Cero coerción silenciosa en columnas Debe/Haber (`motor/importador.py`):**
   - Extracción de `_validar_textos_numericos` aplicada tanto a columna `monto` directa como a las columnas `debito` y `credito` de `--debito-credito`, rechazando cadenas malformadas antes de operar con `COALESCE`.
   - Registro explícito en `control["transformaciones"]` y `control["fechas_invalidas"]` si algún valor de fecha cayó dentro de la tolerancia permitida.
   - Guarda numérica en `motor/estadistica.py` (`z_estadistico`) frente a `n <= 0` o proporciones fuera de `(0, 1)`.
2. **Semáforo previo de confiabilidad de datos (`motor/diagnostico.py`):**
   - Evalúa determinísticamente en DuckDB:
     - Cuadre contable del libro diario (`SUM(monto) = 0` global y por asiento).
     - Cuadre neto de balanza de comprobación (`SUM(saldo_final)`).
     - Integridad y cuadre matemático de extractos bancarios (`Saldo Inicial + Créditos - Débitos = Saldo Final` + errores de línea).
     - Nulos críticos y claves duplicadas `(asiento, linea)`, más advertencias por `linea` sintética o `usuario` por defecto.
     - Validez y cobertura de fechas respecto a `[periodo_inicio, fecha_cierre]` del encargo.
     - Definición de materialidad e identidad del encargo (NIA 320).
   - Se registra en `bitacora.jsonl` (`evento = "diagnostico"`), en la hoja `"Diagnostico"` de `cedula.xlsx`, en la barra/pestaña `"Diagnóstico"` del programa de escritorio y en el banner inicial de la interfaz web.
3. **Endurecimiento del lector bancario offline (`conectores/estado_cuenta_pdf.py`):**
   - Unión controlada de descripciones envueltas en varias líneas (hasta 2 líneas de continuación sin montos/encabezados ni pies).
   - Soporte adicional de formatos de fecha (`YYYY.MM.DD`, `Mmm DD, YYYY`, `DD-MMM-YY`) y signos negativos al final (`1,250.00-`).
   - Extracción de `Saldo Inicial` / `Saldo Final` de encabezados/pies y cálculo del cuadre en `LecturaExtracto.resumen_saldos`.
4. **Cédula Excel ejecutiva (`motor/formato_excel.py` + `motor/exportador.py`):**
   - Encabezados `#0F2744` en blanco negrita, inmovilización de fila superior (`A2`), autofiltro habilitado, formato monetario `#,##0.00`, fechas `yyyy-mm-dd`, ajuste automático de ancho y codificación de color en estados (`ALERTA`, `ADVERTENCIA`, `OK`, `alto`, `medio`, `bajo`).
5. **Estabilidad de escritorio y cobertura regional Latam (`app/escritorio.py`, `conectores/perfiles/`):**
   - `closeEvent` seguro en `VentanaCuadra` esperando la finalización ordenada de `TrabajadorEjecucion` (`QThread`), y registro de excepciones no controladas en `salidas/ultimo_error.log`.
   - Tres conectores ERP regionales Latam adicionales: `siigo-colombia`, `contpaqi-aspel-mx` y `softland-cr-latam`.
