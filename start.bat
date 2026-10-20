@echo off
rem Start pcb-advisor and open it in the browser.
rem After an in-app Update the server exits with code 75 and this loop starts it again on the new code, in a fresh
rem process (no old Python still holding files), without opening a second browser tab: the open page reloads itself.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run install.bat first - it sets everything up. & pause & exit /b 1)
set PCB_ADVISOR_LAUNCHER=start.bat
set PCB_ARGS=
:run
.venv\Scripts\python pcb.py serve %PCB_ARGS%
if %ERRORLEVEL% EQU 75 (set PCB_ARGS=--no-browser & goto run)
if %ERRORLEVEL% NEQ 0 (echo The server stopped with an error. & pause & exit /b 1)
