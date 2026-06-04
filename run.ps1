$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$port = 8001
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Virtual environment not found."
    Write-Host "Run these commands first:"
    Write-Host "  python -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

try {
    & $python -c "import uvicorn, fastapi" | Out-Null
}
catch {
    Write-Host "Dependencies are not installed."
    Write-Host "Run this command first:"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

$lanIp = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host ""
Write-Host "Teacher Achievement System is starting..."
Write-Host "Local URL: http://127.0.0.1:$port"
if ($lanIp) {
    Write-Host "LAN URL:   http://$lanIp`:$port"
}
Write-Host "Press Ctrl+C to stop."
Write-Host ""

& $python -m uvicorn app.main:app --host 0.0.0.0 --port $port --reload
