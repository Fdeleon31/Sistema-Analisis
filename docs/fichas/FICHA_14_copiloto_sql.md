# Ficha 14 · Copiloto en lenguaje natural y redactor de hallazgos NIA

**Fecha:** noviembre 2026  
**Módulo:** `ia/copiloto.py`, `cuadra.py`, `app/escritorio.py`, `app/inicio.py`  
**Referencias públicas:** NIA 230 (*Documentación de auditoría*), NIA 240 (*Fraude*), NIA 500 (*Evidencia de auditoría*), NIA 520 (*Procedimientos analíticos*).  
**Principio rector:** *La IA propone y redacta; el motor determinista calcula; el auditor aprueba.* Ningún número presentado en pantalla o en un borrador de cédula proviene de un modelo generativo; toda cifra proviene del resultado ejecutado en DuckDB bajo supervisión y aprobación explícita del auditor.

---

## 1. Objetivo

Permitir que el auditor formule consultas analíticas ad-hoc en español natural sobre sus tablas contables cargadas (`mayor`, `balanza`, `facturas`, `extracto`), inspeccionando **primero** la consulta `SELECT` exacta propuesta antes de ejecutarla en DuckDB y registrarla en la bitácora SHA-256, y generando posteriormente un **borrador estructurado de hallazgo de auditoría** listo para revisión humana.

---

## 2. Flujo de control en 3 pasos (sin "caja negra")

1. **Propuesta visible (`proponer_consulta_sql`):**
   - Traduce la intención en español **100 % sin internet** (analizando condiciones numéricas, de fechas, cuentas, usuarios, agrupaciones, topes `LIMIT` y pruebas forenses frecuentes).
   - Genera un SQL legible de DuckDB que comienza estrictamente por `SELECT` o `WITH` y se valida mediante `validar_consulta_solo_lectura` (`conectores/sql_fuente.py`).
   - Devuelve título, norma NIA aplicable, explicación de criterios aplicados y el SQL editable para que el auditor lo revise o ajuste antes de correrlo.
2. **Aprobación y cálculo determinista (`ejecutar_propuesta_aprobada`):**
   - Al confirmar explícitamente el auditor (*"Aprobar y ejecutar en motor DuckDB"*), valida nuevamente solo lectura, ejecuta en DuckDB, calcula el `SHA-256` de la consulta y registra un evento `"consulta_copiloto_aprobada"` en `bitacora.jsonl`.
3. **Redacción estructurada (`redactar_borrador_hallazgo`):**
   - Con base únicamente en el `DataFrame` real devuelto por DuckDB (conteo de filas, sumatoria de montos absolutos o netos, rango de fechas y muestra de primeras filas), redacta un borrador con la estructura estándar de papel de trabajo NIA: **Condición**, **Criterio**, **Causa / Indagación requerida**, **Efecto cuantificado (motor determinista)** y **Recomendación**.

---

## 3. Patrones soportados en español offline

- **Filtros de importe:** `mayores a X`, `superiores a X`, `menores a X`, `entre X y Y`, `redondos` (múltiplos exactos de 100 o 1,000).
- **Filtros temporales:** `fin de semana` / `sábados y domingos`, `posterior al cierre`, `cerca del cierre` (últimos 7 días hasta `fecha_cierre`), y cualquier nombre de mes (`enero`..`diciembre`, aplicando año del cierre).
- **Filtros por entidad / cuenta:** `usuario <nombre>`, `usuarios poco frecuentes` (menos de 5 asientos), `cuenta <código>`, `cuentas de ingresos` / `gastos` / `bancos`, `descripción vacía o genérica`.
- **Controles especiales:** `descuadrados` (asientos con `SUM(monto) <> 0`), `duplicados` (líneas repetidas en fecha, cuenta y monto), `facturas DGI` / `CUFE`, `conciliación bancaria` / `extracto bancario`.
- **Agregaciones y ordenamiento:** `por usuario`, `por cuenta`, `por mes`, `top N` / `principales N`.
