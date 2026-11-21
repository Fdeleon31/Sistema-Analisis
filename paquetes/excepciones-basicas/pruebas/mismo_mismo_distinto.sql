-- Ficha 02 · Mismo-mismo-distinto: grupos que coinciden en las claves
-- pero tienen más de un valor distinto en la columna {distinto}.
-- Los valores nulos de {distinto} no cuentan como valor distinto.
WITH grupos AS (
    SELECT {claves}
    FROM {tabla}
    GROUP BY {claves}
    HAVING COUNT(DISTINCT {distinto}) > 1
)
SELECT t.*
FROM {tabla} AS t
JOIN grupos AS g USING ({claves})
ORDER BY {claves}, {distinto}
