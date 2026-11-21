-- Ficha 07 · Mayor contra balanza: saldo inicial + movimientos del mayor - saldo final, por cuenta.
WITH movimientos AS (
    SELECT CAST({cuenta} AS VARCHAR) AS cuenta, SUM({monto}) AS movimiento, COUNT(*) AS lineas
    FROM {mayor}
    GROUP BY 1
),
balanza AS (
    SELECT CAST({cuenta} AS VARCHAR) AS cuenta, {saldo_inicial} AS saldo_inicial, {saldo_final} AS saldo_final
    FROM {balanza}
)
SELECT
    COALESCE(b.cuenta, m.cuenta) AS cuenta,
    b.saldo_inicial,
    COALESCE(m.movimiento, 0) AS movimientos,
    b.saldo_final,
    COALESCE(b.saldo_inicial, 0) + COALESCE(m.movimiento, 0) - COALESCE(b.saldo_final, 0) AS diferencia,
    CASE
        WHEN b.cuenta IS NULL THEN 'En el mayor, no en la balanza'
        WHEN m.cuenta IS NULL THEN 'El saldo cambia sin movimientos en el mayor'
        ELSE 'Diferencia entre balanza y mayor'
    END AS observacion
FROM balanza AS b
FULL OUTER JOIN movimientos AS m ON b.cuenta = m.cuenta
WHERE b.cuenta IS NULL
   OR ABS(COALESCE(b.saldo_inicial, 0) + COALESCE(m.movimiento, 0) - COALESCE(b.saldo_final, 0)) > 0.005
ORDER BY cuenta
