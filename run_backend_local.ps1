param([ValidateSet('integration')][string]$Profile = 'integration')

$ErrorActionPreference = "Stop"
Write-Host "run_backend_local.ps1 is now a compatibility wrapper. Starting isolated runtime '$Profile'."
& (Join-Path $PSScriptRoot 'run_local.ps1') -Profile $Profile
