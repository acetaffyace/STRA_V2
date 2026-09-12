param([ValidateSet('integration','agent-a','agent-b')][string]$Profile = 'agent-a',[switch]$ResetDatabase)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'stop_local.ps1') -Profile $Profile
$dir = Join-Path $PSScriptRoot "data\runtime\$Profile"
Remove-Item -LiteralPath (Join-Path $dir 'runtime.lock') -Force -ErrorAction SilentlyContinue
if ($ResetDatabase) {
  if ($Profile -eq 'integration') { throw 'Integration database reset requires an explicit reviewed operation and is disabled by default.' }
  $db = Join-Path $dir 'sentinext.db'
  if (Test-Path -LiteralPath $db) { Remove-Item -LiteralPath $db -Force }
}
Write-Host "Reset runtime artifacts for '$Profile'; database preserved unless -ResetDatabase was supplied."
