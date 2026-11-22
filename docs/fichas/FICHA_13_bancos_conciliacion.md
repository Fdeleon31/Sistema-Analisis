# Ficha 13 · Estados de cuenta bancarios en PDF y conciliación bancaria

**Fecha:** noviembre 2026  
**Módulos:** `conectores/estado_cuenta_pdf.py`, `paquetes/bancos-conciliacion/`, `motor/servicio.py`, `motor/sintetico.py`  
**Referencias públicas:** NIA 500 (*Evidencia de auditoría*), NIA 330 (*Respuestas del auditor a los riesgos valorados*), NIA 240 (*Responsabilidades del auditor en la auditoría de estados financieros con respecto al fraude*), especificación ISO 32000-1 (PDF 1.4, compresión FlateDecode y operadores de texto `Tj`/`TJ`).  
**Principio rector:** *Nada se corrige en silencio.* Cada línea de extracto omitida por no representar una transacción (encabezados, totales de página, subtotales) o con formato ilegible queda registrada en el control de importación (`lineas_excluidas` / `detalle_excluidas`) y en la bitácora SHA-256 (`importacion_extracto`).

---

## 1. Objetivo

Permitir la lectura **100 % sin conexión a internet** de estados de cuenta bancarios en PDF (individuales, por carpeta o en ZIP) y formatos tabulares (`.csv`/`.xlsx`) de bancos locales en Panamá (**Banco General, Banistmo, BAC Credomatic, Global Bank, Banco Nacional** o formato genérico), normalizándolos para validar su consistencia interna y conciliarlos contra la cuenta de bancos en el Mayor General.

---

## 2. Esquema estándar de tabla `extracto`

| Columna | Tipo | Descripción |
| --- | --- | --- |
| `archivo` | `VARCHAR` | Nombre del archivo origen dentro de la carpeta o ZIP |
| `banco` | `VARCHAR` | Nombre del banco detectado por encabezado (ej. `Banco General`) |
| `cuenta_bancaria` | `VARCHAR` | Número o máscara de cuenta detectada en el encabezado (o vacío si no aparece) |
| `linea` | `INTEGER` | Número consecutivo de movimiento dentro del archivo |
| `fecha` | `DATE` | Fecha efectiva del movimiento |
| `referencia` | `VARCHAR` | Número de cheque, ACH, transferencia o documento (opcional) |
| `descripcion` | `VARCHAR` | Concepto / glosa bancaria del movimiento |
| `debito` | `DECIMAL(18, 2)` | Salida de fondos (valor ≥ 0) |
| `credito` | `DECIMAL(18, 2)` | Entrada de fondos (valor ≥ 0) |
| `monto` | `DECIMAL(18, 2)` | Movimiento neto con signo: `credito - debito` |
| `saldo` | `DECIMAL(18, 2)` | Saldo corrido reportado en la línea (o `NULL` si no está presente) |

---

## 3. Reglas de extracción de PDF (100 % local)

1. Se extrae el texto página por página usando `PySide6.QtPdf.QPdfDocument` cuando hay un contexto Qt disponible, con motor de respaldo integrado en Python puro (`zlib` + análisis de bloques `BT ... ET` y cadenas `Tj`/`TJ` ordenadas por coordenada vertical `Td`/`Tm`).
2. De los encabezados de las primeras líneas se detecta el banco emisor (`Banco General`, `Banistmo`, `BAC Credomatic`, `Global Bank`, `Banco Nacional` o `Banco Genérico`) y el número de cuenta bancaria.
3. Cada línea transaccional valida fecha (`YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY` o `DD MMM YYYY`), montos numéricos limpios y saldo final de línea; las líneas no transaccionales se omiten explícitamente dejando conteo y detalle en `LecturaExtracto.excluidas` / `errores`.
4. Si la columna trae dos montos + saldo al final (`Débito` y `Crédito`) o signo explícito (`+/-`, `CR/DB`), se normaliza a `debito >= 0`, `credito >= 0` y `monto = round(credito - debito, 2)`.

---

## 4. Pruebas del paquete `bancos-conciliacion`

| ID | Ficha | NIA | Regla determinista |
| --- | --- | --- | --- |
| `bancos-continuidad` | `13` | NIA 500 | Ordenado por `(archivo, linea)`, verifica `saldo_anterior + monto = saldo` (tolerancia `0.01`). Reporta cada salto o descuadre aritmético en el extracto. |
| `bancos-duplicados` | `13` | NIA 500, NIA 240 | Movimientos repetidos dentro del extracto con idéntica `(fecha, monto, referencia, descripcion)` cuando aparecen 2 o más veces. |
| `bancos-fuera-periodo` | `13` | NIA 500 | Movimientos del extracto con `fecha < periodo_inicio` o `fecha > fecha_cierre`. |
| `bancos-no-en-mayor` | `13` | NIA 500, NIA 330 | *(Requiere `mayor`)* Emparejamiento 1-a-1 determinista por monto exacto dentro de `±ventana_dias` (`5` días por defecto) sobre movimientos del mayor cuya cuenta inicia con `cuenta_banco` (`'1101'` por defecto). Lista partidas del extracto no registradas en contabilidad (ej. notas de débito/cargos omitidos). |
| `bancos-no-en-extracto` | `13` | NIA 500, NIA 330 | *(Requiere `mayor`)* Movimientos del mayor en `cuenta_banco` sin par en el extracto dentro de la ventana de fechas (partidas en tránsito al cierre o registros contables sin sustento bancario). |
