-- Ficha 03 · Gaps en una secuencia (por ejemplo, número de asiento).
-- Acepta números puros (1500) y alfanuméricos con prefijo (AS-001500):
-- separa el prefijo del número final y busca huecos dentro de cada prefijo.
-- Los valores repetidos se cuentan una vez; cada fila es un rango faltante.
WITH base AS (
    SELECT DISTINCT TRIM(CAST({campo} AS VARCHAR)) AS texto
    FROM {tabla}
    WHERE {campo} IS NOT NULL
),
partes AS (
    SELECT
        regexp_extract(texto, '^(.*?)([0-9]+)$', 1) AS prefijo,
        CAST(regexp_extract(texto, '^(.*?)([0-9]+)$', 2) AS BIGINT) AS valor
    FROM base
    WHERE regexp_matches(texto, '[0-9]+$')
),
ordenados AS (
    SELECT prefijo, valor, LEAD(valor) OVER (PARTITION BY prefijo ORDER BY valor) AS siguiente
    FROM (SELECT DISTINCT prefijo, valor FROM partes)
)
SELECT
    prefijo,
    valor + 1 AS desde,
    siguiente - 1 AS hasta,
    siguiente - valor - 1 AS faltantes
FROM ordenados
WHERE siguiente - valor > 1
ORDER BY prefijo, desde
