param([ValidateSet('integration')][string]$Profile = 'integration')
$ErrorActionPreference = 'Stop'
$lockPath = Join-Path $PSScriptRoot "data\runtime\$Profile\runtime.lock"
if (-not (Test-Path -LiteralPath $lockPath)) { Write-Host "Runtime profile '$Profile' is not running."; exit 0 }
$lock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
function Stop-Tree([int]$rootPid) {
  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $rootPid" -ErrorAction SilentlyContinue
  foreach ($child in $children) { Stop-Tree ([int]$child.ProcessId) }
  Stop-Process -Id $rootPid -Force -ErrorAction SilentlyContinue
}
foreach ($processId in @($lock.frontend_pid, $lock.backend_pid)) { if ($processId) { Stop-Tree ([int]$processId) } }
Remove-Item -LiteralPath $lockPath -Force
Write-Host "Stopped runtime profile '$Profile'. Logs and database were preserved."
