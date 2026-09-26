$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"

Write-Host "Creating virtual environment..."

if (!(Test-Path $Python)) {
    py -3 -m venv $Venv
}

Write-Host "Installing dependencies..."

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "requirements.txt")

Write-Host "Building YADoubleStrumFix..."

& $Python -m PyInstaller `
    --clean `
    --noconfirm `
    (Join-Path $Root "YADoubleStrumFix.spec")

Write-Host ""
Write-Host "Build complete!"
Write-Host "Executable:"
Write-Host "  $Root\dist\YADoubleStrumFix\YADoubleStrumFix.exe"
Write-Host ""
