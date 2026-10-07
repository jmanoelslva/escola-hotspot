@echo off
setlocal
cd /d "%~dp0"
title Painel do Hotspot - instalacao

rem A tarefa agendada e o firewall precisam de administrador.
net session >nul 2>&1
if errorlevel 1 (
    echo Pedindo permissao de administrador...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ==== Painel do Hotspot - instalacao automatica ====
echo.

rem ---- 1. Python
set "PYEXE="
for /f "delims=" %%p in ('py -3 -c "import sys, venv; print(sys.executable)" 2^>nul') do set "PYEXE=%%p"
if defined PYEXE goto temPython
for /f "delims=" %%p in ('python -c "import sys, venv; print(sys.executable)" 2^>nul') do set "PYEXE=%%p"
if defined PYEXE goto temPython
if exist "%ProgramFiles%\Python313\python.exe" set "PYEXE=%ProgramFiles%\Python313\python.exe"
if defined PYEXE goto temPython

echo [1/6] Python nao encontrado. Instalando o Python 3.13 pelo winget...
where winget >nul 2>&1
if errorlevel 1 goto semWinget
winget install -e --id Python.Python.3.13 --scope machine --silent --accept-package-agreements --accept-source-agreements
if exist "%ProgramFiles%\Python313\python.exe" set "PYEXE=%ProgramFiles%\Python313\python.exe"
if not defined PYEXE goto semPython

:temPython
echo [1/6] Python: %PYEXE%

rem ---- 2. Ambiente e bibliotecas
echo [2/6] Instalando as bibliotecas...
if not exist ".venv\Scripts\python.exe" "%PYEXE%" -m venv .venv
if not exist ".venv\Scripts\python.exe" goto erro
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto erro

rem ---- 3. Configuracao (so na primeira vez; reinstalar mantem o .env)
if not exist ".env" copy ".env.example" ".env" >nul
set "PORTA=8080"
for /f "usebackq tokens=1,* delims==" %%a in (".env") do if /i "%%a"=="PORTA" set "PORTA=%%b"
echo [3/6] Configuracao em .env (porta %PORTA%)

rem ---- 4. Iniciar com o Windows e liberar no firewall
echo [4/6] Criando a tarefa "Painel do Hotspot" e liberando a porta %PORTA% no firewall...
schtasks /end /tn "Painel do Hotspot" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verificar-porta.ps1" -Porta %PORTA%
if errorlevel 1 goto portaOcupada
schtasks /create /tn "Painel do Hotspot" /tr "\"%~dp0servico.bat\"" /sc onstart /ru SYSTEM /rl HIGHEST /f >nul
if errorlevel 1 goto erro
netsh advfirewall firewall delete rule name="Painel do Hotspot" >nul 2>&1
netsh advfirewall firewall add rule name="Painel do Hotspot" dir=in action=allow protocol=TCP localport=%PORTA% remoteip=localsubnet >nul
if errorlevel 1 goto erro

rem ---- 5. Atalhos de app na Area de Trabalho e no Menu Iniciar
echo [5/6] Criando os atalhos "Painel do Hotspot"...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0criar-atalhos.ps1" -Porta %PORTA%

rem ---- 6. Iniciar agora
echo [6/6] Iniciando o painel...
schtasks /run /tn "Painel do Hotspot" >nul
set /a TENTATIVAS=0
:esperar
set /a TENTATIVAS+=1
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:%PORTA%/api/info | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto pronto
if %TENTATIVAS% geq 20 goto naoSubiu
timeout /t 1 /nobreak >nul
goto esperar

:pronto
set "IPPC="
rem IP da placa que tem gateway (ignora adaptadores virtuais como WSL e Hyper-V).
for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1).IPv4Address.IPAddress"') do set "IPPC=%%i"
echo.
echo ==== Pronto! ====
echo O painel ja esta rodando e vai iniciar sozinho sempre que o computador ligar.
echo Para abrir: atalho "Painel do Hotspot" na Area de Trabalho ou no Menu Iniciar.
echo   Neste computador:     http://localhost:%PORTA%
if defined IPPC echo   Em outro aparelho:    http://%IPPC%:%PORTA%
echo Entre com um usuario admin do MikroTik.
if exist "%PUBLIC%\Desktop\Painel do Hotspot.lnk" (start "" "%PUBLIC%\Desktop\Painel do Hotspot.lnk") else (start "" "http://localhost:%PORTA%")
echo.
pause
exit /b 0

:portaOcupada
echo.
pause
exit /b 1

:naoSubiu
echo.
echo O painel nao respondeu. Veja o arquivo dados\painel.log nesta pasta.
pause
exit /b 1

:semWinget
echo.
echo Este Windows nao tem o winget. Instale o Python 3 em https://www.python.org/downloads/
echo marcando "Add python.exe to PATH" e rode este instalador de novo.
pause
exit /b 1

:semPython
echo.
echo O Python nao foi instalado. Feche esta janela e rode o instalador de novo;
echo se continuar, instale pelo site https://www.python.org/downloads/
pause
exit /b 1

:erro
echo.
echo A instalacao falhou. Confira a mensagem acima e a conexao com a internet.
pause
exit /b 1
