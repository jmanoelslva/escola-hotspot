@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Rode instalar.bat primeiro.
    pause
    exit /b 1
)
title Painel do Hotspot
".venv\Scripts\python.exe" -m app
pause
