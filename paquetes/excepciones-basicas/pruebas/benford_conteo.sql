-- Ficha 01 · Conteo de primeros dígitos para la Ley de Benford.
-- Usa el valor absoluto y solo montos >= $monto_minimo (por defecto 10),
-- así la parte entera siempre tiene al menos dos dígitos.
SELECT
    CAST(LEFT(CAST(CAST(FLOOR(ABS({monto})) AS BIGINT) AS VARCHAR), $digitos) AS INTEGER) AS digito,
    COUNT(*) AS conteo
FROM {tabla}
WHERE {monto} IS NOT NULL
  AND ABS({monto}) >= $monto_minimo
GROUP BY 1
ORDER BY 1
