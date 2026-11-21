# Cambios

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
