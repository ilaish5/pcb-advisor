@echo off
rem One-step setup on Windows: private Python environment, dependencies, workspace. Run once, then use start.bat.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (echo Python 3.10 or newer is required: https://www.python.org/downloads/ & exit /b 1)
if not exist .venv %PY% -m venv .venv || exit /b 1
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r requirements.txt || exit /b 1
.venv\Scripts\python pcb.py init || exit /b 1
echo.
echo Done. Install and sign in to ONE AI engine (see docs\ENGINES.md), then run start.bat
