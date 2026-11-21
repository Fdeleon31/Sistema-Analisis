-- Ficha 10 · Ventas del mayor contra facturas por mes.
-- Facturas: sin repetir CUFE, sin ambiente de pruebas; notas de crédito restan.
-- Mayor: cuentas que empiezan con el prefijo de ingresos; el crédito se toma como venta positiva.
WITH fe AS (
    SELECT DISTINCT ON (cufe) * FROM {facturas} WHERE COALESCE(ambiente, '1') <> '2' ORDER BY cufe, archivo
),
fe_mes AS (
    SELECT strftime(fecha_emision, '%Y-%m') AS mes,
           SUM(CASE WHEN tipo_documento IN ('04', '06') THEN -total_neto ELSE total_neto END) AS ventas_facturadas,
           COUNT(*) AS documentos
    FROM fe
    GROUP BY 1
),
mayor_mes AS (
    SELECT strftime({fecha}, '%Y-%m') AS mes, -SUM({monto}) AS ventas_mayor
    FROM {mayor}
    WHERE starts_with(CAST({cuenta} AS VARCHAR), $prefijo_ingresos)
    GROUP BY 1
)
SELECT
    COALESCE(f.mes, m.mes) AS mes,
    COALESCE(m.ventas_mayor, 0) AS ventas_mayor,
    COALESCE(f.ventas_facturadas, 0) AS ventas_facturadas,
    COALESCE(f.documentos, 0) AS documentos,
    CAST(COALESCE(m.ventas_mayor, 0) - COALESCE(f.ventas_facturadas, 0) AS DECIMAL(18, 2)) AS diferencia,
    ABS(COALESCE(m.ventas_mayor, 0) - COALESCE(f.ventas_facturadas, 0)) >= $umbral_trivial AS sobre_trivial
FROM fe_mes AS f
FULL OUTER JOIN mayor_mes AS m ON f.mes = m.mes
ORDER BY mes
