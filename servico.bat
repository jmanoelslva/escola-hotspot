@echo off
rem Usado pela tarefa agendada (iniciar-com-windows.bat). Grava a saida em dados\painel.log.
cd /d "%~dp0"
if not exist "dados" mkdir "dados"
".venv\Scripts\python.exe" -m app >> "dados\painel.log" 2>&1
