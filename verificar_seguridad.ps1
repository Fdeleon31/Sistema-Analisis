$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "No se encontro el entorno virtual en $Python. Ejecuta iniciar.bat o crea .venv primero."
}

function Invoke-Paso {
    param(
        [Parameter(Mandatory = $true)][string]$Nombre,
        [Parameter(Mandatory = $true)][scriptblock]$Accion
    )
    Write-Host "==> $Nombre" -ForegroundColor Cyan
    & $Accion
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo el paso '$Nombre' con codigo de salida $LASTEXITCODE."
    }
}

Invoke-Paso "1. Escaneo estatico SAST, secretos, datos/clientes y hardening local" {
    & $Python herramientas\seguridad_build.py --escanear
}

if (-not $env:QT_QPA_PLATFORM) {
    $env:QT_QPA_PLATFORM = "offscreen"
}

Invoke-Paso "2. Suite de pruebas automatizadas de ciberseguridad (Oleadas 1-4)" {
    & $Python -m pytest `
        tests/test_seguridad_hardening.py `
        tests/test_seguridad_cripto_roles.py `
        tests/test_login_pantalla.py `
        tests/test_seguridad_privacidad.py `
        tests/test_seguridad_supply_chain.py `
        tests/test_seguridad_integracion_e2e.py `
        -v
}

Invoke-Paso "3. Generacion offline de SBOM CycloneDX 1.5 y requirements.lock" {
    & $Python herramientas\seguridad_build.py --sbom docs\seguridad\sbom.cdx.json --lockfile requirements.lock
}

Write-Host "==> 4. Verificacion opcional de bandit y pip-audit en .venv" -ForegroundColor Cyan

$TieneBandit = (Test-Path ".\.venv\Scripts\bandit.exe")
if (-not $TieneBandit) {
    & $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('bandit') else 1)"
    $TieneBandit = ($LASTEXITCODE -eq 0)
}
if ($TieneBandit) {
    Invoke-Paso "4a. Ejecutando bandit en codigo fuente" {
        & $Python -m bandit -r motor conectores ia app herramientas cuadra.py -q
    }
} else {
    Write-Host "  [OMITIDO] bandit no esta instalado en .venv (paso opcional)." -ForegroundColor Yellow
}

$TienePipAudit = (Test-Path ".\.venv\Scripts\pip-audit.exe")
if (-not $TienePipAudit) {
    & $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pip_audit') else 1)"
    $TienePipAudit = ($LASTEXITCODE -eq 0)
}
if ($TienePipAudit) {
    Write-Host "  Ejecutando pip-audit (requiere acceso o cache local de vulnerabilidades)..."
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $salidaAudit = & $Python -m pip_audit 2>&1 | Out-String
    $codigoAudit = $LASTEXITCODE
    $ErrorActionPreference = $prevPref
    if ($codigoAudit -eq 0) {
        Write-Host $salidaAudit
    } elseif ($salidaAudit -match "ConnectionError|HTTPSConnectionPool|NameResolutionError|Failed to establish|offline|NewConnectionError|SSLError") {
        Write-Host "  [AVISO] pip-audit omitido porque el entorno opera 100 % sin conexion a internet." -ForegroundColor Yellow
    } else {
        Write-Host $salidaAudit
        throw "pip-audit detecto incidencias (codigo $codigoAudit)."
    }
} else {
    Write-Host "  [OMITIDO] pip-audit no esta instalado en .venv (paso opcional)." -ForegroundColor Yellow
}

Write-Host "Verificacion de seguridad completada correctamente." -ForegroundColor Green
