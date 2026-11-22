-- Ficha 13 · Descuadres en continuidad aritmética del saldo corrido del extracto.
WITH movs AS (
    SELECT
        archivo,
        banco,
        cuenta_bancaria,
        linea,
        fecha,
        referencia,
        descripcion,
        monto,
        LAG(saldo) OVER (PARTITION BY archivo ORDER BY linea) AS saldo_anterior,
        saldo AS saldo_reportado
    FROM {extracto}
    WHERE saldo IS NOT NULL
)
SELECT
    archivo,
    banco,
    cuenta_bancaria,
    linea,
    fecha,
    referencia,
    descripcion,
    CAST(saldo_anterior AS DECIMAL(18, 2)) AS saldo_anterior,
    CAST(monto AS DECIMAL(18, 2)) AS monto,
    CAST(saldo_anterior + monto AS DECIMAL(18, 2)) AS saldo_esperado,
    CAST(saldo_reportado AS DECIMAL(18, 2)) AS saldo_reportado,
    CAST(saldo_reportado - (saldo_anterior + monto) AS DECIMAL(18, 2)) AS diferencia
FROM movs
WHERE saldo_anterior IS NOT NULL
  AND ABS(saldo_reportado - (saldo_anterior + monto)) > 0.01
ORDER BY archivo, linea
