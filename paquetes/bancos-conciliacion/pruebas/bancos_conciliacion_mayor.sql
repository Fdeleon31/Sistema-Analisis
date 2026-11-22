-- Ficha 13 · Universo combinado Extracto Bancario vs. Mayor de Bancos para conciliación 1 a 1.
SELECT
    'origen' AS _lado,
    archivo,
    banco,
    cuenta_bancaria,
    linea,
    CAST(NULL AS VARCHAR) AS asiento,
    CAST(NULL AS VARCHAR) AS cuenta,
    fecha,
    COALESCE(referencia, '') AS referencia,
    descripcion,
    CAST(monto AS DECIMAL(18, 2)) AS monto
FROM {extracto}
UNION ALL
SELECT
    'contraparte' AS _lado,
    'mayor' AS archivo,
    CAST(NULL AS VARCHAR) AS banco,
    CAST(NULL AS VARCHAR) AS cuenta_bancaria,
    CAST({linea} AS BIGINT) AS linea,
    CAST({asiento} AS VARCHAR) AS asiento,
    CAST({cuenta} AS VARCHAR) AS cuenta,
    CAST({fecha} AS DATE) AS fecha,
    '' AS referencia,
    CAST({descripcion} AS VARCHAR) AS descripcion,
    CAST({monto} AS DECIMAL(18, 2)) AS monto
FROM {mayor}
WHERE starts_with(CAST({cuenta} AS VARCHAR), $cuenta_banco)
  AND CAST({monto} AS DECIMAL(18, 2)) <> 0
ORDER BY fecha, ABS(monto) DESC
