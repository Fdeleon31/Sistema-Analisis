@echo off
REM Doble clic para abrir la aplicación nativa de escritorio (100 %% sin internet).
REM Usa "iniciar.bat web" si prefieres la interfaz local en navegador (Streamlit).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Preparando entorno por primera vez...
    py -m venv .venv || python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if /I "%~1"=="web" (
    ".venv\Scripts\python.exe" -m streamlit run app\inicio.py --server.address 127.0.0.1 --server.enableXsrfProtection true --server.enableCORS false --server.maxUploadSize 4096 --browser.gatherUsageStats false
    pause
    exit /b %ERRORLEVEL%
)
start "" ".venv\Scripts\pythonw.exe" app\escritorio.py || ".venv\Scripts\python.exe" app\escritorio.py
