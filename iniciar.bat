@echo off
REM Cuadra: doble clic para abrir la interfaz en el navegador.
REM La primera vez crea el entorno e instala dependencias (tarda unos minutos).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Preparando Cuadra por primera vez...
    py -m venv .venv || python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
".venv\Scripts\python.exe" -m streamlit run app\inicio.py --browser.gatherUsageStats false
pause
