$ErrorActionPreference = "SilentlyContinue"

$port = 8001
$connections = Get-NetTCPConnection -LocalPort $port
if (-not $connections) {
    Write-Host "No service is listening on port $port."
    exit 0
}

$processIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)

$uvicornProcesses = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*uvicorn app.main:app*" -and $_.CommandLine -like "*--port $port*" }

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
        Write-Host "Stopping process $processId on port $port..."
        Stop-Process -Id $processId -Force
    }
}

Write-Host "Stopped."
