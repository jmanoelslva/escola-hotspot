# Cria (ou remove, com -Remover) os atalhos "Painel do Hotspot" na Area de Trabalho
# e no Menu Iniciar de todos os usuarios. O atalho abre o painel numa janela
# propria do Edge (ou do Chrome), sem barra de endereco, como um programa.
# Usado pelo instalar.bat e pelo remover-inicio-automatico.bat.
param(
    [int]$Porta = 8080,
    [switch]$Remover,
    [string[]]$Pastas = @(
        [Environment]::GetFolderPath("CommonDesktopDirectory"),
        [Environment]::GetFolderPath("CommonPrograms")
    )
)

$ErrorActionPreference = "Stop"
$nome = "Painel do Hotspot"
$pastas = $Pastas
$atalhos = $pastas | ForEach-Object { Join-Path $_ "$nome.lnk" }
$atalhosUrl = $pastas | ForEach-Object { Join-Path $_ "$nome.url" }

foreach ($arquivo in $atalhos + $atalhosUrl) {
    if (Test-Path $arquivo) { Remove-Item $arquivo -Force }
}
if ($Remover) {
    Write-Host "Atalhos removidos."
    exit 0
}

$pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
$icone = Join-Path $pasta "static\icone.ico"
$endereco = "http://localhost:$Porta/"

$navegadores = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
)
$navegador = $navegadores | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if ($navegador) {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($arquivo in $atalhos) {
        $atalho = $shell.CreateShortcut($arquivo)
        $atalho.TargetPath = $navegador
        $atalho.Arguments = "--app=$endereco"
        $atalho.IconLocation = "$icone,0"
        $atalho.Description = "Administracao do Wi-Fi da escola"
        $atalho.WorkingDirectory = $pasta
        $atalho.Save()
    }
    Write-Host "Atalhos criados (abre em janela propria: $([IO.Path]::GetFileNameWithoutExtension($navegador)))."
} else {
    # Sem Edge nem Chrome: atalho de internet comum, abre no navegador padrao.
    foreach ($arquivo in $atalhosUrl) {
        Set-Content -Path $arquivo -Encoding ASCII -Value @(
            "[InternetShortcut]", "URL=$endereco", "IconFile=$icone", "IconIndex=0"
        )
    }
    Write-Host "Atalhos criados (abre no navegador padrao)."
}
