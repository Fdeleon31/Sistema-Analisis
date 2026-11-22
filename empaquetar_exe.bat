@echo off
REM Genera el ejecutable portátil para Windows en dist\LibroAuditoria\LibroAuditoria.exe
REM No requiere Python instalado en el equipo destino; funciona 100 %% sin internet.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta iniciar.bat o crea el entorno .venv.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import importlib.metadata, sys; sys.exit(0 if importlib.metadata.version('pyinstaller') == '6.22.3' else 1)" >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller exacto ^(pyinstaller==6.22.3^) en .venv...
    ".venv\Scripts\python.exe" -m pip install pyinstaller==6.22.3
    if errorlevel 1 (
        echo Error al instalar pyinstaller==6.22.3.
        pause
        exit /b 1
    )
)

echo Empaquetando LibroAuditoria.exe...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean cuadra.spec
if errorlevel 1 (
    echo Error al empaquetar.
    pause
    exit /b 1
)

if not exist "dist\LibroAuditoria\encargos" mkdir "dist\LibroAuditoria\encargos"
copy /Y "encargos\*.yaml" "dist\LibroAuditoria\encargos\" >nul
if not exist "dist\LibroAuditoria\salidas" mkdir "dist\LibroAuditoria\salidas"
if not exist "dist\LibroAuditoria\datos\ejemplo" mkdir "dist\LibroAuditoria\datos\ejemplo"

echo Generando SBOM CycloneDX 1.5 y manifiesto SHA256SUMS.txt...
".venv\Scripts\python.exe" herramientas\seguridad_build.py --sbom "dist\LibroAuditoria\sbom.cdx.json" --sha256sums "dist\LibroAuditoria"
if errorlevel 1 (
    echo Error al generar SBOM o manifiesto SHA256SUMS.txt.
    pause
    exit /b 1
)

if defined FOLIO_CERT_PFX goto :intentar_firma
if defined FOLIO_CERT_THUMBPRINT goto :intentar_firma
echo [AVISO] Firma digital Authenticode omitida: no esta definida FOLIO_CERT_PFX ni FOLIO_CERT_THUMBPRINT.
goto :fin_firma

:intentar_firma
where signtool >nul 2>&1
if errorlevel 1 (
    echo [AVISO] signtool.exe no esta disponible en PATH. Instala Windows SDK para firmar LibroAuditoria.exe.
    goto :fin_firma
)

echo Firmando LibroAuditoria.exe con Authenticode SHA-256 ^(RFC 3161^)...
if defined FOLIO_CERT_PFX goto :firmar_pfx
signtool sign /fd SHA256 /sha1 "%FOLIO_CERT_THUMBPRINT%" /tr http://timestamp.digicert.com /td SHA256 "dist\LibroAuditoria\LibroAuditoria.exe"
if errorlevel 1 goto :error_firma
goto :post_firma

:firmar_pfx
if not defined FOLIO_CERT_PASS goto :firmar_pfx_sin_pass
signtool sign /fd SHA256 /f "%FOLIO_CERT_PFX%" /p "%FOLIO_CERT_PASS%" /tr http://timestamp.digicert.com /td SHA256 "dist\LibroAuditoria\LibroAuditoria.exe"
if errorlevel 1 goto :error_firma
goto :post_firma

:firmar_pfx_sin_pass
signtool sign /fd SHA256 /f "%FOLIO_CERT_PFX%" /tr http://timestamp.digicert.com /td SHA256 "dist\LibroAuditoria\LibroAuditoria.exe"
if errorlevel 1 goto :error_firma

:post_firma
echo Regenerando SHA256SUMS.txt tras firma digital...
".venv\Scripts\python.exe" herramientas\seguridad_build.py --sha256sums "dist\LibroAuditoria"
if errorlevel 1 (
    echo Error al regenerar SHA256SUMS.txt.
    pause
    exit /b 1
)
goto :fin_firma

:error_firma
echo Error al firmar digitalmente LibroAuditoria.exe con signtool.
pause
exit /b 1

:fin_firma

echo.
echo Listo. Ejecutable generado en:
echo   dist\LibroAuditoria\LibroAuditoria.exe
echo Puedes copiar la carpeta dist\LibroAuditoria completa a cualquier PC Windows.
pause
