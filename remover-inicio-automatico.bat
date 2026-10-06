@echo off
net session >nul 2>&1
if errorlevel 1 (
    echo Clique com o botao direito neste arquivo e escolha "Executar como administrador".
    pause
    exit /b 1
)
schtasks /end /tn "Painel do Hotspot" >nul 2>&1
schtasks /delete /tn "Painel do Hotspot" /f
netsh advfirewall firewall delete rule name="Painel do Hotspot"
echo Inicio automatico removido. Se o painel ainda estiver aberto, reinicie o computador.
pause
