$ErrorActionPreference = "Continue"

$root = Split-Path -Parent $PSScriptRoot
$port = 8001
$python = Join-Path $root ".venv\Scripts\python.exe"
$dataDir = Join-Path $root "data"
$databasePath = Join-Path $dataDir "database\app.sqlite3"
$uploadDir = Join-Path $dataDir "uploads"
$exportDir = Join-Path $dataDir "exports"

function Write-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail = ""
    )

    $mark = if ($Passed) { "OK" } else { "FAIL" }
    $line = "[$mark] $Name"
    if ($Detail) {
        $line = "$line - $Detail"
    }
    Write-Host $line
}

Write-Host ""
Write-Host "Teacher Achievement System trial readiness check"
Write-Host "Project: $root"
Write-Host ""

$pythonExists = Test-Path $python
Write-Check "Virtual environment Python" $pythonExists $python

if ($pythonExists) {
    & $python -c "import fastapi, uvicorn, sqlalchemy, openpyxl" 2>$null
    Write-Check "Python dependencies" ($LASTEXITCODE -eq 0) "fastapi, uvicorn, sqlalchemy, openpyxl"

    & $python -c "from app.main import app; print(app.title)" 2>$null | Out-Null
    Write-Check "Application imports" ($LASTEXITCODE -eq 0) "app.main:app"
}

Write-Check "Data directory" (Test-Path $dataDir) $dataDir
Write-Check "Database file" (Test-Path $databasePath) $databasePath
Write-Check "Upload directory" (Test-Path $uploadDir) $uploadDir
Write-Check "Export directory" (Test-Path $exportDir) $exportDir

$connections = @(Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue)
$isListening = $connections.Count -gt 0
Write-Check "Port $port listening" $isListening "run .\run.ps1 if this is FAIL"

if ($isListening) {
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 5
        Write-Check "Local health endpoint" ($health.StatusCode -eq 200) "http://127.0.0.1:$port/health"
    }
    catch {
        Write-Check "Local health endpoint" $false $_.Exception.Message
    }
}

$lanIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -First 1 -ExpandProperty IPAddress

if ($lanIp) {
    Write-Check "LAN IP detected" $true "http://$lanIp`:$port"
}
else {
    Write-Check "LAN IP detected" $false "connect to the campus/LAN network first"
}

Write-Host ""
Write-Host "Trial URLs:"
Write-Host "  Local: http://127.0.0.1:$port"
if ($lanIp) {
    Write-Host "  LAN:   http://$lanIp`:$port"
}
Write-Host ""
Write-Host "If LAN access fails on other computers, check Windows Firewall and network isolation."
Write-Host ""
