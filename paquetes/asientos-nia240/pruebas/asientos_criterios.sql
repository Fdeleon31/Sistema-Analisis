-- Ficha 04 · Criterios de riesgo por asiento (NIA 240).
-- Cada criterio se evalúa por línea y se agrega por asiento: basta una línea para marcarlo.
-- Devuelve todos los asientos con sus marcas; el posproceso filtra, selecciona o muestrea.
WITH uso_usuario AS (
    SELECT {usuario} AS usuario, COUNT(DISTINCT {asiento}) AS asientos FROM {tabla} GROUP BY 1
),
uso_cuenta AS (
    SELECT {cuenta} AS cuenta, COUNT(DISTINCT {asiento}) AS asientos FROM {tabla} GROUP BY 1
),
feriados_ AS (
    SELECT DISTINCT CAST(fecha AS DATE) AS dia FROM {feriados}
),
por_asiento AS (
    SELECT
        l.{asiento} AS asiento,
        MIN(l.{fecha}) AS fecha,
        MIN(l.{usuario}) AS usuario,
        STRING_AGG(DISTINCT l.{descripcion}, ' | ') AS descripcion,
        COUNT(*) AS lineas,
        SUM(CASE WHEN l.{monto} > 0 THEN l.{monto} ELSE 0 END) AS total_debito,
        SUM(l.{monto}) AS diferencia,
        BOOL_OR(ISODOW(l.{fecha}) >= 6 OR l.{fecha} IN (SELECT dia FROM feriados_)) AS fin_semana_feriado,
        BOOL_OR(l.{fecha} > CAST($fecha_cierre AS DATE)) AS posterior_cierre,
        BOOL_OR(l.{fecha} BETWEEN CAST($fecha_cierre AS DATE) - CAST($dias_cierre AS INTEGER)
                              AND CAST($fecha_cierre AS DATE)) AS cerca_cierre,
        BOOL_OR(ABS(l.{monto}) >= $redondeo AND ABS(l.{monto}) % $redondeo = 0) AS monto_redondo,
        BOOL_OR($umbral_aprobacion > 0
                AND ABS(l.{monto}) >= $umbral_aprobacion * (1 - $banda_umbral)
                AND ABS(l.{monto}) < $umbral_aprobacion) AS bajo_umbral,
        BOOL_OR(l.{descripcion} IS NULL
                OR LENGTH(TRIM(l.{descripcion})) < 4
                OR regexp_matches(LOWER(l.{descripcion}), $patron_descripcion)) AS descripcion_sospechosa,
        BOOL_OR(uu.asientos <= $usuario_max_asientos) AS usuario_poco_frecuente,
        BOOL_OR(uc.asientos <= $cuenta_max_asientos) AS cuenta_poco_usada
    FROM {tabla} AS l
    LEFT JOIN uso_usuario AS uu ON uu.usuario IS NOT DISTINCT FROM l.{usuario}
    LEFT JOIN uso_cuenta AS uc ON uc.cuenta IS NOT DISTINCT FROM l.{cuenta}
    GROUP BY l.{asiento}
),
marcado AS (
    SELECT
        *,
        ABS(diferencia) > 0.005 AS descuadrado,
        total_debito >= $materialidad_ejecucion AS sobre_materialidad
    FROM por_asiento
)
SELECT
    asiento, fecha, usuario, descripcion, lineas, total_debito, diferencia,
    fin_semana_feriado, posterior_cierre, cerca_cierre, monto_redondo, bajo_umbral,
    descripcion_sospechosa, usuario_poco_frecuente, cuenta_poco_usada, descuadrado, sobre_materialidad,
    CAST(fin_semana_feriado AS INTEGER) + CAST(posterior_cierre AS INTEGER) + CAST(cerca_cierre AS INTEGER)
      + CAST(monto_redondo AS INTEGER) + CAST(bajo_umbral AS INTEGER) + CAST(descripcion_sospechosa AS INTEGER)
      + CAST(usuario_poco_frecuente AS INTEGER) + CAST(cuenta_poco_usada AS INTEGER)
      + CAST(descuadrado AS INTEGER) + CAST(sobre_materialidad AS INTEGER) AS criterios
FROM marcado
ORDER BY criterios DESC, total_debito DESC, asiento
