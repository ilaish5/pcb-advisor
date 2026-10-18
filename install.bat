@echo off
rem One-step setup on Windows: private Python environment, dependencies, workspace. Run once, then use start.bat.
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul || (echo Python 3.10 or newer is required: https://www.python.org/downloads/ & pause & exit /b 1)
if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe -m pip --version >nul 2>nul || rmdir /s /q .venv) else (if exist .venv rmdir /s /q .venv)
if not exist .venv\Scripts\python.exe (%PY% -m venv .venv || (echo Could not create .venv & pause & exit /b 1))
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r requirements.txt || (echo Installing requirements failed & pause & exit /b 1)
.venv\Scripts\python pcb.py init || (echo pcb.py init failed & pause & exit /b 1)
echo.
echo Done. Install and sign in to ONE AI engine (see docs\ENGINES.md), then run start.bat
pause
