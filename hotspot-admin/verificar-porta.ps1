# Usado pelo instalar.bat: encerra so o painel antigo desta pasta (python da .venv)
# e confere se a porta ficou livre. Nunca encerra outros programas: se a porta
# estiver em uso por outro (ex.: controladora UniFi, redirecionamento do Windows),
# mostra quem e e sai com erro, para trocar a PORTA no .env.
param([int]$Porta = 8080)

$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $pasta ".venv\Scripts\python.exe"

Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -ieq $python) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800

$ocupada = Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $ocupada) { exit 0 }

$processo = Get-Process -Id $ocupada.OwningProcess -ErrorAction SilentlyContinue
$nome = if ($processo) { $processo.ProcessName } else { "PID $($ocupada.OwningProcess)" }
$redirecionada = (netsh interface portproxy show all) -match "\s$Porta\s"
Write-Host ""
Write-Host "A porta $Porta ja esta em uso por outro programa ($nome)."
if ($redirecionada) {
    Write-Host "Ela e redirecionada pelo Windows (netsh portproxy), por exemplo para uma controladora UniFi ou um container."
}
Write-Host "Abra o arquivo .env desta pasta, troque a linha PORTA=$Porta por uma porta livre (ex.: PORTA=8090)"
Write-Host "e rode o instalar.bat de novo."
exit 1
