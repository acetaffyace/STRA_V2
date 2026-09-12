# V1/P1 Offline Operations Runbook

## Start locally

Windows PowerShell:

```powershell
./run_backend_local.ps1
```

The script validates `.venv311` and required proxy dependencies before Uvicorn.

## Run an offline pilot

```powershell
$env:PYTHONPATH='.'
./.venv311/Scripts/python.exe tooling/offline_pilot/run_offline.py `
  --app-id 91001 `
  --reviews tooling/offline_pilot/live_service_competitive.jsonl `
  --database data/v1_pilot/offline_runs/live_service.db
```

The output is explicitly `codex_offline_fixture`. It creates no real provider
cost row and must not be used as model-quality or Gold evidence.

## Inspect a completed run

Use the existing run/result endpoints and Dashboard. The primary surface now
contains the five-question summary. Formal rates remain backend-provenance
observations; filtered values remain interactive samples.

## Recover an interrupted run

1. Restart the backend.
2. Startup recovery marks old queued/running general runs as failed with
   `interrupted by process restart`.
3. Use the normal rerun action; eligible cached labels are reused.
4. If a run is still active, use the existing cancel endpoint before rerun.

## Provider revalidation (future, deliberately not run here)

`EXTERNAL_PROVIDER_REVALIDATION` requires a rotated credential, one smoke
request, 5–10 classifications, a staged 50–100 review run, and verification of
retry/circuit/cost behavior. Do not run this as part of the offline release.

