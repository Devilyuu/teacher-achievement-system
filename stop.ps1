$ErrorActionPreference = "SilentlyContinue"

$connections = Get-NetTCPConnection -LocalPort 8000
if (-not $connections) {
    Write-Host "No service is listening on port 8000."
    exit 0
}

$processIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)

$uvicornProcesses = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*uvicorn app.main:app*" }

$processIds += @($uvicornProcesses | Select-Object -ExpandProperty ProcessId)

foreach ($processId in $processIds) {
    $processInfo = $uvicornProcesses | Where-Object { $_.ProcessId -eq $processId } | Select-Object -First 1
    if ($processInfo -and $processInfo.ParentProcessId) {
        $processIds += $processInfo.ParentProcessId
    }
}

$processIds = $processIds | Sort-Object -Unique -Descending
foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId
    if ($process) {
        Write-Host "Stopping process $processId on port 8000..."
        Stop-Process -Id $processId -Force
    }
}

Write-Host "Stopped."
