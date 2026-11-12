# MCC Unlocker — lancement Windows depuis les sources.
# Ne flashe pas à ta place : SP Flash Tool et TWRP GUI restent manuels.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ([Environment]::OSVersion.Version.Major -lt 10) {
    Write-Error "Windows 10 ou supérieur est requis."
    exit 2
}

$pythonExe = $null
$pythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
    $pythonArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
} else {
    Write-Error "Python 3.11+ est introuvable."
    exit 2
}
& $pythonExe @pythonArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 3.11 ou supérieur est requis."
    exit 2
}

$venv = Join-Path $Root ".venv-win"
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Création de l'environnement Python local..." -ForegroundColor Cyan
    & $pythonExe @pythonArgs -m venv $venv
    & $venvPython -m pip install --upgrade pip
}
& $venvPython -c "import mcc_unlocker" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installation de l'interface..." -ForegroundColor Cyan
    & $venvPython -m pip install -e "$Root[gui]"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Installation impossible. Vérifie Python et la connexion."
        exit 2
    }
}

$adb = Get-Command adb -ErrorAction SilentlyContinue
if (-not $adb -and $env:LOCALAPPDATA) {
    $candidate = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    if (Test-Path $candidate) {
        $env:Path = (Split-Path $candidate) + ";" + $env:Path
        $adb = Get-Command adb -ErrorAction SilentlyContinue
    }
}
if (-not $adb) {
    Write-Host "ADB est introuvable. Installe Android platform-tools et ajoute-le au PATH." -ForegroundColor Yellow
    Write-Host "Sans ADB, TWRP ne peut pas être piloté."
    exit 2
}

Write-Host ""
Write-Host "Lancement de MCC Unlocker — déblocage guidé." -ForegroundColor Green
Write-Host "SP Flash Tool et les deux flashs TWRP GUI restent des actions manuelles."
Write-Host "Procédure non validée M0 : ne la présente pas comme un one-click."
Write-Host ""
& $venvPython -m mcc_unlocker ui
exit $LASTEXITCODE
