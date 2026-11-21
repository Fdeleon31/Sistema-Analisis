-- Ficha 10 · Huecos en la numeración por tipo de documento y punto de facturación.
WITH numeros AS (
    SELECT DISTINCT tipo_documento, punto_facturacion, numero
    FROM {facturas}
    WHERE numero IS NOT NULL
),
ordenados AS (
    SELECT *, LEAD(numero) OVER (PARTITION BY tipo_documento, punto_facturacion ORDER BY numero) AS siguiente
    FROM numeros
)
SELECT tipo_documento, punto_facturacion, numero + 1 AS desde, siguiente - 1 AS hasta, siguiente - numero - 1 AS faltantes
FROM ordenados
WHERE siguiente - numero > 1
ORDER BY tipo_documento, punto_facturacion, desde
