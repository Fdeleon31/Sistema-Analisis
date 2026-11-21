-- Ficha 10 · Documentos emitidos fuera del periodo del encargo.
SELECT archivo, cufe, tipo_documento, punto_facturacion, numero, fecha_emision, total_neto, total
FROM {facturas}
WHERE fecha_emision < CAST($periodo_inicio AS DATE) OR fecha_emision > CAST($fecha_cierre AS DATE)
ORDER BY fecha_emision, numero
