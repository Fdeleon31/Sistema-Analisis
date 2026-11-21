-- Ficha 10 · Documentos del ambiente de pruebas (iAmb = 2): no tienen validez fiscal.
SELECT archivo, cufe, tipo_documento, punto_facturacion, numero, fecha_emision, total
FROM {facturas}
WHERE ambiente = '2'
ORDER BY numero
