-- Ficha 03 · Días sin registros entre la primera y la última fecha.
-- Con $solo_habiles = true se omiten sábados y domingos.
-- Con $excluir_feriados = true se omiten los días de la tabla {feriados}.
WITH rango AS (
    SELECT MIN(CAST({campo} AS DATE)) AS inicio, MAX(CAST({campo} AS DATE)) AS fin
    FROM {tabla}
),
calendario AS (
    SELECT CAST(UNNEST(generate_series(inicio, fin, INTERVAL 1 DAY)) AS DATE) AS dia
    FROM rango
),
con_registros AS (
    SELECT DISTINCT CAST({campo} AS DATE) AS dia
    FROM {tabla}
    WHERE {campo} IS NOT NULL
)
SELECT
    c.dia,
    CASE ISODOW(c.dia)
        WHEN 1 THEN 'lunes' WHEN 2 THEN 'martes' WHEN 3 THEN 'miércoles'
        WHEN 4 THEN 'jueves' WHEN 5 THEN 'viernes' WHEN 6 THEN 'sábado'
        ELSE 'domingo'
    END AS dia_semana
FROM calendario AS c
ANTI JOIN con_registros AS r USING (dia)
WHERE NOT ($solo_habiles AND ISODOW(c.dia) >= 6)
  AND NOT ($excluir_feriados AND c.dia IN (SELECT CAST(fecha AS DATE) FROM {feriados}))
ORDER BY c.dia
