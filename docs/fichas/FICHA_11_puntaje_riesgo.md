# Ficha 11 · Puntaje de riesgo explicable por asiento

**Fecha:** noviembre 2026  
**Paquete:** `asientos-nia240` (`asientos-puntaje`)  
**Normas relacionadas:** NIA 240, NIA 330

---

## 1. Objetivo

Calcular un puntaje de riesgo transparente, determinista y explicable para cada asiento del diario a partir de los criterios de riesgo evaluados en la Ficha 04, permitiendo al auditor priorizar la revisión y documentar exactamente qué factores explican la calificación de cada asiento.

---

## 2. Entradas

La consulta `pruebas/asientos_criterios.sql` (Ficha 04) evalúa por línea y agrega por asiento los siguientes 10 criterios booleanos:

1. `fin_semana_feriado` — Fin de semana o feriado
2. `posterior_cierre` — Posterior al cierre
3. `cerca_cierre` — Cerca del cierre
4. `monto_redondo` — Monto redondo
5. `bajo_umbral` — Justo bajo el umbral de aprobación
6. `descripcion_sospechosa` — Descripción vacía o genérica
7. `usuario_poco_frecuente` — Usuario poco frecuente
8. `cuenta_poco_usada` — Cuenta poco usada
9. `descuadrado` — Asiento descuadrado
10. `sobre_materialidad` — Sobre materialidad de ejecución

---

## 3. Fórmula

```text
puntaje = suma de los pesos de los criterios marcados para el asiento
```

Con los pesos por defecto, la suma total posible es `100`, de modo que el rango por defecto es de `0` a `100`.

### Pesos por defecto y criterio profesional

Los pesos reflejan juicio profesional propio según la severidad e impacto directo del indicador sobre el riesgo de incorrección material o fraude, y son totalmente configurables por encargo:

| Criterio | Nombre legible | Peso por defecto | Justificación del peso |
| --- | --- | ---: | --- |
| `descuadrado` | Asiento descuadrado | 20 | Ruptura de partida doble; falla contable directa o manipulación crítica |
| `sobre_materialidad` | Sobre materialidad de ejecución | 15 | Impacto cuantitativo inmediato por encima de la materialidad de ejecución |
| `posterior_cierre` | Posterior al cierre | 12 | Alto riesgo de corte o ajustes extemporáneos tras la fecha de cierre |
| `bajo_umbral` | Justo bajo el umbral de aprobación | 10 | Indicio clásico de fraccionamiento o elusión de controles de autorización |
| `fin_semana_feriado` | Fin de semana o feriado | 8 | Registro en días no laborables fuera de la operación habitual |
| `cerca_cierre` | Cerca del cierre | 8 | Mayor presión de reporte en los días inmediatamente previos al cierre |
| `descripcion_sospechosa` | Descripción vacía o genérica | 8 | Falta de sustento narrativo o uso de términos vagos de ajuste/reclasificación |
| `usuario_poco_frecuente` | Usuario poco frecuente | 8 | Intervención inusual o segregación de funciones atípica |
| `cuenta_poco_usada` | Cuenta poco usada | 6 | Uso de cuentas con baja frecuencia histórica, susceptibles de ocultar partidas |
| `monto_redondo` | Monto redondo | 5 | Indicio de estimación manual o cifra arbitraria |
| **Total** | | **100** | |

---

## 4. Niveles y presentación

Según el puntaje calculado, se asigna un nivel de riesgo:

- **`alto`**: `puntaje >= nivel_alto` (por defecto `>= 25`)
- **`medio`**: `puntaje >= nivel_medio` y `< nivel_alto` (por defecto `>= 15`)
- **`bajo`**: `puntaje > 0` y `< nivel_medio`

Los asientos con `puntaje == 0` no se listan en la tabla de resultados, aunque se conserva el conteo total de `asientos_analizados` en el resumen.

Los resultados se ordenan por `puntaje` descendente, luego por `total_debito` descendente y finalmente por `asiento` ascendente.

### Explicación por asiento

Para cada asiento listado, se genera una cadena `explicacion` con los criterios marcados ordenados por su peso de mayor a menor (conservando el orden de `CRITERIOS_ASIENTO` ante empates), con el formato:

```text
Asiento descuadrado (+20); Fin de semana o feriado (+8)
```

Se utilizan los nombres legibles definidos en `NOMBRES_CRITERIOS`.

---

## 5. Configuración desde el encargo

Cada firma o equipo de auditoría puede ajustar los parámetros en el archivo YAML del encargo (o desde la interfaz en el panel de pesos opcional):

- `pesos_riesgo`: diccionario `{criterio: peso}`. Reemplaza únicamente los criterios especificados; los demás conservan su peso por defecto. Todos los criterios deben pertenecer a los 10 criterios válidos y tener un peso numérico `>= 0`.
- `nivel_riesgo_alto`: umbral numérico para nivel alto (por defecto `25`).
- `nivel_riesgo_medio`: umbral numérico para nivel medio (por defecto `15`; debe cumplir `nivel_riesgo_medio <= nivel_riesgo_alto`).

---

## 6. Casos esperados (`dataset_1_estandar`)

Sobre el dataset sintético estándar de `asientos-nia240` (semilla 7, 1,200 asientos) con pesos y umbrales por defecto:

| Asiento | Criterios marcados | Puntaje | Nivel |
| --- | --- | ---: | --- |
| `1111` | `fin_semana_feriado` (+8), `descripcion_sospechosa` (+8), `usuario_poco_frecuente` (+8), `monto_redondo` (+5) | 29 | `alto` |
| `707` | `descuadrado` (+20) | 20 | `medio` |
| `1001` | `sobre_materialidad` (+15) | 15 | `medio` |
| `909` | `bajo_umbral` (+10) | 10 | `bajo` |
| `101` | `fin_semana_feriado` (+8) | 8 | `bajo` |
| `202` | `fin_semana_feriado` (+8) | 8 | `bajo` |
| `404` | `usuario_poco_frecuente` (+8) | 8 | `bajo` |
| `606` | `descripcion_sospechosa` (+8) | 8 | `bajo` |
| `808` | `cerca_cierre` (+8) | 8 | `bajo` |
| `505` | `cuenta_poco_usada` (+6) | 6 | `bajo` |
| `303` | `monto_redondo` (+5) | 5 | `bajo` |

- Primeros cuatro en el ordenamiento: `["1111", "707", "1001", "909"]`.
- Conteo por nivel: `{"alto": 1, "medio": 2, "bajo": 8}` (11 asientos con puntaje > 0 de 1,200 analizados).
- Explicación esperada para el asiento `1111`:  
  `"Fin de semana o feriado (+8); Descripción vacía o genérica (+8); Usuario poco frecuente (+8); Monto redondo (+5)"`

---

## 7. Fuentes públicas

- NIA 240 (revisada), apéndice sobre selección de asientos de diario y otros ajustes para identificar características de fraude o elusión de controles.
- PCAOB AU 316.61: características de asientos inapropiados o inusuales (descripciones vacías o genéricas, cuentas poco usadas, montos redondos, usuarios atípicos, registros fuera de horario/fin de semana o cerca del cierre).
- Juicio profesional propio para la ponderación relativa de criterios y umbrales de escalamiento (completamente parametrizables por encargo).
