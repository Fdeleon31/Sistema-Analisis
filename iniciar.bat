@echo off
REM Doble clic para abrir la aplicación nativa de escritorio (100 %% sin internet).
REM Usa "iniciar.bat web" si prefieres la interfaz local en navegador (Streamlit).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Preparando entorno por primera vez...
    py -m venv .venv || python -m venv .venv
    REM Versiones fijas y hashes SHA-256 verificados: pip rechaza cualquier paquete alterado.
    ".venv\Scripts\python.exe" -m pip install --require-hashes -r requirements.lock
    if errorlevel 1 (
        echo.
        echo No se pudo instalar con requirements.lock ^(versiones y hashes verificados^).
        echo Revisa tu version de Python ^(se probo con 3.12^) o regenera el lock con hashes:
        echo   python cuadra.py seguridad --lockfile requirements.lock --hashes-lockfile requirements.lock
        rmdir /s /q .venv
        pause
        exit /b 1
    )
)
if /I "%~1"=="web" (
    ".venv\Scripts\python.exe" -m streamlit run app\inicio.py --server.address 127.0.0.1 --server.enableXsrfProtection true --server.enableCORS false --server.maxUploadSize 4096 --browser.gatherUsageStats false
    pause
    exit /b %ERRORLEVEL%
)
start "" ".venv\Scripts\pythonw.exe" app\escritorio.py || ".venv\Scripts\python.exe" app\escritorio.py
