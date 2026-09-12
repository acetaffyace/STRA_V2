param(
  [ValidateSet('integration')]
  [string]$Profile = 'integration'
  ,
  [ValidateSet('legacy', 'v3', 'v3_1')]
  [string]$ClassifierVariant = 'v3_1'
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path $PSScriptRoot).Path
$python = Join-Path $root '.venv311\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Validated .venv311 was not found." }

$profiles = @{
  integration = @{ Frontend = 3000; Backend = 8000; Db = (Join-Path $root 'data\runtime\integration\sentinext.db') }
}
$cfg = $profiles[$Profile]
$backendPort = [int]$cfg.Backend
$frontendPort = [int]$cfg.Frontend
$backendPortText = $backendPort.ToString()
$frontendPortText = $frontendPort.ToString()
$runtimeDir = Join-Path $root "data\runtime\$Profile"
$logDir = Join-Path $root "logs\$Profile"
$lockPath = Join-Path $runtimeDir 'runtime.lock'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (Test-Path -LiteralPath $lockPath) {
  $old = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
  if ($old.backend_pid -and (Get-Process -Id ([int]$old.backend_pid) -ErrorAction SilentlyContinue)) {
    throw "Runtime profile '$Profile' is already running on PID $($old.backend_pid)."
  }
  Remove-Item -LiteralPath $lockPath -Force
}

foreach ($port in @($backendPort, $frontendPort)) {
  $occupied = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if ($occupied) { throw "Reserved port $port is already in use. Stop its owner before starting profile '$Profile'." }
}

$dbParent = Split-Path -Parent $cfg.Db
New-Item -ItemType Directory -Force -Path $dbParent | Out-Null
$env:SENTINEXT_RUNTIME_PROFILE = $Profile
$env:SENTINEXT_BACKEND_PORT = $backendPortText
$env:SENTINEXT_RUNTIME_STARTED_AT = [DateTime]::UtcNow.ToString('o')
$env:DATABASE_URL = "sqlite:///$($cfg.Db.Replace('\','/'))"
$env:SENTINEXT_LOG_FILE = Join-Path $logDir 'backend.log'
$env:NEXT_PUBLIC_API_BASE_URL = '/api'
$env:SENTINEXT_BACKEND_ORIGIN = "http://127.0.0.1:$backendPort"
$env:NEXT_PUBLIC_RUNTIME_PROFILE = $Profile
$env:SENTINEXT_CLASSIFIER_PROMPT_VARIANT = $ClassifierVariant
$env:SENTINEXT_REVIEW_PREPROCESS_MODE = 'active'
$env:SENTINEXT_DYNAMIC_BATCH_ENABLED = 'true'

$backend = Start-Process -FilePath $python -WorkingDirectory $root -ArgumentList @('-m','uvicorn','apps.api.main:app','--host','127.0.0.1','--port',$backendPortText) -PassThru -RedirectStandardOutput (Join-Path $logDir 'backend.stdout.log') -RedirectStandardError (Join-Path $logDir 'backend.stderr.log')
$healthUrl = "http://127.0.0.1:$backendPort/health"
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 500
  try { $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2; if ($health.status -eq 'ok') { $ready = $true; break } } catch { }
}
if (-not $ready) { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue; throw "Backend health check failed for profile '$Profile'." }
$info = Invoke-RestMethod -Uri "http://127.0.0.1:$backendPort/runtime-info" -TimeoutSec 5
if ($info.runtime_profile -ne $Profile -or $info.backend_port -ne $backendPort) { Stop-Process -Id $backend.Id -Force; throw 'Backend runtime handshake failed.' }

$nextLock = Join-Path $root 'apps\dashboard\.next\dev\lock'
if (Test-Path -LiteralPath $nextLock) {
  $lockAge = ((Get-Date) - (Get-Item -LiteralPath $nextLock).LastWriteTime).TotalSeconds
  if ($lockAge -gt 30) {
    Write-Host 'Removing stale Next development lock because the reserved frontend port is free.'
    Remove-Item -LiteralPath $nextLock -Force
  } else {
    Stop-Process -Id $backend.Id -Force
    throw 'A recent Next development lock exists; another frontend may still be starting.'
  }
}

$frontend = Start-Process -FilePath 'npm.cmd' -WorkingDirectory (Join-Path $root 'apps\dashboard') -ArgumentList @('run','dev','--','--webpack','--hostname','127.0.0.1','--port',$frontendPortText) -PassThru -RedirectStandardOutput (Join-Path $logDir 'frontend.stdout.log') -RedirectStandardError (Join-Path $logDir 'frontend.stderr.log')
$lock = [ordered]@{ profile=$Profile; classifier_variant=$ClassifierVariant; backend_pid=$backend.Id; frontend_pid=$frontend.Id; backend_port=$backendPort; frontend_port=$frontendPort; database=$cfg.Db; started_at=$env:SENTINEXT_RUNTIME_STARTED_AT; git_commit=(git rev-parse HEAD); git_branch=(git branch --show-current) }
$lock | ConvertTo-Json | Set-Content -LiteralPath $lockPath -Encoding UTF8
Write-Host "SentiNext Runtime"
Write-Host "Profile: $Profile"
Write-Host "Frontend: http://127.0.0.1:$frontendPort"
Write-Host "Backend:  http://127.0.0.1:$backendPort"
Write-Host "Database: $($cfg.Db)"
Write-Host "Classifier: $ClassifierVariant"
Write-Host "API:      unified-analysis-v1"
