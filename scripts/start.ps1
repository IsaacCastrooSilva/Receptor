param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path .venv\Scripts\python.exe)) {
    throw "Prepare o ambiente Python conforme README.md ou scripts\setup.ps1."
}
if (-not (Test-Path frontend\dist\index.html)) {
    throw "Compile a PWA primeiro: npm --prefix frontend run build"
}
Write-Host "Receptor: http://127.0.0.1:$Port (Ctrl+C para encerrar)"
& .\.venv\Scripts\python.exe -m uvicorn receptor.api:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
