-- Ficha 10 · CUFE repetido: el mismo documento autorizado aparece en más de un archivo.
SELECT cufe, COUNT(*) AS veces, STRING_AGG(archivo, ' | ' ORDER BY archivo) AS archivos,
       MIN(numero) AS numero, MIN(total) AS total
FROM {facturas}
WHERE cufe IS NOT NULL
GROUP BY cufe
HAVING COUNT(*) > 1
ORDER BY cufe
