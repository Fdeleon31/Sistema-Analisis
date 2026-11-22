-- Ficha 13 · Movimientos del extracto bancario fuera del periodo auditado.
SELECT
    archivo,
    banco,
    cuenta_bancaria,
    linea,
    fecha,
    referencia,
    descripcion,
    CAST(debito AS DECIMAL(18, 2)) AS debito,
    CAST(credito AS DECIMAL(18, 2)) AS credito,
    CAST(monto AS DECIMAL(18, 2)) AS monto,
    CAST(saldo AS DECIMAL(18, 2)) AS saldo
FROM {extracto}
WHERE fecha < CAST($periodo_inicio AS DATE)
   OR fecha > CAST($fecha_cierre AS DATE)
ORDER BY fecha, linea
