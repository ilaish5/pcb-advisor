@echo off
rem Start pcb-advisor and open it in the browser.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Run install.bat first. & exit /b 1)
.venv\Scripts\python pcb.py serve
