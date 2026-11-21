-- Ficha 02 · Duplicados exactos: filas que repiten todas las columnas clave.
-- Devuelve cada fila del grupo duplicado y cuántas veces se repite el grupo.
WITH grupos AS (
    SELECT {claves}, COUNT(*) AS veces
    FROM {tabla}
    GROUP BY {claves}
    HAVING COUNT(*) > 1
)
SELECT t.*, g.veces
FROM {tabla} AS t
JOIN grupos AS g USING ({claves})
ORDER BY {claves}
