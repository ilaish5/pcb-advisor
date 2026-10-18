@echo off
rem Start pcb-advisor and open it in the browser.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run install.bat first. & pause & exit /b 1)
.venv\Scripts\python pcb.py serve || (echo The server stopped with an error. & pause & exit /b 1)
