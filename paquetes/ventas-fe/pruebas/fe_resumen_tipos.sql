-- Ficha 10 · Resumen por tipo de documento (todo lo leído, antes de depurar).
SELECT tipo_documento, tipo_documento_nombre, ambiente, COUNT(*) AS documentos,
       COUNT(DISTINCT cufe) AS cufe_distintos, SUM(total_neto) AS total_neto, SUM(total_itbms) AS total_itbms, SUM(total) AS total
FROM {facturas}
GROUP BY ALL
ORDER BY tipo_documento, ambiente
