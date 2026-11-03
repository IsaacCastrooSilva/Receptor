param(
    [string]$Python = "python",
    [switch]$WithML
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path .venv\Scripts\python.exe)) {
    & $Python -c "import sys; assert (3, 11) <= sys.version_info[:2] < (3, 14), 'Use Python 3.11, 3.12 ou 3.13'"
    if ($LASTEXITCODE -ne 0) { throw "Instale Python 3.12 ou informe -Python com o caminho do executavel." }
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel criar .venv." }
}
& .\.venv\Scripts\python.exe -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel preparar pip." }
$package = if ($WithML) { ".[api,ml,dev]" } else { ".[api,dev]" }
& .\.venv\Scripts\python.exe -m pip install -e $package
if ($LASTEXITCODE -ne 0) { throw "Falha na instalacao das dependencias." }
& npm --prefix frontend ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar o frontend. Use Node.js >=22.12." }
& npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw "Falha na compilacao da PWA." }
Write-Host "Pronto. Execute scripts\start.ps1 e acesse http://127.0.0.1:8000"
