-- Ficha 06 · Estratificación de líneas por valor absoluto, relativa a la materialidad del encargo.
WITH lineas AS (
    SELECT ABS({monto}) AS valor FROM {tabla} WHERE {monto} IS NOT NULL
),
estratos AS (
    SELECT
        CASE
            WHEN valor < $umbral_trivial THEN 1
            WHEN valor < $materialidad_ejecucion * 0.25 THEN 2
            WHEN valor < $materialidad_ejecucion THEN 3
            ELSE 4
        END AS orden,
        valor
    FROM lineas
)
SELECT
    orden,
    CASE orden
        WHEN 1 THEN 'Bajo el umbral trivial'
        WHEN 2 THEN 'Hasta 25 % de la materialidad de ejecución'
        WHEN 3 THEN 'Hasta la materialidad de ejecución'
        ELSE 'Igual o mayor a la materialidad de ejecución'
    END AS estrato,
    COUNT(*) AS lineas,
    SUM(valor) AS valor_absoluto,
    ROUND(100.0 * SUM(valor) / SUM(SUM(valor)) OVER (), 2) AS porcentaje_valor
FROM estratos
GROUP BY orden
ORDER BY orden
