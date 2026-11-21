-- Fichas 06 y 09 · Sumarización por rubro. El rubro sale del archivo del cliente si existe;
-- si no, de la regla de prefijo más largo. Las cuentas sin rubro quedan visibles.
WITH cuentas AS (
    SELECT DISTINCT CAST({cuenta} AS VARCHAR) AS cuenta FROM {tabla}
),
por_regla AS (
    SELECT c.cuenta, arg_max(r.rubro, LENGTH(r.prefijo)) AS rubro
    FROM cuentas AS c
    JOIN {reglas} AS r ON starts_with(c.cuenta, TRIM(r.prefijo))
    GROUP BY c.cuenta
),
rubro_cuenta AS (
    SELECT c.cuenta, COALESCE(mc.rubro, pr.rubro, 'Sin rubro') AS rubro,
           CASE WHEN mc.rubro IS NOT NULL THEN 'archivo del cliente'
                WHEN pr.rubro IS NOT NULL THEN 'regla por prefijo'
                ELSE 'sin asignar' END AS origen_rubro
    FROM cuentas AS c
    LEFT JOIN {mapeo_cliente} AS mc ON TRIM(mc.cuenta) = c.cuenta
    LEFT JOIN por_regla AS pr ON pr.cuenta = c.cuenta
)
SELECT
    rc.rubro,
    COUNT(DISTINCT rc.cuenta) AS cuentas,
    COUNT(*) AS lineas,
    SUM(CASE WHEN t.{monto} > 0 THEN t.{monto} ELSE 0 END) AS debitos,
    -SUM(CASE WHEN t.{monto} < 0 THEN t.{monto} ELSE 0 END) AS creditos,
    SUM(t.{monto}) AS neto,
    STRING_AGG(DISTINCT CASE WHEN rc.origen_rubro = 'sin asignar' THEN rc.cuenta END, ', ') AS cuentas_sin_rubro
FROM {tabla} AS t
JOIN rubro_cuenta AS rc ON rc.cuenta = CAST(t.{cuenta} AS VARCHAR)
GROUP BY rc.rubro
ORDER BY rc.rubro
