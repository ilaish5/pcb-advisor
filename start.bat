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
rem 78: the port belongs to another program; the server already printed what to do. Stop here, never loop.
if %ERRORLEVEL% EQU 78 (pause & exit /b 78)
if %ERRORLEVEL% NEQ 0 (echo The server stopped with an error. Details are saved in the logs folder: %~dp0logs & echo Send the newest file in it, or use Settings - Save diagnostic report. & pause & exit /b 1)
