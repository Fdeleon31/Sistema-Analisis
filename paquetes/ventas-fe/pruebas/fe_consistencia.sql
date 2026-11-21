-- Ficha 10 · Totales inconsistentes: total distinto de neto + ITBMS, o suma de ítems distinta del total.
SELECT
    archivo, cufe, tipo_documento, punto_facturacion, numero, fecha_emision,
    total_neto, total_itbms, total, suma_items,
    ROUND(total - (total_neto + total_itbms), 2) AS diferencia_total,
    ROUND(suma_items - total, 2) AS diferencia_items
FROM {facturas}
WHERE ABS(total - (total_neto + total_itbms)) > 0.005
   OR (suma_items IS NOT NULL AND ABS(suma_items - total) > 0.005)
ORDER BY punto_facturacion, tipo_documento, numero
