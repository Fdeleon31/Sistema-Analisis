-- Ficha 13 · Movimientos duplicados exactos en el extracto bancario.
WITH agrupado AS (
    SELECT
        banco,
        cuenta_bancaria,
        fecha,
        CAST(monto AS DECIMAL(18, 2)) AS monto,
        COALESCE(referencia, '') AS referencia,
        descripcion,
        COUNT(*) AS repeticiones,
        STRING_AGG(CAST(linea AS VARCHAR), ', ' ORDER BY linea) AS lineas
    FROM {extracto}
    GROUP BY banco, cuenta_bancaria, fecha, CAST(monto AS DECIMAL(18, 2)), COALESCE(referencia, ''), descripcion
    HAVING COUNT(*) > 1
)
SELECT *
FROM agrupado
ORDER BY fecha, ABS(monto) DESC
