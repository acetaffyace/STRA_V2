# Local Runtime Operations Runbook

Start the canonical product:

```powershell
.\run_local.ps1 -Profile integration
```

Start an isolated agent runtime:

```powershell
.\run_local.ps1 -Profile agent-a
```

Stop only the selected profile:

```powershell
.\stop_local.ps1 -Profile integration
```

Reset an agent runtime while preserving its database:

```powershell
.\reset_runtime.ps1 -Profile agent-a
```

The integration database is never removed by default. Logs and runtime metadata are kept under `data/runtime/<profile>`.
